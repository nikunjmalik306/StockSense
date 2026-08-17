"""
Tests for the inventory risk engine (RiskService) and Block 5 analytics endpoints.

All tests use in-memory SQLite via conftest.py fixtures.
The risk engine is deterministic and testable without PostgreSQL.

NOTE: SELECT ... FOR UPDATE is silently ignored by SQLite — risk calculations
don't use locking, so this is not a concern here.
"""
import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.inventory import InventoryBatch, StockTransaction
from app.models.product import Category, Product
from app.services.risk_service import RiskService
from app.services.inventory_service import InventoryService
from app.schemas.inventory import StockInRequest, StockOutRequest, AdjustmentRequest
from app.schemas.risk import RiskLevel
from tests.conftest import auth_headers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_product(
    db: AsyncSession, *,
    reorder_point: int = 10,
    max_stock_level: int | None = 500,
    expiry_alert_days: int = 30,
    supplier_lead_days: int | None = None,
) -> Product:
    from app.models.product import Supplier
    cat = Category(id=uuid.uuid4(), name=f"Cat-{uuid.uuid4().hex[:6]}")
    db.add(cat)
    await db.flush()

    supplier = None
    if supplier_lead_days is not None:
        supplier = Supplier(
            id=uuid.uuid4(),
            name=f"Sup-{uuid.uuid4().hex[:6]}",
            lead_time_days=supplier_lead_days,
        )
        db.add(supplier)
        await db.flush()

    p = Product(
        id=uuid.uuid4(),
        sku=f"TST-{uuid.uuid4().hex[:8].upper()}",
        name=f"Test Product {uuid.uuid4().hex[:4]}",
        category_id=cat.id,
        supplier_id=supplier.id if supplier else None,
        unit="units",
        reorder_point=reorder_point,
        reorder_quantity=100,
        max_stock_level=max_stock_level,
        expiry_alert_days=expiry_alert_days,
        current_stock=0,
    )
    db.add(p)
    await db.commit()
    return p


async def _stock_in(
    db: AsyncSession, product: Product, user, *,
    qty: int = 100, cost: float = 5.0, expiry: date | None = None,
) -> None:
    svc = InventoryService(db)
    await svc.stock_in(
        StockInRequest(
            product_id=product.id, quantity=qty,
            cost_per_unit=cost, expiry_date=expiry,
        ),
        current_user_id=user.id, request=None,
    )
    await db.refresh(product)


async def _stock_out(db: AsyncSession, product: Product, user, *, qty: int) -> None:
    svc = InventoryService(db)
    await svc.stock_out(
        StockOutRequest(product_id=product.id, quantity=qty),
        current_user_id=user.id, request=None,
    )
    await db.refresh(product)


async def _add_historical_demand(
    db: AsyncSession, product: Product, user, *,
    daily_qty: int, days: int,
) -> None:
    """Insert STOCK_OUT transactions in the past to simulate demand history."""
    from datetime import datetime, timezone
    for i in range(days):
        txn_at = datetime.now(timezone.utc) - timedelta(days=i + 1)
        t = StockTransaction(
            product_id=product.id,
            transaction_type="STOCK_OUT",
            quantity=-daily_qty,
            performed_by=user.id,
            transaction_at=txn_at,
        )
        db.add(t)
    await db.commit()


# ===========================================================================
# Risk level classification tests
# ===========================================================================

class TestRiskLevelClassification:
    """Verify the _risk_level() helper thresholds."""

    def test_score_0_is_low(self):
        from app.services.risk_service import _risk_level
        assert _risk_level(0) == RiskLevel.LOW

    def test_score_24_is_low(self):
        from app.services.risk_service import _risk_level
        assert _risk_level(24.9) == RiskLevel.LOW

    def test_score_25_is_medium(self):
        from app.services.risk_service import _risk_level
        assert _risk_level(25) == RiskLevel.MEDIUM

    def test_score_49_is_medium(self):
        from app.services.risk_service import _risk_level
        assert _risk_level(49.9) == RiskLevel.MEDIUM

    def test_score_50_is_high(self):
        from app.services.risk_service import _risk_level
        assert _risk_level(50) == RiskLevel.HIGH

    def test_score_74_is_high(self):
        from app.services.risk_service import _risk_level
        assert _risk_level(74.9) == RiskLevel.HIGH

    def test_score_75_is_critical(self):
        from app.services.risk_service import _risk_level
        assert _risk_level(75) == RiskLevel.CRITICAL

    def test_score_100_is_critical(self):
        from app.services.risk_service import _risk_level
        assert _risk_level(100) == RiskLevel.CRITICAL


# ===========================================================================
# Core risk calculation tests
# ===========================================================================

class TestRiskEngineCore:
    @pytest.mark.asyncio
    async def test_zero_stock_is_critical(self, db_session: AsyncSession, admin_user):
        """Product with no stock at all → CRITICAL stockout risk."""
        p = await _make_product(db_session, reorder_point=10)
        # No stock-in — current_stock = 0
        svc = RiskService(db_session)
        result = await svc.calculate_product_risk(p.id)
        assert result.current_stock == 0
        assert result.risk_level == RiskLevel.CRITICAL
        assert result.stockout_risk_score == 100.0

    @pytest.mark.asyncio
    async def test_low_stock_with_demand_is_high_or_critical(
        self, db_session: AsyncSession, admin_user
    ):
        """
        Stock below reorder point with active demand and short supplier lead time
        → HIGH or CRITICAL risk.

        We use lead_time=14 days (long lead time) so days_remaining <= lead_time,
        which pushes the stockout sub-score to 90+ and the composite above 50.
        """
        p = await _make_product(db_session, reorder_point=50, supplier_lead_days=14)
        await _stock_in(db_session, p, admin_user, qty=100)
        # 10 units/day for 30 days via historical transactions
        await _add_historical_demand(db_session, p, admin_user, daily_qty=10, days=30)
        # Stock out to 15 units (below reorder_point=50)
        await _stock_out(db_session, p, admin_user, qty=85)

        svc = RiskService(db_session)
        result = await svc.calculate_product_risk(p.id)
        assert result.current_stock == 15
        assert result.current_stock < result.reorder_point
        # days_remaining = 15/10 = 1.5, lead_time = 14 → stockout score ≈ 97
        # Composite: 97*0.40 + 0*0.35 + small*0.15 + vel*0.10 > 50 → HIGH or CRITICAL
        assert result.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    @pytest.mark.asyncio
    async def test_healthy_product_is_low_risk(
        self, db_session: AsyncSession, admin_user
    ):
        """
        Well-stocked product with low demand → LOW risk.

        Note: _add_historical_demand inserts raw StockTransaction rows without
        updating product.current_stock. We only stock-in here (no stock-out),
        so current_stock stays at 300. avg_daily ≈ 1.0, days_remaining ≈ 300 → LOW.
        """
        p = await _make_product(db_session, reorder_point=10)
        await _stock_in(db_session, p, admin_user, qty=300)
        # Very low demand: 1 unit/day in the transaction log
        await _add_historical_demand(db_session, p, admin_user, daily_qty=1, days=30)
        # current_stock stays at 300 (historical txns are raw inserts, not InventoryService)

        svc = RiskService(db_session)
        result = await svc.calculate_product_risk(p.id)
        # days_remaining = 300 / 1.0 = 300 → very low stockout risk
        assert result.current_stock == 300
        assert result.risk_level == RiskLevel.LOW
        assert result.risk_score < 25

    @pytest.mark.asyncio
    async def test_expired_batch_raises_expiry_risk_to_critical(
        self, db_session: AsyncSession, admin_user
    ):
        """Product with an expired batch → expiry sub-score is 100."""
        p = await _make_product(db_session, expiry_alert_days=30)
        expired_date = date.today() - timedelta(days=5)  # already expired
        await _stock_in(db_session, p, admin_user, qty=100,
                        expiry=expired_date)

        svc = RiskService(db_session)
        result = await svc.calculate_product_risk(p.id)
        assert result.expiry_risk_score == 100.0
        assert result.earliest_expiry_date == expired_date

    @pytest.mark.asyncio
    async def test_expiring_soon_raises_expiry_risk(
        self, db_session: AsyncSession, admin_user
    ):
        """Batch expiring within alert window → HIGH expiry risk."""
        p = await _make_product(db_session, expiry_alert_days=30)
        soon = date.today() + timedelta(days=10)  # within 30-day alert
        await _stock_in(db_session, p, admin_user, qty=200, expiry=soon)

        svc = RiskService(db_session)
        result = await svc.calculate_product_risk(p.id)
        assert result.expiry_risk_score >= 60.0  # at least HIGH sub-score
        assert result.earliest_expiry_date == soon

    @pytest.mark.asyncio
    async def test_no_expiry_date_is_zero_expiry_risk(
        self, db_session: AsyncSession, admin_user
    ):
        """Batch without expiry_date → expiry_risk_score == 0."""
        p = await _make_product(db_session)
        await _stock_in(db_session, p, admin_user, qty=100, expiry=None)

        svc = RiskService(db_session)
        result = await svc.calculate_product_risk(p.id)
        assert result.expiry_risk_score == 0.0
        assert result.earliest_expiry_date is None

    @pytest.mark.asyncio
    async def test_overstocked_product_raises_overstock_risk(
        self, db_session: AsyncSession, admin_user
    ):
        """Stock > max_stock_level → overstock sub-score > 50."""
        p = await _make_product(db_session, max_stock_level=100)
        await _stock_in(db_session, p, admin_user, qty=150)  # exceeds max=100

        svc = RiskService(db_session)
        result = await svc.calculate_product_risk(p.id)
        assert result.current_stock == 150
        assert result.overstock_risk_score > 50.0

    @pytest.mark.asyncio
    async def test_zero_demand_product_safe(
        self, db_session: AsyncSession, admin_user
    ):
        """Product with stock but zero consumption — no division by zero."""
        p = await _make_product(db_session)
        await _stock_in(db_session, p, admin_user, qty=100)
        # No STOCK_OUT transactions

        svc = RiskService(db_session)
        result = await svc.calculate_product_risk(p.id)
        assert result.days_of_stock_remaining is None  # undefined, no demand
        assert result.average_daily_demand == 0.0
        assert result.risk_score >= 0
        assert result.risk_score <= 100

    @pytest.mark.asyncio
    async def test_multi_batch_uses_soonest_expiry(
        self, db_session: AsyncSession, admin_user
    ):
        """With multiple batches, earliest expiry date is surfaced."""
        p = await _make_product(db_session, expiry_alert_days=30)
        near = date.today() + timedelta(days=15)
        far  = date.today() + timedelta(days=120)
        await _stock_in(db_session, p, admin_user, qty=50, expiry=far)
        await _stock_in(db_session, p, admin_user, qty=50, expiry=near)

        svc = RiskService(db_session)
        result = await svc.calculate_product_risk(p.id)
        assert result.earliest_expiry_date == near

    @pytest.mark.asyncio
    async def test_days_remaining_calculated_correctly(
        self, db_session: AsyncSession, admin_user
    ):
        """
        days_of_stock_remaining ≈ current_stock / avg_daily_demand.

        _add_historical_demand inserts raw transaction rows without updating
        product.current_stock. current_stock stays at the stock-in quantity.
        avg_daily ≈ 3.0 (90 units / 30 days), days_remaining ≈ 300/3 = 100.
        """
        p = await _make_product(db_session)
        await _stock_in(db_session, p, admin_user, qty=300)
        # 3 units/day for 30 days via raw inserts = 90 total consumed
        await _add_historical_demand(db_session, p, admin_user, daily_qty=3, days=30)
        await db_session.refresh(p)

        svc = RiskService(db_session)
        result = await svc.calculate_product_risk(p.id)
        # current_stock = 300 (unchanged by raw inserts), avg_daily = 3.0
        assert result.average_daily_demand == pytest.approx(3.0, abs=0.2)
        assert result.days_of_stock_remaining is not None
        # days_remaining = 300 / 3.0 = 100 days
        assert 90 < result.days_of_stock_remaining < 110

    @pytest.mark.asyncio
    async def test_increasing_demand_velocity_boosts_stockout_risk(
        self, db_session: AsyncSession, admin_user
    ):
        """Recent demand 2× historical → demand_velocity_trend is 'increasing'."""
        p = await _make_product(db_session)
        await _stock_in(db_session, p, admin_user, qty=300)
        # Historical: 2/day for 23 days
        await _add_historical_demand(db_session, p, admin_user, daily_qty=2, days=23)
        # Recent (last 7 days): 6/day
        await _add_historical_demand(db_session, p, admin_user, daily_qty=6, days=7)
        await db_session.refresh(p)

        svc = RiskService(db_session)
        result = await svc.calculate_product_risk(p.id)
        assert result.demand_velocity_trend == "increasing"

    @pytest.mark.asyncio
    async def test_contributing_factors_always_returned(
        self, db_session: AsyncSession, admin_user
    ):
        """ProductRiskDetail always has 4 contributing factors."""
        p = await _make_product(db_session)
        await _stock_in(db_session, p, admin_user, qty=50)

        svc = RiskService(db_session)
        result = await svc.calculate_product_risk(p.id)
        assert len(result.contributing_factors) == 4
        names = {f.name for f in result.contributing_factors}
        assert names == {"stockout_risk", "expiry_risk", "overstock_risk", "demand_velocity_risk"}

    @pytest.mark.asyncio
    async def test_weights_are_applied(self, db_session: AsyncSession, admin_user):
        """Each contributing factor has the correct weight constant."""
        from app.services.risk_service import (
            WEIGHT_STOCKOUT, WEIGHT_EXPIRY, WEIGHT_OVERSTOCK, WEIGHT_DEMAND
        )
        p = await _make_product(db_session)
        await _stock_in(db_session, p, admin_user, qty=50)

        svc = RiskService(db_session)
        result = await svc.calculate_product_risk(p.id)
        factor_weights = {f.name: f.weight for f in result.contributing_factors}
        assert factor_weights["stockout_risk"] == WEIGHT_STOCKOUT
        assert factor_weights["expiry_risk"] == WEIGHT_EXPIRY
        assert factor_weights["overstock_risk"] == WEIGHT_OVERSTOCK
        assert factor_weights["demand_velocity_risk"] == WEIGHT_DEMAND

    @pytest.mark.asyncio
    async def test_risk_score_is_0_to_100(self, db_session: AsyncSession, admin_user):
        """Risk score must always be in [0, 100]."""
        p = await _make_product(db_session)
        await _stock_in(db_session, p, admin_user, qty=200,
                        expiry=date.today() - timedelta(days=3))  # expired

        svc = RiskService(db_session)
        result = await svc.calculate_product_risk(p.id)
        assert 0.0 <= result.risk_score <= 100.0

    @pytest.mark.asyncio
    async def test_product_not_found_raises_404(self, db_session: AsyncSession):
        from fastapi import HTTPException
        svc = RiskService(db_session)
        with pytest.raises(HTTPException) as exc:
            await svc.calculate_product_risk(uuid.uuid4())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_calculate_and_persist_updates_product(
        self, db_session: AsyncSession, admin_user
    ):
        """calculate_and_persist_all() writes last_risk_score and last_risk_level."""
        p = await _make_product(db_session)
        await _stock_in(db_session, p, admin_user, qty=50)

        svc = RiskService(db_session)
        count = await svc.calculate_and_persist_all()
        assert count >= 1

        await db_session.refresh(p)
        assert p.last_risk_score is not None
        assert p.last_risk_level is not None
        assert p.last_risk_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")

    @pytest.mark.asyncio
    async def test_estimated_waste_value_when_batch_expiring(
        self, db_session: AsyncSession, admin_user
    ):
        """Waste value > 0 when batch is expiring and demand can't clear it."""
        p = await _make_product(db_session, expiry_alert_days=30)
        soon = date.today() + timedelta(days=5)
        await _stock_in(db_session, p, admin_user, qty=500, cost=10.0, expiry=soon)
        # Low demand: 1/day → can only consume 5 × 1 = 5 units before expiry
        await _add_historical_demand(db_session, p, admin_user, daily_qty=1, days=30)
        await db_session.refresh(p)

        svc = RiskService(db_session)
        result = await svc.calculate_product_risk(p.id)
        # ~495 units won't be consumed before expiry
        assert result.estimated_waste_value > 0

    @pytest.mark.asyncio
    async def test_supplier_lead_time_used_in_stockout_scoring(
        self, db_session: AsyncSession, admin_user
    ):
        """Product with long lead time + low stock → higher stockout score."""
        # Short lead time product
        p_short = await _make_product(db_session, supplier_lead_days=2)
        await _stock_in(db_session, p_short, admin_user, qty=30)
        await _add_historical_demand(db_session, p_short, admin_user, daily_qty=5, days=30)
        await db_session.refresh(p_short)

        # Long lead time product (same stock/demand profile)
        p_long = await _make_product(db_session, supplier_lead_days=21)
        await _stock_in(db_session, p_long, admin_user, qty=30)
        await _add_historical_demand(db_session, p_long, admin_user, daily_qty=5, days=30)
        await db_session.refresh(p_long)

        svc = RiskService(db_session)
        r_short = await svc.calculate_product_risk(p_short.id)
        r_long  = await svc.calculate_product_risk(p_long.id)
        # Longer lead time should produce higher stockout risk
        assert r_long.stockout_risk_score >= r_short.stockout_risk_score


# ===========================================================================
# Block 5 Analytics endpoint tests
# ===========================================================================

class TestBlock5AnalyticsEndpoints:
    @pytest.mark.asyncio
    async def test_inventory_risk_list_200(
        self, client: AsyncClient, db_session: AsyncSession, admin_user
    ):
        p = await _make_product(db_session)
        await _stock_in(db_session, p, admin_user, qty=50)

        # Persist risk scores first
        svc = RiskService(db_session)
        await svc.calculate_and_persist_all()

        resp = await client.get(
            "/api/v1/analytics/inventory-risk",
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_product_risk_detail_200(
        self, client: AsyncClient, db_session: AsyncSession, admin_user
    ):
        p = await _make_product(db_session)
        await _stock_in(db_session, p, admin_user, qty=50)

        resp = await client.get(
            f"/api/v1/analytics/inventory-risk/{p.id}",
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        assert resp.status_code == 200
        data = resp.json()
        required_fields = [
            "product_id", "sku", "name", "risk_score", "risk_level",
            "stockout_risk_score", "expiry_risk_score", "overstock_risk_score",
            "contributing_factors", "recommended_action",
        ]
        for f in required_fields:
            assert f in data, f"Missing field: {f}"

    @pytest.mark.asyncio
    async def test_product_risk_detail_404(
        self, client: AsyncClient, admin_user
    ):
        resp = await client.get(
            f"/api/v1/analytics/inventory-risk/{uuid.uuid4()}",
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_risk_refresh_endpoint(
        self, client: AsyncClient, db_session: AsyncSession, admin_user
    ):
        p = await _make_product(db_session)
        await _stock_in(db_session, p, admin_user, qty=50)

        resp = await client.post(
            "/api/v1/analytics/inventory-risk/refresh",
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "updated" in data
        assert data["updated"] >= 1

    @pytest.mark.asyncio
    async def test_risk_refresh_requires_manager_or_admin(
        self, client: AsyncClient, staff_user
    ):
        resp = await client.post(
            "/api/v1/analytics/inventory-risk/refresh",
            headers=auth_headers(str(staff_user.id), "STAFF"),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_risk_distribution_endpoint(
        self, client: AsyncClient, db_session: AsyncSession, admin_user
    ):
        p = await _make_product(db_session)
        await _stock_in(db_session, p, admin_user, qty=50)
        svc = RiskService(db_session)
        await svc.calculate_and_persist_all()

        resp = await client.get(
            "/api/v1/analytics/risk-distribution",
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "low" in data
        assert "medium" in data
        assert "high" in data
        assert "critical" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_expiring_endpoint(
        self, client: AsyncClient, db_session: AsyncSession, admin_user
    ):
        p = await _make_product(db_session, expiry_alert_days=30)
        soon = date.today() + timedelta(days=10)
        await _stock_in(db_session, p, admin_user, qty=100, expiry=soon)

        resp = await client.get(
            "/api/v1/analytics/expiring?days=15",
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        # Verify fields in each item
        for item in data["items"]:
            assert "expiry_date" in item
            assert "remaining_qty" in item
            assert "estimated_value" in item

    @pytest.mark.asyncio
    async def test_low_stock_endpoint(
        self, client: AsyncClient, db_session: AsyncSession, admin_user
    ):
        p = await _make_product(db_session, reorder_point=50)
        await _stock_in(db_session, p, admin_user, qty=20)  # below reorder_point

        resp = await client.get(
            "/api/v1/analytics/low-stock",
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        for item in data["items"]:
            assert item["is_low_stock"] is True

    @pytest.mark.asyncio
    async def test_overstocked_endpoint(
        self, client: AsyncClient, db_session: AsyncSession, admin_user
    ):
        p = await _make_product(db_session, max_stock_level=50)
        await _stock_in(db_session, p, admin_user, qty=80)  # above max=50

        resp = await client.get(
            "/api/v1/analytics/overstocked",
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_demand_endpoint(
        self, client: AsyncClient, db_session: AsyncSession, admin_user
    ):
        p = await _make_product(db_session)
        await _stock_in(db_session, p, admin_user, qty=100)
        await _add_historical_demand(db_session, p, admin_user, daily_qty=3, days=30)
        await db_session.refresh(p)

        resp = await client.get(
            f"/api/v1/analytics/demand/{p.id}",
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "average_daily" in data
        assert "velocity_trend" in data
        assert data["average_daily"] == pytest.approx(3.0, abs=0.2)

    @pytest.mark.asyncio
    async def test_all_risk_endpoints_require_auth(self, client: AsyncClient):
        endpoints = [
            "/api/v1/analytics/inventory-risk",
            f"/api/v1/analytics/inventory-risk/{uuid.uuid4()}",
            "/api/v1/analytics/risk-distribution",
            "/api/v1/analytics/expiring",
            "/api/v1/analytics/low-stock",
            "/api/v1/analytics/overstocked",
            f"/api/v1/analytics/demand/{uuid.uuid4()}",
        ]
        for ep in endpoints:
            resp = await client.get(ep)
            assert resp.status_code == 401, f"{ep} should require auth"

    @pytest.mark.asyncio
    async def test_staff_can_view_risk_endpoints(
        self, client: AsyncClient, db_session: AsyncSession, staff_user, admin_user
    ):
        p = await _make_product(db_session)
        await _stock_in(db_session, p, admin_user, qty=50)

        resp = await client.get(
            f"/api/v1/analytics/inventory-risk/{p.id}",
            headers=auth_headers(str(staff_user.id), "STAFF"),
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_inventory_risk_filter_by_level(
        self, client: AsyncClient, db_session: AsyncSession, admin_user
    ):
        """Filter by risk_level returns only matching products."""
        # Create a zero-stock product → CRITICAL
        p = await _make_product(db_session)
        # No stock → CRITICAL after persist
        svc = RiskService(db_session)
        await svc.calculate_and_persist_all()

        resp = await client.get(
            "/api/v1/analytics/inventory-risk?risk_level=CRITICAL",
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["risk_level"] == "CRITICAL"

    @pytest.mark.asyncio
    async def test_inventory_risk_pagination(
        self, client: AsyncClient, db_session: AsyncSession, admin_user
    ):
        """Pagination params are respected."""
        for _ in range(5):
            p = await _make_product(db_session)
            await _stock_in(db_session, p, admin_user, qty=50)
        svc = RiskService(db_session)
        await svc.calculate_and_persist_all()

        resp = await client.get(
            "/api/v1/analytics/inventory-risk?page=1&page_size=3",
            headers=auth_headers(str(admin_user.id), "ADMIN"),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) <= 3
        assert data["page"] == 1
        assert data["page_size"] == 3
