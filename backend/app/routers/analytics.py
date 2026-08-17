"""
Analytics router — /api/v1/analytics

Existing endpoints (Block 4):
  GET /overview               — dashboard KPI summary
  GET /category-distribution  — per-category breakdown
  GET /stock-status           — per-product inventory table
  GET /recent-transactions    — recent activity feed

Block 5 additions:
  GET /inventory-risk                    — risk summaries for all products
  GET /inventory-risk/{product_id}       — full risk detail for one product
  GET /risk-distribution                 — LOW/MEDIUM/HIGH/CRITICAL counts
  GET /expiring                          — batches expiring within N days
  GET /low-stock                         — products at or below reorder point
  GET /overstocked                       — products above max_stock_level
  GET /demand/{product_id}               — demand metrics for one product
  POST /inventory-risk/refresh           — recalculate and persist all risk scores
"""
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, require_any_role, require_manager_or_admin
from app.models.inventory import InventoryBatch
from app.models.product import Category, Product
from app.models.user import User
from app.schemas.analytics import (
    CategoryDistributionItem,
    InventoryOverview,
    RecentTransactionItem,
    StockStatusItem,
)
from app.schemas.common import PaginatedResponse
from app.schemas.risk import (
    DemandMetrics,
    ProductRiskDetail,
    RiskDistribution,
    RiskSummary,
)
from app.services.analytics_service import AnalyticsService
from app.services.risk_service import RiskService

router = APIRouter()


# ---------------------------------------------------------------------------
# Block 4 endpoints (unchanged)
# ---------------------------------------------------------------------------

@router.get("/overview", response_model=InventoryOverview,
            summary="Dashboard KPI overview")
async def get_overview(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    return await AnalyticsService(db).get_overview()


@router.get("/category-distribution", response_model=list[CategoryDistributionItem],
            summary="Inventory breakdown by category")
async def get_category_distribution(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    return await AnalyticsService(db).get_category_distribution()


@router.get("/stock-status", response_model=PaginatedResponse[StockStatusItem],
            summary="Per-product stock status with inventory value")
async def get_stock_status(
    search: str | None = Query(default=None),
    category_id: uuid.UUID | None = Query(default=None),
    low_stock_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    svc = AnalyticsService(db)
    items, total = await svc.get_stock_status(
        search=search, category_id=category_id,
        low_stock_only=low_stock_only, page=page, page_size=page_size,
    )
    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size,
        pages=max(1, -(-total // page_size)),
    )


@router.get("/recent-transactions", response_model=list[RecentTransactionItem],
            summary="Recent stock transaction activity")
async def get_recent_transactions(
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    return await AnalyticsService(db).get_recent_transactions(limit=limit)


# ---------------------------------------------------------------------------
# Block 5: Risk endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/inventory-risk",
    response_model=PaginatedResponse[RiskSummary],
    summary="Risk summaries for all active products, sorted by risk score descending",
)
async def get_inventory_risk(
    risk_level: str | None = Query(default=None, description="LOW | MEDIUM | HIGH | CRITICAL"),
    search: str | None = Query(default=None, description="Filter by product name or SKU"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    svc = RiskService(db)
    items, total = await svc.get_all_risk_summaries(
        risk_level=risk_level, search=search, page=page, page_size=page_size,
    )
    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size,
        pages=max(1, -(-total // page_size)),
    )


@router.get(
    "/inventory-risk/{product_id}",
    response_model=ProductRiskDetail,
    summary="Full explainable risk detail for a single product",
)
async def get_product_risk(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    return await RiskService(db).calculate_product_risk(product_id)


@router.post(
    "/inventory-risk/refresh",
    response_model=dict,
    summary="Recalculate and persist risk scores for all active products (ADMIN, MANAGER)",
    description=(
        "Runs the risk engine across all active products and writes "
        "last_risk_score and last_risk_level back to the products table. "
        "Typically called after seeding or as a scheduled job."
    ),
)
async def refresh_risk_scores(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_manager_or_admin),
):
    count = await RiskService(db).calculate_and_persist_all()
    return {"updated": count, "message": f"Risk scores refreshed for {count} products."}


@router.get(
    "/risk-distribution",
    response_model=RiskDistribution,
    summary="Count of products at each risk level",
)
async def get_risk_distribution(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    """
    Uses stored last_risk_level on the products table for speed.
    Returns counts per level plus the total active product count.
    """
    result = await db.execute(
        select(
            Product.last_risk_level,
            func.count(Product.id).label("cnt"),
        )
        .where(Product.is_active.is_(True))
        .group_by(Product.last_risk_level)
    )
    rows = result.all()
    counts = {r.last_risk_level: r.cnt for r in rows}
    total = await db.scalar(
        select(func.count(Product.id)).where(Product.is_active.is_(True))
    ) or 0

    return RiskDistribution(
        low=counts.get("LOW", 0),
        medium=counts.get("MEDIUM", 0),
        high=counts.get("HIGH", 0),
        critical=counts.get("CRITICAL", 0),
        total=total,
    )


@router.get(
    "/expiring",
    response_model=PaginatedResponse[dict],
    summary="Batches expiring within N days",
)
async def get_expiring(
    days: int = Query(default=30, ge=1, le=365, description="Look-ahead window in days"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    cutoff = date.today() + timedelta(days=days)
    base_q = (
        select(
            InventoryBatch.id,
            InventoryBatch.product_id,
            Product.sku,
            Product.name.label("product_name"),
            Product.unit,
            InventoryBatch.batch_number,
            InventoryBatch.expiry_date,
            InventoryBatch.remaining_qty,
            InventoryBatch.cost_per_unit,
        )
        .join(Product, InventoryBatch.product_id == Product.id)
        .where(
            InventoryBatch.is_active.is_(True),
            InventoryBatch.remaining_qty > 0,
            InventoryBatch.expiry_date.is_not(None),
            InventoryBatch.expiry_date <= cutoff,
            Product.is_active.is_(True),
        )
        .order_by(InventoryBatch.expiry_date.asc())
    )
    total = await db.scalar(select(func.count()).select_from(base_q.subquery())) or 0
    offset = (page - 1) * page_size
    rows = await db.execute(base_q.offset(offset).limit(page_size))

    items = [
        {
            "batch_id": str(r.id),
            "product_id": str(r.product_id),
            "sku": r.sku,
            "product_name": r.product_name,
            "unit": r.unit,
            "batch_number": r.batch_number,
            "expiry_date": r.expiry_date.isoformat() if r.expiry_date else None,
            "days_until_expiry": (r.expiry_date - date.today()).days if r.expiry_date else None,
            "remaining_qty": r.remaining_qty,
            "estimated_value": round(r.remaining_qty * float(r.cost_per_unit), 2),
        }
        for r in rows.all()
    ]
    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size,
        pages=max(1, -(-total // page_size)),
    )


@router.get(
    "/low-stock",
    response_model=PaginatedResponse[StockStatusItem],
    summary="Products at or below their reorder point",
)
async def get_low_stock(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    svc = AnalyticsService(db)
    items, total = await svc.get_stock_status(
        low_stock_only=True, page=page, page_size=page_size
    )
    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size,
        pages=max(1, -(-total // page_size)),
    )


@router.get(
    "/overstocked",
    response_model=PaginatedResponse[StockStatusItem],
    summary="Products above their max_stock_level",
)
async def get_overstocked(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    """
    Returns products where current_stock > max_stock_level (if set),
    or where days_of_stock_remaining > 180 (proxy for no max_stock_level set).
    """
    base_q = (
        select(
            Product.id,
            Product.sku,
            Product.name,
            Product.unit,
            Category.name.label("category_name"),
            Product.current_stock,
            Product.reorder_point,
            Product.max_stock_level,
            Product.last_risk_level,
        )
        .join(Category, Product.category_id == Category.id)
        .where(
            Product.is_active.is_(True),
            Product.max_stock_level.is_not(None),
            Product.current_stock > Product.max_stock_level,
        )
    )
    total = await db.scalar(select(func.count()).select_from(base_q.subquery())) or 0
    offset = (page - 1) * page_size
    rows = await db.execute(base_q.order_by(Product.name).offset(offset).limit(page_size))

    items = [
        StockStatusItem(
            product_id=r.id,
            sku=r.sku,
            name=r.name,
            unit=r.unit,
            category_name=r.category_name,
            current_stock=r.current_stock,
            reorder_point=r.reorder_point,
            max_stock_level=r.max_stock_level,
            inventory_value=0.0,   # not needed for overstocked view
            is_low_stock=False,
            nearest_expiry=None,
            last_risk_level=r.last_risk_level,
        )
        for r in rows.all()
    ]
    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size,
        pages=max(1, -(-total // page_size)),
    )


@router.get(
    "/demand/{product_id}",
    response_model=DemandMetrics,
    summary="Demand metrics for a single product",
)
async def get_demand(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role),
):
    svc = RiskService(db)
    demand = await svc.get_demand_for_product(product_id)
    return DemandMetrics(
        average_daily=demand.average_daily,
        recent_daily=demand.recent_daily,
        days_remaining=demand.days_remaining,
        velocity_trend=demand.velocity_trend,
    )
