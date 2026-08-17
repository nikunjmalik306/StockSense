"""
AnalyticsService — aggregated inventory metrics for the dashboard.

Design:
- All metrics are calculated using SQL aggregation (func.sum, func.count, etc.)
  so we never pull thousands of rows into Python just to count them.
- Each public method corresponds to one dashboard widget.
- The service has no side effects — purely read-only SELECT queries.
"""
import logging
import uuid
from datetime import date, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import InventoryBatch, StockTransaction
from app.models.product import Category, Product
from app.models.user import User
from app.schemas.analytics import (
    CategoryDistributionItem,
    InventoryOverview,
    RecentTransactionItem,
    StockStatusItem,
)

logger = logging.getLogger("stocksense.analytics")


class AnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # -------------------------------------------------------------------------
    # Dashboard KPI overview
    # -------------------------------------------------------------------------

    async def get_overview(self) -> InventoryOverview:
        """
        Calculate dashboard KPIs in as few round-trips as possible.

        Uses separate focused queries rather than one massive JOIN so the
        code stays readable and each query can be explained independently.
        """
        # 1. Product-level aggregates (active products only)
        product_agg = await self.db.execute(
            select(
                func.count(Product.id).label("total_products"),
                func.coalesce(func.sum(Product.current_stock), 0).label("total_units"),
                func.count(
                    case((Product.current_stock == 0, Product.id))
                ).label("out_of_stock"),
                func.count(
                    case((Product.current_stock <= Product.reorder_point, Product.id))
                ).label("low_stock"),
            ).where(Product.is_active.is_(True))
        )
        row = product_agg.one()
        total_products: int = row.total_products or 0
        total_units: int = int(row.total_units or 0)
        out_of_stock: int = row.out_of_stock or 0
        low_stock: int = row.low_stock or 0

        # 2. Inventory value = SUM(remaining_qty * cost_per_unit) for active batches
        value_row = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(
                        InventoryBatch.remaining_qty * InventoryBatch.cost_per_unit
                    ),
                    0,
                ).label("total_value")
            ).where(
                InventoryBatch.is_active.is_(True),
                InventoryBatch.remaining_qty > 0,
            )
        )
        inventory_value: float = float(value_row.scalar() or 0)

        # 3. Expiring soon — batches where expiry_date <= today + product.expiry_alert_days
        #    We use a conservative 30-day window here (matching default expiry_alert_days).
        #    A more precise version would JOIN on each product's expiry_alert_days.
        today = date.today()
        expiry_cutoff = today + timedelta(days=30)
        expiry_row = await self.db.execute(
            select(func.count(InventoryBatch.id)).where(
                InventoryBatch.is_active.is_(True),
                InventoryBatch.remaining_qty > 0,
                InventoryBatch.expiry_date.is_not(None),
                InventoryBatch.expiry_date <= expiry_cutoff,
            )
        )
        expiring_soon: int = expiry_row.scalar() or 0

        return InventoryOverview(
            total_products=total_products,
            total_inventory_units=total_units,
            inventory_value=round(inventory_value, 2),
            low_stock_count=low_stock,
            expiring_soon_count=expiring_soon,
            out_of_stock_count=out_of_stock,
        )

    # -------------------------------------------------------------------------
    # Category distribution
    # -------------------------------------------------------------------------

    async def get_category_distribution(self) -> list[CategoryDistributionItem]:
        """
        Returns per-category product count, total units, and inventory value.
        Used for the dashboard bar/pie chart.
        """
        rows = await self.db.execute(
            select(
                Category.id.label("category_id"),
                Category.name.label("category_name"),
                func.count(Product.id).label("product_count"),
                func.coalesce(func.sum(Product.current_stock), 0).label("total_units"),
                func.coalesce(
                    func.sum(
                        select(
                            func.sum(
                                InventoryBatch.remaining_qty * InventoryBatch.cost_per_unit
                            )
                        )
                        .where(
                            InventoryBatch.product_id == Product.id,
                            InventoryBatch.is_active.is_(True),
                            InventoryBatch.remaining_qty > 0,
                        )
                        .correlate(Product)
                        .scalar_subquery()
                    ),
                    0,
                ).label("total_value"),
            )
            .join(Product, Product.category_id == Category.id)
            .where(Product.is_active.is_(True))
            .group_by(Category.id, Category.name)
            .order_by(func.count(Product.id).desc())
        )

        return [
            CategoryDistributionItem(
                category_id=r.category_id,
                category_name=r.category_name,
                product_count=r.product_count,
                total_units=int(r.total_units),
                total_value=round(float(r.total_value), 2),
            )
            for r in rows.all()
        ]

    # -------------------------------------------------------------------------
    # Inventory status table (for InventoryPage overview)
    # -------------------------------------------------------------------------

    async def get_stock_status(
        self,
        *,
        search: str | None = None,
        category_id: uuid.UUID | None = None,
        low_stock_only: bool = False,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[list[StockStatusItem], int]:
        """
        Returns a paginated list of per-product stock status rows.
        Each row includes current stock, reorder point, inventory value,
        nearest expiry, and low-stock flag.
        """
        # Subquery: inventory value per product
        value_sq = (
            select(
                InventoryBatch.product_id,
                func.coalesce(
                    func.sum(InventoryBatch.remaining_qty * InventoryBatch.cost_per_unit), 0
                ).label("inv_value"),
                func.min(InventoryBatch.expiry_date).label("nearest_expiry"),
            )
            .where(
                InventoryBatch.is_active.is_(True),
                InventoryBatch.remaining_qty > 0,
            )
            .group_by(InventoryBatch.product_id)
            .subquery()
        )

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
                func.coalesce(value_sq.c.inv_value, 0).label("inventory_value"),
                value_sq.c.nearest_expiry,
            )
            .join(Category, Product.category_id == Category.id)
            .outerjoin(value_sq, value_sq.c.product_id == Product.id)
            .where(Product.is_active.is_(True))
        )

        if search:
            term = f"%{search.lower()}%"
            base_q = base_q.where(
                func.lower(Product.name).like(term)
                | func.lower(Product.sku).like(term)
            )
        if category_id:
            base_q = base_q.where(Product.category_id == category_id)
        if low_stock_only:
            base_q = base_q.where(Product.current_stock <= Product.reorder_point)

        total_row = await self.db.execute(
            select(func.count()).select_from(base_q.subquery())
        )
        total = total_row.scalar() or 0

        offset = (page - 1) * page_size
        rows = await self.db.execute(
            base_q.order_by(Product.name).offset(offset).limit(page_size)
        )

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
                inventory_value=round(float(r.inventory_value), 2),
                is_low_stock=r.current_stock <= r.reorder_point,
                nearest_expiry=r.nearest_expiry,
                last_risk_level=r.last_risk_level,
            )
            for r in rows.all()
        ]
        return items, total

    # -------------------------------------------------------------------------
    # Recent transactions for dashboard activity feed
    # -------------------------------------------------------------------------

    async def get_recent_transactions(self, limit: int = 10) -> list[RecentTransactionItem]:
        """
        Returns the most recent stock transactions with product and user info.
        Used for the dashboard "Recent Activity" feed.
        """
        rows = await self.db.execute(
            select(
                StockTransaction.id,
                StockTransaction.product_id,
                Product.name.label("product_name"),
                Product.sku.label("product_sku"),
                StockTransaction.transaction_type,
                StockTransaction.quantity,
                StockTransaction.transaction_at,
                User.username.label("performed_by_username"),
            )
            .join(Product, StockTransaction.product_id == Product.id)
            .join(User, StockTransaction.performed_by == User.id)
            .order_by(StockTransaction.transaction_at.desc())
            .limit(limit)
        )

        return [
            RecentTransactionItem(
                id=r.id,
                product_id=r.product_id,
                product_name=r.product_name,
                product_sku=r.product_sku,
                transaction_type=r.transaction_type,
                quantity=r.quantity,
                transaction_at=r.transaction_at.isoformat(),
                performed_by_username=r.performed_by_username,
            )
            for r in rows.all()
        ]
