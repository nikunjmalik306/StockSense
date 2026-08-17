/**
 * InventoryRiskPage — comprehensive inventory risk analysis
 *
 * Features:
 * - Searchable/paginated risk table
 * - Risk score, level, stock, demand metrics
 * - Detailed product risk modal with sub-scores and contributing factors
 * - Filter by risk level
 */
import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { analyticsApi } from '../../api'
import { Badge, Pagination, SearchInput, Spinner, EmptyState, Modal, PageHeader } from '../../components/common'

export function InventoryRiskPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [search, setSearch] = useState(searchParams.get('search') || '')
  const [riskLevel, setRiskLevel] = useState<string>(searchParams.get('risk_level') || '')
  const [page, setPage] = useState(Number(searchParams.get('page')) || 1)
  const [selectedProductId, setSelectedProductId] = useState<string | null>(
    searchParams.get('product_id') || null
  )

  // Update URL when filters change
  useEffect(() => {
    const params: Record<string, string> = {}
    if (search) params.search = search
    if (riskLevel) params.risk_level = riskLevel
    if (page > 1) params.page = String(page)
    if (selectedProductId) params.product_id = selectedProductId
    setSearchParams(params)
  }, [search, riskLevel, page, selectedProductId, setSearchParams])

  const { data, isLoading } = useQuery({
    queryKey: ['analytics', 'inventory-risk', { search, riskLevel, page }],
    queryFn: () => analyticsApi.getInventoryRisk({
      search: search || undefined,
      risk_level: riskLevel || undefined,
      page,
      page_size: 25,
    }),
  })

  const handleSearch = (value: string) => {
    setSearch(value)
    setPage(1)
  }

  const handleRiskLevelFilter = (level: string) => {
    setRiskLevel(level === riskLevel ? '' : level)
    setPage(1)
  }

  const handlePageChange = (newPage: number) => {
    setPage(newPage)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <div className="flex flex-col gap-5">
        <PageHeader
        title="Inventory Risk Analysis"
        description="Identify risky products, understand severity, and see recommended actions"
      />

      {/* Filters */}
      <div className="panel">
        <div className="panel-body flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="flex-1">
            <SearchInput
              value={search}
              onChange={handleSearch}
              placeholder="Search by product name or SKU..."
            />
          </div>
          <div className="flex flex-wrap gap-2">
            {(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const).map((level) => (
              <button
                key={level}
                onClick={() => handleRiskLevelFilter(level)}
                className={`filter-chip ${riskLevel === level ? 'filter-chip-active' : ''}`}
              >
                {level.charAt(0) + level.slice(1).toLowerCase()}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Risk table */}
      <div className="panel overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Spinner size="lg" />
          </div>
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            title="No products found"
            description={search || riskLevel ? 'Try adjusting your filters' : 'No risk data available'}
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="table-base">
                <thead>
                  <tr>
                    <th>Product</th>
                    <th className="text-right">Risk Score</th>
                    <th className="text-center">Risk Level</th>
                    <th className="text-right">Current Stock</th>
                    <th className="text-right">Avg Daily Demand</th>
                    <th className="text-right">Days Remaining</th>
                    <th>Recommended Action</th>
                    <th className="text-center">Details</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((product) => (
                    <tr key={product.product_id}>
                      <td>
                        <div className="font-medium text-slate-900">{product.name}</div>
                        <div className="text-xs text-slate-500">{product.sku}</div>
                      </td>
                      <td className="text-right">
                        <span className="font-semibold tabular-nums text-slate-900">
                          {product.risk_score.toFixed(1)}
                        </span>
                      </td>
                      <td className="text-center">
                        <Badge variant={product.risk_level}>{product.risk_level}</Badge>
                      </td>
                      <td className="text-right tabular-nums">{product.current_stock}</td>
                      <td className="text-right tabular-nums">{product.average_daily_demand.toFixed(1)}</td>
                      <td className="text-right tabular-nums">
                        {product.days_of_stock_remaining !== null
                          ? product.days_of_stock_remaining.toFixed(1)
                          : 'N/A'}
                      </td>
                      <td className="max-w-xs truncate text-slate-600">{product.recommended_action}</td>
                      <td className="text-center">
                        <button
                          onClick={() => setSelectedProductId(product.product_id)}
                          className="link-subtle"
                        >
                          View →
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {data.pages > 1 && (
              <div className="border-t border-slate-200 px-4 py-3">
                <Pagination
                  page={page}
                  pages={data.pages}
                  total={data.total}
                  pageSize={data.page_size}
                  onPageChange={handlePageChange}
                />
              </div>
            )}
          </>
        )}
      </div>

      {/* Product risk detail modal */}
      {selectedProductId && (
        <ProductRiskDetailModal
          productId={selectedProductId}
          onClose={() => setSelectedProductId(null)}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Product Risk Detail Modal
// ---------------------------------------------------------------------------

function ProductRiskDetailModal({ productId, onClose }: { productId: string; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ['analytics', 'product-risk', productId],
    queryFn: () => analyticsApi.getProductRisk(productId),
  })

  if (isLoading) {
    return (
      <Modal isOpen onClose={onClose} title="Product Risk Detail">
        <div className="flex items-center justify-center py-12">
          <Spinner size="lg" />
        </div>
      </Modal>
    )
  }

  if (!data) {
    return (
      <Modal isOpen onClose={onClose} title="Product Risk Detail">
        <div className="text-red-600 text-sm">Failed to load risk details</div>
      </Modal>
    )
  }

  return (
    <Modal
      isOpen
      onClose={onClose}
      title={`Risk Analysis: ${data.name}`}
      size="xl"
    >
      <div className="space-y-6">
        {/* Header with overall risk */}
        <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 p-4">
          <div>
            <div className="text-sm text-slate-600">Overall Risk Score</div>
            <div className="text-3xl font-bold tabular-nums text-slate-900">{data.risk_score.toFixed(1)}</div>
          </div>
          <Badge variant={data.risk_level} size="lg">
            {data.risk_level}
          </Badge>
        </div>

        {/* Key metrics */}
        <div className="grid grid-cols-2 gap-4">
          <div className="p-3 bg-slate-50 rounded-lg">
            <div className="text-xs text-slate-600 uppercase tracking-wide">Current Stock</div>
            <div className="text-xl font-semibold text-slate-900 mt-1">
              {data.current_stock} {data.unit}
            </div>
          </div>
          <div className="p-3 bg-slate-50 rounded-lg">
            <div className="text-xs text-slate-600 uppercase tracking-wide">Reorder Point</div>
            <div className="text-xl font-semibold text-slate-900 mt-1">
              {data.reorder_point} {data.unit}
            </div>
          </div>
          <div className="p-3 bg-slate-50 rounded-lg">
            <div className="text-xs text-slate-600 uppercase tracking-wide">Avg Daily Demand</div>
            <div className="text-xl font-semibold text-slate-900 mt-1">
              {data.average_daily_demand.toFixed(1)} {data.unit}/day
            </div>
          </div>
          <div className="p-3 bg-slate-50 rounded-lg">
            <div className="text-xs text-slate-600 uppercase tracking-wide">Days Remaining</div>
            <div className="text-xl font-semibold text-slate-900 mt-1">
              {data.days_of_stock_remaining !== null
                ? `${data.days_of_stock_remaining.toFixed(1)} days`
                : 'N/A'}
            </div>
          </div>
        </div>

        {/* Sub-scores */}
        <div>
          <h3 className="text-sm font-semibold text-slate-900 mb-3">Risk Components</h3>
          <div className="space-y-2">
            <RiskSubScore
              label="Stockout Risk"
              score={data.stockout_risk_score}
              weight={0.40}
            />
            <RiskSubScore
              label="Expiry Risk"
              score={data.expiry_risk_score}
              weight={0.35}
            />
            <RiskSubScore
              label="Overstock Risk"
              score={data.overstock_risk_score}
              weight={0.15}
            />
            <RiskSubScore
              label="Demand Velocity"
              score={data.demand_velocity_score}
              weight={0.10}
            />
          </div>
        </div>

        {/* Contributing factors */}
        {data.contributing_factors && data.contributing_factors.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-slate-900 mb-3">Explanation</h3>
            <div className="space-y-2">
              {data.contributing_factors.map((factor, index) => (
                <div key={index} className="rounded-md border border-slate-200 bg-slate-50/80 p-3">
                  <div className="mb-1 flex items-start justify-between">
                    <span className="text-sm font-medium capitalize text-slate-900">
                      {factor.name.replace(/_/g, ' ')}
                    </span>
                    {factor.weight > 0 && (
                      <span className="text-xs tabular-nums text-slate-500">
                        {factor.score.toFixed(1)} × {(factor.weight * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-slate-600">{factor.explanation}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Demand metrics */}
        <div>
          <h3 className="text-sm font-semibold text-slate-900 mb-3">Demand Metrics</h3>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <span className="text-slate-600">Avg Daily:</span>
              <span className="ml-2 font-medium text-slate-900">
                {data.average_daily_demand.toFixed(1)}
              </span>
            </div>
            <div>
              <span className="text-slate-600">Recent Daily:</span>
              <span className="ml-2 font-medium text-slate-900">
                {data.recent_daily_demand.toFixed(1)}
              </span>
            </div>
            <div>
              <span className="text-slate-600">Trend:</span>
              <span className="ml-2 font-medium text-slate-900 capitalize">
                {data.demand_velocity_trend}
              </span>
            </div>
          </div>
        </div>

        {/* Expiry information */}
        {data.earliest_expiry_date && (
          <div>
            <h3 className="text-sm font-semibold text-slate-900 mb-2">Expiry Information</h3>
            <div className="rounded-md border border-amber-200/80 bg-amber-50/50 p-3 text-sm text-slate-700">
              <div className="text-slate-700">
                Earliest batch expires: <span className="font-medium">{data.earliest_expiry_date}</span>
              </div>
              {data.estimated_waste_value > 0 && (
                <div className="text-slate-700 mt-1">
                  Estimated waste value: <span className="font-semibold text-red-700">
                    ${data.estimated_waste_value.toFixed(2)}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Projected stockout */}
        {data.projected_stockout_date && (
          <div className="rounded-md border border-red-200/80 bg-red-50/50 p-3 text-sm text-slate-700">
            <span className="font-medium text-red-800">Projected stockout date:</span>
            <span className="ml-2 text-red-700">{data.projected_stockout_date}</span>
          </div>
        )}

        {/* Recommended action */}
        <div>
          <h3 className="text-sm font-semibold text-slate-900 mb-2">Recommended Action</h3>
          <div className="rounded-md border border-emerald-200/80 bg-emerald-50/40 p-3">
            <p className="text-sm text-slate-700">{data.recommended_action}</p>
          </div>
        </div>
      </div>
    </Modal>
  )
}

function RiskSubScore({ label, score, weight }: { label: string; score: number; weight: number }) {
  const percentage = score
  const contribution = score * weight

  return (
    <div>
      <div className="flex items-center justify-between text-sm mb-1">
        <span className="text-slate-700">{label}</span>
        <span className="text-slate-600">
          {score.toFixed(1)} × {(weight * 100).toFixed(0)}% = {contribution.toFixed(1)}
        </span>
      </div>
      <div className="w-full bg-slate-200 rounded-full h-2">
        <div
          className={`h-2 rounded-full transition-all duration-300 ${
            score >= 75
              ? 'bg-red-600'
              : score >= 50
              ? 'bg-orange-500'
              : score >= 25
              ? 'bg-yellow-500'
              : 'bg-green-500'
          }`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  )
}
