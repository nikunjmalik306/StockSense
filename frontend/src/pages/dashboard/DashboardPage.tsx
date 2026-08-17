/**
 * DashboardPage — focused operational overview.
 */
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { analyticsApi } from '../../api/analytics'
import { useAuth } from '../../context/AuthContext'
import type { TransactionType } from '../../types'
import { formatCurrency, formatNumber, formatDate } from '../../utils/format'
import { PageHeader, PageSpinner } from '../../components/common'
import { RiskDistributionCard, HighRiskProductsCard } from '../../components/risk'

function KpiCard({
  label,
  value,
  sub,
  variant = 'default',
}: {
  label: string
  value: string
  sub?: string
  variant?: 'default' | 'amber' | 'slate'
}) {
  return (
    <div className={`kpi-card ${variant === 'amber' ? 'kpi-card--amber' : ''} ${variant === 'slate' ? 'kpi-card--slate' : ''}`}>
      <p className="section-label">{label}</p>
      <p className="kpi-card__value">{value}</p>
      {sub && <p className="kpi-card__sub">{sub}</p>}
    </div>
  )
}

function TxnBadge({ type }: { type: TransactionType }) {
  const map: Record<string, string> = {
    STOCK_IN: 'txn-badge-in',
    STOCK_OUT: 'txn-badge-out',
    ADJUSTMENT: 'bg-amber-50 text-amber-700 ring-amber-200/80',
    WRITE_OFF: 'bg-red-50 text-red-700 ring-red-200/80',
  }
  const labels: Record<string, string> = {
    STOCK_IN: 'In',
    STOCK_OUT: 'Out',
    ADJUSTMENT: 'Adj',
    WRITE_OFF: 'WO',
  }
  return (
    <span className={`inline-flex rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${map[type] ?? 'bg-slate-100 text-slate-500 ring-slate-200/80'}`}>
      {labels[type] ?? type}
    </span>
  )
}

export function DashboardPage() {
  const { user } = useAuth()

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ['analytics', 'overview'],
    queryFn: () => analyticsApi.getOverview(),
  })

  const { data: riskDist } = useQuery({
    queryKey: ['analytics', 'risk-distribution'],
    queryFn: () => analyticsApi.getRiskDistribution(),
  })

  const { data: recentTxns } = useQuery({
    queryKey: ['analytics', 'recent-transactions'],
    queryFn: () => analyticsApi.getRecentTransactions(8),
  })

  const productsAtRisk = riskDist
    ? riskDist.critical + riskDist.high + riskDist.medium
    : null

  const riskBreakdown = riskDist && productsAtRisk && productsAtRisk > 0
    ? [
        riskDist.critical > 0 ? `${riskDist.critical} critical` : null,
        riskDist.high > 0 ? `${riskDist.high} high` : null,
        riskDist.medium > 0 ? `${riskDist.medium} medium` : null,
      ].filter(Boolean).join(' · ')
    : null

  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Dashboard"
        description={`Good to see you, ${user?.full_name ?? user?.username}. Here is what needs your attention today.`}
      />

      {overviewLoading ? (
        <PageSpinner />
      ) : overview ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <KpiCard
            label="Total Products"
            value={formatNumber(overview.total_products)}
            sub={`${formatNumber(overview.total_inventory_units)} units on hand`}
            variant="slate"
          />
          <KpiCard
            label="Inventory Value"
            value={formatCurrency(overview.inventory_value)}
            sub="batch cost basis"
          />
          <KpiCard
            label="Products At Risk"
            value={productsAtRisk !== null ? String(productsAtRisk) : '—'}
            sub={riskBreakdown ?? 'medium risk or higher'}
            variant={productsAtRisk && productsAtRisk > 0 ? 'amber' : 'slate'}
          />
          <KpiCard
            label="Expiring Soon"
            value={String(overview.expiring_soon_count)}
            sub={
              overview.out_of_stock_count > 0
                ? `${overview.out_of_stock_count} out of stock · within 30 days`
                : 'within 30 days'
            }
            variant={overview.expiring_soon_count > 0 ? 'amber' : 'slate'}
          />
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 lg:items-start">
        <RiskDistributionCard />
        <HighRiskProductsCard />
      </div>

      <div className="panel">
        <div className="panel-header flex items-center justify-between py-3">
          <div>
            <h2 className="section-heading">Recent inventory activity</h2>
            <p className="section-description">Latest stock movements across your catalog</p>
          </div>
          <Link to="/transactions" className="link-subtle">
            View all →
          </Link>
        </div>
        <div className="panel-body pt-2 pb-3">
          {!recentTxns || recentTxns.length === 0 ? (
            <p className="py-6 text-center text-sm text-slate-400">No transactions yet.</p>
          ) : (
            <div className="divide-y divide-slate-100">
              {recentTxns.map((txn) => {
                const isOut = txn.transaction_type === 'STOCK_OUT' || txn.quantity < 0
                return (
                  <div key={txn.id} className="flex items-center justify-between py-2.5 text-sm">
                    <div className="flex min-w-0 items-center gap-3">
                      <TxnBadge type={txn.transaction_type as TransactionType} />
                      <div className="min-w-0">
                        <p className="truncate font-medium text-slate-900">{txn.product_name}</p>
                        <p className="text-xs text-slate-400">
                          {txn.product_sku} · {txn.performed_by_username}
                        </p>
                      </div>
                    </div>
                    <div className="ml-4 flex flex-shrink-0 flex-col items-end">
                      <span className={`text-base font-semibold tabular-nums ${isOut ? 'text-brand-700' : 'text-emerald-700'}`}>
                        {txn.quantity > 0 ? '+' : ''}{txn.quantity}
                      </span>
                      <span className="text-xs text-slate-400">{formatDate(txn.transaction_at)}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
