"""
FastAPI dependency injection for authentication and RBAC.

These dependencies are used with Depends() in route handlers.

Design:
- get_current_user: verifies JWT and returns the User ORM object.
  Every protected endpoint uses this.
- require_roles(*roles): factory that returns a dependency which
  raises 403 if the user's role is not in the allowed set.
  Used directly in route signatures.

RBAC is enforced here AND in service methods.
Enforcing only at the route level is not sufficient because:
  - Services can be called from Celery tasks (no HTTP context)
  - Tests can call services directly
  - Defense in depth
"""
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User

# HTTPBearer extracts the token from "Authorization: Bearer <token>"
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency: Decode the access token and return the authenticated User.

    Raises 401 if:
    - No Authorization header is present
    - Token signature is invalid
    - Token is expired
    - User no longer exists in the database

    Usage:
        @router.get("/protected")
        async def my_route(current_user: User = Depends(get_current_user)):
            ...
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Provide a Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Import here to avoid circular imports (auth_service imports models)
    from app.services.auth_service import AuthService

    service = AuthService(db)
    return await service.get_current_user_from_token(credentials.credentials)


def require_roles(*roles: str) -> Callable:
    """
    Dependency factory: require the current user to have one of the specified roles.

    Usage:
        @router.delete("/products/{id}")
        async def delete_product(
            current_user: User = Depends(require_roles("ADMIN")),
        ):
            ...

        @router.post("/transactions")
        async def create_transaction(
            current_user: User = Depends(require_roles("ADMIN", "MANAGER", "STAFF")),
        ):
            ...
    """
    allowed = set(roles)

    async def _check(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role.name not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role(s): {', '.join(sorted(allowed))}.",
            )
        return current_user

    return _check


# Convenience pre-built role dependencies used throughout the app
require_admin = require_roles("ADMIN")
require_manager_or_admin = require_roles("ADMIN", "MANAGER")
require_any_role = require_roles("ADMIN", "MANAGER", "STAFF")
