"""
Pydantic schemas for Category endpoints.

Three schemas per resource:
- CreateRequest  — fields accepted when creating
- UpdateRequest  — all fields optional (PATCH semantics)
- Response       — fields returned to the client
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)


class CategoryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)


class CategoryResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CategoryWithProductCountResponse(CategoryResponse):
    """Extended response that includes the number of active products."""
    product_count: int = 0
