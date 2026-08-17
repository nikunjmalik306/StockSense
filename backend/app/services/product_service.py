"""
ProductService — CRUD for products with search, filter, sort, paginate.

RBAC:
  list / get  → any authenticated user
  create      → ADMIN, MANAGER
  update      → ADMIN, MANAGER
  delete      → ADMIN only (soft-delete: sets is_active=False)

Search covers: sku (prefix), name, description (case-insensitive LIKE).
Filters: category_id, supplier_id, is_active, risk_level, low_stock.
Sort: name, sku, current_stock, last_risk_score, created_at, updated_at.
"""
import logging
import uuid
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.product import Category, Product, Supplier
from app.schemas.product import (
    ProductCreateRequest,
    ProductListResponse,
    ProductResponse,
    ProductUpdateRequest,
)
from app.schemas.common import PaginatedResponse

logger = logging.getLogger("stocksense.products")

SortField = Literal["name", "sku", "current_stock", "last_risk_score", "created_at", "updated_at"]
SortOrder = Literal["asc", "desc"]

# Map sort_by parameter → ORM column
_SORT_MAP: dict[str, object] = {
    "name": Product.name,
    "sku": Product.sku,
    "current_stock": Product.current_stock,
    "last_risk_score": Product.last_risk_score,
    "created_at": Product.created_at,
    "updated_at": Product.updated_at,
}


class ProductService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    async def list_products(
        self,
        *,
        search: str | None = None,
        category_id: uuid.UUID | None = None,
        supplier_id: uuid.UUID | None = None,
        is_active: bool | None = True,
        risk_level: str | None = None,
        low_stock_only: bool = False,
        sort_by: SortField = "name",
        sort_order: SortOrder = "asc",
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[ProductListResponse]:
        base_q = select(Product)

        # Filters
        if search:
            term = f"%{search.lower()}%"
            base_q = base_q.where(
                func.lower(Product.sku).like(term)
                | func.lower(Product.name).like(term)
                | func.lower(Product.description).like(term)
            )
        if category_id:
            base_q = base_q.where(Product.category_id == category_id)
        if supplier_id:
            base_q = base_q.where(Product.supplier_id == supplier_id)
        if is_active is not None:
            base_q = base_q.where(Product.is_active.is_(is_active))
        if risk_level:
            base_q = base_q.where(
                func.upper(Product.last_risk_level) == risk_level.upper()
            )
        if low_stock_only:
            # Products where current_stock <= reorder_point
            base_q = base_q.where(Product.current_stock <= Product.reorder_point)

        # Count
        total: int = await self.db.scalar(
            select(func.count()).select_from(base_q.subquery())
        ) or 0

        # Sort
        col = _SORT_MAP.get(sort_by, Product.name)
        order_fn = asc if sort_order == "asc" else desc
        base_q = base_q.order_by(order_fn(col))

        # Pagination
        offset = (page - 1) * page_size
        result = await self.db.execute(
            base_q.offset(offset).limit(page_size)
            .options(selectinload(Product.category), selectinload(Product.supplier))
        )
        products = result.scalars().all()

        items = [_product_list_response(p) for p in products]
        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=max(1, -(-total // page_size)),
        )

    # ------------------------------------------------------------------
    # Get one
    # ------------------------------------------------------------------

    async def get_product(self, product_id: uuid.UUID) -> ProductResponse:
        product = await self._get_or_404_with_relations(product_id)
        return _product_to_response(product)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_product(
        self,
        data: ProductCreateRequest,
        *,
        current_user_id: uuid.UUID,
        request: object,
    ) -> ProductResponse:
        # SKU uniqueness
        await self._assert_sku_unique(data.sku)

        # Foreign key existence checks — prevents cryptic DB errors
        await self._assert_category_exists(data.category_id)
        if data.supplier_id:
            await self._assert_supplier_exists(data.supplier_id)

        product = Product(
            sku=data.sku,
            name=data.name,
            description=data.description,
            category_id=data.category_id,
            supplier_id=data.supplier_id,
            unit=data.unit,
            reorder_point=data.reorder_point,
            reorder_quantity=data.reorder_quantity,
            max_stock_level=data.max_stock_level,
            expiry_alert_days=data.expiry_alert_days,
        )
        self.db.add(product)
        await self.db.flush()

        from app.services.audit_service import AuditService, get_client_ip, get_user_agent
        await AuditService(self.db).log(
            user_id=current_user_id,
            action="CREATE_PRODUCT",
            resource_type="PRODUCT",
            resource_id=product.id,
            new_value=_product_audit_dict(product),
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        await self.db.commit()
        # Re-load with relationships for response
        product = await self._get_or_404_with_relations(product.id)
        logger.info(f"Product created: {product.sku} (id={product.id})")
        return _product_to_response(product)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_product(
        self,
        product_id: uuid.UUID,
        data: ProductUpdateRequest,
        *,
        current_user_id: uuid.UUID,
        request: object,
    ) -> ProductResponse:
        product = await self._get_or_404_with_relations(product_id)
        old_snapshot = _product_audit_dict(product)

        if data.name is not None:
            product.name = data.name
        if data.description is not None:
            product.description = data.description
        if data.category_id is not None:
            await self._assert_category_exists(data.category_id)
            product.category_id = data.category_id
        if data.supplier_id is not None:
            await self._assert_supplier_exists(data.supplier_id)
            product.supplier_id = data.supplier_id
        if data.unit is not None:
            product.unit = data.unit
        if data.reorder_point is not None:
            product.reorder_point = data.reorder_point
        if data.reorder_quantity is not None:
            product.reorder_quantity = data.reorder_quantity
        if data.max_stock_level is not None:
            # Validate cross-field constraint
            rp = data.reorder_point if data.reorder_point is not None else product.reorder_point
            if data.max_stock_level <= rp:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="max_stock_level must be greater than reorder_point.",
                )
            product.max_stock_level = data.max_stock_level
        if data.expiry_alert_days is not None:
            product.expiry_alert_days = data.expiry_alert_days
        if data.is_active is not None:
            product.is_active = data.is_active

        await self.db.flush()

        from app.services.audit_service import AuditService, get_client_ip, get_user_agent
        await AuditService(self.db).log(
            user_id=current_user_id,
            action="UPDATE_PRODUCT",
            resource_type="PRODUCT",
            resource_id=product_id,
            old_value=old_snapshot,
            new_value=_product_audit_dict(product),
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        await self.db.commit()
        product = await self._get_or_404_with_relations(product_id)
        logger.info(f"Product updated: id={product_id}")
        return _product_to_response(product)

    # ------------------------------------------------------------------
    # Delete (soft — sets is_active=False)
    # ------------------------------------------------------------------

    async def delete_product(
        self,
        product_id: uuid.UUID,
        *,
        current_user_id: uuid.UUID,
        request: object,
    ) -> None:
        """
        Soft-delete: mark product inactive rather than physically removing it.

        Physical deletion would cascade into transaction history, losing the
        audit trail. Soft-delete preserves all historical data while hiding
        the product from normal list queries.
        """
        product = await self._get_or_404_with_relations(product_id)
        old_snapshot = _product_audit_dict(product)

        product.is_active = False
        await self.db.flush()

        from app.services.audit_service import AuditService, get_client_ip, get_user_agent
        await AuditService(self.db).log(
            user_id=current_user_id,
            action="DELETE_PRODUCT",
            resource_type="PRODUCT",
            resource_id=product_id,
            old_value=old_snapshot,
            new_value={"is_active": False},
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        await self.db.commit()
        logger.info(f"Product soft-deleted: id={product_id}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_or_404_with_relations(self, product_id: uuid.UUID) -> Product:
        result = await self.db.execute(
            select(Product)
            .options(selectinload(Product.category), selectinload(Product.supplier))
            .where(Product.id == product_id)
        )
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found.",
            )
        return product

    async def _assert_sku_unique(
        self, sku: str, exclude_id: uuid.UUID | None = None
    ) -> None:
        q = select(Product).where(func.upper(Product.sku) == sku.upper())
        if exclude_id:
            q = q.where(Product.id != exclude_id)
        if await self.db.scalar(q):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A product with SKU '{sku}' already exists.",
            )

    async def _assert_category_exists(self, category_id: uuid.UUID) -> None:
        if not await self.db.scalar(select(Category).where(Category.id == category_id)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Category {category_id} does not exist.",
            )

    async def _assert_supplier_exists(self, supplier_id: uuid.UUID) -> None:
        if not await self.db.scalar(select(Supplier).where(Supplier.id == supplier_id)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Supplier {supplier_id} does not exist.",
            )


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _product_to_response(p: Product) -> ProductResponse:
    return ProductResponse(
        id=p.id,
        sku=p.sku,
        name=p.name,
        description=p.description,
        category=p.category,
        supplier=p.supplier,
        unit=p.unit,
        reorder_point=p.reorder_point,
        reorder_quantity=p.reorder_quantity,
        max_stock_level=p.max_stock_level,
        expiry_alert_days=p.expiry_alert_days,
        current_stock=p.current_stock,
        last_risk_score=float(p.last_risk_score) if p.last_risk_score is not None else None,
        last_risk_level=p.last_risk_level,
        is_active=p.is_active,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _product_list_response(p: Product) -> ProductListResponse:
    return ProductListResponse(
        id=p.id,
        sku=p.sku,
        name=p.name,
        unit=p.unit,
        category_id=p.category_id,
        category_name=p.category.name if p.category else "",
        supplier_id=p.supplier_id,
        supplier_name=p.supplier.name if p.supplier else None,
        reorder_point=p.reorder_point,
        max_stock_level=p.max_stock_level,
        current_stock=p.current_stock,
        last_risk_score=float(p.last_risk_score) if p.last_risk_score is not None else None,
        last_risk_level=p.last_risk_level,
        is_active=p.is_active,
    )


def _product_audit_dict(p: Product) -> dict:
    """Compact dict for old_value/new_value JSONB storage."""
    return {
        "sku": p.sku,
        "name": p.name,
        "category_id": str(p.category_id),
        "supplier_id": str(p.supplier_id) if p.supplier_id else None,
        "unit": p.unit,
        "reorder_point": p.reorder_point,
        "reorder_quantity": p.reorder_quantity,
        "max_stock_level": p.max_stock_level,
        "expiry_alert_days": p.expiry_alert_days,
        "is_active": p.is_active,
    }
