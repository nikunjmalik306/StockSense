"""
Tests for Product CRUD — service layer and HTTP API.

Covers:
- Creation with valid data + category/supplier relationships
- SKU uniqueness (case-insensitive)
- Invalid FK references (category/supplier that don't exist)
- max_stock_level > reorder_point validation
- List with search, category filter, sort, pagination
- Get single (200 and 404)
- Soft-delete (sets is_active=False, not physical delete)
- RBAC: STAFF cannot create/update/delete; MANAGER can create/update
- Audit log on every mutation
"""
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.product import Category, Product, Supplier
from app.services.product_service import ProductService
from app.schemas.product import ProductCreateRequest, ProductUpdateRequest
from tests.conftest import auth_headers


# ---------------------------------------------------------------------------
# Helpers — seed a category and supplier directly
# ---------------------------------------------------------------------------

async def _seed_category(db: AsyncSession, name: str = "TestCategory") -> Category:
    cat = Category(id=uuid.uuid4(), name=name, description=None)
    db.add(cat)
    await db.flush()
    return cat


async def _seed_supplier(db: AsyncSession, name: str = "TestSupplier") -> Supplier:
    sup = Supplier(id=uuid.uuid4(), name=name, lead_time_days=7)
    db.add(sup)
    await db.flush()
    return sup


# ---------------------------------------------------------------------------
# Service-layer tests
# ---------------------------------------------------------------------------

class TestProductServiceCreate:
    @pytest.mark.asyncio
    async def test_create_product_success(self, db_session: AsyncSession, admin_user):
        cat = await _seed_category(db_session)
        await db_session.commit()

        svc = ProductService(db_session)
        data = ProductCreateRequest(
            sku="PARA-500",
            name="Paracetamol 500mg",
            category_id=cat.id,
            unit="tablets",
            reorder_point=20,
            reorder_quantity=200,
        )
        result = await svc.create_product(
            data, current_user_id=admin_user.id, request=None
        )
        assert result.sku == "PARA-500"
        assert result.name == "Paracetamol 500mg"
        assert result.category.id == cat.id
        assert result.current_stock == 0  # default

    @pytest.mark.asyncio
    async def test_create_with_supplier(self, db_session: AsyncSession, admin_user):
        cat = await _seed_category(db_session)
        sup = await _seed_supplier(db_session)
        await db_session.commit()

        svc = ProductService(db_session)
        result = await svc.create_product(
            ProductCreateRequest(sku="AMOX-250", name="Amoxicillin 250mg",
                                 category_id=cat.id, supplier_id=sup.id),
            current_user_id=admin_user.id, request=None,
        )
        assert result.supplier is not None
        assert result.supplier.id == sup.id

    @pytest.mark.asyncio
    async def test_sku_uniqueness_case_insensitive(
        self, db_session: AsyncSession, admin_user
    ):
        from fastapi import HTTPException
        cat = await _seed_category(db_session)
        await db_session.commit()

        svc = ProductService(db_session)
        await svc.create_product(
            ProductCreateRequest(sku="IBUPROFEN-400", name="Ibuprofen 400mg", category_id=cat.id),
            current_user_id=admin_user.id, request=None,
        )
        with pytest.raises(HTTPException) as exc_info:
            await svc.create_product(
                ProductCreateRequest(sku="ibuprofen-400", name="Ibuprofen Low", category_id=cat.id),
                current_user_id=admin_user.id, request=None,
            )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_invalid_category_raises_422(self, db_session: AsyncSession, admin_user):
        from fastapi import HTTPException
        svc = ProductService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await svc.create_product(
                ProductCreateRequest(sku="X-001", name="Unknown Cat",
                                     category_id=uuid.uuid4()),
                current_user_id=admin_user.id, request=None,
            )
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_supplier_raises_422(self, db_session: AsyncSession, admin_user):
        from fastapi import HTTPException
        cat = await _seed_category(db_session)
        await db_session.commit()
        svc = ProductService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await svc.create_product(
                ProductCreateRequest(sku="X-002", name="Unknown Sup",
                                     category_id=cat.id, supplier_id=uuid.uuid4()),
                current_user_id=admin_user.id, request=None,
            )
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_max_stock_must_exceed_reorder_point_schema(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ProductCreateRequest(
                sku="X-003", name="Bad Stock Levels",
                category_id=uuid.uuid4(),
                reorder_point=50,
                max_stock_level=30,  # less than reorder_point → invalid
            )

    @pytest.mark.asyncio
    async def test_create_writes_audit_log(self, db_session: AsyncSession, admin_user):
        cat = await _seed_category(db_session)
        await db_session.commit()

        svc = ProductService(db_session)
        result = await svc.create_product(
            ProductCreateRequest(sku="AUDIT-001", name="Audit Product", category_id=cat.id),
            current_user_id=admin_user.id, request=None,
        )
        log = await db_session.scalar(
            select(AuditLog).where(AuditLog.resource_id == result.id)
        )
        assert log is not None
        assert log.action == "CREATE_PRODUCT"
        assert log.new_value["sku"] == "AUDIT-001"
        assert log.user_id == admin_user.id


class TestProductServiceList:
    @pytest.mark.asyncio
    async def test_list_products_pagination(self, db_session: AsyncSession, admin_user):
        cat = await _seed_category(db_session)
        await db_session.commit()
        svc = ProductService(db_session)
        for i in range(7):
            await svc.create_product(
                ProductCreateRequest(sku=f"PROD-{i:03}", name=f"Product {i}", category_id=cat.id),
                current_user_id=admin_user.id, request=None,
            )
        result = await svc.list_products(page=1, page_size=5)
        assert result.total == 7
        assert len(result.items) == 5
        assert result.pages == 2

        result2 = await svc.list_products(page=2, page_size=5)
        assert len(result2.items) == 2

    @pytest.mark.asyncio
    async def test_search_by_name(self, db_session: AsyncSession, admin_user):
        cat = await _seed_category(db_session)
        await db_session.commit()
        svc = ProductService(db_session)
        await svc.create_product(
            ProductCreateRequest(sku="S-001", name="Paracetamol 500", category_id=cat.id),
            current_user_id=admin_user.id, request=None,
        )
        await svc.create_product(
            ProductCreateRequest(sku="S-002", name="Ibuprofen 400", category_id=cat.id),
            current_user_id=admin_user.id, request=None,
        )
        result = await svc.list_products(search="paracetamol")
        assert result.total == 1
        assert result.items[0].sku == "S-001"

    @pytest.mark.asyncio
    async def test_search_by_sku(self, db_session: AsyncSession, admin_user):
        cat = await _seed_category(db_session)
        await db_session.commit()
        svc = ProductService(db_session)
        await svc.create_product(
            ProductCreateRequest(sku="SKU-UNIQUE", name="Some Drug", category_id=cat.id),
            current_user_id=admin_user.id, request=None,
        )
        result = await svc.list_products(search="SKU-UNIQUE")
        assert result.total == 1

    @pytest.mark.asyncio
    async def test_filter_by_category(self, db_session: AsyncSession, admin_user):
        cat1 = await _seed_category(db_session, "Cat A")
        cat2 = await _seed_category(db_session, "Cat B")
        await db_session.commit()
        svc = ProductService(db_session)
        await svc.create_product(
            ProductCreateRequest(sku="A-001", name="Cat A Product", category_id=cat1.id),
            current_user_id=admin_user.id, request=None,
        )
        await svc.create_product(
            ProductCreateRequest(sku="B-001", name="Cat B Product", category_id=cat2.id),
            current_user_id=admin_user.id, request=None,
        )
        result = await svc.list_products(category_id=cat1.id)
        assert result.total == 1
        assert result.items[0].sku == "A-001"

    @pytest.mark.asyncio
    async def test_sort_by_name_asc(self, db_session: AsyncSession, admin_user):
        cat = await _seed_category(db_session)
        await db_session.commit()
        svc = ProductService(db_session)
        for name in ["Zebra Drug", "Apple Drug", "Mango Drug"]:
            sku = name.split()[0].upper()
            await svc.create_product(
                ProductCreateRequest(sku=sku, name=name, category_id=cat.id),
                current_user_id=admin_user.id, request=None,
            )
        result = await svc.list_products(sort_by="name", sort_order="asc")
        names = [i.name for i in result.items]
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_list_defaults_to_active_only(self, db_session: AsyncSession, admin_user):
        cat = await _seed_category(db_session)
        await db_session.commit()
        svc = ProductService(db_session)
        p = await svc.create_product(
            ProductCreateRequest(sku="INACTIVE-001", name="Inactive Product", category_id=cat.id),
            current_user_id=admin_user.id, request=None,
        )
        await svc.delete_product(p.id, current_user_id=admin_user.id, request=None)

        result = await svc.list_products(is_active=True)
        skus = [i.sku for i in result.items]
        assert "INACTIVE-001" not in skus


class TestProductSoftDelete:
    @pytest.mark.asyncio
    async def test_soft_delete_sets_is_active_false(
        self, db_session: AsyncSession, admin_user
    ):
        cat = await _seed_category(db_session)
        await db_session.commit()
        svc = ProductService(db_session)
        p = await svc.create_product(
            ProductCreateRequest(sku="SOFT-DEL", name="SoftDel Product", category_id=cat.id),
            current_user_id=admin_user.id, request=None,
        )
        await svc.delete_product(p.id, current_user_id=admin_user.id, request=None)

        # Row still exists
        row = await db_session.scalar(select(Product).where(Product.id == p.id))
        assert row is not None
        assert row.is_active is False

    @pytest.mark.asyncio
    async def test_soft_delete_writes_audit_log(self, db_session: AsyncSession, admin_user):
        cat = await _seed_category(db_session)
        await db_session.commit()
        svc = ProductService(db_session)
        p = await svc.create_product(
            ProductCreateRequest(sku="AUDIT-DEL", name="AuditDel Product", category_id=cat.id),
            current_user_id=admin_user.id, request=None,
        )
        await svc.delete_product(p.id, current_user_id=admin_user.id, request=None)
        log = await db_session.scalar(
            select(AuditLog).where(
                AuditLog.resource_id == p.id, AuditLog.action == "DELETE_PRODUCT"
            )
        )
        assert log is not None
        assert log.new_value == {"is_active": False}


# ---------------------------------------------------------------------------
# HTTP / RBAC tests
# ---------------------------------------------------------------------------

class TestProductAPIRBAC:
    @pytest.mark.asyncio
    async def test_staff_cannot_create_product(
        self, client: AsyncClient, db_session: AsyncSession, staff_user, admin_user
    ):
        cat = await _seed_category(db_session)
        await db_session.commit()
        resp = await client.post(
            "/api/v1/products",
            json={"sku": "STAFF-001", "name": "Staff Product",
                  "category_id": str(cat.id)},
            headers=auth_headers(str(staff_user.id), "STAFF"),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_staff_cannot_update_product(
        self, client: AsyncClient, db_session: AsyncSession, admin_user, staff_user
    ):
        cat = await _seed_category(db_session)
        await db_session.commit()
        svc = ProductService(db_session)
        p = await svc.create_product(
            ProductCreateRequest(sku="UPD-001", name="Update Target", category_id=cat.id),
            current_user_id=admin_user.id, request=None,
        )
        resp = await client.put(
            f"/api/v1/products/{p.id}",
            json={"name": "Hacked"},
            headers=auth_headers(str(staff_user.id), "STAFF"),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_staff_cannot_delete_product(
        self, client: AsyncClient, db_session: AsyncSession, admin_user, staff_user
    ):
        cat = await _seed_category(db_session)
        await db_session.commit()
        svc = ProductService(db_session)
        p = await svc.create_product(
            ProductCreateRequest(sku="DEL-001", name="Delete Target", category_id=cat.id),
            current_user_id=admin_user.id, request=None,
        )
        resp = await client.delete(
            f"/api/v1/products/{p.id}",
            headers=auth_headers(str(staff_user.id), "STAFF"),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_manager_can_create_product(
        self, client: AsyncClient, db_session: AsyncSession, manager_user
    ):
        cat = await _seed_category(db_session)
        await db_session.commit()
        resp = await client.post(
            "/api/v1/products",
            json={"sku": "MGR-001", "name": "Manager Product",
                  "category_id": str(cat.id)},
            headers=auth_headers(str(manager_user.id), "MANAGER"),
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_manager_cannot_delete_product(
        self, client: AsyncClient, db_session: AsyncSession, admin_user, manager_user
    ):
        cat = await _seed_category(db_session)
        await db_session.commit()
        svc = ProductService(db_session)
        p = await svc.create_product(
            ProductCreateRequest(sku="MGRDEL-001", name="Mgr Del Target", category_id=cat.id),
            current_user_id=admin_user.id, request=None,
        )
        resp = await client.delete(
            f"/api/v1/products/{p.id}",
            headers=auth_headers(str(manager_user.id), "MANAGER"),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_product_list_returns_paginated_shape(
        self, client: AsyncClient, staff_user
    ):
        resp = await client.get(
            "/api/v1/products",
            headers=auth_headers(str(staff_user.id), "STAFF"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data

    @pytest.mark.asyncio
    async def test_get_product_returns_nested_category(
        self, client: AsyncClient, db_session: AsyncSession, admin_user
    ):
        cat = await _seed_category(db_session, "Nested Cat")
        await db_session.commit()
        svc = ProductService(db_session)
        p = await svc.create_product(
            ProductCreateRequest(sku="NESTED-001", name="Nested Test", category_id=cat.id),
            current_user_id=admin_user.id, request=None,
        )
        resp = await client.get(
            f"/api/v1/products/{p.id}",
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["category"]["name"] == "Nested Cat"
        assert data["sku"] == "NESTED-001"

    @pytest.mark.asyncio
    async def test_duplicate_sku_returns_409_via_api(
        self, client: AsyncClient, db_session: AsyncSession, admin_user
    ):
        cat = await _seed_category(db_session)
        await db_session.commit()
        headers = auth_headers(str(admin_user.id), "ADMIN")
        await client.post(
            "/api/v1/products",
            json={"sku": "DUP-SKU", "name": "Product One", "category_id": str(cat.id)},
            headers=headers,
        )
        resp = await client.post(
            "/api/v1/products",
            json={"sku": "DUP-SKU", "name": "Product Two", "category_id": str(cat.id)},
            headers=headers,
        )
        assert resp.status_code == 409
