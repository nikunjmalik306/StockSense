"""
Notification model.

user_id is nullable: NULL means system-wide broadcast notification.
reference_type/reference_id form a polymorphic FK so a notification
can point to any resource type without a column per resource.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


NOTIFICATION_TYPES = ("LOW_STOCK", "EXPIRY", "CRITICAL_RISK", "PURCHASE_REQUEST_UPDATE", "SYSTEM")
NOTIFICATION_SEVERITIES = ("INFO", "WARNING", "ERROR", "CRITICAL")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(10), default="INFO", nullable=False
    )
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    __table_args__ = (
        CheckConstraint(
            f"type IN {NOTIFICATION_TYPES}",
            name="chk_notification_type_valid",
        ),
        CheckConstraint(
            f"severity IN {NOTIFICATION_SEVERITIES}",
            name="chk_notification_severity_valid",
        ),
    )

    # Relationships
    user: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", back_populates="notifications"
    )

    def __repr__(self) -> str:
        return f"<Notification type={self.type} user={self.user_id} read={self.is_read}>"
