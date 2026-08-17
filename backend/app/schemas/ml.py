"""
Pydantic schemas for ML endpoints.
"""
from pydantic import BaseModel, Field
from datetime import datetime


class DemandForecastResponse(BaseModel):
    """Response schema for demand forecast."""
    product_id: str
    product_name: str
    horizon: int = Field(..., description="Forecast horizon in days")
    daily_predictions: list[float] = Field(..., description="Daily demand predictions")
    predicted_total_demand: float
    model_type: str = Field(..., description="'ml' or 'baseline'")
    current_stock: int
    reorder_point: int
    lead_time_days: int
    recommended_reorder_quantity: float
    safety_stock: float
    training_timestamp: str | None = None
    metrics: dict = Field(default_factory=dict)


class ModelMetricsResponse(BaseModel):
    """Response schema for model metrics."""
    model_trained: bool
    model_type: str | None = None
    trained_at: str | None = None
    feature_names: list[str] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    message: str | None = None


class TrainModelRequest(BaseModel):
    """Request schema for model training."""
    force_retrain: bool = Field(False, description="Force retraining even if model exists")


class TrainModelResponse(BaseModel):
    """Response schema for model training."""
    status: str
    model_type: str | None = None
    trained_at: str | None = None
    metrics: dict = Field(default_factory=dict)
