"""
Categories router — /api/v1/categories

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
from app.schemas.category import (
    CategoryCreateRequest,
    CategoryUpdateRequest,
    CategoryResponse,
    CategoryWithProductCountResponse,
)
from app.schemas.common import MessageResponse, PaginatedResponse
from app.services.category_service import CategoryService

router = APIRouter()


@router.get(
    "",
    response_model=PaginatedResponse[CategoryWithProductCountResponse],
    summary="List categories",
)
async def list_categories(
    search: str | None = Query(default=None, description="Search by name or description"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    svc = CategoryService(db)
    return await svc.list_categories(search=search, page=page, page_size=page_size)


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=201,
    summary="Create a category (ADMIN, MANAGER)",
)
async def create_category(
    request: Request,
    data: CategoryCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin),
):
    svc = CategoryService(db)
    return await svc.create_category(
        data, current_user_id=current_user.id, request=request
    )


@router.get(
    "/{category_id}",
    response_model=CategoryWithProductCountResponse,
    summary="Get a single category",
)
async def get_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    svc = CategoryService(db)
    return await svc.get_category(category_id)


@router.put(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Update a category (ADMIN, MANAGER)",
)
async def update_category(
    category_id: uuid.UUID,
    request: Request,
    data: CategoryUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_manager_or_admin),
):
    svc = CategoryService(db)
    return await svc.update_category(
        category_id, data, current_user_id=current_user.id, request=request
    )


@router.delete(
    "/{category_id}",
    response_model=MessageResponse,
    summary="Delete a category (ADMIN only)",
)
async def delete_category(
    category_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    svc = CategoryService(db)
    await svc.delete_category(
        category_id, current_user_id=current_user.id, request=request
    )
    return MessageResponse(message="Category deleted.")
