"""
ML endpoints for demand forecasting.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_any_role, require_manager_or_admin
from app.models.user import User
from app.schemas.ml import (
    DemandForecastResponse,
    ModelMetricsResponse,
    TrainModelRequest,
    TrainModelResponse
)
from app.ml.forecasting_service import ForecastingService


router = APIRouter()


@router.get("/demand-forecast/{product_id}", response_model=DemandForecastResponse)
async def get_demand_forecast(
    product_id: str,
    horizon: int = Query(7, ge=1, le=30, description="Forecast horizon in days"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role)
):
    """
    Get demand forecast for a product.
    
    - **product_id**: Product UUID
    - **horizon**: Number of days to forecast (default: 7, max: 30)
    
    Returns daily predictions, total demand, and reorder recommendation.
    Model type indicates 'ml' (trained model) or 'baseline' (SMA-7 fallback).
    """
    try:
        service = ForecastingService()
        forecast = await service.get_forecast(db, product_id, horizon)
        return forecast
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Forecast error: {str(e)}")


@router.get("/metrics", response_model=ModelMetricsResponse)
async def get_model_metrics(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_any_role)
):
    """
    Get current ML model metrics and metadata.
    
    Returns model type, training timestamp, feature names, MAE/RMSE, and baseline comparison.
    """
    try:
        service = ForecastingService()
        metrics = await service.get_model_metrics(db)
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Metrics error: {str(e)}")


@router.post("/train", response_model=TrainModelResponse)
async def train_model(
    request: TrainModelRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_manager_or_admin)
):
    """
    Train or retrain the global demand forecasting model.
    
    - **force_retrain**: If true, retrain even if model exists
    
    Requires MANAGER or ADMIN role.
    """
    try:
        service = ForecastingService()
        result = await service.train_model(db, force_retrain=request.force_retrain)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training error: {str(e)}")
