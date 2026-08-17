/**
 * RiskDistributionCard — inventory health breakdown
 */
import { useEffect, useState } from 'react'
import { analyticsApi } from '../../api'
import type { RiskDistribution } from '../../types'
import { Spinner } from '../common'

const RISK_ITEMS = [
  { key: 'critical' as const, label: 'Critical', bar: 'bg-red-500', text: 'text-red-700' },
  { key: 'high' as const, label: 'High', bar: 'bg-orange-400', text: 'text-orange-700' },
  { key: 'medium' as const, label: 'Medium', bar: 'bg-amber-400', text: 'text-amber-700' },
  { key: 'low' as const, label: 'Low', bar: 'bg-emerald-400', text: 'text-emerald-700' },
]

export function RiskDistributionCard() {
  const [distribution, setDistribution] = useState<RiskDistribution | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function fetchDistribution() {
      try {
        setLoading(true)
        const data = await analyticsApi.getRiskDistribution()
        setDistribution(data)
      } catch (err: unknown) {
        const message = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        setError(message || 'Failed to load risk distribution')
      } finally {
        setLoading(false)
      }
    }
    fetchDistribution()
  }, [])

  if (loading) {
    return (
      <div className="panel">
        <div className="panel-header py-3">
          <h3 className="section-heading">Inventory health</h3>
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
          <h3 className="section-heading">Inventory health</h3>
        </div>
        <div className="panel-body text-sm text-red-600">{error}</div>
      </div>
    )
  }

  if (!distribution) return null

  const total = distribution.total || 1

  return (
    <div className="panel">
      <div className="panel-header py-3">
        <h3 className="section-heading">Inventory health</h3>
        <p className="section-description">Risk distribution across active products</p>
      </div>
      <div className="panel-body space-y-2.5 pt-3 pb-4">
        {RISK_ITEMS.map((item) => {
          const value = distribution[item.key]
          const percentage = total > 0 ? (value / total) * 100 : 0
          return (
            <div key={item.key}>
              <div className="mb-1 flex items-center justify-between text-sm">
                <span className={`font-medium ${item.text}`}>{item.label}</span>
                <span className="tabular-nums text-slate-600">
                  {value}
                  <span className="ml-1 text-slate-400">({percentage.toFixed(0)}%)</span>
                </span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                  className={`${item.bar} h-full rounded-full transition-all duration-300`}
                  style={{ width: `${percentage}%` }}
                />
              </div>
            </div>
          )
        })}
        <p className="border-t border-slate-100 pt-2.5 text-xs text-slate-400">
          {distribution.total} active products monitored
        </p>
      </div>
    </div>
  )
}
