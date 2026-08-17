"""
AuditService — write-only audit trail.

Every important mutation (create / update / delete) in the application
calls AuditService.log() within the same database transaction so that
the audit entry is committed atomically with the data change.

Design rules:
- Rows are NEVER updated or deleted after insertion.
- old_value / new_value are plain dicts (serialised to JSONB).
  They should contain the resource's public fields — never passwords
  or tokens.
- ip_address and user_agent come from the FastAPI Request object,
  which is passed down from the router to the service.
- user_id is nullable: Celery background jobs set it to None.
"""
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

logger = logging.getLogger("stocksense.audit")


class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        *,
        user_id: uuid.UUID | None,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID | None = None,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """
        Insert an audit log entry.

        The caller is responsible for committing the surrounding
        transaction — this method only adds the object to the session.

        Example:
            await audit.log(
                user_id=current_user.id,
                action="CREATE_PRODUCT",
                resource_type="PRODUCT",
                resource_id=product.id,
                new_value={"sku": product.sku, "name": product.name},
                ip_address=request.client.host,
                user_agent=request.headers.get("user-agent"),
            )
        """
        entry = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(entry)
        logger.debug(
            f"Audit: {action} {resource_type}/{resource_id} by user={user_id}"
        )


def get_client_ip(request: Any) -> str | None:
    """Extract client IP from FastAPI Request, respecting X-Forwarded-For."""
    forwarded = getattr(request, "headers", {}).get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = getattr(request, "client", None)
    return client.host if client else None


def get_user_agent(request: Any) -> str | None:
    """Extract User-Agent header from FastAPI Request."""
    return getattr(request, "headers", {}).get("user-agent")
