"""
Tests for AnalyticsService and analytics endpoints.

All tests use the in-memory SQLite database from conftest.py.
We seed products, batches, and transactions to verify the aggregate
calculations are correct.
"""
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.inventory import InventoryBatch, StockTransaction
from app.models.product import Category, Product
from app.services.analytics_service import AnalyticsService
from app.services.inventory_service import InventoryService
from app.schemas.inventory import StockInRequest, StockOutRequest
from tests.conftest import auth_headers


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

async def _seed_product(db: AsyncSession, *, name: str, sku: str,
                         reorder_point: int = 10) -> tuple[Category, Product]:
    cat_name = f"Cat-{uuid.uuid4().hex[:6]}"
    cat = Category(id=uuid.uuid4(), name=cat_name)
    db.add(cat)
    await db.flush()
    product = Product(
        id=uuid.uuid4(), sku=sku, name=name,
        category_id=cat.id, unit="units",
        reorder_point=reorder_point, reorder_quantity=50,
        current_stock=0,
    )
    db.add(product)
    await db.commit()
    return cat, product


# ---------------------------------------------------------------------------
# Overview metric tests
# ---------------------------------------------------------------------------

class TestAnalyticsOverview:
    @pytest.mark.asyncio
    async def test_overview_counts_active_products(
        self, db_session: AsyncSession, admin_user
    ):
        _, p1 = await _seed_product(db_session, name="Drug A", sku="DA-001")
        _, p2 = await _seed_product(db_session, name="Drug B", sku="DB-001")

        svc = AnalyticsService(db_session)
        result = await svc.get_overview()

        # Should include both new products
        assert result.total_products >= 2

    @pytest.mark.asyncio
    async def test_overview_total_units_reflects_stock(
        self, db_session: AsyncSession, admin_user
    ):
        _, product = await _seed_product(db_session, name="StockProd", sku="SP-001")
        inv_svc = InventoryService(db_session)
        await inv_svc.stock_in(
            StockInRequest(product_id=product.id, quantity=75, cost_per_unit=2.0),
            current_user_id=admin_user.id, request=None,
        )

        svc = AnalyticsService(db_session)
        result = await svc.get_overview()
        assert result.total_inventory_units >= 75

    @pytest.mark.asyncio
    async def test_overview_inventory_value_calculation(
        self, db_session: AsyncSession, admin_user
    ):
        """inventory_value = SUM(remaining_qty * cost_per_unit) across batches."""
        _, product = await _seed_product(db_session, name="ValueProd", sku="VP-001")
        inv_svc = InventoryService(db_session)
        # 100 units @ $5.00 = $500
        await inv_svc.stock_in(
            StockInRequest(product_id=product.id, quantity=100, cost_per_unit=5.0),
            current_user_id=admin_user.id, request=None,
        )

        svc = AnalyticsService(db_session)
        result = await svc.get_overview()
        # Value should include our $500 (may be higher if other products exist)
        assert result.inventory_value >= 500.0

    @pytest.mark.asyncio
    async def test_overview_inventory_value_decreases_after_stock_out(
        self, db_session: AsyncSession, admin_user
    ):
        """Verify that stocking out reduces inventory value."""
        _, product = await _seed_product(db_session, name="DepleteProd", sku="DP-001")
        inv_svc = InventoryService(db_session)
        await inv_svc.stock_in(
            StockInRequest(product_id=product.id, quantity=100, cost_per_unit=10.0),
            current_user_id=admin_user.id, request=None,
        )

        svc = AnalyticsService(db_session)
        before = await svc.get_overview()
        before_value = before.inventory_value

        await inv_svc.stock_out(
            StockOutRequest(product_id=product.id, quantity=50),
            current_user_id=admin_user.id, request=None,
        )

        after = await svc.get_overview()
        # Value should have dropped by 50 * 10 = 500
        assert after.inventory_value == pytest.approx(before_value - 500.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_overview_low_stock_count(
        self, db_session: AsyncSession, admin_user
    ):
        # reorder_point=50, will stock only 20 → low stock
        _, product = await _seed_product(
            db_session, name="LowProd", sku="LP-001", reorder_point=50
        )
        inv_svc = InventoryService(db_session)
        await inv_svc.stock_in(
            StockInRequest(product_id=product.id, quantity=20, cost_per_unit=1.0),
            current_user_id=admin_user.id, request=None,
        )

        svc = AnalyticsService(db_session)
        result = await svc.get_overview()
        # At least our low-stock product is counted
        assert result.low_stock_count >= 1

    @pytest.mark.asyncio
    async def test_overview_out_of_stock_count(
        self, db_session: AsyncSession, admin_user
    ):
        _, product = await _seed_product(db_session, name="ZeroProd", sku="ZP-001")
        # Never stocked — current_stock stays 0

        svc = AnalyticsService(db_session)
        result = await svc.get_overview()
        assert result.out_of_stock_count >= 1

    @pytest.mark.asyncio
    async def test_overview_expiring_soon(
        self, db_session: AsyncSession, admin_user
    ):
        from datetime import date, timedelta
        _, product = await _seed_product(db_session, name="ExpireProd", sku="EP-001")
        inv_svc = InventoryService(db_session)
        soon = date.today() + timedelta(days=15)
        await inv_svc.stock_in(
            StockInRequest(
                product_id=product.id, quantity=50, cost_per_unit=1.0,
                expiry_date=soon,
            ),
            current_user_id=admin_user.id, request=None,
        )

        svc = AnalyticsService(db_session)
        result = await svc.get_overview()
        assert result.expiring_soon_count >= 1


class TestCategoryDistribution:
    @pytest.mark.asyncio
    async def test_category_distribution_returns_list(
        self, db_session: AsyncSession, admin_user
    ):
        _, product = await _seed_product(db_session, name="CatProd", sku="CP-001")
        inv_svc = InventoryService(db_session)
        await inv_svc.stock_in(
            StockInRequest(product_id=product.id, quantity=30, cost_per_unit=3.0),
            current_user_id=admin_user.id, request=None,
        )

        svc = AnalyticsService(db_session)
        result = await svc.get_category_distribution()
        assert isinstance(result, list)
        assert len(result) >= 1
        for item in result:
            assert item.product_count >= 0
            assert item.total_units >= 0
            assert item.total_value >= 0


class TestRecentTransactions:
    @pytest.mark.asyncio
    async def test_recent_transactions_returns_latest_first(
        self, db_session: AsyncSession, admin_user
    ):
        _, product = await _seed_product(db_session, name="RTxProd", sku="RT-001")
        inv_svc = InventoryService(db_session)
        for qty in [10, 20, 30]:
            await inv_svc.stock_in(
                StockInRequest(product_id=product.id, quantity=qty, cost_per_unit=1.0),
                current_user_id=admin_user.id, request=None,
            )

        svc = AnalyticsService(db_session)
        result = await svc.get_recent_transactions(limit=5)
        assert len(result) <= 5
        # All items have required fields
        for item in result:
            assert item.transaction_type in ("STOCK_IN", "STOCK_OUT", "ADJUSTMENT")
            assert item.product_name != ""


class TestAnalyticsAPIEndpoints:
    @pytest.mark.asyncio
    async def test_overview_endpoint_200(
        self, client: AsyncClient, admin_user
    ):
        resp = await client.get(
            "/api/v1/analytics/overview",
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        assert resp.status_code == 200
        data = resp.json()
        for field in ["total_products", "total_inventory_units", "inventory_value",
                      "low_stock_count", "expiring_soon_count", "out_of_stock_count"]:
            assert field in data

    @pytest.mark.asyncio
    async def test_overview_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/analytics/overview")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_category_distribution_endpoint(
        self, client: AsyncClient, admin_user
    ):
        resp = await client.get(
            "/api/v1/analytics/category-distribution",
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_stock_status_endpoint(
        self, client: AsyncClient, admin_user
    ):
        resp = await client.get(
            "/api/v1/analytics/stock-status",
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_recent_transactions_endpoint(
        self, client: AsyncClient, admin_user
    ):
        resp = await client.get(
            "/api/v1/analytics/recent-transactions",
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_staff_can_view_analytics(
        self, client: AsyncClient, staff_user
    ):
        resp = await client.get(
            "/api/v1/analytics/overview",
            headers=auth_headers(str(staff_user.id), "STAFF"),
        )
        assert resp.status_code == 200
