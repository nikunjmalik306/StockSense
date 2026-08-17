/**
 * ProductsPage
 *
 * Lists products with search, category/supplier filter, sort, pagination.
 * ADMIN/MANAGER: create + edit. ADMIN only: delete (soft).
 * STAFF: read-only.
 *
 * Form fields match the backend ProductCreateRequest / ProductUpdateRequest
 * schemas exactly — no invented fields.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

import { productsApi } from '../../api/products'
import { categoriesApi } from '../../api/categories'
import { suppliersApi } from '../../api/suppliers'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useDebounce } from '../../hooks/useDebounce'
import type { ProductListItem } from '../../types'
import { riskLevelClasses } from '../../utils/risk'

import {
  Table,
  Badge,
  StatusBadge,
  Pagination,
  Modal,
  ConfirmDialog,
  EmptyState,
  SearchInput,
  PageSpinner,
} from '../../components/common'

// ---------------------------------------------------------------------------
// Form schema — matches backend ProductCreateRequest exactly
// ---------------------------------------------------------------------------

const productSchema = z
  .object({
    sku: z.string().min(1, 'SKU is required').max(100),
    name: z.string().min(1, 'Name is required').max(255),
    description: z.string().max(2000).optional(),
    category_id: z.string().min(1, 'Category is required'),
    supplier_id: z.string().optional(),
    unit: z.string().min(1).max(50).default('units'),
    reorder_point: z.coerce.number().int().min(0).default(10),
    reorder_quantity: z.coerce.number().int().min(1).default(50),
    // empty string → undefined; otherwise coerce to number
    max_stock_level: z.union([
      z.literal(''),
      z.coerce.number().int().min(1),
    ]).optional(),
    expiry_alert_days: z.coerce.number().int().min(1).default(30),
  })
  .refine(
    (v) => {
      if (!v.max_stock_level) return true
      return Number(v.max_stock_level) > v.reorder_point
    },
    { message: 'Max stock level must exceed reorder point', path: ['max_stock_level'] },
  )

type ProductFormValues = z.infer<typeof productSchema>

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ProductsPage() {
  const { hasRole } = useAuth()
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const canCreate = hasRole('ADMIN', 'MANAGER')
  const canDelete = hasRole('ADMIN')

  // List / filter state
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [supplierFilter, setSupplierFilter] = useState('')
  const [sortBy, setSortBy] = useState('name')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 20
  const debouncedSearch = useDebounce(search, 350)

  // Modal state
  const [modalOpen, setModalOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<ProductListItem | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ProductListItem | null>(null)

  // ---------------------------------------------------------------------------
  // Queries
  // ---------------------------------------------------------------------------

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['products', { search: debouncedSearch, categoryFilter, supplierFilter, sortBy, sortOrder, page }],
    queryFn: () =>
      productsApi.list({
        search: debouncedSearch || undefined,
        category_id: categoryFilter || undefined,
        supplier_id: supplierFilter || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
        page,
        page_size: PAGE_SIZE,
        is_active: true,
      }),
  })

  // Fetch all categories (for filter dropdown + form select)
  const { data: categoriesData } = useQuery({
    queryKey: ['categories', { page_size: 100 }],
    queryFn: () => categoriesApi.list({ page_size: 100 }),
  })

  // Fetch all suppliers (for filter dropdown + form select)
  const { data: suppliersData } = useQuery({
    queryKey: ['suppliers', { is_active: true, page_size: 100 }],
    queryFn: () => suppliersApi.list({ is_active: true, page_size: 100 }),
  })

  const categories = categoriesData?.items ?? []
  const suppliers = suppliersData?.items ?? []

  const handleSearchChange = (value: string) => {
    setSearch(value)
    setPage(1)
  }

  // ---------------------------------------------------------------------------
  // Sort toggle
  // ---------------------------------------------------------------------------

  function handleSort(field: string) {
    if (sortBy === field) {
      setSortOrder((o) => (o === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortBy(field)
      setSortOrder('asc')
    }
    setPage(1)
  }

  function SortIndicator({ field }: { field: string }) {
    if (sortBy !== field) return <span className="ml-1 text-slate-300">↕</span>
    return <span className="ml-1">{sortOrder === 'asc' ? '↑' : '↓'}</span>
  }

  // ---------------------------------------------------------------------------
  // Mutations
  // ---------------------------------------------------------------------------

  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } =
    useForm<ProductFormValues>({ resolver: zodResolver(productSchema) })

  const createMutation = useMutation({
    mutationFn: (data: ProductFormValues) =>
      productsApi.create({
        sku: data.sku,
        name: data.name,
        description: data.description || undefined,
        category_id: data.category_id,
        supplier_id: data.supplier_id || undefined,
        unit: data.unit,
        reorder_point: data.reorder_point,
        reorder_quantity: data.reorder_quantity,
        max_stock_level: data.max_stock_level ? Number(data.max_stock_level) : undefined,
        expiry_alert_days: data.expiry_alert_days,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
      toast.success('Product created.')
      closeModal()
    },
    onError: (err: { message?: string }) => {
      toast.error(err.message ?? 'Failed to create product.')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: ProductFormValues }) =>
      productsApi.update(id, {
        name: data.name,
        description: data.description || undefined,
        category_id: data.category_id,
        supplier_id: data.supplier_id || undefined,
        unit: data.unit,
        reorder_point: data.reorder_point,
        reorder_quantity: data.reorder_quantity,
        max_stock_level: data.max_stock_level ? Number(data.max_stock_level) : undefined,
        expiry_alert_days: data.expiry_alert_days,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
      toast.success('Product updated.')
      closeModal()
    },
    onError: (err: { message?: string }) => {
      toast.error(err.message ?? 'Failed to update product.')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: productsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
      toast.success('Product deactivated.')
      setDeleteTarget(null)
    },
    onError: (err: { message?: string }) => {
      toast.error(err.message ?? 'Failed to deactivate product.')
      setDeleteTarget(null)
    },
  })

  // ---------------------------------------------------------------------------
  // Modal helpers
  // ---------------------------------------------------------------------------

  function openCreate() {
    setEditTarget(null)
    reset({
      sku: '',
      name: '',
      description: '',
      category_id: '',
      supplier_id: '',
      unit: 'units',
      reorder_point: 10,
      reorder_quantity: 50,
      max_stock_level: '',
      expiry_alert_days: 30,
    })
    setModalOpen(true)
  }

  function openEdit(product: ProductListItem) {
    setEditTarget(product)
    reset({
      sku: product.sku,
      name: product.name,
      description: '',
      category_id: product.category_id,
      supplier_id: product.supplier_id ?? '',
      unit: product.unit,
      reorder_point: product.reorder_point,
      reorder_quantity: 50,
      max_stock_level: product.max_stock_level ?? '',
      expiry_alert_days: 30,
    })
    setModalOpen(true)
  }

  function closeModal() {
    setModalOpen(false)
    setEditTarget(null)
    reset()
  }

  async function onSubmit(values: ProductFormValues) {
    if (editTarget) {
      await updateMutation.mutateAsync({ id: editTarget.id, data: values })
    } else {
      await createMutation.mutateAsync(values)
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="page-title">Products</h1>
          <p className="page-subtitle">
            Manage product catalog, thresholds, and supplier assignments.
          </p>
        </div>
        {canCreate && (
          <button onClick={openCreate} className="btn-primary">
            + New Product
          </button>
        )}
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <SearchInput
          value={search}
          onChange={handleSearchChange}
          placeholder="Search SKU, name…"
          className="w-64"
        />
        {/* Category filter */}
        <select
          value={categoryFilter}
          onChange={(e) => { setCategoryFilter(e.target.value); setPage(1) }}
          className="select-base w-44"
          aria-label="Filter by category"
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        {/* Supplier filter */}
        <select
          value={supplierFilter}
          onChange={(e) => { setSupplierFilter(e.target.value); setPage(1) }}
          className="select-base w-44"
          aria-label="Filter by supplier"
        >
          <option value="">All suppliers</option>
          {suppliers.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
        {data && (
          <span className="text-sm text-slate-400">
            {data.total} {data.total === 1 ? 'product' : 'products'}
          </span>
        )}
      </div>

      {/* Content */}
      {isLoading ? (
        <PageSpinner />
      ) : isError ? (
        <ErrorState message={(error as { message?: string })?.message} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title={search || categoryFilter || supplierFilter ? 'No products match your filters.' : 'No products yet.'}
          description="Add your first product to start tracking inventory."
          action={
            canCreate ? (
              <button onClick={openCreate} className="btn-primary">
                + New Product
              </button>
            ) : undefined
          }
        />
      ) : (
        <div>
          <Table>
            <Table.Head>
              <Table.Row>
                <Table.Th>
                  <button className="hover:text-slate-700" onClick={() => handleSort('sku')}>
                    SKU <SortIndicator field="sku" />
                  </button>
                </Table.Th>
                <Table.Th>
                  <button className="hover:text-slate-700" onClick={() => handleSort('name')}>
                    Name <SortIndicator field="name" />
                  </button>
                </Table.Th>
                <Table.Th>Category</Table.Th>
                <Table.Th>Supplier</Table.Th>
                <Table.Th>
                  <button className="hover:text-slate-700" onClick={() => handleSort('current_stock')}>
                    Stock <SortIndicator field="current_stock" />
                  </button>
                </Table.Th>
                <Table.Th>Reorder</Table.Th>
                <Table.Th>Risk</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th className="w-28 text-right">Actions</Table.Th>
              </Table.Row>
            </Table.Head>
            <Table.Body>
              {data.items.map((product) => (
                <Table.Row key={product.id}>
                  <Table.Td>
                    <span className="font-mono text-xs text-slate-600">{product.sku}</span>
                  </Table.Td>
                  <Table.Td>
                    <span className="font-medium text-slate-900">{product.name}</span>
                    <span className="ml-1.5 text-xs text-slate-400">{product.unit}</span>
                  </Table.Td>
                  <Table.Td>
                    <Badge variant="slate">{product.category_name}</Badge>
                  </Table.Td>
                  <Table.Td className="text-slate-500">
                    {product.supplier_name ?? <span className="italic text-slate-300">—</span>}
                  </Table.Td>
                  <Table.Td>
                    <StockCell
                      current={product.current_stock}
                      reorderPoint={product.reorder_point}
                    />
                  </Table.Td>
                  <Table.Td className="text-slate-500">{product.reorder_point}</Table.Td>
                  <Table.Td>
                    {product.last_risk_level ? (
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${riskLevelClasses(product.last_risk_level)}`}
                      >
                        {product.last_risk_level}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-300">N/A</span>
                    )}
                  </Table.Td>
                  <Table.Td>
                    <StatusBadge active={product.is_active} />
                  </Table.Td>
                  <Table.Td>
                    <div className="flex justify-end gap-2">
                      {canCreate && (
                        <button onClick={() => openEdit(product)} className="btn-ghost text-xs">
                          Edit
                        </button>
                      )}
                      {canDelete && (
                        <button
                          onClick={() => setDeleteTarget(product)}
                          className="btn-ghost text-xs text-red-500 hover:text-red-700"
                        >
                          Deactivate
                        </button>
                      )}
                      {!canCreate && !canDelete && (
                        <span className="text-xs text-slate-400">View only</span>
                      )}
                    </div>
                  </Table.Td>
                </Table.Row>
              ))}
            </Table.Body>
          </Table>
          <Pagination
            page={data.page}
            pages={data.pages}
            total={data.total}
            pageSize={PAGE_SIZE}
            onPageChange={setPage}
          />
        </div>
      )}

      {/* Create / Edit modal */}
      <Modal
        isOpen={modalOpen}
        onClose={closeModal}
        title={editTarget ? `Edit Product — ${editTarget.sku}` : 'New Product'}
        size="xl"
      >
        <form onSubmit={handleSubmit(onSubmit)} noValidate>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {/* SKU — read-only when editing (SKU is immutable) */}
            <div>
              <label className="form-label">
                SKU <span className="text-red-500">*</span>
              </label>
              <input
                className="input-base"
                placeholder="e.g. PARA-500MG"
                disabled={!!editTarget}
                {...register('sku')}
              />
              {errors.sku && <p className="form-error">{errors.sku.message}</p>}
            </div>

            {/* Name */}
            <div>
              <label className="form-label">
                Name <span className="text-red-500">*</span>
              </label>
              <input className="input-base" placeholder="e.g. Paracetamol 500mg" {...register('name')} />
              {errors.name && <p className="form-error">{errors.name.message}</p>}
            </div>

            {/* Category */}
            <div>
              <label className="form-label">
                Category <span className="text-red-500">*</span>
              </label>
              <select className="select-base" {...register('category_id')}>
                <option value="">Select category…</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
              {errors.category_id && <p className="form-error">{errors.category_id.message}</p>}
            </div>

            {/* Supplier */}
            <div>
              <label className="form-label">Supplier</label>
              <select className="select-base" {...register('supplier_id')}>
                <option value="">No supplier</option>
                {suppliers.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>

            {/* Unit */}
            <div>
              <label className="form-label">Unit</label>
              <input className="input-base" placeholder="e.g. tablets, kg, boxes" {...register('unit')} />
            </div>

            {/* Expiry alert days */}
            <div>
              <label className="form-label">Expiry Alert (days before)</label>
              <input type="number" min={1} className="input-base" {...register('expiry_alert_days')} />
              {errors.expiry_alert_days && (
                <p className="form-error">{errors.expiry_alert_days.message}</p>
              )}
            </div>

            {/* Reorder point */}
            <div>
              <label className="form-label">Reorder Point</label>
              <input type="number" min={0} className="input-base" {...register('reorder_point')} />
              {errors.reorder_point && <p className="form-error">{errors.reorder_point.message}</p>}
            </div>

            {/* Reorder quantity */}
            <div>
              <label className="form-label">Reorder Quantity</label>
              <input type="number" min={1} className="input-base" {...register('reorder_quantity')} />
            </div>

            {/* Max stock level */}
            <div>
              <label className="form-label">Max Stock Level</label>
              <input
                type="number"
                min={1}
                placeholder="Optional"
                className="input-base"
                {...register('max_stock_level')}
              />
              {errors.max_stock_level && (
                <p className="form-error">{errors.max_stock_level.message}</p>
              )}
            </div>

            {/* Description */}
            <div className="sm:col-span-2">
              <label className="form-label">Description</label>
              <textarea
                rows={2}
                className="input-base resize-none"
                placeholder="Optional product description"
                {...register('description')}
              />
            </div>
          </div>

          <div className="mt-6 flex justify-end gap-3">
            <button type="button" onClick={closeModal} className="btn-secondary">
              Cancel
            </button>
            <button type="submit" disabled={isSubmitting} className="btn-primary">
              {isSubmitting
                ? editTarget ? 'Saving…' : 'Creating…'
                : editTarget ? 'Save Changes' : 'Create Product'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Delete / deactivate confirmation */}
      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
        isLoading={deleteMutation.isPending}
        title="Deactivate Product"
        message={`Deactivate "${deleteTarget?.name}" (${deleteTarget?.sku})? The product will be hidden from active lists but historical data is preserved.`}
        confirmLabel="Deactivate"
        variant="danger"
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StockCell({ current, reorderPoint }: { current: number; reorderPoint: number }) {
  const isLow = current <= reorderPoint
  return (
    <span className={`font-semibold tabular-nums ${isLow ? 'text-red-600' : 'text-slate-900'}`}>
      {current}
      {isLow && <span className="ml-1 text-xs font-normal text-red-400">low</span>}
    </span>
  )
}

function ErrorState({ message }: { message?: string }) {
  return (
    <div className="card flex items-center gap-3 border-red-200 bg-red-50">
      <span className="text-xl">⚠️</span>
      <div>
        <p className="text-sm font-medium text-red-700">Failed to load products.</p>
        {message && <p className="mt-0.5 text-xs text-red-500">{message}</p>}
      </div>
    </div>
  )
}
