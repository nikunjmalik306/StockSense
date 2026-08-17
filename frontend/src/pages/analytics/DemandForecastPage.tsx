/**
 * DemandForecastPage — ML-powered 7-day demand forecasting
 *
 * Features:
 * - Product selector with search
 * - 7-day demand forecast visualization
 * - Reorder recommendation with explanation
 * - Model performance metrics (MAE, RMSE)
 * - ML vs baseline model indicator
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { productsApi, getDemandForecast, getModelMetrics } from '../../api'
import { Badge, Spinner, EmptyState, PageHeader } from '../../components/common'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'

function formatForecastModelLabel(
  modelType: 'ml' | 'baseline',
  trainedModelType?: string,
): string {
  if (modelType === 'baseline') return 'Baseline forecast (SMA-7)'
  if (trainedModelType) {
    const labels: Record<string, string> = {
      xgboost: 'XGBoost',
      random_forest: 'Random Forest',
    }
    return labels[trainedModelType] ?? trainedModelType
  }
  return 'ML model'
}

export function DemandForecastPage() {
  const [selectedProductId, setSelectedProductId] = useState<string>('')
  const [searchTerm, setSearchTerm] = useState('')

  // Fetch products for selector
  const { data: productsResponse } = useQuery({
    queryKey: ['products'],
    queryFn: () => productsApi.list({ page_size: 1000 }), // Get all products
  })

  const products = productsResponse?.items || []

  // Fetch forecast when product selected
  const {
    data: forecast,
    isLoading: forecastLoading,
    error: forecastError,
  } = useQuery({
    queryKey: ['demand-forecast', selectedProductId],
    queryFn: () => getDemandForecast(selectedProductId, 7),
    enabled: !!selectedProductId,
  })

  // Fetch model metrics
  const { data: metrics } = useQuery({
    queryKey: ['ml-metrics'],
    queryFn: getModelMetrics,
  })

  // Filter products based on search
  const filteredProducts =
    products?.filter(
      (p: { name: string; sku: string }) =>
        p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        p.sku.toLowerCase().includes(searchTerm.toLowerCase())
    ) || []

  // Prepare chart data
  const chartData =
    forecast?.daily_predictions.map((value, index) => ({
      day: `Day ${index + 1}`,
      demand: Number(value.toFixed(2)),
    })) || []

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Demand Forecasting"
        description="7-day demand predictions, stock coverage, and reorder recommendations"
      />

      {/* Product Selector */}
      <div className="panel">
        <div className="panel-body space-y-3">
          <label className="form-label mb-0">Select product</label>
          <input
            type="text"
            placeholder="Search by name or SKU..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="input-base"
          />
          <select
            value={selectedProductId}
            onChange={(e) => setSelectedProductId(e.target.value)}
            className="select-base"
          >
            <option value="">— Choose a product —</option>
            {filteredProducts.slice(0, 50).map((product: { id: string; name: string; sku: string }) => (
              <option key={product.id} value={product.id}>
                {product.name} ({product.sku})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Loading State */}
      {forecastLoading && (
        <div className="flex justify-center items-center py-12">
          <Spinner size="lg" />
        </div>
      )}

      {/* Error State */}
      {forecastError && (
        <div className="panel">
          <div className="panel-body">
            <EmptyState
              title="Unable to generate forecast"
              description={
                (forecastError as Error).message ||
                'An error occurred while fetching the forecast.'
              }
            />
          </div>
        </div>
      )}

      {!selectedProductId && !forecastLoading && (
        <div className="panel">
          <div className="panel-body">
            <EmptyState
              title="No product selected"
              description="Select a product above to view its 7-day demand forecast and reorder recommendation."
            />
          </div>
        </div>
      )}

      {forecast && !forecastLoading && (
        <>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
            <div className="kpi-card">
              <p className="section-label">Current Stock</p>
              <p className="kpi-card__value">{forecast.current_stock}</p>
            </div>
            <div className="kpi-card">
              <p className="section-label">Predicted 7-Day Demand</p>
              <p className="kpi-card__value">{forecast.predicted_total_demand.toFixed(1)}</p>
            </div>
            <div className="kpi-card">
              <p className="section-label">Supplier Lead Time</p>
              <p className="kpi-card__value">{forecast.lead_time_days} days</p>
            </div>
            <div className="kpi-card kpi-card--slate">
              <p className="section-label">Recommended Reorder</p>
              <p className="kpi-card__value text-emerald-700">{Math.ceil(forecast.recommended_reorder_quantity)}</p>
            </div>
          </div>

          <div className="panel">
            <div className="panel-header flex items-center justify-between py-3">
              <h2 className="section-heading">7-Day Demand Forecast</h2>
              <Badge variant={forecast.model_type === 'ml' ? 'green' : 'amber'} size="sm">
                {formatForecastModelLabel(forecast.model_type, metrics?.model_type)}
              </Badge>
            </div>
            <div className="panel-body">
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="day" stroke="#64748b" style={{ fontSize: '12px' }} />
                    <YAxis
                      stroke="#64748b"
                      style={{ fontSize: '12px' }}
                      label={{
                        value: 'Predicted Demand',
                        angle: -90,
                        position: 'insideLeft',
                        style: { fontSize: '12px', fill: '#64748b' },
                      }}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'white',
                        border: '1px solid #e2e8f0',
                        borderRadius: '0.375rem',
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="demand"
                      stroke="#2563eb"
                      strokeWidth={2}
                      dot={{ fill: '#2563eb', r: 3 }}
                      activeDot={{ r: 5 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="panel border-emerald-200/80 bg-emerald-50/30">
            <div className="panel-body">
              <h2 className="section-heading">Reorder Recommendation</h2>
              <p className="mt-2 text-sm leading-relaxed text-slate-700">
                Based on predicted 7-day demand of{' '}
                <span className="font-semibold">{forecast.predicted_total_demand.toFixed(1)} units</span>
                , supplier lead time of{' '}
                <span className="font-semibold">{forecast.lead_time_days} days</span>, safety stock of{' '}
                <span className="font-semibold">{forecast.safety_stock.toFixed(1)} units</span>, and current
                inventory of <span className="font-semibold">{forecast.current_stock} units</span>, StockSense
                recommends ordering{' '}
                <span className="font-semibold text-emerald-700">
                  {Math.ceil(forecast.recommended_reorder_quantity)} units
                </span>
                .
              </p>
              <p className="mt-3 rounded-md border border-emerald-200/80 bg-white px-3 py-2 text-xs text-slate-600">
                Model prediction shows expected demand. Reorder quantity applies business logic:
                predicted demand + lead-time demand + safety stock − current stock.
              </p>
            </div>
          </div>

          {forecast.model_type === 'ml' && forecast.metrics && (
            <div className="panel">
              <div className="panel-header py-3">
                <h2 className="section-heading">Model Performance</h2>
              </div>
              <div className="panel-body">
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  {forecast.metrics.val_mae !== undefined && (
                    <div className="rounded-md border border-slate-200 bg-slate-50/80 p-3">
                      <p className="section-label">ML Model MAE</p>
                      <p className="kpi-card__value text-xl">{forecast.metrics.val_mae.toFixed(2)} units</p>
                    </div>
                  )}
                  {forecast.metrics.val_rmse !== undefined && (
                    <div className="rounded-md border border-slate-200 bg-slate-50/80 p-3">
                      <p className="section-label">ML Model RMSE</p>
                      <p className="kpi-card__value text-xl">{forecast.metrics.val_rmse.toFixed(2)} units</p>
                    </div>
                  )}
                  {forecast.metrics.baseline_mae !== undefined && (
                    <div className="rounded-md border border-slate-200 bg-slate-50/80 p-3">
                      <p className="section-label">Baseline MAE</p>
                      <p className="kpi-card__value text-xl">{forecast.metrics.baseline_mae.toFixed(2)} units</p>
                    </div>
                  )}
                  {forecast.metrics.baseline_rmse !== undefined && (
                    <div className="rounded-md border border-slate-200 bg-slate-50/80 p-3">
                      <p className="section-label">Baseline RMSE</p>
                      <p className="kpi-card__value text-xl">{forecast.metrics.baseline_rmse.toFixed(2)} units</p>
                    </div>
                  )}
                </div>
                {forecast.training_timestamp && (
                  <p className="mt-3 text-xs text-slate-500">
                    Model trained: {new Date(forecast.training_timestamp).toLocaleString()}
                  </p>
                )}
              </div>
            </div>
          )}

          {metrics?.model_trained && metrics.model_type && (
            <div className="rounded-lg border border-brand-200/80 bg-brand-50/40 px-4 py-3 text-sm text-slate-700">
              <strong>Trained model:</strong> {formatForecastModelLabel('ml', metrics.model_type)} (global model across products)
              {metrics.feature_names && metrics.feature_names.length > 0 && (
                <> · <strong>{metrics.feature_names.length}</strong> engineered features</>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
