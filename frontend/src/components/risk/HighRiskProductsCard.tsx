/**
 * HighRiskProductsCard — products requiring immediate attention
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { analyticsApi } from '../../api'
import type { RiskSummary } from '../../types'
import { Badge, Spinner } from '../common'

export function HighRiskProductsCard() {
  const [products, setProducts] = useState<RiskSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function fetchHighRiskProducts() {
      try {
        setLoading(true)
        const data = await analyticsApi.getInventoryRisk({ page: 1, page_size: 5 })
        setProducts(data.items)
      } catch (err: unknown) {
        const message = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        setError(message || 'Failed to load high-risk products')
      } finally {
        setLoading(false)
      }
    }
    fetchHighRiskProducts()
  }, [])

  if (loading) {
    return (
      <div className="panel">
        <div className="panel-header py-3">
          <h3 className="section-heading">Products requiring attention</h3>
        </div>
        <div className="flex h-32 items-center justify-center panel-body">
          <Spinner size="lg" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="panel">
        <div className="panel-header py-3">
          <h3 className="section-heading">Products requiring attention</h3>
        </div>
        <div className="panel-body text-sm text-red-600">{error}</div>
      </div>
    )
  }

  if (products.length === 0) {
    return (
      <div className="panel">
        <div className="panel-header py-3">
          <h3 className="section-heading">Products requiring attention</h3>
        </div>
        <div className="panel-body py-8 text-center text-sm text-slate-400">No risk data available</div>
      </div>
    )
  }

  return (
    <div className="panel">
      <div className="panel-header flex items-center justify-between py-3">
        <div>
          <h3 className="section-heading">Products requiring attention</h3>
          <p className="section-description">Highest risk items ranked by score</p>
        </div>
        <Link to="/analytics/risk" className="link-subtle">
          View all →
        </Link>
      </div>
      <div className="divide-y divide-slate-100">
        {products.map((product) => (
          <Link
            key={product.product_id}
            to={`/analytics/risk?product_id=${product.product_id}`}
            className="flex items-center justify-between px-5 py-3 transition-colors hover:bg-slate-50/80"
          >
            <div className="min-w-0 flex-1 pr-4">
              <div className="flex items-center gap-2">
                <span className="truncate text-sm font-medium text-slate-900">{product.name}</span>
                <Badge variant={product.risk_level} size="sm">{product.risk_level}</Badge>
              </div>
              <p className="mt-0.5 text-xs text-slate-400">
                {product.sku} · Stock {product.current_stock}
                {product.days_of_stock_remaining !== null && (
                  <> · {product.days_of_stock_remaining.toFixed(1)}d left</>
                )}
              </p>
            </div>
            <span className="risk-score-pill">{product.risk_score.toFixed(0)}</span>
          </Link>
        ))}
      </div>
    </div>
  )
}
