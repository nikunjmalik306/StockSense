"""
Forecasting service for demand prediction and reorder recommendations.

Main entry point for ML functionality.
"""
import pandas as pd
import numpy as np
from datetime import date, timedelta
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.data_pipeline import extract_daily_demand, get_product_metadata
from app.ml.features import create_features, get_feature_columns, prepare_train_test_split
from app.ml.model import DemandForecastModel, BaselineModel, MODEL_DIR


class ForecastingService:
    """
    Service layer for ML demand forecasting.
    """
    
    def __init__(self):
        self.model = DemandForecastModel()
        self.model_path = MODEL_DIR / "global_model.joblib"
    
    async def train_model(self, db: AsyncSession, force_retrain: bool = False):
        """
        Train the global demand forecasting model.
        
        Steps:
        1. Extract historical STOCK_OUT data
        2. Create features
        3. Chronological train/test split
        4. Train XGBoost (or RandomForest)
        5. Evaluate vs baseline
        6. Save model to disk
        """
        # Check if model already exists
        if not force_retrain and self.model_path.exists():
            self.model.load(self.model_path)
            return {
                'status': 'loaded_existing',
                'model_type': self.model.model_type,
                'trained_at': self.model.trained_at.isoformat() if self.model.trained_at else None,
                'metrics': self.model.metrics
            }
        
        # Extract data
        demand_df = await extract_daily_demand(db)
        if demand_df.empty:
            raise ValueError("No historical demand data available")
        
        product_metadata = await get_product_metadata(db)
        
        # Create features
        features_df = create_features(demand_df, product_metadata)
        if features_df.empty or len(features_df) < 30:
            raise ValueError("Insufficient data for training (need at least 30 rows with features)")
        
        # Train/test split
        X_train, X_test, y_train, y_test = prepare_train_test_split(features_df, test_days=14)
        
        if len(X_train) < 20:
            raise ValueError("Insufficient training data")
        
        # Train model
        self.model.train(X_train, y_train, X_test, y_test)
        
        # Evaluate baseline on test set
        if len(y_test) > 0:
            # Get historical demand up to test period for baseline
            test_start_date = features_df['date'].max() - timedelta(days=13)
            historical = features_df[features_df['date'] < test_start_date]['daily_demand']
            baseline_metrics = BaselineModel.evaluate_baseline(y_test, historical)
            self.model.metrics.update(baseline_metrics)
        
        # Save model
        self.model.save(self.model_path)
        
        return {
            'status': 'trained',
            'model_type': self.model.model_type,
            'trained_at': self.model.trained_at.isoformat() if self.model.trained_at else None,
            'metrics': self.model.metrics
        }
    
    async def get_forecast(
        self,
        db: AsyncSession,
        product_id: str,
        horizon: int = 7
    ) -> dict:
        """
        Get demand forecast for a specific product.
        
        Returns:
        - product_id, product_name
        - horizon
        - daily_predictions (list of daily demand predictions)
        - predicted_total_demand
        - model_type ('ml' or 'baseline')
        - current_stock
        - reorder_point
        - lead_time_days
        - recommended_reorder_quantity
        - metrics (MAE, RMSE, baseline comparison)
        """
        # Load model if not already loaded
        if self.model.model is None:
            if self.model_path.exists():
                self.model.load(self.model_path)
            else:
                # No trained model, train it first
                await self.train_model(db)
        
        # Get product info
        from app.models.product import Product, Supplier
        from sqlalchemy import select
        
        query = select(Product, Supplier).join(
            Supplier, Product.supplier_id == Supplier.id, isouter=True
        ).where(Product.id == product_id)
        result = await db.execute(query)
        row = result.first()
        
        if not row:
            raise ValueError(f"Product {product_id} not found")
        
        product, supplier = row
        lead_time_days = supplier.lead_time_days if supplier else 7
        
        # Extract recent demand history
        end_date = date.today()
        start_date = end_date - timedelta(days=90)  # Last 90 days for context
        
        demand_df = await extract_daily_demand(db, product_id=product_id, start_date=start_date, end_date=end_date)
        
        # Check if sufficient data for ML prediction
        use_baseline = False
        if demand_df.empty or len(demand_df) < 21:  # Need at least 21 days for features
            use_baseline = True
        
        if use_baseline:
            # Use baseline SMA-7
            if not demand_df.empty:
                daily_pred = BaselineModel.predict_sma7(demand_df['daily_demand'], horizon)
            else:
                daily_pred = 0.0
            
            daily_predictions = [float(daily_pred)] * horizon
            model_type = 'baseline'
            metrics = {}
        else:
            # Use ML model
            product_metadata = await get_product_metadata(db)
            product_meta = product_metadata[product_metadata['product_id'] == product_id]
            
            if product_meta.empty:
                product_meta = pd.DataFrame([{
                    'product_id': product_id,
                    'current_stock': product.current_stock,
                    'reorder_point': product.reorder_point,
                    'lead_time_days': lead_time_days
                }])
            
            features_df = create_features(demand_df, product_meta)
            
            if features_df.empty or len(features_df) < 14:
                # Fallback to baseline
                daily_pred = BaselineModel.predict_sma7(demand_df['daily_demand'], horizon)
                daily_predictions = [float(daily_pred)] * horizon
                model_type = 'baseline'
                metrics = {}
            else:
                # Predict next `horizon` days
                # Use last available features as base, adjust day_of_week
                last_row = features_df.iloc[-1]
                last_date = last_row['date']
                
                daily_predictions = []
                for day_offset in range(1, horizon + 1):
                    pred_date = last_date + timedelta(days=day_offset)
                    
                    # Create feature vector
                    # In production, we'd update lags/rolling with predictions
                    # For simplicity, use last known features
                    features = last_row[get_feature_columns()].values.reshape(1, -1)
                    
                    # Update day_of_week
                    features[0, 6] = pred_date.dayofweek
                    features[0, 7] = 1 if pred_date.dayofweek >= 5 else 0
                    
                    pred = self.model.predict(features)[0]
                    daily_predictions.append(max(0.0, float(pred)))
                
                model_type = 'ml'
                metrics = self.model.metrics
        
        predicted_total_demand = sum(daily_predictions)
        
        # Calculate reorder recommendation
        safety_stock = product.reorder_point * 0.5  # Simple safety stock
        expected_demand_during_lead_time = (predicted_total_demand / horizon) * lead_time_days
        
        recommended_reorder = max(
            predicted_total_demand + expected_demand_during_lead_time + safety_stock - product.current_stock,
            0
        )
        
        return {
            'product_id': product_id,
            'product_name': product.name,
            'horizon': horizon,
            'daily_predictions': daily_predictions,
            'predicted_total_demand': round(predicted_total_demand, 2),
            'model_type': model_type,
            'current_stock': product.current_stock,
            'reorder_point': product.reorder_point,
            'lead_time_days': lead_time_days,
            'recommended_reorder_quantity': round(recommended_reorder, 2),
            'safety_stock': round(safety_stock, 2),
            'training_timestamp': self.model.trained_at.isoformat() if self.model.trained_at else None,
            'metrics': metrics
        }
    
    async def get_model_metrics(self, db: AsyncSession) -> dict:
        """
        Get current model metrics and metadata.
        """
        if self.model.model is None and self.model_path.exists():
            self.model.load(self.model_path)
        
        if self.model.model is None:
            return {
                'model_trained': False,
                'message': 'No model trained yet'
            }
        
        return {
            'model_trained': True,
            'model_type': self.model.model_type,
            'trained_at': self.model.trained_at.isoformat() if self.model.trained_at else None,
            'feature_names': self.model.feature_names,
            'metrics': self.model.metrics
        }
