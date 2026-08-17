"""
Product, Category, and Supplier models.

Design decisions:
- Category and Supplier are separate tables (not enums) so managers
  can add new ones without code changes.
- reorder_point: when current_stock falls below this, trigger low-stock alert
- max_stock_level: when current_stock exceeds this, trigger overstock alert
- expiry_alert_days: how many days before expiry to start alerting
- current_stock is denormalized here for fast list/sort queries.
  It is kept consistent by InventoryService within the same DB transaction
  as every StockTransaction write.
- last_risk_score / last_risk_level are denormalized for dashboard sorting.
  They are recomputed by the risk engine and written back here.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    # Relationships
    products: Mapped[list["Product"]] = relationship("Product", back_populates="category")

    def __repr__(self) -> str:
        return f"<Category name={self.name}>"


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    lead_time_days: Mapped[int] = mapped_column(
        Integer,
        default=7,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint("lead_time_days > 0", name="chk_supplier_lead_time_positive"),
    )

    # Relationships
    products: Mapped[list["Product"]] = relationship("Product", back_populates="supplier")

    def __repr__(self) -> str:
        return f"<Supplier name={self.name} lead_time={self.lead_time_days}d>"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sku: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False, index=True
    )
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=True, index=True
    )
    unit: Mapped[str] = mapped_column(
        String(50), default="units", nullable=False
    )
    reorder_point: Mapped[int] = mapped_column(
        Integer, default=10, nullable=False
    )
    reorder_quantity: Mapped[int] = mapped_column(
        Integer, default=50, nullable=False
    )
    max_stock_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expiry_alert_days: Mapped[int] = mapped_column(
        Integer, default=30, nullable=False
    )
    # Denormalized current stock — kept in sync by InventoryService
    current_stock: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, index=True
    )
    # Denormalized risk — recomputed by RiskEngine, stored for sorting
    last_risk_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    last_risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint("reorder_point >= 0", name="chk_product_reorder_point_non_negative"),
        CheckConstraint("reorder_quantity > 0", name="chk_product_reorder_quantity_positive"),
        CheckConstraint("current_stock >= 0", name="chk_product_current_stock_non_negative"),
        CheckConstraint(
            "max_stock_level IS NULL OR max_stock_level > reorder_point",
            name="chk_product_max_stock_gt_reorder",
        ),
    )

    # Relationships
    category: Mapped["Category"] = relationship("Category", back_populates="products")
    supplier: Mapped["Supplier | None"] = relationship("Supplier", back_populates="products")
    inventory_batches: Mapped[list["InventoryBatch"]] = relationship(  # type: ignore[name-defined]
        "InventoryBatch", back_populates="product", order_by="InventoryBatch.received_at"
    )
    stock_transactions: Mapped[list["StockTransaction"]] = relationship(  # type: ignore[name-defined]
        "StockTransaction", back_populates="product"
    )
    purchase_request_items: Mapped[list["PurchaseRequestItem"]] = relationship(  # type: ignore[name-defined]
        "PurchaseRequestItem", back_populates="product"
    )

    def __repr__(self) -> str:
        return f"<Product sku={self.sku} name={self.name} stock={self.current_stock}>"
