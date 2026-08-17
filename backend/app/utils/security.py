"""
Security utilities: password hashing and JWT token management.

Password hashing:
- bcrypt via passlib, cost factor 12 (slow enough to resist brute force,
  fast enough for a web server under normal load ~200ms/hash)
- Never returns the plain password anywhere

JWT strategy:
- Access token: short-lived (15 min), carries user_id + role
- Refresh token: long-lived (7 days), carries only user_id + jti
- jti (JWT ID) is a UUID stored in the refresh token so we can blacklist
  individual tokens on logout without invalidating all sessions
- HS256 symmetric signing — appropriate for a single-service monolith
  (RS256 would be needed if other services need to verify tokens independently)
"""
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Hash a plain-text password with bcrypt. Never store plain passwords."""
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if the plain password matches the stored hash."""
    return _pwd_context.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def _make_token(payload: dict, expires_delta: timedelta) -> str:
    """Internal helper: sign a JWT with expiry and return the encoded string."""
    now = datetime.now(timezone.utc)
    payload = payload.copy()
    payload.update({"iat": now, "exp": now + expires_delta})
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, role: str) -> str:
    """
    Create a short-lived access token.

    Payload:
      sub  — user UUID (string)
      role — role name (ADMIN / MANAGER / STAFF)
      type — "access" (prevents a refresh token being used as access)
    """
    return _make_token(
        payload={"sub": user_id, "role": role, "type": "access"},
        expires_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes),
    )


def create_refresh_token(user_id: str) -> tuple[str, str]:
    """
    Create a long-lived refresh token.

    Returns (encoded_token, jti) so the caller can store the jti
    for blacklist lookups on logout.

    Payload:
      sub  — user UUID (string)
      jti  — unique token ID (UUID)
      type — "refresh" (prevents an access token being used for refresh)
    """
    jti = str(uuid.uuid4())
    token = _make_token(
        payload={"sub": user_id, "jti": jti, "type": "refresh"},
        expires_delta=timedelta(days=settings.jwt_refresh_token_expire_days),
    )
    return token, jti


def decode_access_token(token: str) -> dict:
    """
    Decode and validate an access token.

    Raises jose.JWTError on invalid signature, expiry, or wrong type.
    The caller (get_current_user dependency) converts this to HTTP 401.
    """
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    if payload.get("type") != "access":
        raise JWTError("Token type is not 'access'")
    return payload


def decode_refresh_token(token: str) -> dict:
    """
    Decode and validate a refresh token.

    Raises jose.JWTError on invalid signature, expiry, or wrong type.
    """
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    if payload.get("type") != "refresh":
        raise JWTError("Token type is not 'refresh'")
    return payload
