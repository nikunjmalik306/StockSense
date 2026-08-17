"""
SupplierService — CRUD for product suppliers.

RBAC:
  list / get  → any authenticated user
  create      → ADMIN, MANAGER
  update      → ADMIN, MANAGER
  delete      → ADMIN only (blocked if supplier has products)
"""
import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Supplier, Product
from app.schemas.supplier import (
    SupplierCreateRequest,
    SupplierUpdateRequest,
    SupplierResponse,
    SupplierWithProductCountResponse,
)
from app.schemas.common import PaginatedResponse

logger = logging.getLogger("stocksense.suppliers")


class SupplierService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    async def list_suppliers(
        self,
        *,
        search: str | None = None,
        is_active: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[SupplierWithProductCountResponse]:
        base_q = select(Supplier)

        if search:
            term = f"%{search.lower()}%"
            base_q = base_q.where(
                func.lower(Supplier.name).like(term)
                | func.lower(Supplier.contact_name).like(term)
            )
        if is_active is not None:
            base_q = base_q.where(Supplier.is_active.is_(is_active))

        total: int = await self.db.scalar(
            select(func.count()).select_from(base_q.subquery())
        ) or 0

        offset = (page - 1) * page_size
        result = await self.db.execute(
            base_q.order_by(Supplier.name).offset(offset).limit(page_size)
        )
        suppliers = result.scalars().all()

        sup_ids = [s.id for s in suppliers]
        counts: dict[uuid.UUID, int] = {}
        if sup_ids:
            cnt_result = await self.db.execute(
                select(Product.supplier_id, func.count(Product.id))
                .where(Product.supplier_id.in_(sup_ids), Product.is_active.is_(True))
                .group_by(Product.supplier_id)
            )
            counts = {row[0]: row[1] for row in cnt_result.all()}

        items = [
            SupplierWithProductCountResponse(
                **_supplier_dict(s),
                product_count=counts.get(s.id, 0),
            )
            for s in suppliers
        ]

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

    async def get_supplier(self, supplier_id: uuid.UUID) -> SupplierWithProductCountResponse:
        supplier = await self._get_or_404(supplier_id)
        count = await self.db.scalar(
            select(func.count(Product.id))
            .where(Product.supplier_id == supplier_id, Product.is_active.is_(True))
        ) or 0
        return SupplierWithProductCountResponse(**_supplier_dict(supplier), product_count=count)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_supplier(
        self,
        data: SupplierCreateRequest,
        *,
        current_user_id: uuid.UUID,
        request: object,
    ) -> SupplierResponse:
        await self._assert_name_unique(data.name)

        supplier = Supplier(
            name=data.name,
            contact_name=data.contact_name,
            email=data.email,
            phone=data.phone,
            address=data.address,
            lead_time_days=data.lead_time_days,
        )
        self.db.add(supplier)
        await self.db.flush()

        from app.services.audit_service import AuditService, get_client_ip, get_user_agent
        await AuditService(self.db).log(
            user_id=current_user_id,
            action="CREATE_SUPPLIER",
            resource_type="SUPPLIER",
            resource_id=supplier.id,
            new_value=_supplier_audit_dict(supplier),
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        await self.db.commit()
        await self.db.refresh(supplier)
        logger.info(f"Supplier created: {supplier.name} (id={supplier.id})")
        return SupplierResponse(**_supplier_dict(supplier))

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_supplier(
        self,
        supplier_id: uuid.UUID,
        data: SupplierUpdateRequest,
        *,
        current_user_id: uuid.UUID,
        request: object,
    ) -> SupplierResponse:
        supplier = await self._get_or_404(supplier_id)
        old_snapshot = _supplier_audit_dict(supplier)

        if data.name is not None and data.name != supplier.name:
            await self._assert_name_unique(data.name, exclude_id=supplier_id)
            supplier.name = data.name
        if data.contact_name is not None:
            supplier.contact_name = data.contact_name
        if data.email is not None:
            supplier.email = data.email
        if data.phone is not None:
            supplier.phone = data.phone
        if data.address is not None:
            supplier.address = data.address
        if data.lead_time_days is not None:
            supplier.lead_time_days = data.lead_time_days
        if data.is_active is not None:
            supplier.is_active = data.is_active

        await self.db.flush()

        from app.services.audit_service import AuditService, get_client_ip, get_user_agent
        await AuditService(self.db).log(
            user_id=current_user_id,
            action="UPDATE_SUPPLIER",
            resource_type="SUPPLIER",
            resource_id=supplier_id,
            old_value=old_snapshot,
            new_value=_supplier_audit_dict(supplier),
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        await self.db.commit()
        await self.db.refresh(supplier)
        logger.info(f"Supplier updated: id={supplier_id}")
        return SupplierResponse(**_supplier_dict(supplier))

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_supplier(
        self,
        supplier_id: uuid.UUID,
        *,
        current_user_id: uuid.UUID,
        request: object,
    ) -> None:
        supplier = await self._get_or_404(supplier_id)

        product_count = await self.db.scalar(
            select(func.count(Product.id)).where(Product.supplier_id == supplier_id)
        ) or 0
        if product_count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot delete supplier '{supplier.name}': "
                    f"{product_count} product(s) reference it. "
                    "Reassign products first."
                ),
            )

        old_snapshot = _supplier_audit_dict(supplier)
        await self.db.delete(supplier)
        await self.db.flush()

        from app.services.audit_service import AuditService, get_client_ip, get_user_agent
        await AuditService(self.db).log(
            user_id=current_user_id,
            action="DELETE_SUPPLIER",
            resource_type="SUPPLIER",
            resource_id=supplier_id,
            old_value=old_snapshot,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        await self.db.commit()
        logger.info(f"Supplier deleted: id={supplier_id}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_or_404(self, supplier_id: uuid.UUID) -> Supplier:
        supplier = await self.db.scalar(
            select(Supplier).where(Supplier.id == supplier_id)
        )
        if not supplier:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Supplier {supplier_id} not found.",
            )
        return supplier

    async def _assert_name_unique(
        self, name: str, exclude_id: uuid.UUID | None = None
    ) -> None:
        q = select(Supplier).where(func.lower(Supplier.name) == name.lower())
        if exclude_id:
            q = q.where(Supplier.id != exclude_id)
        if await self.db.scalar(q):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A supplier named '{name}' already exists.",
            )


# ---------------------------------------------------------------------------
# Response helper — converts ORM object to plain dict for Pydantic
# ---------------------------------------------------------------------------

def _supplier_dict(s: Supplier) -> dict:
    """For building SupplierResponse (keeps native types for Pydantic)."""
    return {
        "id": s.id,
        "name": s.name,
        "contact_name": s.contact_name,
        "email": s.email,
        "phone": s.phone,
        "address": s.address,
        "lead_time_days": s.lead_time_days,
        "is_active": s.is_active,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


def _supplier_audit_dict(s: Supplier) -> dict:
    """JSON-safe dict for AuditLog old_value/new_value (no UUID or datetime objects)."""
    return {
        "name": s.name,
        "contact_name": s.contact_name,
        "email": s.email,
        "phone": s.phone,
        "lead_time_days": s.lead_time_days,
        "is_active": s.is_active,
    }
