"""
Pydantic schemas for authentication endpoints.

Separate request and response schemas enforce:
- Never returning hashed_password in any response
- Never accepting role or is_active from untrusted user input on register
- Explicit field validation (email format, password length)
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        """Only allow letters, digits, underscores, hyphens."""
        if not all(c.isalnum() or c in ("_", "-") for c in v):
            raise ValueError("Username may only contain letters, digits, _ and -")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Returned on successful login."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenResponse(BaseModel):
    """Returned on successful refresh (new access token only)."""
    access_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Body for the refresh endpoint (client sends refresh token in body)."""
    refresh_token: str


class UserResponse(BaseModel):
    """Safe user representation — never includes hashed_password."""
    id: uuid.UUID
    email: str
    username: str
    full_name: str | None
    role: str          # role name string, e.g. "MANAGER"
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    """Generic success message response."""
    message: str
