"""
Comprehensive Block 3 tests for inventory operations.

Testing strategy
----------------
All tests use SQLite in-memory (via conftest.py fixtures).

SQLite limitations acknowledged:
  - SELECT ... FOR UPDATE is silently ignored by SQLite.
  - These tests therefore validate business logic, FIFO ordering,
    data consistency, and constraint enforcement — NOT PostgreSQL
    row-level locking behaviour.

PostgreSQL concurrency (FOR UPDATE) is tested in production via
manual load testing or a separate integration test suite that requires
a real Postgres instance. See concurrency_design note at end of file.

Test categories:
  - STOCK_IN
  - STOCK_OUT (FIFO)
  - ADJUSTMENT
  - RBAC
  - TRANSACTION HISTORY
  - BATCH ENDPOINTS
  - DATA CONSISTENCY
"""
import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.inventory import InventoryBatch, StockTransaction
from app.models.product import Category, Product
from app.services.inventory_service import InventoryService
from app.schemas.inventory import (
    StockInRequest,
    StockOutRequest,
    AdjustmentRequest,
)
from tests.conftest import auth_headers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_product(db: AsyncSession) -> tuple[Category, Product]:
    cat = Category(id=uuid.uuid4(), name=f"Cat-{uuid.uuid4().hex[:6]}")
    db.add(cat)
    await db.flush()

    product = Product(
        id=uuid.uuid4(),
        sku=f"SKU-{uuid.uuid4().hex[:8].upper()}",
        name="Test Product",
        category_id=cat.id,
        unit="units",
        reorder_point=10,
        reorder_quantity=50,
        current_stock=0,
    )
    db.add(product)
    await db.commit()
    return cat, product


async def _stock_in_direct(
    db: AsyncSession, product: Product, user, *, qty: int = 100, cost: float = 5.0,
    expiry: date | None = None, batch_number: str | None = None,
) -> tuple[InventoryBatch, StockTransaction]:
    """Convenience: stock-in via service, return (batch, transaction)."""
    svc = InventoryService(db)
    resp = await svc.stock_in(
        StockInRequest(
            product_id=product.id,
            quantity=qty,
            cost_per_unit=cost,
            expiry_date=expiry,
            batch_number=batch_number,
        ),
        current_user_id=user.id,
        request=None,
    )
    # Reload ORM objects
    batch = await db.scalar(select(InventoryBatch).where(InventoryBatch.id == resp.batch.id))
    txn = await db.scalar(select(StockTransaction).where(StockTransaction.id == resp.transaction.id))
    await db.refresh(product)
    return batch, txn


# ===========================================================================
# STOCK-IN tests
# ===========================================================================

class TestStockIn:
    @pytest.mark.asyncio
    async def test_stock_in_creates_batch(self, db_session: AsyncSession, admin_user):
        _, product = await _make_product(db_session)
        batch, _ = await _stock_in_direct(db_session, product, admin_user, qty=50, cost=2.5)

        assert batch is not None
        assert batch.quantity == 50
        assert batch.remaining_qty == 50
        assert float(batch.cost_per_unit) == 2.5

    @pytest.mark.asyncio
    async def test_stock_in_creates_stock_in_transaction(
        self, db_session: AsyncSession, admin_user
    ):
        _, product = await _make_product(db_session)
        batch, txn = await _stock_in_direct(db_session, product, admin_user, qty=30)

        assert txn.transaction_type == "STOCK_IN"
        assert txn.quantity == 30          # positive
        assert txn.batch_id == batch.id
        assert txn.performed_by == admin_user.id

    @pytest.mark.asyncio
    async def test_stock_in_increments_current_stock(
        self, db_session: AsyncSession, admin_user
    ):
        _, product = await _make_product(db_session)
        assert product.current_stock == 0

        await _stock_in_direct(db_session, product, admin_user, qty=60)
        await db_session.refresh(product)
        assert product.current_stock == 60

        await _stock_in_direct(db_session, product, admin_user, qty=40)
        await db_session.refresh(product)
        assert product.current_stock == 100

    @pytest.mark.asyncio
    async def test_stock_in_stores_expiry_date(self, db_session: AsyncSession, admin_user):
        _, product = await _make_product(db_session)
        expiry = date.today() + timedelta(days=90)
        batch, _ = await _stock_in_direct(
            db_session, product, admin_user, qty=10, expiry=expiry
        )
        assert batch.expiry_date == expiry

    @pytest.mark.asyncio
    async def test_stock_in_stores_batch_number(self, db_session: AsyncSession, admin_user):
        _, product = await _make_product(db_session)
        batch, _ = await _stock_in_direct(
            db_session, product, admin_user, qty=10, batch_number="LOT-2025-001"
        )
        assert batch.batch_number == "LOT-2025-001"

    @pytest.mark.asyncio
    async def test_stock_in_zero_quantity_rejected(
        self, db_session: AsyncSession, admin_user
    ):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            StockInRequest(product_id=uuid.uuid4(), quantity=0, cost_per_unit=1.0)

    @pytest.mark.asyncio
    async def test_stock_in_negative_quantity_rejected(
        self, db_session: AsyncSession, admin_user
    ):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            StockInRequest(product_id=uuid.uuid4(), quantity=-5, cost_per_unit=1.0)

    @pytest.mark.asyncio
    async def test_stock_in_negative_cost_rejected(self, db_session: AsyncSession):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            StockInRequest(product_id=uuid.uuid4(), quantity=10, cost_per_unit=-1.0)

    @pytest.mark.asyncio
    async def test_stock_in_zero_cost_allowed(self, db_session: AsyncSession, admin_user):
        """Zero cost is valid (e.g. samples / donations)."""
        _, product = await _make_product(db_session)
        batch, _ = await _stock_in_direct(db_session, product, admin_user, qty=10, cost=0.0)
        assert float(batch.cost_per_unit) == 0.0

    @pytest.mark.asyncio
    async def test_stock_in_nonexistent_product_raises_404(
        self, db_session: AsyncSession, admin_user
    ):
        from fastapi import HTTPException
        svc = InventoryService(db_session)
        with pytest.raises(HTTPException) as exc:
            await svc.stock_in(
                StockInRequest(
                    product_id=uuid.uuid4(), quantity=10, cost_per_unit=1.0
                ),
                current_user_id=admin_user.id, request=None,
            )
        assert exc.value.status_code == 404


# ===========================================================================
# STOCK-OUT (FIFO) tests
# ===========================================================================

class TestStockOut:
    @pytest.mark.asyncio
    async def test_stock_out_single_batch_fifo(
        self, db_session: AsyncSession, admin_user
    ):
        _, product = await _make_product(db_session)
        await _stock_in_direct(db_session, product, admin_user, qty=100)

        svc = InventoryService(db_session)
        resp = await svc.stock_out(
            StockOutRequest(product_id=product.id, quantity=30),
            current_user_id=admin_user.id, request=None,
        )

        assert resp.total_quantity == 30
        assert resp.updated_stock == 70
        assert len(resp.transactions) == 1
        assert resp.transactions[0].quantity == -30  # NEGATIVE

    @pytest.mark.asyncio
    async def test_stock_out_multi_batch_fifo_order(
        self, db_session: AsyncSession, admin_user
    ):
        """Oldest batch must be depleted first."""
        from datetime import timedelta
        _, product = await _make_product(db_session)

        # Batch A received first
        batchA, _ = await _stock_in_direct(db_session, product, admin_user, qty=50, cost=1.0)
        # Batch B received second
        batchB, _ = await _stock_in_direct(db_session, product, admin_user, qty=50, cost=2.0)

        # Stock out 70: should take all 50 from A, then 20 from B
        svc = InventoryService(db_session)
        resp = await svc.stock_out(
            StockOutRequest(product_id=product.id, quantity=70),
            current_user_id=admin_user.id, request=None,
        )

        assert resp.total_quantity == 70
        assert resp.updated_stock == 30
        assert len(resp.transactions) == 2
        assert len(resp.allocations) == 2

        # First allocation = Batch A (older)
        alloc_a = next(a for a in resp.allocations if a.batch_id == batchA.id)
        alloc_b = next(a for a in resp.allocations if a.batch_id == batchB.id)
        assert alloc_a.quantity_taken == 50
        assert alloc_b.quantity_taken == 20

        # Verify batch remaining_qty in DB
        await db_session.refresh(batchA)
        await db_session.refresh(batchB)
        assert batchA.remaining_qty == 0
        assert batchB.remaining_qty == 30

    @pytest.mark.asyncio
    async def test_stock_out_exact_depletion(self, db_session: AsyncSession, admin_user):
        """Exact depletion: remaining_qty = 0, not negative."""
        _, product = await _make_product(db_session)
        batch, _ = await _stock_in_direct(db_session, product, admin_user, qty=100)

        svc = InventoryService(db_session)
        await svc.stock_out(
            StockOutRequest(product_id=product.id, quantity=100),
            current_user_id=admin_user.id, request=None,
        )

        await db_session.refresh(batch)
        assert batch.remaining_qty == 0
        await db_session.refresh(product)
        assert product.current_stock == 0

    @pytest.mark.asyncio
    async def test_stock_out_partial_batch(self, db_session: AsyncSession, admin_user):
        """Partial depletion: batch still has remaining stock."""
        _, product = await _make_product(db_session)
        batch, _ = await _stock_in_direct(db_session, product, admin_user, qty=100)

        svc = InventoryService(db_session)
        await svc.stock_out(
            StockOutRequest(product_id=product.id, quantity=40),
            current_user_id=admin_user.id, request=None,
        )

        await db_session.refresh(batch)
        assert batch.remaining_qty == 60

    @pytest.mark.asyncio
    async def test_stock_out_insufficient_stock_raises_409(
        self, db_session: AsyncSession, admin_user
    ):
        from fastapi import HTTPException
        _, product = await _make_product(db_session)
        await _stock_in_direct(db_session, product, admin_user, qty=50)

        svc = InventoryService(db_session)
        with pytest.raises(HTTPException) as exc:
            await svc.stock_out(
                StockOutRequest(product_id=product.id, quantity=51),
                current_user_id=admin_user.id, request=None,
            )
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_stock_out_insufficient_no_partial_changes(
        self, db_session: AsyncSession, admin_user
    ):
        """When stock-out fails, neither current_stock nor batches are modified."""
        _, product = await _make_product(db_session)
        batch, _ = await _stock_in_direct(db_session, product, admin_user, qty=20)
        original_stock = product.current_stock

        from fastapi import HTTPException
        svc = InventoryService(db_session)
        with pytest.raises(HTTPException):
            await svc.stock_out(
                StockOutRequest(product_id=product.id, quantity=999),
                current_user_id=admin_user.id, request=None,
            )

        # Verify nothing changed
        await db_session.refresh(product)
        await db_session.refresh(batch)
        assert product.current_stock == original_stock
        assert batch.remaining_qty == 20

        # Verify no STOCK_OUT transaction was created
        txn_count = await db_session.scalar(
            select(StockTransaction)
            .where(
                StockTransaction.product_id == product.id,
                StockTransaction.transaction_type == "STOCK_OUT",
            )
        )
        assert txn_count is None  # no STOCK_OUT should exist

    @pytest.mark.asyncio
    async def test_stock_out_zero_quantity_rejected(self, db_session: AsyncSession):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            StockOutRequest(product_id=uuid.uuid4(), quantity=0)

    @pytest.mark.asyncio
    async def test_stock_out_transactions_are_negative(
        self, db_session: AsyncSession, admin_user
    ):
        """All STOCK_OUT transaction quantities must be negative."""
        _, product = await _make_product(db_session)
        # Two batches
        await _stock_in_direct(db_session, product, admin_user, qty=60)
        await _stock_in_direct(db_session, product, admin_user, qty=60)

        svc = InventoryService(db_session)
        resp = await svc.stock_out(
            StockOutRequest(product_id=product.id, quantity=100),
            current_user_id=admin_user.id, request=None,
        )
        for txn in resp.transactions:
            assert txn.quantity < 0, f"STOCK_OUT transaction quantity must be negative, got {txn.quantity}"

    @pytest.mark.asyncio
    async def test_stock_out_stores_batch_cost_in_transaction(
        self, db_session: AsyncSession, admin_user
    ):
        """unit_cost on STOCK_OUT transaction should match the batch cost (FIFO valuation)."""
        _, product = await _make_product(db_session)
        await _stock_in_direct(db_session, product, admin_user, qty=50, cost=7.50)

        svc = InventoryService(db_session)
        resp = await svc.stock_out(
            StockOutRequest(product_id=product.id, quantity=10),
            current_user_id=admin_user.id, request=None,
        )
        assert resp.transactions[0].unit_cost == 7.50

    @pytest.mark.asyncio
    async def test_stock_out_one_transaction_per_depleted_batch(
        self, db_session: AsyncSession, admin_user
    ):
        """When two batches are depleted, two StockTransaction rows are created."""
        _, product = await _make_product(db_session)
        await _stock_in_direct(db_session, product, admin_user, qty=30)
        await _stock_in_direct(db_session, product, admin_user, qty=30)

        svc = InventoryService(db_session)
        resp = await svc.stock_out(
            StockOutRequest(product_id=product.id, quantity=55),
            current_user_id=admin_user.id, request=None,
        )
        assert len(resp.transactions) == 2

    @pytest.mark.asyncio
    async def test_stock_out_decrements_current_stock_correctly(
        self, db_session: AsyncSession, admin_user
    ):
        _, product = await _make_product(db_session)
        await _stock_in_direct(db_session, product, admin_user, qty=200)

        svc = InventoryService(db_session)
        await svc.stock_out(
            StockOutRequest(product_id=product.id, quantity=75),
            current_user_id=admin_user.id, request=None,
        )

        await db_session.refresh(product)
        assert product.current_stock == 125


# ===========================================================================
# ADJUSTMENT tests
# ===========================================================================

class TestAdjustment:
    @pytest.mark.asyncio
    async def test_positive_adjustment_increases_stock(
        self, db_session: AsyncSession, admin_user
    ):
        _, product = await _make_product(db_session)
        await _stock_in_direct(db_session, product, admin_user, qty=100)

        svc = InventoryService(db_session)
        resp = await svc.adjustment(
            AdjustmentRequest(
                product_id=product.id, quantity_delta=10, reason="Count correction"
            ),
            current_user_id=admin_user.id, request=None,
        )
        assert resp.updated_stock == 110
        assert resp.transaction.quantity == 10
        assert resp.transaction.transaction_type == "ADJUSTMENT"

    @pytest.mark.asyncio
    async def test_negative_adjustment_decreases_stock(
        self, db_session: AsyncSession, admin_user
    ):
        _, product = await _make_product(db_session)
        await _stock_in_direct(db_session, product, admin_user, qty=100)

        svc = InventoryService(db_session)
        resp = await svc.adjustment(
            AdjustmentRequest(
                product_id=product.id, quantity_delta=-20, reason="Damaged goods"
            ),
            current_user_id=admin_user.id, request=None,
        )
        assert resp.updated_stock == 80

    @pytest.mark.asyncio
    async def test_missing_reason_rejected_by_schema(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            AdjustmentRequest(
                product_id=uuid.uuid4(),
                quantity_delta=5,
                reason="",  # blank
            )

    @pytest.mark.asyncio
    async def test_blank_whitespace_reason_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            AdjustmentRequest(
                product_id=uuid.uuid4(),
                quantity_delta=5,
                reason="   ",  # only whitespace
            )

    @pytest.mark.asyncio
    async def test_zero_delta_rejected_by_schema(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            AdjustmentRequest(
                product_id=uuid.uuid4(),
                quantity_delta=0,
                reason="Something",
            )

    @pytest.mark.asyncio
    async def test_adjustment_causing_negative_stock_raises_409(
        self, db_session: AsyncSession, admin_user
    ):
        from fastapi import HTTPException
        _, product = await _make_product(db_session)
        await _stock_in_direct(db_session, product, admin_user, qty=50)

        svc = InventoryService(db_session)
        with pytest.raises(HTTPException) as exc:
            await svc.adjustment(
                AdjustmentRequest(
                    product_id=product.id,
                    quantity_delta=-51,
                    reason="Too big deduction",
                ),
                current_user_id=admin_user.id, request=None,
            )
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_adjustment_stores_reason_in_notes(
        self, db_session: AsyncSession, admin_user
    ):
        _, product = await _make_product(db_session)
        await _stock_in_direct(db_session, product, admin_user, qty=100)

        svc = InventoryService(db_session)
        resp = await svc.adjustment(
            AdjustmentRequest(
                product_id=product.id,
                quantity_delta=-5,
                reason="Spoiled during storage",
            ),
            current_user_id=admin_user.id, request=None,
        )
        assert resp.transaction.notes == "Spoiled during storage"

    @pytest.mark.asyncio
    async def test_adjustment_with_valid_batch_id(
        self, db_session: AsyncSession, admin_user
    ):
        _, product = await _make_product(db_session)
        batch, _ = await _stock_in_direct(db_session, product, admin_user, qty=100)

        svc = InventoryService(db_session)
        resp = await svc.adjustment(
            AdjustmentRequest(
                product_id=product.id,
                quantity_delta=-10,
                reason="Write off",
                batch_id=batch.id,
            ),
            current_user_id=admin_user.id, request=None,
        )
        assert resp.batch_updated is True
        await db_session.refresh(batch)
        assert batch.remaining_qty == 90

    @pytest.mark.asyncio
    async def test_adjustment_batch_remaining_cannot_exceed_original(
        self, db_session: AsyncSession, admin_user
    ):
        """Positive batch adjustment exceeding original quantity → 409."""
        from fastapi import HTTPException
        _, product = await _make_product(db_session)
        batch, _ = await _stock_in_direct(db_session, product, admin_user, qty=100)

        svc = InventoryService(db_session)
        with pytest.raises(HTTPException) as exc:
            await svc.adjustment(
                AdjustmentRequest(
                    product_id=product.id,
                    quantity_delta=1,   # remaining is already 100 = quantity
                    reason="Over-adjustment attempt",
                    batch_id=batch.id,
                ),
                current_user_id=admin_user.id, request=None,
            )
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_adjustment_batch_remaining_cannot_go_negative(
        self, db_session: AsyncSession, admin_user
    ):
        from fastapi import HTTPException
        _, product = await _make_product(db_session)
        batch, _ = await _stock_in_direct(db_session, product, admin_user, qty=50)

        svc = InventoryService(db_session)
        with pytest.raises(HTTPException) as exc:
            await svc.adjustment(
                AdjustmentRequest(
                    product_id=product.id,
                    quantity_delta=-51,
                    reason="Overdepletion attempt",
                    batch_id=batch.id,
                ),
                current_user_id=admin_user.id, request=None,
            )
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_adjustment_batch_wrong_product_raises_409(
        self, db_session: AsyncSession, admin_user
    ):
        """Batch that belongs to a different product → 409."""
        from fastapi import HTTPException
        _, product1 = await _make_product(db_session)
        _, product2 = await _make_product(db_session)
        batch1, _ = await _stock_in_direct(db_session, product1, admin_user, qty=50)
        await _stock_in_direct(db_session, product2, admin_user, qty=50)

        svc = InventoryService(db_session)
        with pytest.raises(HTTPException) as exc:
            await svc.adjustment(
                AdjustmentRequest(
                    product_id=product2.id,  # product2
                    quantity_delta=-5,
                    reason="Wrong batch",
                    batch_id=batch1.id,     # batch from product1
                ),
                current_user_id=admin_user.id, request=None,
            )
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_adjustment_writes_audit_log(
        self, db_session: AsyncSession, admin_user
    ):
        from app.models.audit_log import AuditLog
        _, product = await _make_product(db_session)
        await _stock_in_direct(db_session, product, admin_user, qty=100)

        svc = InventoryService(db_session)
        await svc.adjustment(
            AdjustmentRequest(
                product_id=product.id, quantity_delta=-15, reason="Audit test"
            ),
            current_user_id=admin_user.id, request=None,
        )

        log = await db_session.scalar(
            select(AuditLog).where(
                AuditLog.resource_id == product.id,
                AuditLog.action == "ADJUSTMENT",
            )
        )
        assert log is not None
        assert log.old_value["current_stock"] == 100
        assert log.new_value["current_stock"] == 85
        assert log.new_value["reason"] == "Audit test"

    @pytest.mark.asyncio
    async def test_failed_adjustment_no_partial_changes(
        self, db_session: AsyncSession, admin_user
    ):
        """Failed adjustment should not modify current_stock or create a transaction."""
        from fastapi import HTTPException
        _, product = await _make_product(db_session)
        await _stock_in_direct(db_session, product, admin_user, qty=10)

        svc = InventoryService(db_session)
        with pytest.raises(HTTPException):
            await svc.adjustment(
                AdjustmentRequest(
                    product_id=product.id,
                    quantity_delta=-100,  # would go negative
                    reason="Test fail",
                ),
                current_user_id=admin_user.id, request=None,
            )

        await db_session.refresh(product)
        assert product.current_stock == 10  # unchanged

        count = await db_session.scalar(
            select(StockTransaction).where(
                StockTransaction.product_id == product.id,
                StockTransaction.transaction_type == "ADJUSTMENT",
            )
        )
        assert count is None


# ===========================================================================
# RBAC tests (via HTTP)
# ===========================================================================

class TestInventoryRBAC:
    @pytest.mark.asyncio
    async def test_staff_can_stock_in(
        self, client: AsyncClient, db_session: AsyncSession, staff_user, admin_user
    ):
        _, product = await _make_product(db_session)
        resp = await client.post(
            "/api/v1/transactions/stock-in",
            json={
                "product_id": str(product.id),
                "quantity": 10,
                "cost_per_unit": 1.0,
            },
            headers=auth_headers(str(staff_user.id), "STAFF"),
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_staff_can_stock_out(
        self, client: AsyncClient, db_session: AsyncSession, staff_user, admin_user
    ):
        _, product = await _make_product(db_session)
        await _stock_in_direct(db_session, product, admin_user, qty=50)

        resp = await client.post(
            "/api/v1/transactions/stock-out",
            json={"product_id": str(product.id), "quantity": 10},
            headers=auth_headers(str(staff_user.id), "STAFF"),
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_staff_cannot_adjust(
        self, client: AsyncClient, db_session: AsyncSession, staff_user, admin_user
    ):
        _, product = await _make_product(db_session)
        await _stock_in_direct(db_session, product, admin_user, qty=50)

        resp = await client.post(
            "/api/v1/transactions/adjustment",
            json={
                "product_id": str(product.id),
                "quantity_delta": -5,
                "reason": "Hack attempt",
            },
            headers=auth_headers(str(staff_user.id), "STAFF"),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_manager_can_adjust(
        self, client: AsyncClient, db_session: AsyncSession, manager_user, admin_user
    ):
        _, product = await _make_product(db_session)
        await _stock_in_direct(db_session, product, admin_user, qty=50)

        resp = await client.post(
            "/api/v1/transactions/adjustment",
            json={
                "product_id": str(product.id),
                "quantity_delta": -5,
                "reason": "Count correction",
            },
            headers=auth_headers(str(manager_user.id), "MANAGER"),
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_staff_cannot_patch_batch(
        self, client: AsyncClient, db_session: AsyncSession, staff_user, admin_user
    ):
        _, product = await _make_product(db_session)
        batch, _ = await _stock_in_direct(db_session, product, admin_user, qty=50)

        resp = await client.patch(
            f"/api/v1/inventory/batches/{batch.id}",
            json={"notes": "Hack"},
            headers=auth_headers(str(staff_user.id), "STAFF"),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_manager_can_patch_batch(
        self, client: AsyncClient, db_session: AsyncSession, manager_user, admin_user
    ):
        _, product = await _make_product(db_session)
        batch, _ = await _stock_in_direct(db_session, product, admin_user, qty=50)

        resp = await client.patch(
            f"/api/v1/inventory/batches/{batch.id}",
            json={"notes": "Updated notes"},
            headers=auth_headers(str(manager_user.id), "MANAGER"),
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unauthenticated_gets_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/transactions")
        assert resp.status_code == 401


# ===========================================================================
# TRANSACTION HISTORY tests
# ===========================================================================

class TestTransactionHistory:
    @pytest.mark.asyncio
    async def test_list_transactions_paginated(
        self, client: AsyncClient, db_session: AsyncSession, admin_user
    ):
        _, product = await _make_product(db_session)
        svc = InventoryService(db_session)
        for _ in range(5):
            await svc.stock_in(
                StockInRequest(product_id=product.id, quantity=10, cost_per_unit=1.0),
                current_user_id=admin_user.id, request=None,
            )

        resp = await client.get(
            "/api/v1/transactions?page_size=3&page=1",
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["page_size"] == 3
        assert data["total"] >= 5

    @pytest.mark.asyncio
    async def test_filter_by_product_id(
        self, db_session: AsyncSession, admin_user
    ):
        _, product1 = await _make_product(db_session)
        _, product2 = await _make_product(db_session)
        await _stock_in_direct(db_session, product1, admin_user, qty=10)
        await _stock_in_direct(db_session, product1, admin_user, qty=10)
        await _stock_in_direct(db_session, product2, admin_user, qty=10)

        svc = InventoryService(db_session)
        result = await svc.list_transactions(product_id=product1.id)
        assert result.total == 2
        for item in result.items:
            assert item.product_id == product1.id

    @pytest.mark.asyncio
    async def test_filter_by_transaction_type(
        self, db_session: AsyncSession, admin_user
    ):
        _, product = await _make_product(db_session)
        await _stock_in_direct(db_session, product, admin_user, qty=100)

        svc = InventoryService(db_session)
        await svc.stock_out(
            StockOutRequest(product_id=product.id, quantity=30),
            current_user_id=admin_user.id, request=None,
        )

        ins = await svc.list_transactions(
            product_id=product.id, transaction_type="STOCK_IN"
        )
        outs = await svc.list_transactions(
            product_id=product.id, transaction_type="STOCK_OUT"
        )
        assert all(t.transaction_type == "STOCK_IN" for t in ins.items)
        assert all(t.transaction_type == "STOCK_OUT" for t in outs.items)

    @pytest.mark.asyncio
    async def test_transaction_history_is_immutable_no_put_delete(
        self, client: AsyncClient, admin_user
    ):
        """No PUT or DELETE endpoints should exist for transactions."""
        txn_id = uuid.uuid4()
        headers = auth_headers(str(admin_user.id), "ADMIN")

        put_resp = await client.put(
            f"/api/v1/transactions/{txn_id}", json={}, headers=headers
        )
        delete_resp = await client.delete(
            f"/api/v1/transactions/{txn_id}", headers=headers
        )
        # 405 Method Not Allowed or 404 (route doesn't exist) — both correct
        assert put_resp.status_code in (404, 405)
        assert delete_resp.status_code in (404, 405)


# ===========================================================================
# BATCH ENDPOINT tests
# ===========================================================================

class TestBatchEndpoints:
    @pytest.mark.asyncio
    async def test_list_batches_for_product(
        self, db_session: AsyncSession, admin_user
    ):
        _, product = await _make_product(db_session)
        await _stock_in_direct(db_session, product, admin_user, qty=50)
        await _stock_in_direct(db_session, product, admin_user, qty=50)

        svc = InventoryService(db_session)
        result = await svc.get_product_batches(product.id)
        assert result.total == 2

    @pytest.mark.asyncio
    async def test_batch_patch_cannot_change_quantities(
        self, client: AsyncClient, db_session: AsyncSession, admin_user
    ):
        _, product = await _make_product(db_session)
        batch, _ = await _stock_in_direct(db_session, product, admin_user, qty=100)

        # PATCH with remaining_qty — should be ignored (field not in schema)
        resp = await client.patch(
            f"/api/v1/inventory/batches/{batch.id}",
            json={"remaining_qty": 999, "notes": "legit update"},
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        # Should succeed (legit field processed) but remaining_qty must be unchanged
        assert resp.status_code == 200
        await db_session.refresh(batch)
        assert batch.remaining_qty == 100  # unchanged

    @pytest.mark.asyncio
    async def test_patch_batch_notes(
        self, client: AsyncClient, db_session: AsyncSession, admin_user
    ):
        _, product = await _make_product(db_session)
        batch, _ = await _stock_in_direct(db_session, product, admin_user, qty=50)

        resp = await client.patch(
            f"/api/v1/inventory/batches/{batch.id}",
            json={"notes": "Stored in cold chain unit 3"},
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        assert resp.status_code == 200
        assert resp.json()["notes"] == "Stored in cold chain unit 3"


# ===========================================================================
# DATA CONSISTENCY tests
# ===========================================================================

class TestDataConsistency:
    @pytest.mark.asyncio
    async def test_current_stock_equals_ledger_sum_after_operations(
        self, db_session: AsyncSession, admin_user
    ):
        """
        After a series of stock-in + stock-out operations,
        products.current_stock must equal SUM(stock_transactions.quantity).
        """
        from sqlalchemy import select as sa_select, func

        _, product = await _make_product(db_session)
        svc = InventoryService(db_session)

        await svc.stock_in(
            StockInRequest(product_id=product.id, quantity=100, cost_per_unit=5.0),
            current_user_id=admin_user.id, request=None,
        )
        await svc.stock_in(
            StockInRequest(product_id=product.id, quantity=50, cost_per_unit=6.0),
            current_user_id=admin_user.id, request=None,
        )
        await svc.stock_out(
            StockOutRequest(product_id=product.id, quantity=80),
            current_user_id=admin_user.id, request=None,
        )
        await svc.adjustment(
            AdjustmentRequest(
                product_id=product.id, quantity_delta=-5, reason="Shrinkage"
            ),
            current_user_id=admin_user.id, request=None,
        )

        # Recompute from transaction ledger
        ledger_sum = await db_session.scalar(
            sa_select(func.coalesce(func.sum(StockTransaction.quantity), 0))
            .where(StockTransaction.product_id == product.id)
        )

        await db_session.refresh(product)
        assert product.current_stock == ledger_sum, (
            f"Inconsistency: current_stock={product.current_stock}, "
            f"ledger_sum={ledger_sum}"
        )

    @pytest.mark.asyncio
    async def test_reconcile_function(self, db_session: AsyncSession, admin_user):
        _, product = await _make_product(db_session)
        svc = InventoryService(db_session)
        await svc.stock_in(
            StockInRequest(product_id=product.id, quantity=100, cost_per_unit=1.0),
            current_user_id=admin_user.id, request=None,
        )
        result = await svc.reconcile_stock(product.id)
        assert result["consistent"] is True
        assert result["current_stock"] == 100
        assert result["ledger_sum"] == 100


# ===========================================================================
# CONCURRENCY DESIGN NOTE (not a test — documentation)
# ===========================================================================
#
# The InventoryService uses SELECT ... FOR UPDATE to serialize concurrent
# stock mutations in PostgreSQL production.
#
# Why this cannot be unit-tested with SQLite:
#   SQLite does not implement row-level locking. The with_for_update()
#   clause is silently ignored. Running two coroutines concurrently in
#   an asyncio test with SQLite would not reproduce the PostgreSQL locking
#   behaviour.
#
# Production concurrency guarantee:
#   Two concurrent stock-out requests for the same product will queue at
#   the PostgreSQL level:
#     TX1: SELECT ... FOR UPDATE (acquires lock)
#     TX2: SELECT ... FOR UPDATE (waits)
#     TX1: validates stock, depletes batches, commits, releases lock
#     TX2: reads updated current_stock (already decremented by TX1), validates
#          If TX1 depleted all stock → TX2 gets 409 (insufficient stock)
#
# Integration test approach (for full Postgres CI):
#   Use asyncio.gather() with two simultaneous stock-out requests targeting
#   the same product. Assert that exactly one succeeds and one fails with 409,
#   and that products.current_stock ends up non-negative.
#   This test requires a real PostgreSQL instance and is outside the SQLite
#   test suite scope.
