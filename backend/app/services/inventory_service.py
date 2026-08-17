"""
InventoryService — stock-in, stock-out (FIFO), adjustment, batch and
transaction history.

Concurrency strategy
--------------------
All stock mutations use PostgreSQL row-level locking (SELECT ... FOR UPDATE).

Locking order (consistent across all operations to prevent deadlocks):
  1. products row (always first)
  2. inventory_batches rows (always second, for stock-out)

Why pessimistic locking instead of optimistic:
  Optimistic locking with version columns would require the caller to retry
  the entire operation on conflict. For stock operations, a retry would
  deplete stock twice. Pessimistic locking serializes concurrent mutations
  per product without the retry complexity.

NOTE: SELECT ... FOR UPDATE is a PostgreSQL production feature.
  SQLite (used in unit tests) does not implement FOR UPDATE — it ignores
  the hint silently. The unit tests therefore validate business logic and
  atomicity via service-level checks, NOT PostgreSQL lock behaviour.
  Concurrency correctness in production relies on FOR UPDATE at the DB level.

Source of truth
---------------
products.current_stock  — fast operational read
stock_transactions      — immutable audit ledger

Both are updated atomically within the same database transaction.
Reconciliation: SUM(stock_transactions.quantity) WHERE product_id = X
should always equal products.current_stock.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import asc, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inventory import InventoryBatch, StockTransaction
from app.models.product import Product
from app.schemas.common import PaginatedResponse
from app.schemas.inventory import (
    AdjustmentRequest,
    AdjustmentResponse,
    BatchAllocation,
    InventoryBatchPatchRequest,
    InventoryBatchResponse,
    StockInRequest,
    StockInResponse,
    StockOutRequest,
    StockOutResponse,
    StockTransactionResponse,
    TransactionSortField,
    TransactionSortOrder,
)

logger = logging.getLogger("stocksense.inventory")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InventoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # STOCK-IN
    # =========================================================================

    async def stock_in(
        self,
        data: StockInRequest,
        *,
        current_user_id: uuid.UUID,
        request: object,
    ) -> StockInResponse:
        """
        Receive new stock for a product.

        Creates an InventoryBatch, a STOCK_IN transaction, and increments
        product.current_stock — all within a single DB transaction.
        """
        # 1. Lock and validate product
        product = await self._lock_product_or_404(data.product_id)
        if not product.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot stock-in for an inactive product.",
            )

        # 2. Create the inventory batch
        batch = InventoryBatch(
            product_id=product.id,
            batch_number=data.batch_number,
            quantity=data.quantity,
            remaining_qty=data.quantity,  # fully available on receipt
            cost_per_unit=data.cost_per_unit,
            expiry_date=data.expiry_date,
            manufacture_date=data.manufacture_date,
            notes=data.notes,
        )
        self.db.add(batch)
        await self.db.flush()  # get batch.id before creating transaction

        # 3. Create STOCK_IN transaction (positive quantity)
        txn = StockTransaction(
            product_id=product.id,
            batch_id=batch.id,
            transaction_type="STOCK_IN",
            quantity=data.quantity,            # positive
            unit_cost=data.cost_per_unit,
            reference_type=data.reference_type,
            reference_id=data.reference_id,
            notes=data.notes,
            performed_by=current_user_id,
        )
        self.db.add(txn)

        # 4. Increment product.current_stock
        product.current_stock += data.quantity

        await self.db.flush()

        # 5. Audit
        from app.services.audit_service import AuditService, get_client_ip, get_user_agent
        await AuditService(self.db).log(
            user_id=current_user_id,
            action="STOCK_IN",
            resource_type="PRODUCT",
            resource_id=product.id,
            new_value={
                "batch_id": str(batch.id),
                "quantity": data.quantity,
                "cost_per_unit": float(data.cost_per_unit),
                "new_stock": product.current_stock,
            },
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        await self.db.commit()
        # Refresh to get server-set timestamps
        await self.db.refresh(batch)
        await self.db.refresh(txn)
        await self.db.refresh(product)

        logger.info(
            f"STOCK_IN product={product.id} qty={data.quantity} "
            f"batch={batch.id} new_stock={product.current_stock}"
        )

        return StockInResponse(
            transaction=_txn_to_response(txn),
            batch=_batch_to_response(batch),
            updated_stock=product.current_stock,
        )

    # =========================================================================
    # STOCK-OUT (FIFO)
    # =========================================================================

    async def stock_out(
        self,
        data: StockOutRequest,
        *,
        current_user_id: uuid.UUID,
        request: object,
    ) -> StockOutResponse:
        """
        Consume stock using FIFO depletion.

        Locking order:
          1. Lock product row (FOR UPDATE)
          2. Lock batch rows (FOR UPDATE) in received_at ASC order

        A single stock-out may produce multiple StockTransaction records
        (one per batch depleted) and multiple BatchAllocation entries.

        If insufficient stock exists, no modifications are made.
        """
        # 1. Lock and validate product
        product = await self._lock_product_or_404(data.product_id)
        if not product.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot stock-out for an inactive product.",
            )

        # 2. Validate sufficient stock BEFORE touching any batches
        if product.current_stock < data.quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Insufficient stock. Requested: {data.quantity}, "
                    f"available: {product.current_stock}."
                ),
            )

        # 3. Fetch and lock FIFO batches
        # Order: received_at ASC (oldest first), then batch.id for determinism.
        # FOR UPDATE locks selected rows so no concurrent operation can
        # deplete the same batch simultaneously.
        batch_result = await self.db.execute(
            select(InventoryBatch)
            .where(
                InventoryBatch.product_id == data.product_id,
                InventoryBatch.remaining_qty > 0,
                InventoryBatch.is_active.is_(True),
            )
            .order_by(
                asc(InventoryBatch.received_at),
                asc(InventoryBatch.id),  # deterministic secondary sort
            )
            .with_for_update()
        )
        batches = list(batch_result.scalars().all())

        # 4. FIFO allocation
        allocations: list[tuple[InventoryBatch, int]] = []
        remaining_to_allocate = data.quantity

        for batch in batches:
            if remaining_to_allocate == 0:
                break
            take = min(batch.remaining_qty, remaining_to_allocate)
            allocations.append((batch, take))
            remaining_to_allocate -= take

        # 5. Data-consistency guard (should never fire if current_stock is correct)
        if remaining_to_allocate > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Stock inconsistency detected: current_stock says "
                    f"{data.quantity} units are available but batches only "
                    f"cover {data.quantity - remaining_to_allocate}. "
                    "Contact an administrator."
                ),
            )

        # 6. Apply allocations atomically
        created_transactions: list[StockTransaction] = []
        batch_allocation_responses: list[BatchAllocation] = []

        for batch, take in allocations:
            batch.remaining_qty -= take

            txn = StockTransaction(
                product_id=data.product_id,
                batch_id=batch.id,
                transaction_type="STOCK_OUT",
                quantity=-take,  # negative — stock decreases
                unit_cost=batch.cost_per_unit,
                reference_type=data.reference_type,
                reference_id=data.reference_id,
                notes=data.notes,
                performed_by=current_user_id,
            )
            self.db.add(txn)
            created_transactions.append(txn)

            batch_allocation_responses.append(
                BatchAllocation(
                    batch_id=batch.id,
                    batch_number=batch.batch_number,
                    quantity_taken=take,
                    cost_per_unit=float(batch.cost_per_unit),
                    expiry_date=batch.expiry_date,
                )
            )

        # 7. Decrement product stock once by total requested
        product.current_stock -= data.quantity

        await self.db.flush()

        # 8. Audit
        from app.services.audit_service import AuditService, get_client_ip, get_user_agent
        await AuditService(self.db).log(
            user_id=current_user_id,
            action="STOCK_OUT",
            resource_type="PRODUCT",
            resource_id=product.id,
            new_value={
                "quantity": data.quantity,
                "new_stock": product.current_stock,
                "batches_depleted": len(allocations),
            },
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        await self.db.commit()

        for txn in created_transactions:
            await self.db.refresh(txn)
        await self.db.refresh(product)

        logger.info(
            f"STOCK_OUT product={data.product_id} qty={data.quantity} "
            f"batches_used={len(allocations)} new_stock={product.current_stock}"
        )

        return StockOutResponse(
            transactions=[_txn_to_response(t) for t in created_transactions],
            allocations=batch_allocation_responses,
            updated_stock=product.current_stock,
            total_quantity=data.quantity,
        )

    # =========================================================================
    # ADJUSTMENT
    # =========================================================================

    async def adjustment(
        self,
        data: AdjustmentRequest,
        *,
        current_user_id: uuid.UUID,
        request: object,
    ) -> AdjustmentResponse:
        """
        Manual stock correction.

        reason is mandatory and stored on the transaction and audit log.
        If batch_id is provided, the batch's remaining_qty is also adjusted
        and validated to stay within [0, batch.quantity].
        """
        # 1. Lock and validate product
        product = await self._lock_product_or_404(data.product_id)

        old_stock = product.current_stock
        new_stock = old_stock + data.quantity_delta

        # 2. Prevent negative current_stock
        if new_stock < 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Adjustment would result in negative stock "
                    f"({old_stock} + {data.quantity_delta} = {new_stock})."
                ),
            )

        # 3. Optional batch adjustment
        batch_updated = False
        batch_id_for_txn: uuid.UUID | None = None

        if data.batch_id is not None:
            # Load and lock the batch
            batch_result = await self.db.execute(
                select(InventoryBatch)
                .where(InventoryBatch.id == data.batch_id)
                .with_for_update()
            )
            batch = batch_result.scalar_one_or_none()

            if batch is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Batch {data.batch_id} not found.",
                )

            # Verify batch belongs to this product
            if batch.product_id != data.product_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Batch {data.batch_id} does not belong to "
                        f"product {data.product_id}."
                    ),
                )

            new_remaining = batch.remaining_qty + data.quantity_delta

            # Enforce batch bounds: 0 <= new_remaining <= batch.quantity
            if new_remaining < 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Adjustment would make batch remaining_qty negative "
                        f"({batch.remaining_qty} + {data.quantity_delta} = {new_remaining})."
                    ),
                )
            if new_remaining > batch.quantity:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Adjustment would make batch remaining_qty ({new_remaining}) "
                        f"exceed original batch quantity ({batch.quantity})."
                    ),
                )

            batch.remaining_qty = new_remaining
            batch_updated = True
            batch_id_for_txn = batch.id

        # 4. Create ADJUSTMENT transaction
        # Store reason in notes — that's the designated free-text field
        txn = StockTransaction(
            product_id=data.product_id,
            batch_id=batch_id_for_txn,
            transaction_type="ADJUSTMENT",
            quantity=data.quantity_delta,  # signed
            unit_cost=None,
            reference_type=None,
            reference_id=None,
            notes=data.reason,  # reason stored as notes
            performed_by=current_user_id,
        )
        self.db.add(txn)

        # 5. Update product stock
        product.current_stock = new_stock

        await self.db.flush()

        # 6. Audit with before/after values and reason
        from app.services.audit_service import AuditService, get_client_ip, get_user_agent
        await AuditService(self.db).log(
            user_id=current_user_id,
            action="ADJUSTMENT",
            resource_type="PRODUCT",
            resource_id=product.id,
            old_value={"current_stock": old_stock},
            new_value={
                "current_stock": new_stock,
                "delta": data.quantity_delta,
                "reason": data.reason,
                "batch_id": str(data.batch_id) if data.batch_id else None,
            },
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        await self.db.commit()
        await self.db.refresh(txn)
        await self.db.refresh(product)

        logger.info(
            f"ADJUSTMENT product={data.product_id} delta={data.quantity_delta} "
            f"new_stock={product.current_stock} reason='{data.reason}'"
        )

        return AdjustmentResponse(
            transaction=_txn_to_response(txn),
            updated_stock=product.current_stock,
            batch_updated=batch_updated,
        )

    # =========================================================================
    # BATCH ENDPOINTS
    # =========================================================================

    async def list_batches(
        self,
        *,
        product_id: uuid.UUID | None = None,
        include_depleted: bool = False,
        expiring_within_days: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[InventoryBatchResponse]:
        """List inventory batches with optional filters."""
        from datetime import date, timedelta

        base_q = select(InventoryBatch)

        if product_id:
            base_q = base_q.where(InventoryBatch.product_id == product_id)
        if not include_depleted:
            base_q = base_q.where(InventoryBatch.remaining_qty > 0)
        if expiring_within_days is not None:
            cutoff = date.today() + timedelta(days=expiring_within_days)
            base_q = base_q.where(
                InventoryBatch.expiry_date.is_not(None),
                InventoryBatch.expiry_date <= cutoff,
            )

        total: int = await self.db.scalar(
            select(func.count()).select_from(base_q.subquery())
        ) or 0

        offset = (page - 1) * page_size
        result = await self.db.execute(
            base_q.order_by(
                asc(InventoryBatch.received_at),
                asc(InventoryBatch.id),
            )
            .offset(offset)
            .limit(page_size)
        )
        batches = result.scalars().all()

        return PaginatedResponse(
            items=[_batch_to_response(b) for b in batches],
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, -(-total // page_size)),
        )

    async def get_batch(self, batch_id: uuid.UUID) -> InventoryBatchResponse:
        batch = await self._get_batch_or_404(batch_id)
        return _batch_to_response(batch)

    async def get_product_batches(
        self,
        product_id: uuid.UUID,
        *,
        include_depleted: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[InventoryBatchResponse]:
        """List all batches for a specific product."""
        # Verify product exists
        product = await self.db.scalar(
            select(Product).where(Product.id == product_id)
        )
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found.",
            )

        return await self.list_batches(
            product_id=product_id,
            include_depleted=include_depleted,
            page=page,
            page_size=page_size,
        )

    async def patch_batch(
        self,
        batch_id: uuid.UUID,
        data: InventoryBatchPatchRequest,
        *,
        current_user_id: uuid.UUID,
        request: object,
    ) -> InventoryBatchResponse:
        """
        Update safe metadata on a batch.
        remaining_qty and quantity are NOT patchable — they change only
        through stock transactions.
        """
        batch = await self._get_batch_or_404(batch_id)
        old_snapshot = {
            "batch_number": batch.batch_number,
            "notes": batch.notes,
            "expiry_date": batch.expiry_date.isoformat() if batch.expiry_date else None,
            "manufacture_date": batch.manufacture_date.isoformat() if batch.manufacture_date else None,
            "is_active": batch.is_active,
        }

        if data.batch_number is not None:
            batch.batch_number = data.batch_number
        if data.notes is not None:
            batch.notes = data.notes
        if data.expiry_date is not None:
            batch.expiry_date = data.expiry_date
        if data.manufacture_date is not None:
            batch.manufacture_date = data.manufacture_date
        if data.is_active is not None:
            batch.is_active = data.is_active

        await self.db.flush()

        from app.services.audit_service import AuditService, get_client_ip, get_user_agent
        await AuditService(self.db).log(
            user_id=current_user_id,
            action="UPDATE_BATCH",
            resource_type="INVENTORY_BATCH",
            resource_id=batch_id,
            old_value=old_snapshot,
            new_value={
                "batch_number": batch.batch_number,
                "notes": batch.notes,
                "expiry_date": batch.expiry_date.isoformat() if batch.expiry_date else None,
                "is_active": batch.is_active,
            },
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        await self.db.commit()
        await self.db.refresh(batch)
        return _batch_to_response(batch)

    # =========================================================================
    # TRANSACTION HISTORY
    # =========================================================================

    async def list_transactions(
        self,
        *,
        product_id: uuid.UUID | None = None,
        transaction_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        sort_by: TransactionSortField = "transaction_at",
        sort_order: TransactionSortOrder = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[StockTransactionResponse]:
        base_q = select(StockTransaction)

        if product_id:
            base_q = base_q.where(StockTransaction.product_id == product_id)
        if transaction_type:
            base_q = base_q.where(
                StockTransaction.transaction_type == transaction_type.upper()
            )
        if date_from:
            base_q = base_q.where(StockTransaction.transaction_at >= date_from)
        if date_to:
            base_q = base_q.where(StockTransaction.transaction_at <= date_to)

        total: int = await self.db.scalar(
            select(func.count()).select_from(base_q.subquery())
        ) or 0

        col = (
            StockTransaction.transaction_at
            if sort_by == "transaction_at"
            else StockTransaction.created_at
        )
        order_fn = asc if sort_order == "asc" else desc
        offset = (page - 1) * page_size

        result = await self.db.execute(
            base_q.order_by(order_fn(col))
            .offset(offset)
            .limit(page_size)
        )
        transactions = result.scalars().all()

        return PaginatedResponse(
            items=[_txn_to_response(t) for t in transactions],
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, -(-total // page_size)),
        )

    async def get_transaction(
        self, transaction_id: uuid.UUID
    ) -> StockTransactionResponse:
        txn = await self.db.scalar(
            select(StockTransaction).where(StockTransaction.id == transaction_id)
        )
        if not txn:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transaction {transaction_id} not found.",
            )
        return _txn_to_response(txn)

    # =========================================================================
    # Reconciliation utility
    # =========================================================================

    async def reconcile_stock(self, product_id: uuid.UUID) -> dict:
        """
        Compare products.current_stock against the sum of all transaction quantities.

        This is a diagnostic utility. If the values differ, it indicates
        a data inconsistency (e.g. a bug that updated one without the other).

        Not exposed as a major UI feature — useful for admin debugging.
        """
        product = await self.db.scalar(
            select(Product).where(Product.id == product_id)
        )
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found.",
            )

        ledger_sum: int = await self.db.scalar(
            select(func.coalesce(func.sum(StockTransaction.quantity), 0))
            .where(StockTransaction.product_id == product_id)
        ) or 0

        return {
            "product_id": str(product_id),
            "current_stock": product.current_stock,
            "ledger_sum": ledger_sum,
            "consistent": product.current_stock == ledger_sum,
        }

    # =========================================================================
    # Private helpers
    # =========================================================================

    async def _lock_product_or_404(self, product_id: uuid.UUID) -> Product:
        """
        Load and lock the product row using SELECT ... FOR UPDATE.

        FOR UPDATE acquires a row-level lock in PostgreSQL. Any concurrent
        transaction attempting to lock the same product row will wait until
        this transaction commits or rolls back. This serializes concurrent
        stock mutations per product.

        Note: SQLite (used in unit tests) silently ignores FOR UPDATE.
        """
        result = await self.db.execute(
            select(Product)
            .where(Product.id == product_id)
            .with_for_update()
        )
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found.",
            )
        return product

    async def _get_batch_or_404(self, batch_id: uuid.UUID) -> InventoryBatch:
        batch = await self.db.scalar(
            select(InventoryBatch).where(InventoryBatch.id == batch_id)
        )
        if not batch:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Batch {batch_id} not found.",
            )
        return batch


# ---------------------------------------------------------------------------
# Response helpers — convert ORM objects to Pydantic models
# ---------------------------------------------------------------------------

def _batch_to_response(b: InventoryBatch) -> InventoryBatchResponse:
    return InventoryBatchResponse(
        id=b.id,
        product_id=b.product_id,
        batch_number=b.batch_number,
        quantity=b.quantity,
        remaining_qty=b.remaining_qty,
        cost_per_unit=float(b.cost_per_unit),
        expiry_date=b.expiry_date,
        manufacture_date=b.manufacture_date,
        received_at=b.received_at,
        notes=b.notes,
        is_active=b.is_active,
        created_at=b.created_at,
        updated_at=b.updated_at,
    )


def _txn_to_response(t: StockTransaction) -> StockTransactionResponse:
    return StockTransactionResponse(
        id=t.id,
        product_id=t.product_id,
        batch_id=t.batch_id,
        transaction_type=t.transaction_type,
        quantity=t.quantity,
        unit_cost=float(t.unit_cost) if t.unit_cost is not None else None,
        reference_type=t.reference_type,
        reference_id=t.reference_id,
        notes=t.notes,
        performed_by=t.performed_by,
        transaction_at=t.transaction_at,
        created_at=t.created_at,
    )
