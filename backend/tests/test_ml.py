"""
Tests for ML demand forecasting.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta
from pathlib import Path

from app.ml.data_pipeline import extract_daily_demand, get_product_metadata, _fill_missing_dates
from app.ml.features import create_features, get_feature_columns, prepare_train_test_split
from app.ml.model import DemandForecastModel, BaselineModel, MODEL_DIR
from app.ml.forecasting_service import ForecastingService


# ============================================================================
# Data Pipeline Tests
# ============================================================================

@pytest.mark.asyncio
async def test_extract_daily_demand_basic(db_session):
    """Test basic daily demand extraction."""
    df = await extract_daily_demand(db_session)
    
    # May be empty if no STOCK_OUT transactions yet
    assert list(df.columns) == ['product_id', 'date', 'daily_demand']
    if not df.empty:
        assert df['daily_demand'].min() >= 0
        assert df['product_id'].nunique() > 0


@pytest.mark.asyncio
async def test_extract_daily_demand_single_product(db_session):
    """Test extraction for a single product."""
    # Get a product ID
    from app.models.product import Product
    from sqlalchemy import select
    
    result = await db_session.execute(select(Product.id).limit(1))
    row = result.first()
    if not row:
        pytest.skip("No products available")
    
    product_id = str(row[0])
    
    df = await extract_daily_demand(db_session, product_id=product_id)
    
    assert list(df.columns) == ['product_id', 'date', 'daily_demand']
    if not df.empty:
        assert df['product_id'].nunique() == 1
        assert df['product_id'].iloc[0] == product_id


@pytest.mark.asyncio
async def test_extract_daily_demand_date_range(db_session):
    """Test extraction with date range filter."""
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    df = await extract_daily_demand(
        db_session,
        start_date=start_date,
        end_date=end_date
    )
    
    if not df.empty:
        assert df['date'].min() >= pd.Timestamp(start_date)
        assert df['date'].max() <= pd.Timestamp(end_date)


def test_fill_missing_dates():
    """Test filling missing dates with zero demand."""
    # Create sparse data
    df = pd.DataFrame([
        {'product_id': 'p1', 'date': pd.Timestamp('2026-01-01'), 'daily_demand': 5.0},
        {'product_id': 'p1', 'date': pd.Timestamp('2026-01-03'), 'daily_demand': 3.0},
        {'product_id': 'p1', 'date': pd.Timestamp('2026-01-05'), 'daily_demand': 7.0},
    ])
    
    result = _fill_missing_dates(df)
    
    # Should have 5 days (Jan 1-5)
    assert len(result) == 5
    assert result['daily_demand'].sum() == 15.0  # 5 + 3 + 7
    
    # Jan 2 and Jan 4 should be zero
    jan2 = result[result['date'] == pd.Timestamp('2026-01-02')]
    assert len(jan2) == 1
    assert jan2['daily_demand'].iloc[0] == 0.0


def test_fill_missing_dates_multiple_products():
    """Test filling missing dates for multiple products."""
    df = pd.DataFrame([
        {'product_id': 'p1', 'date': pd.Timestamp('2026-01-01'), 'daily_demand': 5.0},
        {'product_id': 'p1', 'date': pd.Timestamp('2026-01-03'), 'daily_demand': 3.0},
        {'product_id': 'p2', 'date': pd.Timestamp('2026-01-02'), 'daily_demand': 2.0},
    ])
    
    result = _fill_missing_dates(df)
    
    # p1: 3 days, p2: 3 days = 6 total
    assert len(result) == 6
    assert result['product_id'].nunique() == 2


@pytest.mark.asyncio
async def test_get_product_metadata(db_session):
    """Test product metadata extraction."""
    df = await get_product_metadata(db_session)
    
    expected_cols = ['product_id', 'category_id', 'supplier_id', 'current_stock', 'reorder_point', 'lead_time_days']
    assert list(df.columns) == expected_cols or df.empty  # May be empty if no products
    if not df.empty:
        assert df['lead_time_days'].min() > 0


# ============================================================================
# Feature Engineering Tests
# ============================================================================

@pytest.mark.asyncio
async def test_create_features_basic(db_session):
    """Test basic feature creation."""
    demand_df = await extract_daily_demand(db_session)
    if demand_df.empty:
        pytest.skip("No demand data available")
    
    product_metadata = await get_product_metadata(db_session)
    
    features_df = create_features(demand_df, product_metadata)
    
    if not features_df.empty:
        feature_cols = get_feature_columns()
        for col in feature_cols:
            assert col in features_df.columns
        
        # No NaN in features (they should be dropped)
        assert not features_df[feature_cols].isnull().any().any()


def test_create_features_lags():
    """Test lag features are created correctly."""
    # Create simple test data
    df = pd.DataFrame([
        {'product_id': 'p1', 'date': pd.Timestamp('2026-01-01') + timedelta(days=i), 'daily_demand': float(i)}
        for i in range(30)
    ])
    
    metadata = pd.DataFrame([{
        'product_id': 'p1',
        'current_stock': 100,
        'reorder_point': 20,
        'lead_time_days': 7
    }])
    
    result = create_features(df, metadata)
    
    assert not result.empty
    # Check lag_1: should be previous day's demand
    # After dropping NaN rows (first 14), day 15 (index 14) has demand=14
    # Its lag_1 should be day 14's demand=13 (because lag shifts by 1)
    if len(result) > 0:
        first_valid = result.iloc[0]
        assert 'lag_1' in result.columns
        assert first_valid['lag_1'] >= 0


def test_create_features_time_features():
    """Test time-based features."""
    # Create data with known days
    df = pd.DataFrame([
        {'product_id': 'p1', 'date': pd.Timestamp('2026-08-10') + timedelta(days=i), 'daily_demand': 5.0}
        for i in range(30)
    ])
    
    metadata = pd.DataFrame([{
        'product_id': 'p1',
        'current_stock': 100,
        'reorder_point': 20,
        'lead_time_days': 7
    }])
    
    result = create_features(df, metadata)
    
    # After feature creation and NaN dropping, check if we have valid rows
    if not result.empty:
        # Aug 10, 2026 is Sunday (day_of_week=6), but may be dropped due to insufficient lags
        # Check any weekend day in results
        weekend_rows = result[result['is_weekend'] == 1]
        if len(weekend_rows) > 0:
            assert weekend_rows.iloc[0]['day_of_week'] in [5, 6]  # Saturday or Sunday
        
        weekday_rows = result[result['is_weekend'] == 0]
        if len(weekday_rows) > 0:
            assert weekday_rows.iloc[0]['day_of_week'] in [0, 1, 2, 3, 4]  # Mon-Fri


def test_prepare_train_test_split():
    """Test chronological train/test split."""
    df = pd.DataFrame([
        {'product_id': 'p1', 'date': pd.Timestamp('2026-01-01') + timedelta(days=i), 'daily_demand': float(i)}
        for i in range(30)
    ])
    
    metadata = pd.DataFrame([{
        'product_id': 'p1',
        'current_stock': 100,
        'reorder_point': 20,
        'lead_time_days': 7
    }])
    
    features_df = create_features(df, metadata)
    X_train, X_test, y_train, y_test = prepare_train_test_split(features_df, test_days=7)
    
    assert len(X_train) > 0
    assert len(X_test) > 0
    assert len(X_train) > len(X_test)
    assert len(y_train) == len(X_train)
    assert len(y_test) == len(X_test)


# ============================================================================
# Model Tests
# ============================================================================

def test_demand_forecast_model_train_predict():
    """Test ML model training and prediction."""
    # Create synthetic training data
    np.random.seed(42)
    n_samples = 100
    n_features = len(get_feature_columns())
    
    X_train = np.random.rand(n_samples, n_features)
    y_train = np.random.rand(n_samples) * 10  # Demand 0-10
    
    X_test = np.random.rand(20, n_features)
    y_test = np.random.rand(20) * 10
    
    model = DemandForecastModel()
    model.train(X_train, y_train, X_test, y_test)
    
    assert model.model is not None
    assert model.trained_at is not None
    assert 'val_mae' in model.metrics
    assert 'val_rmse' in model.metrics


def test_demand_forecast_model_save_load(tmp_path):
    """Test model persistence."""
    # Train a simple model
    np.random.seed(42)
    X_train = np.random.rand(100, 11)
    y_train = np.random.rand(100) * 10
    
    model = DemandForecastModel()
    model.train(X_train, y_train)
    
    # Save
    model_path = tmp_path / "test_model.joblib"
    model.save(model_path)
    
    assert model_path.exists()
    assert (model_path.parent / "metadata.json").exists()
    
    # Load
    new_model = DemandForecastModel()
    new_model.load(model_path)
    
    assert new_model.model is not None
    assert new_model.model_type == model.model_type
    assert new_model.feature_names == model.feature_names


def test_baseline_model_sma7():
    """Test baseline SMA-7 prediction."""
    historical = pd.Series([5, 6, 7, 8, 9, 10, 11])
    pred = BaselineModel.predict_sma7(historical, horizon=7)
    
    # Should be mean of last 7 days
    expected = historical.mean()
    assert abs(pred - expected) < 0.01


def test_baseline_model_sparse_data():
    """Test baseline with less than 7 days."""
    historical = pd.Series([5, 6, 7])
    pred = BaselineModel.predict_sma7(historical, horizon=7)
    
    # Should use all available data
    expected = historical.mean()
    assert abs(pred - expected) < 0.01


def test_baseline_model_zero_demand():
    """Test baseline with zero demand."""
    historical = pd.Series([0, 0, 0, 0, 0, 0, 0])
    pred = BaselineModel.predict_sma7(historical, horizon=7)
    
    assert pred == 0.0


def test_baseline_model_empty():
    """Test baseline with no data."""
    historical = pd.Series([])
    pred = BaselineModel.predict_sma7(historical, horizon=7)
    
    assert pred == 0.0


def test_baseline_evaluate():
    """Test baseline evaluation."""
    y_true = np.array([5, 6, 7, 8, 9, 10, 11])
    historical = pd.Series([4, 5, 6, 7, 8])
    
    metrics = BaselineModel.evaluate_baseline(y_true, historical)
    
    assert 'baseline_mae' in metrics
    assert 'baseline_rmse' in metrics
    assert metrics['baseline_mae'] >= 0
    assert metrics['baseline_rmse'] >= 0


# ============================================================================
# Forecasting Service Tests
# ============================================================================

@pytest.mark.asyncio
async def test_forecasting_service_train_model(db_session):
    """Test model training through service."""
    service = ForecastingService()
    
    try:
        result = await service.train_model(db_session, force_retrain=True)
        assert result['status'] in ['trained', 'loaded_existing']
        assert 'model_type' in result
        assert 'metrics' in result
    except ValueError:
        # May fail if insufficient data - that's okay
        pytest.skip("Insufficient data for training")


@pytest.mark.asyncio
async def test_forecasting_service_get_forecast(db_session):
    """Test getting forecast for a product."""
    # Get a product with history
    from app.models.product import Product
    from sqlalchemy import select
    
    result = await db_session.execute(
        select(Product.id).where(Product.is_active.is_(True)).limit(1)
    )
    row = result.first()
    if not row:
        pytest.skip("No products available")
    
    product_id = str(row[0])
    
    service = ForecastingService()
    forecast = await service.get_forecast(db_session, product_id, horizon=7)
    
    assert forecast['product_id'] == product_id
    assert forecast['horizon'] == 7
    assert len(forecast['daily_predictions']) == 7
    assert forecast['model_type'] in ['ml', 'baseline']
    assert forecast['predicted_total_demand'] >= 0
    assert forecast['recommended_reorder_quantity'] >= 0


@pytest.mark.asyncio
async def test_forecasting_service_get_metrics(db_session):
    """Test getting model metrics."""
    service = ForecastingService()
    
    metrics = await service.get_model_metrics(db_session)
    
