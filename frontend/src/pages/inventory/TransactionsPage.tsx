/**
 * TransactionsPage — read-only ledger of all stock movements.
 *
 * Supports:
 *   - Pagination
 *   - Filter by transaction type
 *   - Filter by product (via search)
 *   - Date range filter
 *   - Sort by transaction_at (desc by default)
 *
 * Transactions are immutable — no edit or delete controls.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

import { inventoryApi } from '../../api/inventory'
import { productsApi } from '../../api/products'
import type { TransactionType } from '../../types'
import { formatDate, formatCurrency } from '../../utils/format'

import {
  Table, Pagination, EmptyState, PageSpinner, PageHeader,
} from '../../components/common'

// ---------------------------------------------------------------------------
// Transaction type badge colours
// ---------------------------------------------------------------------------
function TxnBadge({ type }: { type: TransactionType }) {
  const cfg: Record<string, { label: string; cls: string }> = {
    STOCK_IN:   { label: 'Stock In',    cls: 'txn-badge-in' },
    STOCK_OUT:  { label: 'Stock Out',   cls: 'txn-badge-out' },
    ADJUSTMENT: { label: 'Adjustment',  cls: 'bg-amber-50 text-amber-700 ring-amber-200/80' },
    WRITE_OFF:  { label: 'Write-off',   cls: 'bg-red-50 text-red-700 ring-red-200/80' },
    TRANSFER:   { label: 'Transfer',    cls: 'bg-slate-100 text-slate-600 ring-slate-200/80' },
  }
  const { label, cls } = cfg[type] ?? { label: type, cls: 'bg-slate-100 text-slate-500 ring-slate-200/80' }
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${cls}`}>
      {label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export function TransactionsPage() {

  const [typeFilter, setTypeFilter] = useState('')
  const [productFilter, setProductFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 25

  const { data, isLoading, isError } = useQuery({
    queryKey: ['transactions', { typeFilter, productFilter, dateFrom, dateTo, page }],
    queryFn: () => inventoryApi.listTransactions({
      transaction_type: typeFilter || undefined,
      product_id: productFilter || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      sort_by: 'transaction_at',
      sort_order: 'desc',
      page,
      page_size: PAGE_SIZE,
    }),
  })

  // Product list for filter dropdown
  const { data: productsData } = useQuery({
    queryKey: ['products', { page_size: 200 }],
    queryFn: () => productsApi.list({ page_size: 200, is_active: undefined }),
  })
  const products = productsData?.items ?? []
  const productNameById = new Map(products.map((p) => [p.id, p.name]))

  function clearFilters() {
    setTypeFilter(''); setProductFilter(''); setDateFrom(''); setDateTo(''); setPage(1)
  }
  const hasFilters = !!(typeFilter || productFilter || dateFrom || dateTo)

  // ---------------------------------------------------------------------------
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Transaction History"
        description="Immutable ledger of every stock movement."
      />

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3">
        {/* Type filter */}
        <div>
          <label className="form-label">Type</label>
          <select value={typeFilter}
            onChange={(e) => { setTypeFilter(e.target.value); setPage(1) }}
            className="select-base w-40">
            <option value="">All types</option>
            <option value="STOCK_IN">Stock In</option>
            <option value="STOCK_OUT">Stock Out</option>
            <option value="ADJUSTMENT">Adjustment</option>
            <option value="WRITE_OFF">Write-off</option>
          </select>
        </div>

        {/* Product filter */}
        <div>
          <label className="form-label">Product</label>
          <select value={productFilter}
            onChange={(e) => { setProductFilter(e.target.value); setPage(1) }}
            className="select-base w-52">
            <option value="">All products</option>
            {products.map((p) => (
              <option key={p.id} value={p.id}>{p.name} ({p.sku})</option>
            ))}
          </select>
        </div>

        {/* Date range */}
        <div>
          <label className="form-label">From</label>
          <input type="datetime-local" className="input-base w-48"
            value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1) }} />
        </div>
        <div>
          <label className="form-label">To</label>
          <input type="datetime-local" className="input-base w-48"
            value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1) }} />
        </div>

        {hasFilters && (
          <button onClick={clearFilters} className="btn-ghost text-sm self-end">
            Clear filters
          </button>
        )}

        {data && (
          <span className="text-sm text-slate-400 self-end">
            {data.total} transaction{data.total !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Table */}
      {isLoading ? <PageSpinner /> : isError ? (
        <div className="card bg-red-50 text-red-700 text-sm">Failed to load transactions.</div>
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title="No transactions found"
          description={hasFilters ? 'Try different filters.' : 'Record your first stock movement to see it here.'}
        />
      ) : (
        <div>
          <Table>
            <Table.Head>
              <Table.Row>
                <Table.Th>Timestamp</Table.Th>
                <Table.Th>Type</Table.Th>
                <Table.Th>Product</Table.Th>
                <Table.Th>Quantity</Table.Th>
                <Table.Th>Unit Cost</Table.Th>
                <Table.Th>Notes / Reason</Table.Th>
                <Table.Th>Ref</Table.Th>
              </Table.Row>
            </Table.Head>
            <Table.Body>
              {data.items.map((txn) => {
                const isNeg = txn.quantity < 0
                return (
                  <Table.Row key={txn.id}>
                    <Table.Td className="whitespace-nowrap text-xs text-slate-500">
                      {formatDate(txn.transaction_at)}
                    </Table.Td>
                    <Table.Td>
                      <TxnBadge type={txn.transaction_type as TransactionType} />
                    </Table.Td>
                    <Table.Td>
                      <span className="text-sm font-medium text-slate-900">
                        {productNameById.get(txn.product_id) ?? 'Unknown product'}
                      </span>
                    </Table.Td>
                    <Table.Td>
                      <span className={`font-semibold tabular-nums ${isNeg ? 'text-red-600' : 'text-green-600'}`}>
                        {isNeg ? '' : '+'}{txn.quantity}
                      </span>
                    </Table.Td>
                    <Table.Td className="text-slate-500">
                      {txn.unit_cost != null ? formatCurrency(txn.unit_cost) : '—'}
                    </Table.Td>
                    <Table.Td className="max-w-xs truncate text-slate-500 text-xs">
                      {txn.notes ?? '—'}
                    </Table.Td>
                    <Table.Td className="text-xs text-slate-400">
                      {txn.reference_type ?? '—'}
                    </Table.Td>
                  </Table.Row>
                )
              })}
            </Table.Body>
          </Table>
          <Pagination page={data.page} pages={data.pages} total={data.total}
            pageSize={PAGE_SIZE} onPageChange={setPage} />
        </div>
      )}
    </div>
  )
}
