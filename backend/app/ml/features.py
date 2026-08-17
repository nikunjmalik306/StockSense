"""
Feature engineering for demand forecasting.

Creates time-based and lag features from daily demand data.
"""
import pandas as pd
import numpy as np


def create_features(df: pd.DataFrame, product_metadata: pd.DataFrame) -> pd.DataFrame:
    """
    Create ML features from daily demand data.
    
    Input DataFrame must have: product_id, date, daily_demand
    
    Returns DataFrame with additional feature columns:
      - lag_1, lag_7, lag_14
      - rolling_mean_7, rolling_mean_14
      - rolling_std_7
      - day_of_week (0=Monday, 6=Sunday)
      - is_weekend
      - current_stock, reorder_point, lead_time_days (from metadata)
    
    Rows with NaN features (due to insufficient history) are dropped.
    """
    if df.empty:
        return df
    
    df = df.copy()
    df = df.sort_values(['product_id', 'date']).reset_index(drop=True)
    
    # Group by product to compute lags/rolling features
    grouped = df.groupby('product_id')
    
    # Lag features
    df['lag_1'] = grouped['daily_demand'].shift(1)
    df['lag_7'] = grouped['daily_demand'].shift(7)
    df['lag_14'] = grouped['daily_demand'].shift(14)
    
    # Rolling features
    df['rolling_mean_7'] = grouped['daily_demand'].transform(
        lambda x: x.rolling(window=7, min_periods=7).mean().shift(1)
    )
    df['rolling_mean_14'] = grouped['daily_demand'].transform(
        lambda x: x.rolling(window=14, min_periods=14).mean().shift(1)
    )
    df['rolling_std_7'] = grouped['daily_demand'].transform(
        lambda x: x.rolling(window=7, min_periods=7).std().shift(1)
    )
    
    # Time-based features
    df['day_of_week'] = df['date'].dt.dayofweek  # 0=Monday, 6=Sunday
    df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
    
    # Merge product metadata
    df = df.merge(
        product_metadata[['product_id', 'current_stock', 'reorder_point', 'lead_time_days']],
        on='product_id',
        how='left'
    )
    
    # Fill missing metadata with defaults
    df['current_stock'] = df['current_stock'].fillna(0).astype(int)
    df['reorder_point'] = df['reorder_point'].fillna(10).astype(int)
    df['lead_time_days'] = df['lead_time_days'].fillna(7).astype(int)
    
    # Drop rows with NaN in lag/rolling features (insufficient history)
    feature_cols = [
        'lag_1', 'lag_7', 'lag_14',
        'rolling_mean_7', 'rolling_mean_14', 'rolling_std_7'
    ]
    df = df.dropna(subset=feature_cols)
    
    return df


def get_feature_columns() -> list[str]:
    """Return list of feature column names used for ML model."""
    return [
        'lag_1', 'lag_7', 'lag_14',
        'rolling_mean_7', 'rolling_mean_14', 'rolling_std_7',
        'day_of_week', 'is_weekend',
        'current_stock', 'reorder_point', 'lead_time_days'
    ]


def prepare_train_test_split(df: pd.DataFrame, test_days: int = 14):
    """
    Chronological train/test split.
    
    Last `test_days` days → test set
    Everything before → train set
    
    Returns: X_train, X_test, y_train, y_test
    """
    if df.empty:
        return None, None, None, None
    
    df = df.sort_values('date')
    
    # Get cutoff date
    max_date = df['date'].max()
    cutoff_date = max_date - pd.Timedelta(days=test_days)
    
    train_df = df[df['date'] <= cutoff_date]
    test_df = df[df['date'] > cutoff_date]
    
    feature_cols = get_feature_columns()
    
    X_train = train_df[feature_cols].values if not train_df.empty else np.array([])
    y_train = train_df['daily_demand'].values if not train_df.empty else np.array([])
    X_test = test_df[feature_cols].values if not test_df.empty else np.array([])
    y_test = test_df['daily_demand'].values if not test_df.empty else np.array([])
    
    return X_train, X_test, y_train, y_test
