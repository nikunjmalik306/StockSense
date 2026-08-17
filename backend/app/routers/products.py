"""
Products router — /api/v1/products

GET    /              → list with search/filter/sort/paginate (any role)
POST   /              → create (ADMIN, MANAGER)
GET    /{id}          → get one with nested category + supplier (any role)
PUT    /{id}          → update (ADMIN, MANAGER)
DELETE /{id}          → soft-delete (ADMIN only)
"""
import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, require_any_role, require_manager_or_admin
from app.models.user import User
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.product import (
    ProductCreateRequest,
    ProductListResponse,
    ProductResponse,
    ProductUpdateRequest,
)
from app.services.product_service import ProductService, SortField, SortOrder

router = APIRouter()


@router.get(
    "",
    response_model=PaginatedResponse[ProductListResponse],
    summary="List products with search, filter, sort, paginate",
)
async def list_products(
    search: str | None = Query(default=None, description="Search SKU, name, description"),
    category_id: uuid.UUID | None = Query(default=None),
    supplier_id: uuid.UUID | None = Query(default=None),
    is_active: bool | None = Query(default=True),
    risk_level: str | None = Query(default=None, description="LOW | MEDIUM | HIGH | CRITICAL"),
    low_stock_only: bool = Query(default=False),
    sort_by: SortField = Query(default="name"),
    sort_order: SortOrder = Query(default="asc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    svc = ProductService(db)
    return await svc.list_products(
        search=search,
        category_id=category_id,
        supplier_id=supplier_id,
        is_active=is_active,
        risk_level=risk_level,
        low_stock_only=low_stock_only,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=ProductResponse,
    status_code=201,
    summary="Create a product (ADMIN, MANAGER)",
)
async def create_product(
    request: Request,
    data: ProductCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin),
):
    svc = ProductService(db)
    return await svc.create_product(
        data, current_user_id=current_user.id, request=request
    )


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Get a single product",
)
async def get_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    svc = ProductService(db)
    return await svc.get_product(product_id)


@router.put(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Update a product (ADMIN, MANAGER)",
)
async def update_product(
    product_id: uuid.UUID,
    request: Request,
    data: ProductUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin),
):
    svc = ProductService(db)
    return await svc.update_product(
        product_id, data, current_user_id=current_user.id, request=request
    )


@router.delete(
    "/{product_id}",
    response_model=MessageResponse,
    summary="Soft-delete a product (ADMIN only)",
)
async def delete_product(
    product_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    svc = ProductService(db)
    await svc.delete_product(
        product_id, current_user_id=current_user.id, request=request
    )
    return MessageResponse(message="Product deactivated.")


# ---------------------------------------------------------------------------
# Product-scoped batch and transaction endpoints
# (Added in Block 3 — co-located here to keep product resources together)
# ---------------------------------------------------------------------------

@router.get(
    "/{product_id}/batches",
    response_model=PaginatedResponse,
    summary="List inventory batches for a product",
)
async def get_product_batches(
    product_id: uuid.UUID,
    include_depleted: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    from app.services.inventory_service import InventoryService
    svc = InventoryService(db)
    return await svc.get_product_batches(
        product_id, include_depleted=include_depleted, page=page, page_size=page_size
    )


@router.get(
    "/{product_id}/transactions",
    response_model=PaginatedResponse,
    summary="List transaction history for a product",
)
async def get_product_transactions(
    product_id: uuid.UUID,
    transaction_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    from app.services.inventory_service import InventoryService
    svc = InventoryService(db)
    return await svc.list_transactions(
        product_id=product_id,
        transaction_type=transaction_type,
        page=page,
        page_size=page_size,
    )
