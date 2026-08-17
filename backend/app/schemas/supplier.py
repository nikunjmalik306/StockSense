"""Pydantic schemas for Supplier endpoints."""
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SupplierCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    contact_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=1000)
    lead_time_days: int = Field(default=7, ge=1, le=365)


class SupplierUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    contact_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=1000)
    lead_time_days: int | None = Field(default=None, ge=1, le=365)
    is_active: bool | None = None


class SupplierResponse(BaseModel):
    id: uuid.UUID
    name: str
    contact_name: str | None
    email: str | None
    phone: str | None
    address: str | None
    lead_time_days: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SupplierWithProductCountResponse(SupplierResponse):
    product_count: int = 0
