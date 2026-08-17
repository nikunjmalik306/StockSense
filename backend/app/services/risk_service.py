"""
RiskService — explainable, rule-based inventory risk scoring.

For each product this service calculates:
  - Average daily consumption (from last 30 days of STOCK_OUT transactions)
  - Days of stock remaining
  - Projected stockout date
  - Expiry risk (from active batches)
  - Overstock risk (relative to max_stock_level and demand coverage)
  - A composite 0–100 risk score with contributing factors

Design decisions:
  - Entirely rule-based and deterministic. No ML model.
  - All inputs come from the database (real data, not fabricated).
  - Each sub-score is independently explainable.
  - Contributing factors are returned so the UI can show WHY a risk level was assigned.
  - Zero-demand products are handled safely (no division by zero).
  - The score is stored back on products.last_risk_score for fast sorting.

Risk levels:
  0–24   LOW
  25–49  MEDIUM
  50–74  HIGH
  75–100 CRITICAL
"""
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import InventoryBatch, StockTransaction
from app.models.product import Product, Supplier
from app.schemas.risk import (
    ContributingFactor,
    DemandMetrics,
    ProductRiskDetail,
    RiskLevel,
    RiskSummary,
)

logger = logging.getLogger("stocksense.risk")

# ---------------------------------------------------------------------------
# Constants — weights must sum to 1.0
# ---------------------------------------------------------------------------
WEIGHT_STOCKOUT = 0.40   # Most important — running out causes immediate operational failure
WEIGHT_EXPIRY   = 0.35   # Second — expired stock is waste and a compliance issue
WEIGHT_OVERSTOCK = 0.15  # Third — excess capital tied up
WEIGHT_DEMAND   = 0.10   # Fourth — demand velocity modulates other risks

# Thresholds
DEMAND_LOOKBACK_DAYS = 30    # days of history used for consumption rate
DEMAND_RECENT_DAYS   = 7     # "recent" window for velocity comparison
MIN_DEMAND_DAYS      = 3     # minimum days with any movement to calculate rate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _risk_level(score: float) -> RiskLevel:
    if score >= 75:
        return RiskLevel.CRITICAL
    if score >= 50:
        return RiskLevel.HIGH
    if score >= 25:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# RiskService
# ---------------------------------------------------------------------------

class RiskService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # Public API
    # =========================================================================

    async def calculate_product_risk(self, product_id: uuid.UUID) -> ProductRiskDetail:
        """
        Calculate full risk detail for a single product.
        Raises 404 if the product doesn't exist.
        """
        from fastapi import HTTPException, status

        product = await self.db.scalar(
            select(Product).where(Product.id == product_id)
        )
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found.",
            )

        return await self._score_product(product)

    async def get_all_risk_summaries(
        self,
        *,
        risk_level: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[list[RiskSummary], int]:
        """
        Return risk summaries for all active products, sorted by risk score descending.

        Uses last_risk_score stored on Product for the sort/filter so the list
        query is fast.  The score is refreshed by calculate_and_persist_all().
        """
        base_q = select(Product).where(Product.is_active.is_(True))

        if risk_level:
            base_q = base_q.where(
                func.upper(Product.last_risk_level) == risk_level.upper()
            )
        if search:
            term = f"%{search.lower()}%"
            base_q = base_q.where(
                func.lower(Product.name).like(term)
                | func.lower(Product.sku).like(term)
            )

        total: int = await self.db.scalar(
            select(func.count()).select_from(base_q.subquery())
        ) or 0

        offset = (page - 1) * page_size
        result = await self.db.execute(
            base_q.order_by(
                Product.last_risk_score.desc().nullslast()
            )
            .offset(offset)
            .limit(page_size)
        )
        products = result.scalars().all()

        summaries: list[RiskSummary] = []
        for p in products:
            # Use stored score if available (fast path), otherwise compute live
            if p.last_risk_score is not None and p.last_risk_level is not None:
                demand = await self._get_demand_metrics(p)
                summaries.append(
                    RiskSummary(
                        product_id=p.id,
                        sku=p.sku,
                        name=p.name,
                        current_stock=p.current_stock,
                        risk_score=float(p.last_risk_score),
                        risk_level=RiskLevel(p.last_risk_level),
                        average_daily_demand=demand.average_daily,
                        days_of_stock_remaining=demand.days_remaining,
                        recommended_action=_recommended_action(
                            float(p.last_risk_score),
                            p.current_stock,
                            demand.days_remaining,
                            p.reorder_point,
                        ),
                    )
                )
            else:
                detail = await self._score_product(p)
                summaries.append(
                    RiskSummary(
                        product_id=detail.product_id,
                        sku=detail.sku,
                        name=detail.name,
                        current_stock=detail.current_stock,
                        risk_score=detail.risk_score,
                        risk_level=detail.risk_level,
                        average_daily_demand=detail.average_daily_demand,
                        days_of_stock_remaining=detail.days_of_stock_remaining,
                        recommended_action=detail.recommended_action,
                    )
                )

        return summaries, total

    async def get_demand_for_product(self, product_id: uuid.UUID) -> "DemandData":
        """
        Public method for the /demand/{product_id} endpoint.
        Validates the product exists then delegates to the internal helper.
        """
        from fastapi import HTTPException, status
        product = await self.db.scalar(
            select(Product).where(Product.id == product_id)
        )
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found.",
            )
        return await self._get_demand_metrics(product)

    async def calculate_and_persist_all(self) -> int:
        """
        Recalculate risk scores for all active products and write them back
        to products.last_risk_score and products.last_risk_level.

        Returns the number of products updated.
        Called at startup after seeding or from a periodic Celery job.
        """
        result = await self.db.execute(
            select(Product).where(Product.is_active.is_(True))
        )
        products = result.scalars().all()
        count = 0
        for p in products:
            try:
                detail = await self._score_product(p)
                p.last_risk_score = detail.risk_score
                p.last_risk_level = detail.risk_level.value
                count += 1
            except Exception as e:
                logger.warning(f"Risk calc failed for product {p.id}: {e}")
        await self.db.commit()
        logger.info(f"Risk scores updated for {count} products")
        return count

    # =========================================================================
    # Demand metrics
    # =========================================================================

    async def _get_demand_metrics(self, product: Product) -> "DemandData":
        """
        Compute demand statistics from the last DEMAND_LOOKBACK_DAYS of STOCK_OUT
        and WRITE_OFF transactions.

        Returns a DemandData dataclass with:
          average_daily    — mean units consumed per day over the lookback window
          recent_daily     — mean units consumed per day over DEMAND_RECENT_DAYS
          days_remaining   — current_stock / average_daily (None if no demand)
          velocity_trend   — "increasing" / "stable" / "decreasing"
        """
        since = datetime.now(timezone.utc) - timedelta(days=DEMAND_LOOKBACK_DAYS)
        since_recent = datetime.now(timezone.utc) - timedelta(days=DEMAND_RECENT_DAYS)

        # Total consumed in lookback window
        total_consumed: int = abs(
            await self.db.scalar(
                select(func.coalesce(func.sum(StockTransaction.quantity), 0))
                .where(
                    StockTransaction.product_id == product.id,
                    StockTransaction.transaction_type.in_(["STOCK_OUT", "WRITE_OFF"]),
                    StockTransaction.transaction_at >= since,
                )
            ) or 0
        )

        # Recent consumed
        recent_consumed: int = abs(
            await self.db.scalar(
                select(func.coalesce(func.sum(StockTransaction.quantity), 0))
                .where(
                    StockTransaction.product_id == product.id,
                    StockTransaction.transaction_type.in_(["STOCK_OUT", "WRITE_OFF"]),
                    StockTransaction.transaction_at >= since_recent,
                )
            ) or 0
        )

        avg_daily = total_consumed / DEMAND_LOOKBACK_DAYS
        recent_daily = recent_consumed / DEMAND_RECENT_DAYS

        days_remaining: float | None = None
        if avg_daily > 0:
            days_remaining = product.current_stock / avg_daily
        elif product.current_stock == 0:
            days_remaining = 0.0

        # Velocity trend: compare recent rate vs historical rate
        if avg_daily > 0 and recent_daily > avg_daily * 1.25:
            trend = "increasing"
        elif avg_daily > 0 and recent_daily < avg_daily * 0.75:
            trend = "decreasing"
        else:
            trend = "stable"

        return DemandData(
            average_daily=round(avg_daily, 2),
            recent_daily=round(recent_daily, 2),
            days_remaining=round(days_remaining, 1) if days_remaining is not None else None,
            velocity_trend=trend,
        )

    # =========================================================================
    # Expiry data
    # =========================================================================

    async def _get_expiry_data(self, product: Product) -> "ExpiryData":
        """
        Find the soonest-expiring active batch and calculate expiry risk.
        """
        today = date.today()

        result = await self.db.execute(
            select(InventoryBatch)
            .where(
                InventoryBatch.product_id == product.id,
                InventoryBatch.is_active.is_(True),
                InventoryBatch.remaining_qty > 0,
                InventoryBatch.expiry_date.is_not(None),
            )
            .order_by(InventoryBatch.expiry_date.asc())
        )
        batches = result.scalars().all()

        if not batches:
            return ExpiryData(has_expiry=False)

        soonest = batches[0]
        days_to_expiry = (soonest.expiry_date - today).days
        at_risk_qty = sum(b.remaining_qty for b in batches if b.expiry_date <= today + timedelta(days=product.expiry_alert_days))
        at_risk_value = sum(
            b.remaining_qty * float(b.cost_per_unit)
            for b in batches
            if b.expiry_date <= today + timedelta(days=product.expiry_alert_days)
        )

        return ExpiryData(
            has_expiry=True,
            days_to_expiry=days_to_expiry,
            earliest_expiry_date=soonest.expiry_date,
            at_risk_qty=at_risk_qty,
            at_risk_value=round(at_risk_value, 2),
            batch_number=soonest.batch_number,
        )

    # =========================================================================
    # Sub-scores
    # =========================================================================

    def _stockout_sub_score(
        self,
        product: Product,
        demand: "DemandData",
        lead_time: int,
        factors: list[ContributingFactor],
    ) -> float:
        """
        Score 0–100 for stockout risk.

        Logic:
          - Zero stock → 100 (out of stock now)
          - days_remaining <= lead_time → escalating score
          - days_remaining <= 2 * lead_time → medium-high risk
          - No demand data → low score (stable, just watch reorder_point)
        """
        stock = product.current_stock

        if stock == 0:
            factors.append(ContributingFactor(
                name="stockout_risk",
                score=100,
                weight=WEIGHT_STOCKOUT,
                explanation="Product is completely out of stock.",
            ))
            return 100.0

        if demand.days_remaining is None:
            # No consumption history — rely on reorder_point as a proxy
            if stock <= product.reorder_point:
                score = 50.0
                factors.append(ContributingFactor(
                    name="stockout_risk",
                    score=score,
                    weight=WEIGHT_STOCKOUT,
                    explanation=f"Stock ({stock}) is at or below reorder point ({product.reorder_point}). No recent demand data.",
                ))
                return score
            factors.append(ContributingFactor(
                name="stockout_risk",
                score=5,
                weight=WEIGHT_STOCKOUT,
                explanation="No recent consumption. Stock level is adequate.",
            ))
            return 5.0

        days = demand.days_remaining
        # Within lead time → very high risk (can't reorder in time)
        if days <= lead_time:
            # Linear scale from 100 (days=0) to 75 (days=lead_time)
            score = _clamp(100 - (days / max(lead_time, 1)) * 25)
        elif days <= lead_time * 2:
            # Warning zone: between 1x and 2x lead time
            fraction = (days - lead_time) / max(lead_time, 1)
            score = _clamp(75 - fraction * 35)
        elif days <= 30:
            score = _clamp(40 - (days - lead_time * 2) * 1.5)
        else:
            score = _clamp(max(5, 30 - days))

        # Boost if velocity is increasing
        if demand.velocity_trend == "increasing" and score < 80:
            score = min(score + 10, 100)

        explanation = (
            f"{days:.1f} days of stock remaining "
            f"(avg daily demand: {demand.average_daily:.1f} units, "
            f"supplier lead time: {lead_time} days)."
        )
        if stock <= product.reorder_point:
            explanation += f" Stock is below reorder point ({product.reorder_point})."

        factors.append(ContributingFactor(
            name="stockout_risk",
            score=round(score, 1),
            weight=WEIGHT_STOCKOUT,
            explanation=explanation,
        ))
        return score

    def _expiry_sub_score(
        self,
        product: Product,
        expiry: "ExpiryData",
        demand: "DemandData",
        factors: list[ContributingFactor],
    ) -> float:
        """
        Score 0–100 for expiry risk.

        Logic:
          - Already expired → 100
          - Within expiry_alert_days → high (60–95 depending on days left)
          - Demand can clear stock before expiry → reduce score
          - No expiry date → 0 (not applicable)
        """
        if not expiry.has_expiry:
            factors.append(ContributingFactor(
                name="expiry_risk",
                score=0,
                weight=WEIGHT_EXPIRY,
                explanation="Product has no expiry date.",
            ))
            return 0.0

        days = expiry.days_to_expiry
        alert = product.expiry_alert_days

        if days <= 0:
            score = 100.0
            explanation = (
                f"Batch {expiry.batch_number or 'unknown'} has EXPIRED "
                f"({abs(days)} days ago). "
                f"{expiry.at_risk_qty} units worth ${expiry.at_risk_value:.2f} at risk."
            )
        elif days <= alert:
            # Scale from 95 (just expired) to 60 (at alert threshold)
            fraction = days / alert
            base_score = 95 - fraction * 35
            # Reduce if demand can consume expiring stock in time
            if demand.average_daily > 0 and expiry.at_risk_qty > 0:
                days_to_clear = expiry.at_risk_qty / demand.average_daily
                if days_to_clear < days:
                    base_score *= 0.60  # demand will clear stock before expiry
                    explanation_suffix = f" Current demand ({demand.average_daily:.1f}/day) should clear expiring stock in {days_to_clear:.1f} days."
                else:
                    explanation_suffix = f" Current demand ({demand.average_daily:.1f}/day) may NOT clear {expiry.at_risk_qty} units before expiry."
            else:
                explanation_suffix = f" No significant demand to consume {expiry.at_risk_qty} expiring units."
            score = _clamp(base_score)
            explanation = (
                f"Batch expires in {days} day{'s' if days != 1 else ''} "
                f"(alert threshold: {alert} days). "
                f"${expiry.at_risk_value:.2f} at risk.{explanation_suffix}"
            )
        elif days <= alert * 2:
            fraction = (days - alert) / alert
            score = _clamp(30 - fraction * 25)
            explanation = (
                f"Batch expires in {days} days. "
                f"Outside alert window ({alert} days) but worth monitoring."
            )
        else:
            score = max(0, _clamp(10 - (days - alert * 2) * 0.1))
            explanation = f"Earliest batch expires in {days} days. Low expiry risk."

        factors.append(ContributingFactor(
            name="expiry_risk",
            score=round(score, 1),
            weight=WEIGHT_EXPIRY,
            explanation=explanation,
        ))
        return score

    def _overstock_sub_score(
        self,
        product: Product,
        demand: "DemandData",
        factors: list[ContributingFactor],
    ) -> float:
        """
        Score 0–100 for overstock risk.

        Logic:
          - No max_stock_level set → use days-of-coverage proxy
          - If stock > max_stock_level → escalating score
          - If days_remaining > 180 and demand exists → moderate overstock flag
        """
        stock = product.current_stock

        if stock == 0:
            factors.append(ContributingFactor(
                name="overstock_risk", score=0, weight=WEIGHT_OVERSTOCK,
                explanation="No stock to be overstocked.",
            ))
            return 0.0

        # Primary check: compare to max_stock_level
        if product.max_stock_level and product.max_stock_level > 0:
            ratio = stock / product.max_stock_level
            if ratio > 1.0:
                score = _clamp(50 + (ratio - 1.0) * 100)
                explanation = (
                    f"Stock ({stock}) exceeds max_stock_level ({product.max_stock_level}). "
                    f"Excess: {stock - product.max_stock_level} units."
                )
            elif ratio > 0.9:
                score = 30.0
                explanation = f"Stock ({stock}) is at {ratio*100:.0f}% of max_stock_level ({product.max_stock_level})."
            else:
                score = 5.0
                explanation = f"Stock ({stock}) is within normal range of max_stock_level ({product.max_stock_level})."
        else:
            # No max_stock_level: use days-of-coverage
            if demand.days_remaining is not None and demand.days_remaining > 180:
                score = _clamp(20 + (demand.days_remaining - 180) * 0.1)
                explanation = (
                    f"No max stock level set. "
                    f"{demand.days_remaining:.0f} days of coverage at current demand — "
                    f"potentially over-purchased."
                )
            else:
                score = 5.0
                explanation = "No max stock level configured. Stock level appears reasonable."

        factors.append(ContributingFactor(
            name="overstock_risk",
            score=round(score, 1),
            weight=WEIGHT_OVERSTOCK,
            explanation=explanation,
        ))
        return score

    def _demand_velocity_sub_score(
        self,
        demand: "DemandData",
        factors: list[ContributingFactor],
    ) -> float:
        """
        Score 0–100 for demand volatility risk.

        A rapidly increasing demand velocity increases risk (stock may run out
        faster than expected). Decreasing velocity is low risk.
        Zero demand on an active product is noteworthy (slow mover).
        """
        if demand.average_daily == 0:
            score = 20.0
            explanation = "No recorded consumption in last 30 days. Product may be a slow mover."
        elif demand.velocity_trend == "increasing":
            ratio = demand.recent_daily / max(demand.average_daily, 0.01)
            score = _clamp(30 + (ratio - 1.0) * 40)
            explanation = (
                f"Demand velocity increasing: {demand.recent_daily:.1f}/day recently "
                f"vs {demand.average_daily:.1f}/day average. "
                f"Stock may deplete faster than expected."
            )
        elif demand.velocity_trend == "decreasing":
            score = 5.0
            explanation = (
                f"Demand slowing: {demand.recent_daily:.1f}/day recently "
                f"vs {demand.average_daily:.1f}/day average."
            )
        else:
            score = 10.0
            explanation = (
                f"Stable demand at {demand.average_daily:.1f} units/day."
            )

        factors.append(ContributingFactor(
            name="demand_velocity_risk",
            score=round(score, 1),
            weight=WEIGHT_DEMAND,
            explanation=explanation,
        ))
        return score

    # =========================================================================
    # Core scoring
    # =========================================================================

    async def _score_product(self, product: Product) -> "ProductRiskDetail":
        """
        Compute all sub-scores and combine into a final 0–100 risk score.

        Short-circuit: zero stock always produces a CRITICAL score (≥ 75).
        The stockout sub-score alone returns 100, but because of weighting
        the composite could fall below 75 when all other sub-scores are low.
        We enforce the minimum so the UI always sees zero-stock as CRITICAL.
        """
        # Get supplier lead time
        lead_time = 7  # default if no supplier
        if product.supplier_id:
            sup = await self.db.scalar(
                select(Supplier).where(Supplier.id == product.supplier_id)
            )
            if sup:
                lead_time = sup.lead_time_days

        demand = await self._get_demand_metrics(product)
        expiry = await self._get_expiry_data(product)

        factors: list[ContributingFactor] = []

        s_stockout  = self._stockout_sub_score(product, demand, lead_time, factors)
        s_expiry    = self._expiry_sub_score(product, expiry, demand, factors)
        s_overstock = self._overstock_sub_score(product, demand, factors)
        s_demand    = self._demand_velocity_sub_score(demand, factors)

        # Weighted composite score
        raw_score = (
            s_stockout  * WEIGHT_STOCKOUT
            + s_expiry    * WEIGHT_EXPIRY
            + s_overstock * WEIGHT_OVERSTOCK
            + s_demand    * WEIGHT_DEMAND
        )

        # -----------------------------------------------------------------------
        # Business-risk escalation rules
        # -----------------------------------------------------------------------
        # These rules enforce minimum risk levels for operationally critical
        # scenarios where the weighted composite may underestimate real-world
        # urgency. Each escalation is explainable and adds a contributing factor.
        escalation_reason: str | None = None

        # Rule 1: Zero stock → CRITICAL (minimum score 75)
        if product.current_stock == 0:
            if raw_score < 75.0:
                escalation_reason = "Operational escalation: product is completely out of stock."
                raw_score = 75.0

        # Rule 2: Imminent stockout + long lead time → HIGH minimum (score ≥ 50)
        # If stock is below reorder point AND will run out before supplier can deliver,
        # this is operationally HIGH risk regardless of other factors.
        elif (
            product.current_stock < product.reorder_point
            and demand.days_remaining is not None
            and demand.days_remaining <= lead_time
        ):
            if raw_score < 50.0:
                escalation_reason = (
                    f"Operational escalation: projected stockout in {demand.days_remaining:.1f} days, "
                    f"while supplier lead time is {lead_time} days."
                )
                raw_score = 50.0

        # Add escalation as a contributing factor if triggered
        if escalation_reason:
            factors.append(ContributingFactor(
                name="operational_escalation",
                score=raw_score,
                weight=0.0,  # no additional weight — this is a floor adjustment
                explanation=escalation_reason,
            ))

        risk_score = round(_clamp(raw_score), 1)
        risk_level = _risk_level(risk_score)

        # Estimated waste value (expiring stock that may not be consumed)
        estimated_waste = 0.0
        if expiry.has_expiry and expiry.days_to_expiry <= product.expiry_alert_days:
            if demand.average_daily > 0 and expiry.at_risk_qty > 0:
                can_consume = demand.average_daily * max(expiry.days_to_expiry, 0)
                waste_qty = max(0, expiry.at_risk_qty - can_consume)
                estimated_waste = round(waste_qty * (expiry.at_risk_value / max(expiry.at_risk_qty, 1)), 2)
            else:
                estimated_waste = expiry.at_risk_value

        # Projected stockout date
        projected_stockout_date: date | None = None
        if demand.days_remaining is not None and demand.average_daily > 0:
            projected_stockout_date = date.today() + timedelta(days=demand.days_remaining)

        recommended = _recommended_action(
            risk_score, product.current_stock, demand.days_remaining, product.reorder_point,
            expiry=expiry, lead_time=lead_time, reorder_qty=product.reorder_quantity,
        )

        return ProductRiskDetail(
            product_id=product.id,
            sku=product.sku,
            name=product.name,
            unit=product.unit,
            current_stock=product.current_stock,
            reorder_point=product.reorder_point,
            max_stock_level=product.max_stock_level,
            average_daily_demand=demand.average_daily,
            recent_daily_demand=demand.recent_daily,
            demand_velocity_trend=demand.velocity_trend,
            days_of_stock_remaining=demand.days_remaining,
            projected_stockout_date=projected_stockout_date,
            risk_score=risk_score,
            risk_level=risk_level,
            stockout_risk_score=round(s_stockout, 1),
            expiry_risk_score=round(s_expiry, 1),
            overstock_risk_score=round(s_overstock, 1),
            demand_velocity_score=round(s_demand, 1),
            earliest_expiry_date=expiry.earliest_expiry_date,
            estimated_waste_value=estimated_waste,
            recommended_action=recommended,
            contributing_factors=factors,
        )


# ---------------------------------------------------------------------------
# Recommended action text
# ---------------------------------------------------------------------------

def _recommended_action(
    score: float,
    current_stock: int,
    days_remaining: float | None,
    reorder_point: int,
    expiry: "ExpiryData | None" = None,
    lead_time: int = 7,
    reorder_qty: int = 50,
) -> str:
    if current_stock == 0:
        return f"URGENT: Product is out of stock. Reorder {reorder_qty} units immediately."

    if score >= 75:
        parts = ["CRITICAL — Immediate action required."]
        if days_remaining is not None and days_remaining <= lead_time:
            parts.append(f"Reorder now — only {days_remaining:.1f} days of stock remain (lead time: {lead_time}d).")
        if expiry and expiry.has_expiry and expiry.days_to_expiry is not None and expiry.days_to_expiry <= 0:
            parts.append("Remove expired batch from inventory immediately.")
        elif expiry and expiry.has_expiry and expiry.days_to_expiry is not None and expiry.days_to_expiry <= 7:
            parts.append(f"Prioritise consumption of batch expiring in {expiry.days_to_expiry} days.")
        return " ".join(parts)

    if score >= 50:
        parts = ["HIGH RISK — Action recommended soon."]
        if days_remaining is not None and days_remaining <= lead_time * 2:
            parts.append(f"Consider reordering {reorder_qty} units (lead time: {lead_time}d).")
        if expiry and expiry.has_expiry and expiry.days_to_expiry is not None and expiry.days_to_expiry <= 30:
            parts.append(f"Monitor batch expiring in {expiry.days_to_expiry} days — prioritise consumption.")
        return " ".join(parts)

    if score >= 25:
        if current_stock <= reorder_point:
            return f"MEDIUM — Stock below reorder point ({reorder_point}). Schedule a reorder of {reorder_qty} units."
        return "MEDIUM — Monitor stock levels. No immediate action required."

    return "LOW — Stock levels are healthy."


# ---------------------------------------------------------------------------
# Internal data classes (not exposed via API — used within service)
# ---------------------------------------------------------------------------

@dataclass
class DemandData:
    average_daily: float = 0.0
    recent_daily: float = 0.0
    days_remaining: float | None = None
    velocity_trend: str = "stable"


@dataclass
class ExpiryData:
    has_expiry: bool = False
    days_to_expiry: int = 0
    earliest_expiry_date: date | None = None
    at_risk_qty: int = 0
    at_risk_value: float = 0.0
    batch_number: str | None = None
