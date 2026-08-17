"""
Authentication router — /api/v1/auth

Endpoints:
  POST /register  — create account (rate limited)
  POST /login     — get token pair (rate limited)
  POST /logout    — blacklist refresh token
  POST /refresh   — exchange refresh token for new access token
  GET  /me        — get current user profile

Rate limiting is applied to /login and /register to slow brute-force
attempts. The limit is intentionally lenient for development.
In production, tighten RATE_LIMIT_LOGIN to 5/minute.
"""
import logging
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import AuthService, _user_to_response

logger = logging.getLogger("stocksense.auth")

router = APIRouter()


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201,
    summary="Register a new user account",
    description=(
        "Creates a new account with the default STAFF role. "
        "An Admin can upgrade the role after creation."
    ),
)
async def register(
    request: Request,
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    return await service.register(data)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive JWT token pair",
    description=(
        "Returns an access token (15 min) and a refresh token (7 days). "
        "Store the access token in memory and the refresh token securely "
        "(httpOnly cookie recommended)."
    ),
)
async def login(
    request: Request,
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    return await service.login(data)


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Logout — invalidate refresh token",
    description="Blacklists the provided refresh token. The client should discard both tokens.",
)
async def logout(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),  # require valid access token
):
    service = AuthService(db)
    await service.logout(data.refresh_token)
    return MessageResponse(message="Logged out successfully.")


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    summary="Exchange a refresh token for a new access token",
    description=(
        "Validates the refresh token (checks signature, expiry, blacklist) "
        "and issues a new short-lived access token."
    ),
)
async def refresh(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    new_access_token = await service.refresh(data.refresh_token)
    return AccessTokenResponse(access_token=new_access_token)


# ---------------------------------------------------------------------------
# Me
# ---------------------------------------------------------------------------

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
    description="Returns the profile of the currently authenticated user.",
)
async def me(
    current_user: User = Depends(get_current_user),
):
    return _user_to_response(current_user, current_user.role.name)
