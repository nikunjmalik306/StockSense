"""
Data pipeline for ML demand forecasting.

Extracts historical STOCK_OUT transactions and aggregates to daily demand per product.
"""
import pandas as pd
from datetime import date, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import StockTransaction
from app.models.product import Product


async def extract_daily_demand(
    db: AsyncSession,
    product_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    """
    Extract historical daily demand from STOCK_OUT transactions.
    
    Returns DataFrame with columns:
      - product_id (str)
      - date (datetime64)
      - daily_demand (float)
    
    Zero-demand days are included (important for ML training).
    """
    # Build query for STOCK_OUT transactions
    query = select(
        StockTransaction.product_id,
        func.date(StockTransaction.transaction_at).label('date'),
        func.sum(func.abs(StockTransaction.quantity)).label('daily_demand')
    ).where(
        StockTransaction.transaction_type == 'STOCK_OUT'
    )
    
    if product_id:
        query = query.where(StockTransaction.product_id == product_id)
    if start_date:
        query = query.where(func.date(StockTransaction.transaction_at) >= start_date)
    if end_date:
        query = query.where(func.date(StockTransaction.transaction_at) <= end_date)
    
    query = query.group_by(
        StockTransaction.product_id,
        func.date(StockTransaction.transaction_at)
    ).order_by(
        StockTransaction.product_id,
        func.date(StockTransaction.transaction_at)
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    if not rows:
        return pd.DataFrame(columns=['product_id', 'date', 'daily_demand'])
    
    # Convert to DataFrame
    df = pd.DataFrame([
        {
            'product_id': str(row.product_id),
            'date': pd.to_datetime(row.date),
            'daily_demand': float(row.daily_demand)
        }
        for row in rows
    ])
    
    # Fill missing dates with zero demand (critical for ML)
    if not df.empty:
        df = _fill_missing_dates(df)
    
    return df


def _fill_missing_dates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fill missing dates with zero demand for each product.
    This ensures we have continuous time series data.
    """
    if df.empty:
        return df
    
    # Get date range
    min_date = df['date'].min()
    max_date = df['date'].max()
    all_dates = pd.date_range(start=min_date, end=max_date, freq='D')
    
    # Create complete date grid for all products
    products = df['product_id'].unique()
    complete_grid = []
    
    for product_id in products:
        for date in all_dates:
            complete_grid.append({
                'product_id': product_id,
                'date': date,
            })
    
    complete_df = pd.DataFrame(complete_grid)
    
    # Merge with actual data, filling missing with 0
    result = complete_df.merge(
        df[['product_id', 'date', 'daily_demand']],
        on=['product_id', 'date'],
        how='left'
    )
    result['daily_demand'] = result['daily_demand'].fillna(0.0)
    
    return result.sort_values(['product_id', 'date']).reset_index(drop=True)


async def get_product_metadata(db: AsyncSession) -> pd.DataFrame:
    """
    Get product metadata for feature engineering.
    
    Returns DataFrame with columns:
      - product_id
      - category_id
      - supplier_id  
      - current_stock
      - reorder_point
      - lead_time_days
    """
    from app.models.product import Supplier
    
    query = select(
        Product.id,
        Product.category_id,
        Product.supplier_id,
        Product.current_stock,
        Product.reorder_point,
        Supplier.lead_time_days
    ).join(
        Supplier,
        Product.supplier_id == Supplier.id,
        isouter=True
    ).where(
        Product.is_active.is_(True)
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    df = pd.DataFrame([
        {
            'product_id': str(row.id),
            'category_id': str(row.category_id) if row.category_id else None,
            'supplier_id': str(row.supplier_id) if row.supplier_id else None,
            'current_stock': int(row.current_stock),
            'reorder_point': int(row.reorder_point),
            'lead_time_days': int(row.lead_time_days) if row.lead_time_days else 7
        }
        for row in rows
    ])
    
    return df
