/**
 * InventoryPage
 *
 * Main inventory operations page. Shows a per-product stock overview
 * table with quick-action buttons for Stock In, Stock Out, and Adjust.
 *
 * All business logic (FIFO, validation, atomicity) lives on the backend.
 * This page: collects input → calls API → displays results.
 *
 * RBAC:
 *   Stock In / Stock Out → ADMIN, MANAGER, STAFF
 *   Adjustment            → ADMIN, MANAGER only
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

import { analyticsApi } from '../../api/analytics'
import { inventoryApi } from '../../api/inventory'
import { categoriesApi } from '../../api/categories'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useDebounce } from '../../hooks/useDebounce'
import type {
  StockStatusItem, StockOutResponse,
} from '../../types'
import { formatCurrency, formatDate, formatNumber } from '../../utils/format'
import { riskLevelClasses } from '../../utils/risk'

import {
  Table, Badge, Pagination, Modal, EmptyState,
  SearchInput, PageSpinner, PageHeader,
} from '../../components/common'

// ---------------------------------------------------------------------------
// Stock-In form schema — matches backend StockInRequest exactly
// ---------------------------------------------------------------------------
const stockInSchema = z.object({
  quantity: z.coerce.number().int().min(1, 'Quantity must be at least 1'),
  cost_per_unit: z.coerce.number().min(0, 'Cost cannot be negative'),
  batch_number: z.string().max(100).optional(),
  expiry_date: z.string().optional(),
  manufacture_date: z.string().optional(),
  notes: z.string().max(2000).optional(),
})
type StockInForm = z.infer<typeof stockInSchema>

// ---------------------------------------------------------------------------
// Stock-Out form schema
// ---------------------------------------------------------------------------
const stockOutSchema = z.object({
  quantity: z.coerce.number().int().min(1, 'Quantity must be at least 1'),
  notes: z.string().max(2000).optional(),
})
type StockOutForm = z.infer<typeof stockOutSchema>

// ---------------------------------------------------------------------------
// Adjustment form schema
// ---------------------------------------------------------------------------
const adjustmentSchema = z.object({
  quantity_delta: z.coerce.number().int().refine((v) => v !== 0, 'Delta cannot be zero'),
  reason: z.string().min(1, 'Reason is required').max(500),
})
type AdjustmentForm = z.infer<typeof adjustmentSchema>

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export function InventoryPage() {
  const { hasRole } = useAuth()
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const canAdjust = hasRole('ADMIN', 'MANAGER')

  // List state
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [lowStockOnly, setLowStockOnly] = useState(false)
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 25
  const debouncedSearch = useDebounce(search, 350)

  // Selected product for modals
  const [stockInProduct, setStockInProduct] = useState<StockStatusItem | null>(null)
  const [stockOutProduct, setStockOutProduct] = useState<StockStatusItem | null>(null)
  const [adjustProduct, setAdjustProduct] = useState<StockStatusItem | null>(null)

  // Stock-out result (FIFO allocation display)
  const [stockOutResult, setStockOutResult] = useState<StockOutResponse | null>(null)

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------
  const { data, isLoading, isError } = useQuery({
    queryKey: ['stock-status', { search: debouncedSearch, categoryFilter, lowStockOnly, page }],
    queryFn: () => analyticsApi.getStockStatus({
      search: debouncedSearch || undefined,
      category_id: categoryFilter || undefined,
      low_stock_only: lowStockOnly || undefined,
      page, page_size: PAGE_SIZE,
    }),
  })

  const { data: categoriesData } = useQuery({
    queryKey: ['categories', { page_size: 100 }],
    queryFn: () => categoriesApi.list({ page_size: 100 }),
  })
  const categories = categoriesData?.items ?? []

  const handleSearchChange = (v: string) => { setSearch(v); setPage(1) }

  function invalidateAll() {
    queryClient.invalidateQueries({ queryKey: ['stock-status'] })
    queryClient.invalidateQueries({ queryKey: ['products'] })
    queryClient.invalidateQueries({ queryKey: ['analytics'] })
  }

  // ---------------------------------------------------------------------------
  // Stock-In
  // ---------------------------------------------------------------------------
  const stockInForm = useForm<StockInForm>({ resolver: zodResolver(stockInSchema) })
  const stockInMutation = useMutation({
    mutationFn: (vals: StockInForm & { product_id: string }) =>
      inventoryApi.stockIn({
        product_id: vals.product_id,
        quantity: vals.quantity,
        cost_per_unit: vals.cost_per_unit,
        batch_number: vals.batch_number || undefined,
        expiry_date: vals.expiry_date || undefined,
        manufacture_date: vals.manufacture_date || undefined,
        notes: vals.notes || undefined,
      }),
    onSuccess: (resp) => {
      toast.success(`Stock in: +${resp.updated_stock} total units now in stock.`)
      invalidateAll()
      setStockInProduct(null)
      stockInForm.reset()
    },
    onError: (err: { message?: string }) => toast.error(err.message ?? 'Stock-in failed.'),
  })

  // ---------------------------------------------------------------------------
  // Stock-Out
  // ---------------------------------------------------------------------------
  const stockOutForm = useForm<StockOutForm>({ resolver: zodResolver(stockOutSchema) })
  const stockOutMutation = useMutation({
    mutationFn: (vals: StockOutForm & { product_id: string }) =>
      inventoryApi.stockOut({
        product_id: vals.product_id,
        quantity: vals.quantity,
        notes: vals.notes || undefined,
      }),
    onSuccess: (resp) => {
      setStockOutResult(resp)
      invalidateAll()
      setStockOutProduct(null)
      stockOutForm.reset()
    },
    onError: (err: { message?: string }) => toast.error(err.message ?? 'Stock-out failed.'),
  })

  // ---------------------------------------------------------------------------
  // Adjustment
  // ---------------------------------------------------------------------------
  const adjustForm = useForm<AdjustmentForm>({ resolver: zodResolver(adjustmentSchema) })
  const adjustMutation = useMutation({
    mutationFn: (vals: AdjustmentForm & { product_id: string }) =>
      inventoryApi.adjustment({
        product_id: vals.product_id,
        quantity_delta: vals.quantity_delta,
        reason: vals.reason,
      }),
    onSuccess: (resp) => {
      toast.success(`Adjustment applied. New stock: ${resp.updated_stock} units.`)
      invalidateAll()
      setAdjustProduct(null)
      adjustForm.reset()
    },
    onError: (err: { message?: string }) => toast.error(err.message ?? 'Adjustment failed.'),
  })

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div className="flex flex-col gap-5">
      <PageHeader
        title="Inventory"
        description="Current stock levels, values, and quick stock operations."
      />

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <SearchInput value={search} onChange={handleSearchChange}
          placeholder="Search SKU, name…" className="w-64" />
        <select value={categoryFilter}
          onChange={(e) => { setCategoryFilter(e.target.value); setPage(1) }}
          className="select-base w-44" aria-label="Filter by category">
          <option value="">All categories</option>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={lowStockOnly}
            onChange={(e) => { setLowStockOnly(e.target.checked); setPage(1) }}
            className="rounded border-slate-300 text-brand-600" />
          <span className="text-sm text-slate-600">Low stock only</span>
        </label>
        {data && (
          <span className="text-sm text-slate-400">
            {data.total} {data.total === 1 ? 'product' : 'products'}
          </span>
        )}
      </div>

      {/* Table */}
      {isLoading ? <PageSpinner /> : isError ? (
        <div className="card bg-red-50 text-red-700 text-sm">Failed to load inventory.</div>
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title="No inventory found"
          description="Stock in products to start tracking inventory."
        />
      ) : (
        <div>
          <Table>
            <Table.Head>
              <Table.Row>
                <Table.Th>Product</Table.Th>
                <Table.Th>Category</Table.Th>
                <Table.Th>Stock</Table.Th>
                <Table.Th>Reorder at</Table.Th>
                <Table.Th>Value</Table.Th>
                <Table.Th>Nearest Expiry</Table.Th>
                <Table.Th>Risk</Table.Th>
                <Table.Th className="text-right">Actions</Table.Th>
              </Table.Row>
            </Table.Head>
            <Table.Body>
              {data.items.map((item) => (
                <Table.Row key={item.product_id}>
                  <Table.Td>
                    <div>
                      <p className="font-medium text-slate-900">{item.name}</p>
                      <p className="font-mono text-xs text-slate-400">{item.sku}</p>
                    </div>
                  </Table.Td>
                  <Table.Td>
                    <Badge variant="slate">{item.category_name}</Badge>
                  </Table.Td>
                  <Table.Td>
                    <span className={`font-semibold tabular-nums ${item.is_low_stock ? 'text-red-600' : 'text-slate-900'}`}>
                      {formatNumber(item.current_stock)}
                    </span>
                    {item.is_low_stock && <span className="ml-1 text-xs text-red-400">low</span>}
                    <span className="ml-1 text-xs text-slate-400">{item.unit}</span>
                  </Table.Td>
                  <Table.Td className="text-slate-500">{item.reorder_point}</Table.Td>
                  <Table.Td className="font-medium text-slate-700">
                    {formatCurrency(item.inventory_value)}
                  </Table.Td>
                  <Table.Td>
                    <ExpiryCell expiry={item.nearest_expiry} />
                  </Table.Td>
                  <Table.Td>
                    {item.last_risk_level ? (
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${riskLevelClasses(item.last_risk_level)}`}>
                        {item.last_risk_level}
                      </span>
                    ) : <span className="text-xs text-slate-300">—</span>}
                  </Table.Td>
                  <Table.Td>
                    <div className="flex justify-end gap-1">
                      <button onClick={() => { setStockInProduct(item); stockInForm.reset({ cost_per_unit: 0 }) }}
                        className="btn-ghost text-xs text-green-700 hover:bg-green-50">+In</button>
                      <button onClick={() => { setStockOutProduct(item); stockOutForm.reset() }}
                        className="btn-ghost text-xs text-blue-700 hover:bg-blue-50">−Out</button>
                      {canAdjust && (
                        <button onClick={() => { setAdjustProduct(item); adjustForm.reset() }}
                          className="btn-ghost text-xs text-amber-700 hover:bg-amber-50">±Adj</button>
                      )}
                    </div>
                  </Table.Td>
                </Table.Row>
              ))}
            </Table.Body>
          </Table>
          <Pagination page={data.page} pages={data.pages} total={data.total}
            pageSize={PAGE_SIZE} onPageChange={setPage} />
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* STOCK-IN MODAL */}
      {/* ------------------------------------------------------------------ */}
      <Modal isOpen={!!stockInProduct} onClose={() => setStockInProduct(null)}
        title={`Stock In — ${stockInProduct?.name ?? ''}`}>
        <form onSubmit={stockInForm.handleSubmit((vals) =>
          stockInMutation.mutate({ ...vals, product_id: stockInProduct!.product_id })
        )} noValidate className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="form-label">Quantity <span className="text-red-500">*</span></label>
              <input type="number" min={1} className="input-base" {...stockInForm.register('quantity')} />
              {stockInForm.formState.errors.quantity && (
                <p className="form-error">{stockInForm.formState.errors.quantity.message}</p>
              )}
            </div>
            <div>
              <label className="form-label">Cost per unit <span className="text-red-500">*</span></label>
              <input type="number" min={0} step="0.01" className="input-base" {...stockInForm.register('cost_per_unit')} />
              {stockInForm.formState.errors.cost_per_unit && (
                <p className="form-error">{stockInForm.formState.errors.cost_per_unit.message}</p>
              )}
            </div>
            <div>
              <label className="form-label">Batch number</label>
              <input className="input-base" placeholder="e.g. LOT-2025-001" {...stockInForm.register('batch_number')} />
            </div>
            <div>
              <label className="form-label">Expiry date</label>
              <input type="date" className="input-base" {...stockInForm.register('expiry_date')} />
            </div>
            <div>
              <label className="form-label">Manufacture date</label>
              <input type="date" className="input-base" {...stockInForm.register('manufacture_date')} />
            </div>
          </div>
          <div>
            <label className="form-label">Notes</label>
            <textarea rows={2} className="input-base resize-none" {...stockInForm.register('notes')} />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={() => setStockInProduct(null)} className="btn-secondary">Cancel</button>
            <button type="submit" disabled={stockInMutation.isPending} className="btn-primary">
              {stockInMutation.isPending ? 'Recording…' : 'Record Stock In'}
            </button>
          </div>
        </form>
      </Modal>

      {/* ------------------------------------------------------------------ */}
      {/* STOCK-OUT MODAL */}
      {/* ------------------------------------------------------------------ */}
      <Modal isOpen={!!stockOutProduct} onClose={() => setStockOutProduct(null)}
        title={`Stock Out — ${stockOutProduct?.name ?? ''}`}>
        <form onSubmit={stockOutForm.handleSubmit((vals) =>
          stockOutMutation.mutate({ ...vals, product_id: stockOutProduct!.product_id })
        )} noValidate className="space-y-4">
          {stockOutProduct && (
            <div className="rounded-md bg-slate-50 p-3 text-sm">
              <span className="text-slate-500">Available: </span>
              <span className="font-semibold text-slate-900">
                {formatNumber(stockOutProduct.current_stock)} {stockOutProduct.unit}
              </span>
            </div>
          )}
          <div>
            <label className="form-label">Quantity <span className="text-red-500">*</span></label>
            <input type="number" min={1}
              max={stockOutProduct?.current_stock}
              className="input-base" {...stockOutForm.register('quantity')} />
            {stockOutForm.formState.errors.quantity && (
              <p className="form-error">{stockOutForm.formState.errors.quantity.message}</p>
            )}
          </div>
          <div>
            <label className="form-label">Notes</label>
            <textarea rows={2} className="input-base resize-none"
              placeholder="e.g. Dispensed to ward B" {...stockOutForm.register('notes')} />
          </div>
          <p className="text-xs text-slate-400">
            Stock will be allocated using FIFO (oldest batch first).
          </p>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={() => setStockOutProduct(null)} className="btn-secondary">Cancel</button>
            <button type="submit" disabled={stockOutMutation.isPending} className="btn-primary">
              {stockOutMutation.isPending ? 'Processing…' : 'Record Stock Out'}
            </button>
          </div>
        </form>
      </Modal>

      {/* ------------------------------------------------------------------ */}
      {/* ADJUSTMENT MODAL */}
      {/* ------------------------------------------------------------------ */}
      <Modal isOpen={!!adjustProduct} onClose={() => setAdjustProduct(null)}
        title={`Adjust Stock — ${adjustProduct?.name ?? ''}`}>
        <form onSubmit={adjustForm.handleSubmit((vals) =>
          adjustMutation.mutate({ ...vals, product_id: adjustProduct!.product_id })
        )} noValidate className="space-y-4">
          {adjustProduct && (
            <div className="rounded-md bg-slate-50 p-3 text-sm">
              <span className="text-slate-500">Current stock: </span>
              <span className="font-semibold">{formatNumber(adjustProduct.current_stock)} {adjustProduct.unit}</span>
            </div>
          )}
          <div>
            <label className="form-label">
              Quantity delta <span className="text-red-500">*</span>
              <span className="ml-2 text-xs text-slate-400">(positive = increase, negative = decrease)</span>
            </label>
            <input type="number" className="input-base"
              placeholder="e.g. +10 or -5" {...adjustForm.register('quantity_delta')} />
            {adjustForm.formState.errors.quantity_delta && (
              <p className="form-error">{adjustForm.formState.errors.quantity_delta.message}</p>
            )}
          </div>
          <div>
            <label className="form-label">Reason <span className="text-red-500">*</span></label>
            <input className="input-base"
              placeholder="e.g. Count correction after stocktake"
              {...adjustForm.register('reason')} />
            {adjustForm.formState.errors.reason && (
              <p className="form-error">{adjustForm.formState.errors.reason.message}</p>
            )}
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={() => setAdjustProduct(null)} className="btn-secondary">Cancel</button>
            <button type="submit" disabled={adjustMutation.isPending} className="btn-primary">
              {adjustMutation.isPending ? 'Applying…' : 'Apply Adjustment'}
            </button>
          </div>
        </form>
      </Modal>

      {/* ------------------------------------------------------------------ */}
      {/* STOCK-OUT FIFO RESULT MODAL */}
      {/* ------------------------------------------------------------------ */}
      <Modal isOpen={!!stockOutResult} onClose={() => setStockOutResult(null)}
        title="Stock Out Complete — FIFO Allocation">
        {stockOutResult && (
          <div className="space-y-4">
            <div className="rounded-md bg-green-50 p-3 text-sm text-green-800">
              ✓ {stockOutResult.total_quantity} units removed.
              Remaining stock: <strong>{stockOutResult.updated_stock}</strong>
            </div>
            <div>
              <p className="mb-2 text-sm font-medium text-slate-700">Batch allocation (FIFO):</p>
              <Table>
                <Table.Head>
                  <Table.Row>
                    <Table.Th>Batch</Table.Th>
                    <Table.Th>Units taken</Table.Th>
                    <Table.Th>Cost/unit</Table.Th>
                    <Table.Th>Expiry</Table.Th>
                  </Table.Row>
                </Table.Head>
                <Table.Body>
                  {stockOutResult.allocations.map((alloc) => (
                    <Table.Row key={alloc.batch_id}>
                      <Table.Td>
                        <span className="font-mono text-xs">
                          {alloc.batch_number ?? alloc.batch_id.slice(0, 8) + '…'}
                        </span>
                      </Table.Td>
                      <Table.Td>
                        <span className="font-semibold text-blue-700">{alloc.quantity_taken}</span>
                      </Table.Td>
                      <Table.Td>{formatCurrency(alloc.cost_per_unit)}</Table.Td>
                      <Table.Td>{alloc.expiry_date ? formatDate(alloc.expiry_date) : '—'}</Table.Td>
                    </Table.Row>
                  ))}
                </Table.Body>
              </Table>
            </div>
            <div className="flex justify-end">
              <button onClick={() => setStockOutResult(null)} className="btn-primary">Done</button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------
function ExpiryCell({ expiry }: { expiry: string | null }) {
  if (!expiry) return <span className="text-slate-300 text-xs">—</span>
  const daysLeft = Math.ceil(
    (new Date(expiry).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
  )
  const cls = daysLeft <= 0
    ? 'text-red-600 font-semibold'
    : daysLeft <= 30
    ? 'text-orange-600 font-medium'
    : daysLeft <= 90
    ? 'text-amber-600'
    : 'text-slate-500'
  return (
    <span className={`text-xs ${cls}`}>
      {formatDate(expiry)}
      {daysLeft <= 30 && daysLeft > 0 && <span className="ml-1">({daysLeft}d)</span>}
      {daysLeft <= 0 && <span className="ml-1">(expired)</span>}
    </span>
  )
}
