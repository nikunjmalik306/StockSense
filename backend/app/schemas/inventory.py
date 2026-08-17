"""
Pydantic schemas for inventory batch and stock transaction endpoints.

Three operation schemas map to the three transaction types:
  StockInRequest    → STOCK_IN
  StockOutRequest   → STOCK_OUT
  AdjustmentRequest → ADJUSTMENT

Response schemas are separate from request schemas so we never
accidentally expose internal fields (e.g. raw batch IDs to untrusted input).
"""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Inventory Batch schemas
# ---------------------------------------------------------------------------

class InventoryBatchResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    batch_number: str | None
    quantity: int
    remaining_qty: int
    cost_per_unit: float
    expiry_date: date | None
    manufacture_date: date | None
    received_at: datetime
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InventoryBatchPatchRequest(BaseModel):
    """
    Only safe metadata fields are patchable.
    remaining_qty and quantity are immutable after creation —
    they change only through stock transactions.
    """
    batch_number: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
    expiry_date: date | None = None
    manufacture_date: date | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Stock-In
# ---------------------------------------------------------------------------

class StockInRequest(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0, description="Units received. Must be positive.")
    cost_per_unit: float = Field(ge=0, description="Unit cost. Zero is allowed (e.g. samples).")
    batch_number: str | None = Field(default=None, max_length=100)
    expiry_date: date | None = None
    manufacture_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    reference_type: str | None = Field(default=None, max_length=50)
    reference_id: uuid.UUID | None = None


class StockInResponse(BaseModel):
    """
    Returned after a successful stock-in.
    Includes the created batch and transaction so the UI can confirm details.
    """
    transaction: "StockTransactionResponse"
    batch: InventoryBatchResponse
    updated_stock: int  # products.current_stock after the operation


# ---------------------------------------------------------------------------
# Stock-Out
# ---------------------------------------------------------------------------

class StockOutRequest(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0, description="Units to consume. Must be positive.")
    notes: str | None = Field(default=None, max_length=2000)
    reference_type: str | None = Field(default=None, max_length=50)
    reference_id: uuid.UUID | None = None


class BatchAllocation(BaseModel):
    """Describes how many units were taken from a specific batch."""
    batch_id: uuid.UUID
    batch_number: str | None
    quantity_taken: int
    cost_per_unit: float
    expiry_date: date | None


class StockOutResponse(BaseModel):
    """
    Returned after a successful stock-out.
    Shows how the FIFO allocation was split across batches.
    """
    transactions: list["StockTransactionResponse"]
    allocations: list[BatchAllocation]
    updated_stock: int
    total_quantity: int


# ---------------------------------------------------------------------------
# Adjustment
# ---------------------------------------------------------------------------

class AdjustmentRequest(BaseModel):
    product_id: uuid.UUID
    quantity_delta: int = Field(
        description="Signed integer. Positive = increase stock. Negative = decrease."
    )
    reason: str = Field(
        min_length=1,
        max_length=500,
        description="Mandatory reason for the adjustment (e.g. 'Damaged goods', 'Count correction').",
    )
    batch_id: uuid.UUID | None = Field(
        default=None,
        description="Optional. If provided, the specific batch whose remaining_qty is also adjusted.",
    )

    @field_validator("quantity_delta")
    @classmethod
    def delta_not_zero(cls, v: int) -> int:
        if v == 0:
            raise ValueError("quantity_delta cannot be zero. Use positive or negative values only.")
        return v

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reason cannot be blank.")
        return v.strip()


class AdjustmentResponse(BaseModel):
    transaction: "StockTransactionResponse"
    updated_stock: int
    batch_updated: bool  # true if a specific batch's remaining_qty was also adjusted


# ---------------------------------------------------------------------------
# Stock Transaction (read-only ledger)
# ---------------------------------------------------------------------------

class StockTransactionResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    batch_id: uuid.UUID | None
    transaction_type: str
    quantity: int
    unit_cost: float | None
    reference_type: str | None
    reference_id: uuid.UUID | None
    notes: str | None
    performed_by: uuid.UUID
    transaction_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# Resolve forward references
StockInResponse.model_rebuild()
StockOutResponse.model_rebuild()
AdjustmentResponse.model_rebuild()


# ---------------------------------------------------------------------------
# Transaction list filter / sort
# ---------------------------------------------------------------------------

TransactionSortField = Literal["transaction_at", "created_at"]
TransactionSortOrder = Literal["asc", "desc"]
