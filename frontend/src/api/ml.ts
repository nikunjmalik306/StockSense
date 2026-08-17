/**
 * ML API — Demand Forecasting Endpoints
 */
import { apiClient } from './client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DemandForecast {
  product_id: string
  product_name: string
  horizon: number
  daily_predictions: number[]
  predicted_total_demand: number
  model_type: 'ml' | 'baseline'
  current_stock: number
  reorder_point: number
  lead_time_days: number
  recommended_reorder_quantity: number
  safety_stock: number
  training_timestamp: string | null
  metrics: {
    val_mae?: number
    val_rmse?: number
    baseline_mae?: number
    baseline_rmse?: number
    n_train?: number
    n_val?: number
  }
}

export interface ModelMetrics {
  model_trained: boolean
  model_type?: string
  trained_at?: string
  feature_names: string[]
  metrics: {
    val_mae?: number
    val_rmse?: number
    baseline_mae?: number
    baseline_rmse?: number
    n_train?: number
    n_val?: number
  }
  message?: string
}

// ---------------------------------------------------------------------------
// API Functions
// ---------------------------------------------------------------------------

/**
 * Get demand forecast for a specific product.
 */
export async function getDemandForecast(
  productId: string,
  horizon: number = 7
): Promise<DemandForecast> {
  const { data } = await apiClient.get<DemandForecast>(
    `/ml/demand-forecast/${productId}`,
    { params: { horizon } }
  )
  return data
}

/**
 * Get current model metrics and metadata.
 */
export async function getModelMetrics(): Promise<ModelMetrics> {
  const { data } = await apiClient.get<ModelMetrics>('/ml/metrics')
  return data
}

/**
 * Train or retrain the global forecasting model (MANAGER/ADMIN only).
 */
export async function trainModel(forceRetrain: boolean = false): Promise<{
  status: string
  model_type?: string
  trained_at?: string
  metrics: Record<string, unknown>
}> {
  const { data } = await apiClient.post('/ml/train', {
    force_retrain: forceRetrain,
  })
  return data
}
