"""
Authentication service.

Handles all auth business logic:
- register: create user with hashed password, assign default role
- login: verify credentials, issue token pair
- logout: blacklist refresh token JTI
- refresh: validate refresh token, issue new access token
- get_current_user: decode access token, load user from DB

All methods raise HTTPException directly — this keeps route handlers
thin (they just call the service and return the result).

Why raise HTTPException in the service layer:
The service layer is where auth decisions are made. Having the service
return a status code directly is simpler and easier to test than
returning a result enum and translating it in the router.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import RefreshTokenBlacklist, Role, User
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserResponse
from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)
from app.config import get_settings

logger = logging.getLogger("stocksense.auth")
settings = get_settings()

# Default role for new registrations
DEFAULT_ROLE_NAME = "STAFF"


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Register
    # ------------------------------------------------------------------

    async def register(self, data: RegisterRequest) -> UserResponse:
        """
        Create a new user account with the default STAFF role.

        Admins can upgrade roles after creation via the user management
        endpoint. We never allow self-assignment of elevated roles.
        """
        # Check for duplicate email
        existing = await self.db.scalar(
            select(User).where(User.email == data.email)
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            )

        # Check for duplicate username
        existing_username = await self.db.scalar(
            select(User).where(User.username == data.username)
        )
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This username is already taken.",
            )

        # Resolve the default role
        role = await self.db.scalar(
            select(Role).where(Role.name == DEFAULT_ROLE_NAME)
        )
        if not role:
            # This should never happen after seeding — fail loudly
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Default role '{DEFAULT_ROLE_NAME}' not found. Run seed data.",
            )

        user = User(
            email=data.email,
            username=data.username,
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            role_id=role.id,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        logger.info(f"New user registered: {user.email} (id={user.id})")
        return _user_to_response(user, role.name)

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    async def login(self, data: LoginRequest) -> TokenResponse:
        """
        Verify credentials and issue an access + refresh token pair.

        We deliberately use the same error message for wrong email and
        wrong password to avoid user enumeration.
        """
        user = await self._get_user_with_role_by_email(data.email)

        if not user or not verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account has been deactivated. Contact an administrator.",
            )

        user_id = str(user.id)
        role_name = user.role.name

        access_token = create_access_token(user_id=user_id, role=role_name)
        refresh_token, jti = create_refresh_token(user_id=user_id)

        logger.info(f"User logged in: {user.email} (id={user.id})")

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        )

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    async def logout(self, refresh_token: str) -> None:
        """
        Blacklist the refresh token's JTI so it cannot be reused.

        We decode without verifying expiry here — if someone passes
        an already-expired token, we still blacklist it (harmless) and
        return success (avoids revealing token state to the caller).
        """
        try:
            payload = decode_refresh_token(refresh_token)
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti:
                expires_at = datetime.fromtimestamp(exp, tz=timezone.utc) if exp else (
                    datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
                )
                blacklist_entry = RefreshTokenBlacklist(
                    jti=jti,
                    expires_at=expires_at,
                )
                self.db.add(blacklist_entry)
                await self.db.commit()
                logger.info(f"Refresh token blacklisted: jti={jti}")
        except (JWTError, Exception) as e:
            # Token was invalid anyway — logout is still "successful"
            logger.warning(f"Logout with invalid token: {e}")

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    async def refresh(self, refresh_token: str) -> str:
        """
        Validate a refresh token and issue a new access token.

        Returns the new access token string.
        Raises 401 if the token is invalid, expired, or blacklisted.
        """
        try:
            payload = decode_refresh_token(refresh_token)
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        jti = payload.get("jti")
        user_id = payload.get("sub")

        if not jti or not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed refresh token.",
            )

        # Check blacklist
        blacklisted = await self.db.scalar(
            select(RefreshTokenBlacklist).where(RefreshTokenBlacklist.jti == jti)
        )
        if blacklisted:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has been revoked.",
            )

        # Load user to get current role (role may have changed since token was issued)
        user = await self._get_user_with_role_by_id(user_id)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or deactivated.",
            )

        new_access_token = create_access_token(
            user_id=str(user.id), role=user.role.name
        )
        logger.info(f"Access token refreshed for user: {user.email}")
        return new_access_token

    # ------------------------------------------------------------------
    # Get current user from access token
    # ------------------------------------------------------------------

    async def get_current_user_from_token(self, token: str) -> User:
        """
        Decode an access token and return the corresponding User ORM object.

        Called by the FastAPI dependency get_current_user on every
        protected request.
        """
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            payload = decode_access_token(token)
            user_id: str | None = payload.get("sub")
            if not user_id:
                raise credentials_exception
        except JWTError:
            raise credentials_exception

        user = await self._get_user_with_role_by_id(user_id)
        if not user:
            raise credentials_exception
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated.",
            )
        return user

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_user_with_role_by_email(self, email: str) -> User | None:
        """Load user with role eagerly to avoid lazy-load issues in async context."""
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.role))
            .where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def _get_user_with_role_by_id(self, user_id: str) -> User | None:
        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            return None
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.role))
            .where(User.id == uid)
        )
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Helper to build UserResponse from ORM objects
# ---------------------------------------------------------------------------

def _user_to_response(user: User, role_name: str) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        role=role_name,
        is_active=user.is_active,
        created_at=user.created_at,
    )
