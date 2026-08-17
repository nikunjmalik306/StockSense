"""
User and Role models.

Design decisions:
- UUID primary keys to prevent IDOR enumeration attacks
- Role is its own table (not an enum column) for future extensibility
- refresh_token_blacklist tracks invalidated JTIs for logout support
- is_active flag allows disabling accounts without deleting audit history
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    # Relationships
    users: Mapped[list["User"]] = relationship("User", back_populates="role")

    def __repr__(self) -> str:
        return f"<Role name={self.name}>"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    username: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    # Relationships
    role: Mapped["Role"] = relationship("Role", back_populates="users")
    stock_transactions: Mapped[list["StockTransaction"]] = relationship(  # type: ignore[name-defined]
        "StockTransaction", back_populates="performed_by_user", foreign_keys="StockTransaction.performed_by"
    )
    purchase_requests: Mapped[list["PurchaseRequest"]] = relationship(  # type: ignore[name-defined]
        "PurchaseRequest", back_populates="requester", foreign_keys="PurchaseRequest.requested_by"
    )
    reviewed_requests: Mapped[list["PurchaseRequest"]] = relationship(  # type: ignore[name-defined]
        "PurchaseRequest", back_populates="reviewer", foreign_keys="PurchaseRequest.reviewed_by"
    )
    notifications: Mapped[list["Notification"]] = relationship(  # type: ignore[name-defined]
        "Notification", back_populates="user"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(  # type: ignore[name-defined]
        "AuditLog", back_populates="user"
    )

    def __repr__(self) -> str:
        return f"<User email={self.email} role={self.role_id}>"


class RefreshTokenBlacklist(Base):
    """
    Tracks invalidated refresh token JTIs (JWT IDs).

    When a user logs out, we store the JTI here. On each refresh
    request we check this table to reject stolen/reused tokens.
    Expired entries can be cleaned up periodically by a Celery job.
    """
    __tablename__ = "refresh_token_blacklist"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    jti: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<RefreshTokenBlacklist jti={self.jti}>"
