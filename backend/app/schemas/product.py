"""Pydantic schemas for Product endpoints."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ProductCreateRequest(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    category_id: uuid.UUID
    supplier_id: uuid.UUID | None = None
    unit: str = Field(default="units", max_length=50)
    reorder_point: int = Field(default=10, ge=0)
    reorder_quantity: int = Field(default=50, ge=1)
    max_stock_level: int | None = Field(default=None, ge=1)
    expiry_alert_days: int = Field(default=30, ge=1)

    @model_validator(mode="after")
    def max_stock_gt_reorder(self) -> "ProductCreateRequest":
        if (
            self.max_stock_level is not None
            and self.max_stock_level <= self.reorder_point
        ):
            raise ValueError("max_stock_level must be greater than reorder_point")
        return self


class ProductUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    category_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    unit: str | None = Field(default=None, max_length=50)
    reorder_point: int | None = Field(default=None, ge=0)
    reorder_quantity: int | None = Field(default=None, ge=1)
    max_stock_level: int | None = Field(default=None, ge=1)
    expiry_alert_days: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


# Nested summaries used inside ProductResponse
class CategorySummary(BaseModel):
    id: uuid.UUID
    name: str
    model_config = {"from_attributes": True}


class SupplierSummary(BaseModel):
    id: uuid.UUID
    name: str
    lead_time_days: int
    model_config = {"from_attributes": True}


class ProductResponse(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    description: str | None
    category: CategorySummary
    supplier: SupplierSummary | None
    unit: str
    reorder_point: int
    reorder_quantity: int
    max_stock_level: int | None
    expiry_alert_days: int
    current_stock: int
    last_risk_score: float | None
    last_risk_level: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# Lightweight response for list endpoints (omits heavy nested objects)
class ProductListResponse(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    unit: str
    category_id: uuid.UUID
    category_name: str
    supplier_id: uuid.UUID | None
    supplier_name: str | None
    reorder_point: int
    max_stock_level: int | None
    current_stock: int
    last_risk_score: float | None
    last_risk_level: str | None
    is_active: bool

    model_config = {"from_attributes": True}


# Valid sort fields for the product list endpoint
ProductSortField = Literal[
    "name", "sku", "current_stock", "last_risk_score", "created_at", "updated_at"
]
