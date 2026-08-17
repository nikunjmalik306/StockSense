"""
InventoryBatch and StockTransaction models.

Design decisions:
- InventoryBatch represents a single shipment/lot of a product.
  Tracking batches separately enables:
    * Granular expiry date tracking (different batches expire differently)
    * FIFO cost tracking for inventory valuation
    * Write-off of specific expired batches
- remaining_qty is denormalized on the batch (vs computing from transactions)
  for efficient FIFO depletion queries. It is always updated in the same
  transaction as the StockTransaction insert.
- StockTransaction is the immutable ledger of all inventory movements.
  quantity is signed: positive = stock increase, negative = decrease.
- transaction_type uses a string column with a CHECK constraint rather than
  a PostgreSQL ENUM so adding new types doesn't require a migration.
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Boolean,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Valid transaction types — also referenced in InventoryService
TRANSACTION_TYPES = ("STOCK_IN", "STOCK_OUT", "ADJUSTMENT", "WRITE_OFF", "TRANSFER")


class InventoryBatch(Base):
    __tablename__ = "inventory_batches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True
    )
    batch_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_per_unit: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    manufacture_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint("quantity >= 0", name="chk_batch_quantity_non_negative"),
        CheckConstraint("remaining_qty >= 0", name="chk_batch_remaining_non_negative"),
        CheckConstraint(
            "remaining_qty <= quantity", name="chk_batch_remaining_lte_quantity"
        ),
        CheckConstraint("cost_per_unit >= 0", name="chk_batch_cost_non_negative"),
    )

    # Relationships
    product: Mapped["Product"] = relationship(  # type: ignore[name-defined]
        "Product", back_populates="inventory_batches"
    )
    stock_transactions: Mapped[list["StockTransaction"]] = relationship(
        "StockTransaction", back_populates="batch"
    )

    def __repr__(self) -> str:
        return (
            f"<InventoryBatch product={self.product_id} "
            f"remaining={self.remaining_qty}/{self.quantity} "
            f"expires={self.expiry_date}>"
        )


class StockTransaction(Base):
    """
    Immutable ledger of every inventory movement.

    Once written, rows are never updated or deleted — this is the
    audit-ready source of truth for all stock changes.

    quantity convention:
      STOCK_IN   → positive (stock increases)
      STOCK_OUT  → negative (stock decreases)
      ADJUSTMENT → positive or negative (direct correction)
      WRITE_OFF  → negative (expired/damaged stock removed)
    """
    __tablename__ = "stock_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_batches.id"), nullable=True
    )
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    # reference_type / reference_id link to the source document
    # e.g. reference_type="PURCHASE_REQUEST", reference_id=<pr_uuid>
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    performed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    transaction_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            f"transaction_type IN {TRANSACTION_TYPES}",
            name="chk_transaction_type_valid",
        ),
    )

    # Relationships
    product: Mapped["Product"] = relationship(  # type: ignore[name-defined]
        "Product", back_populates="stock_transactions"
    )
    batch: Mapped["InventoryBatch | None"] = relationship(
        "InventoryBatch", back_populates="stock_transactions"
    )
    performed_by_user: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", back_populates="stock_transactions", foreign_keys=[performed_by]
    )

    def __repr__(self) -> str:
        return (
            f"<StockTransaction type={self.transaction_type} "
            f"product={self.product_id} qty={self.quantity}>"
        )
