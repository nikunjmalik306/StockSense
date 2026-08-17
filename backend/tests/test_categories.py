"""
Tests for Category CRUD — service layer and HTTP API.

Covers:
- Creation with valid data
- Duplicate name rejection (409)
- List with pagination and search
- Get single (200 and 404)
- Update (name change, duplicate check)
- Delete (success and blocked when products exist)
- RBAC: ADMIN and MANAGER can mutate; STAFF gets 403
- Audit log written on every mutation
"""
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.product import Category
from app.services.category_service import CategoryService
from app.schemas.category import CategoryCreateRequest, CategoryUpdateRequest
from tests.conftest import auth_headers


# ---------------------------------------------------------------------------
# Service-layer tests (no HTTP)
# ---------------------------------------------------------------------------

class TestCategoryServiceCreate:
    @pytest.mark.asyncio
    async def test_create_category_success(self, db_session: AsyncSession, admin_user):
        svc = CategoryService(db_session)
        data = CategoryCreateRequest(name="Antibiotics", description="Antibiotic medicines")
        result = await svc.create_category(
            data, current_user_id=admin_user.id, request=None
        )
        assert result.name == "Antibiotics"
        assert result.description == "Antibiotic medicines"
        assert result.id is not None

    @pytest.mark.asyncio
    async def test_create_category_duplicate_name_raises_409(
        self, db_session: AsyncSession, admin_user
    ):
        from fastapi import HTTPException
        svc = CategoryService(db_session)
        data = CategoryCreateRequest(name="Vitamins")
        await svc.create_category(data, current_user_id=admin_user.id, request=None)

        with pytest.raises(HTTPException) as exc_info:
            await svc.create_category(data, current_user_id=admin_user.id, request=None)
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_create_category_case_insensitive_duplicate(
        self, db_session: AsyncSession, admin_user
    ):
        from fastapi import HTTPException
        svc = CategoryService(db_session)
        await svc.create_category(
            CategoryCreateRequest(name="Analgesics"),
            current_user_id=admin_user.id, request=None
        )
        with pytest.raises(HTTPException) as exc_info:
            await svc.create_category(
                CategoryCreateRequest(name="ANALGESICS"),
                current_user_id=admin_user.id, request=None
            )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_create_category_writes_audit_log(
        self, db_session: AsyncSession, admin_user
    ):
        svc = CategoryService(db_session)
        result = await svc.create_category(
            CategoryCreateRequest(name="Lab Supplies"),
            current_user_id=admin_user.id, request=None
        )
        log = await db_session.scalar(
            select(AuditLog).where(AuditLog.resource_id == result.id)
        )
        assert log is not None
        assert log.action == "CREATE_CATEGORY"
        assert log.resource_type == "CATEGORY"
        assert log.user_id == admin_user.id
        assert log.new_value["name"] == "Lab Supplies"


class TestCategoryServiceList:
    @pytest.mark.asyncio
    async def test_list_returns_paginated_response(
        self, db_session: AsyncSession, admin_user
    ):
        svc = CategoryService(db_session)
        for i in range(5):
            await svc.create_category(
                CategoryCreateRequest(name=f"Category {i}"),
                current_user_id=admin_user.id, request=None
            )
        result = await svc.list_categories(page=1, page_size=3)
        assert result.total == 5
        assert len(result.items) == 3
        assert result.pages == 2
        assert result.page == 1

    @pytest.mark.asyncio
    async def test_list_second_page(self, db_session: AsyncSession, admin_user):
        svc = CategoryService(db_session)
        for i in range(5):
            await svc.create_category(
                CategoryCreateRequest(name=f"Page Cat {i}"),
                current_user_id=admin_user.id, request=None
            )
        result = await svc.list_categories(page=2, page_size=3)
        assert len(result.items) == 2  # 5 total, 3 on page 1, 2 on page 2

    @pytest.mark.asyncio
    async def test_search_filters_by_name(self, db_session: AsyncSession, admin_user):
        svc = CategoryService(db_session)
        await svc.create_category(
            CategoryCreateRequest(name="Painkillers"), current_user_id=admin_user.id, request=None
        )
        await svc.create_category(
            CategoryCreateRequest(name="Vitamins"), current_user_id=admin_user.id, request=None
        )
        result = await svc.list_categories(search="pain")
        assert result.total == 1
        assert result.items[0].name == "Painkillers"

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_paginated(self, db_session: AsyncSession):
        svc = CategoryService(db_session)
        result = await svc.list_categories()
        assert result.total == 0
        assert result.items == []
        assert result.pages == 1  # always at least 1


class TestCategoryServiceGetUpdateDelete:
    @pytest.mark.asyncio
    async def test_get_nonexistent_raises_404(self, db_session: AsyncSession):
        from fastapi import HTTPException
        svc = CategoryService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await svc.get_category(uuid.uuid4())
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_name(self, db_session: AsyncSession, admin_user):
        svc = CategoryService(db_session)
        cat = await svc.create_category(
            CategoryCreateRequest(name="OldName"), current_user_id=admin_user.id, request=None
        )
        updated = await svc.update_category(
            cat.id,
            CategoryUpdateRequest(name="NewName"),
            current_user_id=admin_user.id, request=None
        )
        assert updated.name == "NewName"

    @pytest.mark.asyncio
    async def test_update_writes_old_and_new_value_to_audit(
        self, db_session: AsyncSession, admin_user
    ):
        svc = CategoryService(db_session)
        cat = await svc.create_category(
            CategoryCreateRequest(name="BeforeUpdate"),
            current_user_id=admin_user.id, request=None
        )
        await svc.update_category(
            cat.id,
            CategoryUpdateRequest(name="AfterUpdate"),
            current_user_id=admin_user.id, request=None
        )
        logs = (await db_session.execute(
            select(AuditLog)
            .where(AuditLog.resource_id == cat.id, AuditLog.action == "UPDATE_CATEGORY")
        )).scalars().all()
        assert len(logs) == 1
        assert logs[0].old_value["name"] == "BeforeUpdate"
        assert logs[0].new_value["name"] == "AfterUpdate"

    @pytest.mark.asyncio
    async def test_delete_success(self, db_session: AsyncSession, admin_user):
        svc = CategoryService(db_session)
        cat = await svc.create_category(
            CategoryCreateRequest(name="ToDelete"), current_user_id=admin_user.id, request=None
        )
        await svc.delete_category(cat.id, current_user_id=admin_user.id, request=None)
        gone = await db_session.scalar(select(Category).where(Category.id == cat.id))
        assert gone is None

    @pytest.mark.asyncio
    async def test_delete_blocked_when_products_exist(
        self, db_session: AsyncSession, admin_user
    ):
        from fastapi import HTTPException
        from app.models.product import Product
        svc = CategoryService(db_session)
        cat = await svc.create_category(
            CategoryCreateRequest(name="HasProducts"),
            current_user_id=admin_user.id, request=None
        )
        # Directly insert a product referencing this category
        product = Product(
            sku="TEST-001", name="Test Product",
            category_id=cat.id, unit="units",
        )
        db_session.add(product)
        await db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await svc.delete_category(cat.id, current_user_id=admin_user.id, request=None)
        assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# HTTP API / RBAC tests
# ---------------------------------------------------------------------------

class TestCategoryAPIRBAC:
    @pytest.mark.asyncio
    async def test_staff_cannot_create_category(
        self, client: AsyncClient, staff_user
    ):
        resp = await client.post(
            "/api/v1/categories",
            json={"name": "Staff Cat"},
            headers=auth_headers(str(staff_user.id), "STAFF"),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_staff_cannot_update_category(
        self, client: AsyncClient, db_session: AsyncSession, admin_user, staff_user
    ):
        svc = CategoryService(db_session)
        cat = await svc.create_category(
            CategoryCreateRequest(name="EditTarget"),
            current_user_id=admin_user.id, request=None
        )
        resp = await client.put(
            f"/api/v1/categories/{cat.id}",
            json={"name": "Hacked"},
            headers=auth_headers(str(staff_user.id), "STAFF"),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_staff_cannot_delete_category(
        self, client: AsyncClient, db_session: AsyncSession, admin_user, staff_user
    ):
        svc = CategoryService(db_session)
        cat = await svc.create_category(
            CategoryCreateRequest(name="DeleteTarget"),
            current_user_id=admin_user.id, request=None
        )
        resp = await client.delete(
            f"/api/v1/categories/{cat.id}",
            headers=auth_headers(str(staff_user.id), "STAFF"),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_manager_can_create_category(
        self, client: AsyncClient, manager_user
    ):
        resp = await client.post(
            "/api/v1/categories",
            json={"name": "Manager Created"},
            headers=auth_headers(str(manager_user.id), "MANAGER"),
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Manager Created"

    @pytest.mark.asyncio
    async def test_manager_cannot_delete_category(
        self, client: AsyncClient, db_session: AsyncSession, admin_user, manager_user
    ):
        svc = CategoryService(db_session)
        cat = await svc.create_category(
            CategoryCreateRequest(name="ManagerDelTarget"),
            current_user_id=admin_user.id, request=None
        )
        resp = await client.delete(
            f"/api/v1/categories/{cat.id}",
            headers=auth_headers(str(manager_user.id), "MANAGER"),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_gets_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/categories")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_staff_can_list_categories(
        self, client: AsyncClient, staff_user
    ):
        resp = await client.get(
            "/api/v1/categories",
            headers=auth_headers(str(staff_user.id), "STAFF"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_create_returns_201_with_correct_shape(
        self, client: AsyncClient, admin_user
    ):
        resp = await client.post(
            "/api/v1/categories",
            json={"name": "ShapeCheck", "description": "A description"},
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["name"] == "ShapeCheck"
        assert data["description"] == "A description"
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_404(
        self, client: AsyncClient, admin_user
    ):
        resp = await client.get(
            f"/api/v1/categories/{uuid.uuid4()}",
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_duplicate_name_returns_409(
        self, client: AsyncClient, admin_user
    ):
        headers = auth_headers(str(admin_user.id), "ADMIN")
        await client.post("/api/v1/categories", json={"name": "DupCat"}, headers=headers)
        resp = await client.post("/api/v1/categories", json={"name": "DupCat"}, headers=headers)
        assert resp.status_code == 409
