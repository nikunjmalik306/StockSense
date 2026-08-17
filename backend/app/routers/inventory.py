"""
Inventory batches router — /api/v1/inventory

GET    /batches                     — list all batches (any role)
GET    /batches/{id}                — get one batch (any role)
PATCH  /batches/{id}                — update batch metadata (ADMIN, MANAGER)

Product-scoped batch endpoints are added to the products router
via include_router with a prefix.
"""
import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_any_role, require_manager_or_admin
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.inventory import InventoryBatchPatchRequest, InventoryBatchResponse
from app.services.inventory_service import InventoryService

router = APIRouter()


@router.get(
    "/batches",
    response_model=PaginatedResponse[InventoryBatchResponse],
    summary="List inventory batches",
)
async def list_batches(
    product_id: uuid.UUID | None = Query(default=None),
    include_depleted: bool = Query(
        default=False, description="Include batches with remaining_qty = 0"
    ),
    expiring_within_days: int | None = Query(
        default=None, description="Only batches expiring within N days"
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    svc = InventoryService(db)
    return await svc.list_batches(
        product_id=product_id,
        include_depleted=include_depleted,
        expiring_within_days=expiring_within_days,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/batches/{batch_id}",
    response_model=InventoryBatchResponse,
    summary="Get a single inventory batch",
)
async def get_batch(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    svc = InventoryService(db)
    return await svc.get_batch(batch_id)


@router.patch(
    "/batches/{batch_id}",
    response_model=InventoryBatchResponse,
    summary="Update batch metadata (ADMIN, MANAGER) — quantity fields not patchable",
    description=(
        "Only safe metadata (batch_number, notes, expiry_date, "
        "manufacture_date, is_active) can be updated. "
        "remaining_qty and quantity are controlled exclusively by stock transactions."
    ),
)
async def patch_batch(
    batch_id: uuid.UUID,
    request: Request,
    data: InventoryBatchPatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin),
):
    svc = InventoryService(db)
    return await svc.patch_batch(
        batch_id, data, current_user_id=current_user.id, request=request
    )
