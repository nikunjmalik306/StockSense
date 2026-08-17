/**
 * ExpiringInventoryCard — displays batches expiring within 30 days
 */
import { useEffect, useState } from 'react'
import { analyticsApi } from '../../api'
import type { ExpiringBatch } from '../../types'
import { Spinner } from '../common'

export function ExpiringInventoryCard() {
  const [batches, setBatches] = useState<ExpiringBatch[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function fetchExpiring() {
      try {
        setLoading(true)
        const data = await analyticsApi.getExpiringBatches({ days: 30, page: 1, page_size: 5 })
        setBatches(data.items)
        setTotal(data.total)
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Failed to load expiring inventory')
      } finally {
        setLoading(false)
      }
    }
    fetchExpiring()
  }, [])

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Expiring Inventory</h3>
        <div className="flex items-center justify-center h-48">
          <Spinner size="lg" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Expiring Inventory</h3>
        <div className="text-red-600 text-sm">{error}</div>
      </div>
    )
  }

  if (batches.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Expiring Inventory</h3>
        <div className="text-green-600 text-sm py-8 text-center flex flex-col items-center gap-2">
          <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>No batches expiring within 30 days</span>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">Expiring Inventory</h3>
        {total > 5 && (
          <span className="text-sm text-gray-600">{total} total within 30 days</span>
        )}
      </div>

      <div className="space-y-2">
        {batches.map((batch) => {
          const isExpired = batch.days_until_expiry < 0
          const isCritical = batch.days_until_expiry <= 7 && batch.days_until_expiry >= 0
          
          const bgColor = isExpired ? 'bg-red-50 border-red-300' : isCritical ? 'bg-orange-50 border-orange-300' : 'bg-yellow-50 border-yellow-200'
          const textColor = isExpired ? 'text-red-700' : isCritical ? 'text-orange-700' : 'text-yellow-700'
          
          return (
            <div
              key={batch.batch_id}
              className={`p-3 rounded-lg border ${bgColor}`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-gray-900 truncate mb-1">
                    {batch.product_name}
                  </div>
                  <div className="text-sm text-gray-600">
                    {batch.sku} • Batch: {batch.batch_number || 'N/A'}
                  </div>
                  <div className={`text-sm font-medium ${textColor} mt-1`}>
                    {isExpired ? (
                      <>EXPIRED {Math.abs(batch.days_until_expiry)} days ago</>
                    ) : (
                      <>Expires in {batch.days_until_expiry} day{batch.days_until_expiry !== 1 ? 's' : ''}</>
                    )}
                  </div>
                </div>
                <div className="text-right ml-3">
                  <div className="text-sm font-semibold text-gray-900">
                    {batch.remaining_qty} {batch.unit}
                  </div>
                  <div className="text-xs text-gray-500">
                    ${batch.estimated_value.toFixed(2)}
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
