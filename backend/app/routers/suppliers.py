"""
Suppliers router — /api/v1/suppliers

GET    /              → list (any role)
POST   /              → create (ADMIN, MANAGER)
GET    /{id}          → get one (any role)
PUT    /{id}          → update (ADMIN, MANAGER)
DELETE /{id}          → delete (ADMIN only)
"""
import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, require_any_role, require_manager_or_admin
from app.models.user import User
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.supplier import (
    SupplierCreateRequest,
    SupplierUpdateRequest,
    SupplierResponse,
    SupplierWithProductCountResponse,
)
from app.services.supplier_service import SupplierService

router = APIRouter()


@router.get(
    "",
    response_model=PaginatedResponse[SupplierWithProductCountResponse],
    summary="List suppliers",
)
async def list_suppliers(
    search: str | None = Query(default=None, description="Search by name or contact name"),
    is_active: bool | None = Query(default=None, description="Filter by active status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    svc = SupplierService(db)
    return await svc.list_suppliers(
        search=search, is_active=is_active, page=page, page_size=page_size
    )


@router.post(
    "",
    response_model=SupplierResponse,
    status_code=201,
    summary="Create a supplier (ADMIN, MANAGER)",
)
async def create_supplier(
    request: Request,
    data: SupplierCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin),
):
    svc = SupplierService(db)
    return await svc.create_supplier(
        data, current_user_id=current_user.id, request=request
    )


@router.get(
    "/{supplier_id}",
    response_model=SupplierWithProductCountResponse,
    summary="Get a single supplier",
)
async def get_supplier(
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    svc = SupplierService(db)
    return await svc.get_supplier(supplier_id)


@router.put(
    "/{supplier_id}",
    response_model=SupplierResponse,
    summary="Update a supplier (ADMIN, MANAGER)",
)
async def update_supplier(
    supplier_id: uuid.UUID,
    request: Request,
    data: SupplierUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin),
):
    svc = SupplierService(db)
    return await svc.update_supplier(
        supplier_id, data, current_user_id=current_user.id, request=request
    )


@router.delete(
    "/{supplier_id}",
    response_model=MessageResponse,
    summary="Delete a supplier (ADMIN only)",
)
async def delete_supplier(
    supplier_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    svc = SupplierService(db)
    await svc.delete_supplier(
        supplier_id, current_user_id=current_user.id, request=request
    )
    return MessageResponse(message="Supplier deleted.")
