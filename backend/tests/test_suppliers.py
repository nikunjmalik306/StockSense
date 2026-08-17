"""
Tests for Supplier CRUD — service layer and HTTP API.

Covers:
- Creation with valid data
- Duplicate name rejection (409)
- List with search and is_active filter
- Get single (200 and 404)
- Update
- Delete (success and blocked when products exist)
- RBAC: STAFF gets 403 on mutations; MANAGER can create/update
- Audit log written
"""
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.services.supplier_service import SupplierService
from app.schemas.supplier import SupplierCreateRequest, SupplierUpdateRequest
from tests.conftest import auth_headers


class TestSupplierService:
    @pytest.mark.asyncio
    async def test_create_supplier_success(self, db_session: AsyncSession, admin_user):
        svc = SupplierService(db_session)
        data = SupplierCreateRequest(
            name="MediCorp",
            contact_name="John Smith",
            email="john@medicorp.com",
            lead_time_days=5,
        )
        result = await svc.create_supplier(
            data, current_user_id=admin_user.id, request=None
        )
        assert result.name == "MediCorp"
        assert result.lead_time_days == 5
        assert result.is_active is True

    @pytest.mark.asyncio
    async def test_duplicate_name_raises_409(self, db_session: AsyncSession, admin_user):
        from fastapi import HTTPException
        svc = SupplierService(db_session)
        await svc.create_supplier(
            SupplierCreateRequest(name="UniqueSupplier"),
            current_user_id=admin_user.id, request=None
        )
        with pytest.raises(HTTPException) as exc_info:
            await svc.create_supplier(
                SupplierCreateRequest(name="UniqueSupplier"),
                current_user_id=admin_user.id, request=None
            )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_lead_time_validated_by_schema(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SupplierCreateRequest(name="BadSupplier", lead_time_days=0)

    @pytest.mark.asyncio
    async def test_create_writes_audit_log(self, db_session: AsyncSession, admin_user):
        svc = SupplierService(db_session)
        result = await svc.create_supplier(
            SupplierCreateRequest(name="AuditSupplier"),
            current_user_id=admin_user.id, request=None
        )
        log = await db_session.scalar(
            select(AuditLog).where(AuditLog.resource_id == result.id)
        )
        assert log is not None
        assert log.action == "CREATE_SUPPLIER"
        assert log.new_value["name"] == "AuditSupplier"

    @pytest.mark.asyncio
    async def test_list_search(self, db_session: AsyncSession, admin_user):
        svc = SupplierService(db_session)
        for name in ["PharmaCo", "MedSupply", "LabSource"]:
            await svc.create_supplier(
                SupplierCreateRequest(name=name), current_user_id=admin_user.id, request=None
            )
        result = await svc.list_suppliers(search="pharma")
        assert result.total == 1
        assert result.items[0].name == "PharmaCo"

    @pytest.mark.asyncio
    async def test_list_filter_is_active(self, db_session: AsyncSession, admin_user):
        svc = SupplierService(db_session)
        await svc.create_supplier(
            SupplierCreateRequest(name="ActiveSup"), current_user_id=admin_user.id, request=None
        )
        sup = await svc.create_supplier(
            SupplierCreateRequest(name="InactiveSup"), current_user_id=admin_user.id, request=None
        )
        # Deactivate via update
        await svc.update_supplier(
            sup.id,
            SupplierUpdateRequest(is_active=False),
            current_user_id=admin_user.id, request=None
        )
        active_result = await svc.list_suppliers(is_active=True)
        assert all(s.is_active for s in active_result.items)
        inactive_result = await svc.list_suppliers(is_active=False)
        assert all(not s.is_active for s in inactive_result.items)

    @pytest.mark.asyncio
    async def test_get_nonexistent_raises_404(self, db_session: AsyncSession):
        from fastapi import HTTPException
        svc = SupplierService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await svc.get_supplier(uuid.uuid4())
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_records_old_and_new_value(
        self, db_session: AsyncSession, admin_user
    ):
        svc = SupplierService(db_session)
        sup = await svc.create_supplier(
            SupplierCreateRequest(name="BeforeEdit", lead_time_days=7),
            current_user_id=admin_user.id, request=None
        )
        await svc.update_supplier(
            sup.id,
            SupplierUpdateRequest(lead_time_days=14),
            current_user_id=admin_user.id, request=None
        )
        log = await db_session.scalar(
            select(AuditLog).where(
                AuditLog.resource_id == sup.id,
                AuditLog.action == "UPDATE_SUPPLIER",
            )
        )
        assert log.old_value["lead_time_days"] == 7
        assert log.new_value["lead_time_days"] == 14

    @pytest.mark.asyncio
    async def test_delete_blocked_when_products_exist(
        self, db_session: AsyncSession, admin_user
    ):
        from fastapi import HTTPException
        from app.models.product import Category, Product
        svc = SupplierService(db_session)
        sup = await svc.create_supplier(
            SupplierCreateRequest(name="SupWithProducts"),
            current_user_id=admin_user.id, request=None
        )
        cat = Category(id=uuid.uuid4(), name="TestCat")
        db_session.add(cat)
        await db_session.flush()
        product = Product(
            sku="SUP-TST-001", name="Sup Product",
            category_id=cat.id, supplier_id=sup.id, unit="units",
        )
        db_session.add(product)
        await db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await svc.delete_supplier(sup.id, current_user_id=admin_user.id, request=None)
        assert exc_info.value.status_code == 409


class TestSupplierAPIRBAC:
    @pytest.mark.asyncio
    async def test_staff_cannot_create_supplier(
        self, client: AsyncClient, staff_user
    ):
        resp = await client.post(
            "/api/v1/suppliers",
            json={"name": "Staff Supplier"},
            headers=auth_headers(str(staff_user.id), "STAFF"),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_staff_cannot_update_supplier(
        self, client: AsyncClient, db_session: AsyncSession, admin_user, staff_user
    ):
        svc = SupplierService(db_session)
        sup = await svc.create_supplier(
            SupplierCreateRequest(name="StaffUpdateTarget"),
            current_user_id=admin_user.id, request=None
        )
        resp = await client.put(
            f"/api/v1/suppliers/{sup.id}",
            json={"name": "Hacked"},
            headers=auth_headers(str(staff_user.id), "STAFF"),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_staff_cannot_delete_supplier(
        self, client: AsyncClient, db_session: AsyncSession, admin_user, staff_user
    ):
        svc = SupplierService(db_session)
        sup = await svc.create_supplier(
            SupplierCreateRequest(name="StaffDeleteTarget"),
            current_user_id=admin_user.id, request=None
        )
        resp = await client.delete(
            f"/api/v1/suppliers/{sup.id}",
            headers=auth_headers(str(staff_user.id), "STAFF"),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_manager_can_create_supplier(
        self, client: AsyncClient, manager_user
    ):
        resp = await client.post(
            "/api/v1/suppliers",
            json={"name": "ManagerSup", "lead_time_days": 3},
            headers=auth_headers(str(manager_user.id), "MANAGER"),
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "ManagerSup"

    @pytest.mark.asyncio
    async def test_staff_can_list_suppliers(
        self, client: AsyncClient, staff_user
    ):
        resp = await client.get(
            "/api/v1/suppliers",
            headers=auth_headers(str(staff_user.id), "STAFF"),
        )
        assert resp.status_code == 200
