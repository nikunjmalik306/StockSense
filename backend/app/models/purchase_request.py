"""
PurchaseRequest and PurchaseRequestItem models.

Design decisions:
- PurchaseRequest has a simple state machine:
    DRAFT → PENDING → APPROVED → FULFILLED
                    → REJECTED
- is_ai_generated flag shows provenance in the UI (Block 8 Copilot)
- request_number is a human-readable identifier (PR-2025-0001) generated
  by the service layer, not a DB sequence, so the format is flexible.
- ON DELETE CASCADE on items: deleting a draft PR removes its line items.
  Approved/fulfilled PRs should never be deleted (enforced in service layer).
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


PURCHASE_REQUEST_STATUSES = ("DRAFT", "PENDING", "APPROVED", "REJECTED", "FULFILLED")


class PurchaseRequest(Base):
    __tablename__ = "purchase_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    request_number: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="DRAFT", nullable=False, index=True
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            f"status IN {PURCHASE_REQUEST_STATUSES}",
            name="chk_purchase_request_status_valid",
        ),
    )

    # Relationships
    requester: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User", back_populates="purchase_requests", foreign_keys=[requested_by]
    )
    reviewer: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", back_populates="reviewed_requests", foreign_keys=[reviewed_by]
    )
    items: Mapped[list["PurchaseRequestItem"]] = relationship(
        "PurchaseRequestItem",
        back_populates="purchase_request",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<PurchaseRequest {self.request_number} status={self.status}>"


class PurchaseRequestItem(Base):
    __tablename__ = "purchase_request_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    purchase_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True
    )
    quantity_requested: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_unit_cost: Mapped[float | None] = mapped_column(
        Numeric(10, 4), nullable=True
    )
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    urgency_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "quantity_requested > 0", name="chk_pri_quantity_positive"
        ),
    )

    # Relationships
    purchase_request: Mapped["PurchaseRequest"] = relationship(
        "PurchaseRequest", back_populates="items"
    )
    product: Mapped["Product"] = relationship(  # type: ignore[name-defined]
        "Product", back_populates="purchase_request_items"
    )

    def __repr__(self) -> str:
        return (
            f"<PurchaseRequestItem product={self.product_id} "
            f"qty={self.quantity_requested}>"
        )
