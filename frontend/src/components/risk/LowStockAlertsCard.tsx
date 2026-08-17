/**
 * LowStockAlertsCard — displays products at or below reorder point
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { analyticsApi } from '../../api'
import type { StockStatusItem } from '../../types'
import { Badge, Spinner } from '../common'

export function LowStockAlertsCard() {
  const [products, setProducts] = useState<StockStatusItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function fetchLowStock() {
      try {
        setLoading(true)
        const data = await analyticsApi.getLowStock({ page: 1, page_size: 5 })
        setProducts(data.items)
        setTotal(data.total)
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Failed to load low stock alerts')
      } finally {
        setLoading(false)
      }
    }
    fetchLowStock()
  }, [])

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Low Stock Alerts</h3>
        <div className="flex items-center justify-center h-48">
          <Spinner size="lg" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Low Stock Alerts</h3>
        <div className="text-red-600 text-sm">{error}</div>
      </div>
    )
  }

  if (products.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Low Stock Alerts</h3>
        <div className="text-green-600 text-sm py-8 text-center flex flex-col items-center gap-2">
          <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          <span>All products have adequate stock</span>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">Low Stock Alerts</h3>
        {total > 5 && (
          <span className="text-sm text-gray-600">{total} total</span>
        )}
      </div>

      <div className="space-y-2">
        {products.map((product) => (
          <div
            key={product.product_id}
            className="flex items-center justify-between p-3 rounded-lg border border-orange-200 bg-orange-50"
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="font-medium text-gray-900 truncate">{product.name}</span>
                {product.last_risk_level && (
                  <Badge variant={product.last_risk_level} size="sm">{product.last_risk_level}</Badge>
                )}
              </div>
              <div className="text-sm text-gray-600">
                {product.sku} • Stock: {product.current_stock} / Reorder: {product.reorder_point}
              </div>
            </div>
            <Link
              to={`/analytics/risk-forecast?product_id=${product.product_id}`}
              className="ml-3 text-sm text-blue-600 hover:text-blue-700 font-medium whitespace-nowrap"
            >
              View Risk →
            </Link>
          </div>
        ))}
      </div>
    </div>
  )
}
