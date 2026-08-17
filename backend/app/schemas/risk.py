"""
Pydantic schemas for the inventory risk engine.

These are the API-facing models returned by /api/v1/analytics/inventory-risk/*.
Internal helper dataclasses (DemandData, ExpiryData) live in risk_service.py.
"""
import uuid
from datetime import date
from enum import Enum

from pydantic import BaseModel


class RiskLevel(str, Enum):
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


class ContributingFactor(BaseModel):
    """
    One element in the risk explanation.
    Returned as a list so the UI can render each factor independently.
    """
    name: str            # e.g. "stockout_risk", "expiry_risk"
    score: float         # 0–100 sub-score before weighting
    weight: float        # contribution weight (0–1), weights sum to 1.0
    explanation: str     # human-readable reason


class DemandMetrics(BaseModel):
    """Demand and stock coverage metrics for a product."""
    average_daily: float           # units/day over last 30 days
    recent_daily: float            # units/day over last 7 days
    days_remaining: float | None   # current_stock / average_daily; None = no demand data
    velocity_trend: str            # "increasing" | "stable" | "decreasing"


class ProductRiskDetail(BaseModel):
    """Full risk detail for a single product — returned by /{product_id} endpoint."""
    product_id: uuid.UUID
    sku: str
    name: str
    unit: str
    current_stock: int
    reorder_point: int
    max_stock_level: int | None

    # Demand
    average_daily_demand: float
    recent_daily_demand: float
    demand_velocity_trend: str
    days_of_stock_remaining: float | None
    projected_stockout_date: date | None

    # Overall risk
    risk_score: float          # 0–100
    risk_level: RiskLevel

    # Sub-scores (before weighting) — useful for charting
    stockout_risk_score: float
    expiry_risk_score: float
    overstock_risk_score: float
    demand_velocity_score: float

    # Expiry
    earliest_expiry_date: date | None
    estimated_waste_value: float   # $ value of stock that may expire unsold

    # Action
    recommended_action: str
    contributing_factors: list[ContributingFactor]


class RiskSummary(BaseModel):
    """
    Lightweight risk row for the risk list/table.
    Uses stored last_risk_score for performance; full detail via /{product_id}.
    """
    product_id: uuid.UUID
    sku: str
    name: str
    current_stock: int
    risk_score: float
    risk_level: RiskLevel
    average_daily_demand: float
    days_of_stock_remaining: float | None
    recommended_action: str


class RiskDistribution(BaseModel):
    """Risk level counts across the entire product portfolio."""
    low: int
    medium: int
    high: int
    critical: int
    total: int
