/**
 * SuppliersPage
 *
 * Lists suppliers with search + active filter + pagination.
 * ADMIN/MANAGER: create and edit. ADMIN only: delete.
 * STAFF: read-only.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

import { suppliersApi } from '../../api/suppliers'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useDebounce } from '../../hooks/useDebounce'
import type { Supplier } from '../../types'

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
// Form schema — mirrors SupplierCreateRequest / SupplierUpdateRequest
// ---------------------------------------------------------------------------

const supplierSchema = z.object({
  name: z.string().min(1, 'Name is required').max(255),
  contact_name: z.string().max(255).optional(),
  email: z.string().email('Enter a valid email').optional().or(z.literal('')),
  phone: z.string().max(50).optional(),
  address: z.string().max(1000).optional(),
  lead_time_days: z.coerce.number().int().min(1, 'Must be at least 1 day').max(365),
})
type SupplierFormValues = z.infer<typeof supplierSchema>

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SuppliersPage() {
  const { hasRole } = useAuth()
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const canCreate = hasRole('ADMIN', 'MANAGER')
  const canDelete = hasRole('ADMIN')

  const [search, setSearch] = useState('')
  const [activeFilter, setActiveFilter] = useState<boolean | undefined>(true)
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 15
  const debouncedSearch = useDebounce(search, 350)

  const [modalOpen, setModalOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<Supplier | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Supplier | null>(null)

  // ---------------------------------------------------------------------------
  // Query
  // ---------------------------------------------------------------------------

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['suppliers', { search: debouncedSearch, is_active: activeFilter, page, page_size: PAGE_SIZE }],
    queryFn: () =>
      suppliersApi.list({
        search: debouncedSearch || undefined,
        is_active: activeFilter,
        page,
        page_size: PAGE_SIZE,
      }),
  })

  const handleSearchChange = (value: string) => {
    setSearch(value)
    setPage(1)
  }

  // ---------------------------------------------------------------------------
  // Mutations
  // ---------------------------------------------------------------------------

  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } =
    useForm<SupplierFormValues>({
      resolver: zodResolver(supplierSchema),
      defaultValues: { lead_time_days: 7 },
    })

  const createMutation = useMutation({
    mutationFn: (data: SupplierFormValues) =>
      suppliersApi.create({
        ...data,
        email: data.email || undefined,
        contact_name: data.contact_name || undefined,
        phone: data.phone || undefined,
        address: data.address || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['suppliers'] })
      toast.success('Supplier created.')
      closeModal()
    },
    onError: (err: { message?: string }) => {
      toast.error(err.message ?? 'Failed to create supplier.')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: SupplierFormValues }) =>
      suppliersApi.update(id, {
        ...data,
        email: data.email || undefined,
        contact_name: data.contact_name || undefined,
        phone: data.phone || undefined,
        address: data.address || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['suppliers'] })
      toast.success('Supplier updated.')
      closeModal()
    },
    onError: (err: { message?: string }) => {
      toast.error(err.message ?? 'Failed to update supplier.')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: suppliersApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['suppliers'] })
      toast.success('Supplier deleted.')
      setDeleteTarget(null)
    },
    onError: (err: { message?: string }) => {
      toast.error(err.message ?? 'Failed to delete supplier.')
      setDeleteTarget(null)
    },
  })

  // ---------------------------------------------------------------------------
  // Modal helpers
  // ---------------------------------------------------------------------------

  function openCreate() {
    setEditTarget(null)
    reset({ name: '', contact_name: '', email: '', phone: '', address: '', lead_time_days: 7 })
    setModalOpen(true)
  }

  function openEdit(sup: Supplier) {
    setEditTarget(sup)
    reset({
      name: sup.name,
      contact_name: sup.contact_name ?? '',
      email: sup.email ?? '',
      phone: sup.phone ?? '',
      address: sup.address ?? '',
      lead_time_days: sup.lead_time_days,
    })
    setModalOpen(true)
  }

  function closeModal() {
    setModalOpen(false)
    setEditTarget(null)
    reset()
  }

  async function onSubmit(values: SupplierFormValues) {
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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="page-title">Suppliers</h1>
          <p className="page-subtitle">Manage suppliers and lead times.</p>
        </div>
        {canCreate && (
          <button onClick={openCreate} className="btn-primary">
            + New Supplier
          </button>
        )}
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <SearchInput
          value={search}
          onChange={handleSearchChange}
          placeholder="Search suppliers…"
          className="w-72"
        />
        {/* Active filter toggle */}
        <div className="flex rounded-md border border-slate-300 text-sm overflow-hidden">
          {([
            { label: 'Active', value: true },
            { label: 'All', value: undefined },
            { label: 'Inactive', value: false },
          ] as const).map(({ label, value }) => (
            <button
              key={label}
              onClick={() => { setActiveFilter(value); setPage(1) }}
              className={`px-3 py-1.5 transition-colors ${
                activeFilter === value
                  ? 'bg-brand-600 text-white'
                  : 'bg-white text-slate-600 hover:bg-slate-50'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        {data && (
          <span className="text-sm text-slate-400">
            {data.total} {data.total === 1 ? 'supplier' : 'suppliers'}
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
          title={search ? 'No suppliers match your search.' : 'No suppliers yet.'}
          description="Suppliers track where products come from and their expected lead times."
          action={
            canCreate ? (
              <button onClick={openCreate} className="btn-primary">
                + New Supplier
              </button>
            ) : undefined
          }
        />
      ) : (
        <div>
          <Table>
            <Table.Head>
              <Table.Row>
                <Table.Th>Name</Table.Th>
                <Table.Th>Contact</Table.Th>
                <Table.Th>Email</Table.Th>
                <Table.Th>Lead Time</Table.Th>
                <Table.Th>Products</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th className="w-28 text-right">Actions</Table.Th>
              </Table.Row>
            </Table.Head>
            <Table.Body>
              {data.items.map((sup) => (
                <Table.Row key={sup.id}>
                  <Table.Td>
                    <div>
                      <p className="font-medium text-slate-900">{sup.name}</p>
                      {sup.phone && (
                        <p className="text-xs text-slate-400">{sup.phone}</p>
                      )}
                    </div>
                  </Table.Td>
                  <Table.Td className="text-slate-500">
                    {sup.contact_name ?? <span className="italic text-slate-300">—</span>}
                  </Table.Td>
                  <Table.Td className="text-slate-500">
                    {sup.email ? (
                      <a href={`mailto:${sup.email}`} className="hover:underline">
                        {sup.email}
                      </a>
                    ) : (
                      <span className="italic text-slate-300">—</span>
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Badge variant="blue">{sup.lead_time_days}d</Badge>
                  </Table.Td>
                  <Table.Td>
                    <Badge variant="slate">{sup.product_count ?? 0}</Badge>
                  </Table.Td>
                  <Table.Td>
                    <StatusBadge active={sup.is_active} />
                  </Table.Td>
                  <Table.Td>
                    <div className="flex justify-end gap-2">
                      {canCreate && (
                        <button onClick={() => openEdit(sup)} className="btn-ghost text-xs">
                          Edit
                        </button>
                      )}
                      {canDelete && (
                        <button
                          onClick={() => setDeleteTarget(sup)}
                          className="btn-ghost text-xs text-red-500 hover:text-red-700"
                        >
                          Delete
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
        title={editTarget ? 'Edit Supplier' : 'New Supplier'}
        size="lg"
      >
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="form-label">
                Name <span className="text-red-500">*</span>
              </label>
              <input className="input-base" placeholder="e.g. MediCorp Ltd" {...register('name')} />
              {errors.name && <p className="form-error">{errors.name.message}</p>}
            </div>
            <div>
              <label className="form-label">Contact Name</label>
              <input className="input-base" placeholder="e.g. Jane Smith" {...register('contact_name')} />
            </div>
            <div>
              <label className="form-label">Email</label>
              <input type="email" className="input-base" placeholder="supplier@example.com" {...register('email')} />
              {errors.email && <p className="form-error">{errors.email.message}</p>}
            </div>
            <div>
              <label className="form-label">Phone</label>
              <input className="input-base" placeholder="+1 555 000 0000" {...register('phone')} />
            </div>
            <div className="sm:col-span-2">
              <label className="form-label">Address</label>
              <textarea rows={2} className="input-base resize-none" {...register('address')} />
            </div>
            <div>
              <label className="form-label">
                Lead Time (days) <span className="text-red-500">*</span>
              </label>
              <input
                type="number"
                min={1}
                max={365}
                className="input-base"
                {...register('lead_time_days')}
              />
              {errors.lead_time_days && (
                <p className="form-error">{errors.lead_time_days.message}</p>
              )}
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={closeModal} className="btn-secondary">
              Cancel
            </button>
            <button type="submit" disabled={isSubmitting} className="btn-primary">
              {isSubmitting
                ? editTarget ? 'Saving…' : 'Creating…'
                : editTarget ? 'Save Changes' : 'Create Supplier'}
            </button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
        isLoading={deleteMutation.isPending}
        title="Delete Supplier"
        message={`Delete "${deleteTarget?.name}"? Suppliers with assigned products cannot be deleted.`}
        confirmLabel="Delete"
        variant="danger"
      />
    </div>
  )
}

function ErrorState({ message }: { message?: string }) {
  return (
    <div className="card flex items-center gap-3 border-red-200 bg-red-50">
      <span className="text-xl">⚠️</span>
      <div>
        <p className="text-sm font-medium text-red-700">Failed to load suppliers.</p>
        {message && <p className="mt-0.5 text-xs text-red-500">{message}</p>}
      </div>
    </div>
  )
}
