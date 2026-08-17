"""
AuditLog model.

Design decisions:
- old_value / new_value: JSON base type works on both SQLite (TEXT) and
  PostgreSQL (JSONB via dialect override). Same model, no conditional code.
- ip_address: stored as Text; on PostgreSQL the migration creates it as
  INET. We don't need INET enforcement in the ORM layer for app logic.
- user_id / resource_id: UUID columns same as all other models.
- Rows are insert-only — never updated or deleted.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    # JSON renders as JSON on SQLite (compatible) and we upgrade to JSONB
    # in the Alembic migration for PostgreSQL.
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Stored as Text at ORM level; Alembic migration uses INET on PostgreSQL.
    ip_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    # Relationships
    user: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", back_populates="audit_logs"
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog action={self.action} "
            f"resource={self.resource_type}/{self.resource_id} "
            f"user={self.user_id}>"
        )
