"""
CategoryService — CRUD for product categories.

RBAC summary:
  list / get  → any authenticated user (ADMIN, MANAGER, STAFF)
  create      → ADMIN, MANAGER
  update      → ADMIN, MANAGER
  delete      → ADMIN only (categories with products cannot be deleted)

The router enforces role checks via Depends(). The service adds a
second check where ownership or data integrity matters (e.g., blocking
delete when products exist).
"""
import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Category, Product
from app.schemas.category import (
    CategoryCreateRequest,
    CategoryUpdateRequest,
    CategoryResponse,
    CategoryWithProductCountResponse,
)
from app.schemas.common import PaginatedResponse

logger = logging.getLogger("stocksense.categories")


class CategoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    async def list_categories(
        self,
        *,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[CategoryWithProductCountResponse]:
        """
        Return a paginated list of categories with product counts.

        search: case-insensitive substring match on name or description.
        """
        base_q = select(Category)

        if search:
            term = f"%{search.lower()}%"
            base_q = base_q.where(
                func.lower(Category.name).like(term)
                | func.lower(Category.description).like(term)
            )

        # Total count (before pagination)
        count_q = select(func.count()).select_from(base_q.subquery())
        total: int = await self.db.scalar(count_q) or 0

        # Paginated rows, ordered by name
        offset = (page - 1) * page_size
        rows_q = base_q.order_by(Category.name).offset(offset).limit(page_size)
        result = await self.db.execute(rows_q)
        categories = result.scalars().all()

        # Batch-fetch product counts for the returned categories
        cat_ids = [c.id for c in categories]
        counts: dict[uuid.UUID, int] = {}
        if cat_ids:
            cnt_result = await self.db.execute(
                select(Product.category_id, func.count(Product.id))
                .where(Product.category_id.in_(cat_ids), Product.is_active.is_(True))
                .group_by(Product.category_id)
            )
            counts = {row[0]: row[1] for row in cnt_result.all()}

        items = [
            CategoryWithProductCountResponse(
                id=c.id,
                name=c.name,
                description=c.description,
                created_at=c.created_at,
                updated_at=c.updated_at,
                product_count=counts.get(c.id, 0),
            )
            for c in categories
        ]

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, -(-total // page_size)),  # ceiling division
        )

    # ------------------------------------------------------------------
    # Get one
    # ------------------------------------------------------------------

    async def get_category(self, category_id: uuid.UUID) -> CategoryWithProductCountResponse:
        category = await self._get_or_404(category_id)
        count = await self.db.scalar(
            select(func.count(Product.id))
            .where(Product.category_id == category_id, Product.is_active.is_(True))
        ) or 0
        return CategoryWithProductCountResponse(
            id=category.id,
            name=category.name,
            description=category.description,
            created_at=category.created_at,
            updated_at=category.updated_at,
            product_count=count,
        )

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_category(
        self,
        data: CategoryCreateRequest,
        *,
        current_user_id: uuid.UUID,
        request: object,
    ) -> CategoryResponse:
        await self._assert_name_unique(data.name)

        category = Category(name=data.name, description=data.description)
        self.db.add(category)

        # Flush to get the generated id before committing (needed for audit)
        await self.db.flush()

        # Audit log — added to same session, committed together
        from app.services.audit_service import AuditService, get_client_ip, get_user_agent
        audit = AuditService(self.db)
        await audit.log(
            user_id=current_user_id,
            action="CREATE_CATEGORY",
            resource_type="CATEGORY",
            resource_id=category.id,
            new_value={"name": category.name, "description": category.description},
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        await self.db.commit()
        await self.db.refresh(category)
        logger.info(f"Category created: {category.name} (id={category.id})")
        return _category_to_response(category)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_category(
        self,
        category_id: uuid.UUID,
        data: CategoryUpdateRequest,
        *,
        current_user_id: uuid.UUID,
        request: object,
    ) -> CategoryResponse:
        category = await self._get_or_404(category_id)

        # Snapshot before state for audit
        old_snapshot = {"name": category.name, "description": category.description}

        if data.name is not None and data.name != category.name:
            await self._assert_name_unique(data.name, exclude_id=category_id)
            category.name = data.name

        if data.description is not None:
            category.description = data.description

        await self.db.flush()

        from app.services.audit_service import AuditService, get_client_ip, get_user_agent
        audit = AuditService(self.db)
        await audit.log(
            user_id=current_user_id,
            action="UPDATE_CATEGORY",
            resource_type="CATEGORY",
            resource_id=category.id,
            old_value=old_snapshot,
            new_value={"name": category.name, "description": category.description},
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        await self.db.commit()
        await self.db.refresh(category)
        logger.info(f"Category updated: id={category_id}")
        return _category_to_response(category)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_category(
        self,
        category_id: uuid.UUID,
        *,
        current_user_id: uuid.UUID,
        request: object,
    ) -> None:
        category = await self._get_or_404(category_id)

        # Business rule: cannot delete a category that still has products
        product_count = await self.db.scalar(
            select(func.count(Product.id)).where(Product.category_id == category_id)
        ) or 0
        if product_count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot delete category '{category.name}': "
                    f"it has {product_count} associated product(s). "
                    "Reassign or delete them first."
                ),
            )

        old_snapshot = {"name": category.name, "description": category.description}
        await self.db.delete(category)
        await self.db.flush()

        from app.services.audit_service import AuditService, get_client_ip, get_user_agent
        audit = AuditService(self.db)
        await audit.log(
            user_id=current_user_id,
            action="DELETE_CATEGORY",
            resource_type="CATEGORY",
            resource_id=category_id,
            old_value=old_snapshot,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        await self.db.commit()
        logger.info(f"Category deleted: id={category_id}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_or_404(self, category_id: uuid.UUID) -> Category:
        category = await self.db.scalar(
            select(Category).where(Category.id == category_id)
        )
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Category {category_id} not found.",
            )
        return category

    async def _assert_name_unique(
        self, name: str, exclude_id: uuid.UUID | None = None
    ) -> None:
        q = select(Category).where(func.lower(Category.name) == name.lower())
        if exclude_id:
            q = q.where(Category.id != exclude_id)
        existing = await self.db.scalar(q)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A category named '{name}' already exists.",
            )


# ---------------------------------------------------------------------------
# Response helper
# ---------------------------------------------------------------------------

def _category_to_response(c: Category) -> CategoryResponse:
    return CategoryResponse(
        id=c.id,
        name=c.name,
        description=c.description,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )
