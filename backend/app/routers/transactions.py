"""
Transactions router — /api/v1/transactions

POST /stock-in    — receive stock (ADMIN, MANAGER, STAFF)
POST /stock-out   — consume stock via FIFO (ADMIN, MANAGER, STAFF)
POST /adjustment  — manual correction (ADMIN, MANAGER only)

GET  /            — transaction history
GET  /{id}        — single transaction

Transaction rows are immutable — no PUT or DELETE endpoints.
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_any_role, require_manager_or_admin
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.inventory import (
    AdjustmentRequest,
    AdjustmentResponse,
    StockInRequest,
    StockInResponse,
    StockOutRequest,
    StockOutResponse,
    StockTransactionResponse,
    TransactionSortField,
    TransactionSortOrder,
)
from app.services.inventory_service import InventoryService

router = APIRouter()


@router.post(
    "/stock-in",
    response_model=StockInResponse,
    status_code=201,
    summary="Record stock received (ADMIN, MANAGER, STAFF)",
    description=(
        "Creates an inventory batch and a STOCK_IN transaction, "
        "then increments product.current_stock atomically."
    ),
)
async def stock_in(
    request: Request,
    data: StockInRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role),
):
    svc = InventoryService(db)
    return await svc.stock_in(data, current_user_id=current_user.id, request=request)


@router.post(
    "/stock-out",
    response_model=StockOutResponse,
    status_code=201,
    summary="Record stock consumed using FIFO (ADMIN, MANAGER, STAFF)",
    description=(
        "Depletes stock using FIFO (oldest batch first). "
        "Returns the allocation breakdown showing which batches were depleted."
    ),
)
async def stock_out(
    request: Request,
    data: StockOutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_role),
):
    svc = InventoryService(db)
    return await svc.stock_out(data, current_user_id=current_user.id, request=request)


@router.post(
    "/adjustment",
    response_model=AdjustmentResponse,
    status_code=201,
    summary="Manual stock adjustment — requires reason (ADMIN, MANAGER)",
    description=(
        "Applies a signed quantity_delta to product.current_stock. "
        "A mandatory reason is stored on the transaction and audit log. "
        "Staff are not permitted to perform adjustments."
    ),
)
async def adjustment(
    request: Request,
    data: AdjustmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin),
):
    svc = InventoryService(db)
    return await svc.adjustment(data, current_user_id=current_user.id, request=request)


@router.get(
    "",
    response_model=PaginatedResponse[StockTransactionResponse],
    summary="List transaction history",
    description="Immutable ledger of all stock movements. Supports filtering and pagination.",
)
async def list_transactions(
    product_id: uuid.UUID | None = Query(default=None),
    transaction_type: str | None = Query(
        default=None, description="STOCK_IN | STOCK_OUT | ADJUSTMENT | WRITE_OFF"
    ),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    sort_by: TransactionSortField = Query(default="transaction_at"),
    sort_order: TransactionSortOrder = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    svc = InventoryService(db)
    return await svc.list_transactions(
        product_id=product_id,
        transaction_type=transaction_type,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{transaction_id}",
    response_model=StockTransactionResponse,
    summary="Get a single transaction",
)
async def get_transaction(
    transaction_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    svc = InventoryService(db)
    return await svc.get_transaction(transaction_id)
