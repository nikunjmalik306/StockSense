"""
Pydantic schemas for analytics endpoints.

All values are calculated from real database data via aggregation queries.
Nothing is fabricated or hardcoded.
"""
import uuid
from datetime import date
from pydantic import BaseModel


class InventoryOverview(BaseModel):
    """
    Dashboard KPI summary.
    Calculated via SQL aggregation — not by loading every row into Python.
    """
    total_products: int          # active products
    total_inventory_units: int   # SUM(current_stock) across active products
    inventory_value: float       # SUM(remaining_qty * cost_per_unit) across active batches
    low_stock_count: int         # products where current_stock <= reorder_point
    expiring_soon_count: int     # batches with expiry_date within expiry_alert_days
    out_of_stock_count: int      # active products with current_stock = 0


class CategoryDistributionItem(BaseModel):
    category_id: uuid.UUID
    category_name: str
    product_count: int
    total_units: int
    total_value: float


class StockStatusItem(BaseModel):
    """Per-product stock status row for the inventory overview table."""
    product_id: uuid.UUID
    sku: str
    name: str
    unit: str
    category_name: str
    current_stock: int
    reorder_point: int
    max_stock_level: int | None
    inventory_value: float      # SUM(remaining_qty * cost_per_unit) for this product
    is_low_stock: bool
    nearest_expiry: date | None  # earliest expiry date across active batches
    last_risk_level: str | None


class RecentTransactionItem(BaseModel):
    """Compact transaction row for the dashboard activity feed."""
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    product_sku: str
    transaction_type: str
    quantity: int
    transaction_at: str
    performed_by_username: str
