"""
ML models for demand forecasting.

Uses a single global XGBoost model trained across all products.
Falls back to baseline (SMA-7) for products with insufficient data.
"""
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
import joblib
import json

try:
    from xgboost import XGBRegressor
    XGBOOST_AVAILABLE = True
except ImportError:
    from sklearn.ensemble import RandomForestRegressor
    XGBOOST_AVAILABLE = False

from sklearn.metrics import mean_absolute_error, mean_squared_error

from app.ml.features import get_feature_columns


# Model storage directory
MODEL_DIR = Path(__file__).parent.parent.parent / "models" / "demand_forecast"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


class DemandForecastModel:
    """
    Global ML model for demand forecasting across all products.
    """
    
    def __init__(self):
        self.model = None
        self.feature_names = get_feature_columns()
        self.model_type = "xgboost" if XGBOOST_AVAILABLE else "random_forest"
        self.trained_at = None
        self.metrics = {}
    
    def train(self, X_train: np.ndarray, y_train: np.ndarray, 
              X_val: np.ndarray | None = None, y_val: np.ndarray | None = None):
        """
        Train the global model.
        
        Uses XGBoost if available, otherwise RandomForest.
        """
        if XGBOOST_AVAILABLE:
            self.model = XGBRegressor(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
                n_jobs=-1
            )
        else:
            self.model = RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                min_samples_split=5,
                random_state=42,
                n_jobs=-1
            )
        
        # Train
        self.model.fit(X_train, y_train)
        self.trained_at = datetime.utcnow()
        
        # Evaluate on validation if provided
        if X_val is not None and y_val is not None and len(X_val) > 0:
            y_pred_val = self.model.predict(X_val)
            self.metrics = {
                'val_mae': float(mean_absolute_error(y_val, y_pred_val)),
                'val_rmse': float(np.sqrt(mean_squared_error(y_val, y_pred_val))),
                'n_train': len(X_train),
                'n_val': len(X_val)
            }
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict demand for given features."""
        if self.model is None:
            raise ValueError("Model not trained yet")
        return self.model.predict(X)
    
    def save(self, filepath: Path | None = None):
        """Save model and metadata to disk."""
        if filepath is None:
            filepath = MODEL_DIR / "global_model.joblib"
        
        joblib.dump(self.model, filepath)
        
        # Save metadata
        metadata = {
            'model_type': self.model_type,
            'trained_at': self.trained_at.isoformat() if self.trained_at else None,
            'feature_names': self.feature_names,
            'metrics': self.metrics
        }
        
        metadata_path = filepath.parent / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
    
    def load(self, filepath: Path | None = None):
        """Load model and metadata from disk."""
        if filepath is None:
            filepath = MODEL_DIR / "global_model.joblib"
        
        if not filepath.exists():
            raise FileNotFoundError(f"Model file not found: {filepath}")
        
        self.model = joblib.load(filepath)
        
        # Load metadata
        metadata_path = filepath.parent / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            
            self.model_type = metadata.get('model_type', 'unknown')
            self.trained_at = datetime.fromisoformat(metadata['trained_at']) if metadata.get('trained_at') else None
            self.feature_names = metadata.get('feature_names', [])
            self.metrics = metadata.get('metrics', {})


class BaselineModel:
    """
    Simple baseline: 7-day Simple Moving Average.
    
    Used as fallback for products with insufficient data.
    """
    
    @staticmethod
    def predict_sma7(historical_demand: pd.Series, horizon: int = 7) -> float:
        """
        Predict demand using 7-day simple moving average.
        
        Returns: predicted daily demand (averaged over last 7 days)
        """
        if len(historical_demand) == 0:
            return 0.0
        
        # Use last 7 days (or fewer if insufficient history)
        window = min(7, len(historical_demand))
        recent = historical_demand.tail(window)
        
        return float(recent.mean())
    
    @staticmethod
    def evaluate_baseline(y_true: np.ndarray, historical_demand: pd.Series) -> dict:
        """
        Evaluate baseline performance on test set.
        
        For each test point, predict using SMA-7 based on data available at that time.
        """
        if len(y_true) == 0 or len(historical_demand) == 0:
            return {'baseline_mae': 0.0, 'baseline_rmse': 0.0}
        
        # Simple approach: predict with SMA-7 from all historical data
        prediction = BaselineModel.predict_sma7(historical_demand)
        y_pred = np.full(len(y_true), prediction)
        
        mae = mean_absolute_error(y_true, y_pred)
        rmse = np.sqrt(mean_squared_error(y_true, y_pred))
        
        return {
            'baseline_mae': float(mae),
            'baseline_rmse': float(rmse)
        }
