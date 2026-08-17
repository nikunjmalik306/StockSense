/**
 * CategoriesPage
 *
 * Lists product categories with search + pagination.
 * ADMIN/MANAGER: create and edit. ADMIN only: delete.
 * STAFF: read-only.
 *
 * Data fetching uses TanStack Query (already configured in main.tsx).
 * Mutations call the categories API directly then invalidate the query cache.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

import { categoriesApi } from '../../api/categories'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useDebounce } from '../../hooks/useDebounce'
import type { Category } from '../../types'
import { formatDate } from '../../utils/format'

import {
  Table,
  Badge,
  Pagination,
  Modal,
  ConfirmDialog,
  EmptyState,
  SearchInput,
  PageSpinner,
} from '../../components/common'

// ---------------------------------------------------------------------------
// Form schema
// ---------------------------------------------------------------------------

const categorySchema = z.object({
  name: z.string().min(1, 'Name is required').max(100),
  description: z.string().max(1000).optional(),
})
type CategoryFormValues = z.infer<typeof categorySchema>

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CategoriesPage() {
  const { hasRole } = useAuth()
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const canCreate = hasRole('ADMIN', 'MANAGER')
  const canDelete = hasRole('ADMIN')

  // List state
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 15
  const debouncedSearch = useDebounce(search, 350)

  // Modal state
  const [modalOpen, setModalOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<Category | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Category | null>(null)

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['categories', { search: debouncedSearch, page, page_size: PAGE_SIZE }],
    queryFn: () =>
      categoriesApi.list({ search: debouncedSearch || undefined, page, page_size: PAGE_SIZE }),
  })

  // Reset to page 1 when search changes
  const handleSearchChange = (value: string) => {
    setSearch(value)
    setPage(1)
  }

  // ---------------------------------------------------------------------------
  // Create / Update
  // ---------------------------------------------------------------------------

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<CategoryFormValues>({ resolver: zodResolver(categorySchema) })

  const createMutation = useMutation({
    mutationFn: categoriesApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] })
      toast.success('Category created.')
      closeModal()
    },
    onError: (err: { message?: string }) => {
      toast.error(err.message ?? 'Failed to create category.')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: CategoryFormValues }) =>
      categoriesApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] })
      toast.success('Category updated.')
      closeModal()
    },
    onError: (err: { message?: string }) => {
      toast.error(err.message ?? 'Failed to update category.')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: categoriesApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories'] })
      toast.success('Category deleted.')
      setDeleteTarget(null)
    },
    onError: (err: { message?: string }) => {
      toast.error(err.message ?? 'Failed to delete category.')
      setDeleteTarget(null)
    },
  })

  // ---------------------------------------------------------------------------
  // Modal helpers
  // ---------------------------------------------------------------------------

  function openCreate() {
    setEditTarget(null)
    reset({ name: '', description: '' })
    setModalOpen(true)
  }

  function openEdit(cat: Category) {
    setEditTarget(cat)
    reset({ name: cat.name, description: cat.description ?? '' })
    setModalOpen(true)
  }

  function closeModal() {
    setModalOpen(false)
    setEditTarget(null)
    reset()
  }

  async function onSubmit(values: CategoryFormValues) {
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
      {/* Page header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="page-title">Categories</h1>
          <p className="page-subtitle">Organize products into categories.</p>
        </div>
        {canCreate && (
          <button onClick={openCreate} className="btn-primary">
            + New Category
          </button>
        )}
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-3">
        <SearchInput
          value={search}
          onChange={handleSearchChange}
          placeholder="Search categories…"
          className="w-72"
        />
        {data && (
          <span className="text-sm text-slate-400">
            {data.total} {data.total === 1 ? 'category' : 'categories'}
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
          title={search ? 'No categories match your search.' : 'No categories yet.'}
          description={search ? 'Try a different search term.' : 'Create your first category to start organising products.'}
          action={
            canCreate ? (
              <button onClick={openCreate} className="btn-primary">
                + New Category
              </button>
            ) : undefined
          }
        />
      ) : (
        <div className="flex flex-col gap-0">
          <Table>
            <Table.Head>
              <Table.Row>
                <Table.Th>Name</Table.Th>
                <Table.Th>Description</Table.Th>
                <Table.Th>Products</Table.Th>
                <Table.Th>Created</Table.Th>
                <Table.Th className="w-28 text-right">Actions</Table.Th>
              </Table.Row>
            </Table.Head>
            <Table.Body>
              {data.items.map((cat) => (
                <Table.Row key={cat.id}>
                  <Table.Td>
                    <span className="font-medium text-slate-900">{cat.name}</span>
                  </Table.Td>
                  <Table.Td className="text-slate-400">
                    {cat.description ?? <span className="italic text-slate-300">No description</span>}
                  </Table.Td>
                  <Table.Td>
                    <Badge variant="blue">{cat.product_count ?? 0}</Badge>
                  </Table.Td>
                  <Table.Td className="text-slate-400">{formatDate(cat.created_at)}</Table.Td>
                  <Table.Td>
                    <div className="flex justify-end gap-2">
                      {canCreate && (
                        <button
                          onClick={() => openEdit(cat)}
                          className="btn-ghost text-xs"
                        >
                          Edit
                        </button>
                      )}
                      {canDelete && (
                        <button
                          onClick={() => setDeleteTarget(cat)}
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
        title={editTarget ? 'Edit Category' : 'New Category'}
      >
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4">
          <div>
            <label className="form-label">
              Name <span className="text-red-500">*</span>
            </label>
            <input
              className="input-base"
              placeholder="e.g. Antibiotics"
              aria-invalid={!!errors.name}
              {...register('name')}
            />
            {errors.name && <p className="form-error">{errors.name.message}</p>}
          </div>

          <div>
            <label className="form-label">Description</label>
            <textarea
              rows={3}
              className="input-base resize-none"
              placeholder="Optional description"
              {...register('description')}
            />
            {errors.description && (
              <p className="form-error">{errors.description.message}</p>
            )}
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={closeModal} className="btn-secondary">
              Cancel
            </button>
            <button type="submit" disabled={isSubmitting} className="btn-primary">
              {isSubmitting
                ? editTarget ? 'Saving…' : 'Creating…'
                : editTarget ? 'Save Changes' : 'Create Category'}
            </button>
          </div>
        </form>
      </Modal>

      {/* Delete confirmation */}
      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
        isLoading={deleteMutation.isPending}
        title="Delete Category"
        message={`Delete "${deleteTarget?.name}"? This cannot be undone. Categories with products cannot be deleted.`}
        confirmLabel="Delete"
        variant="danger"
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Local sub-components
// ---------------------------------------------------------------------------

function ErrorState({ message }: { message?: string }) {
  return (
    <div className="card flex items-center gap-3 border-red-200 bg-red-50">
      <span className="text-xl">⚠️</span>
      <div>
        <p className="text-sm font-medium text-red-700">Failed to load categories.</p>
        {message && <p className="mt-0.5 text-xs text-red-500">{message}</p>}
      </div>
    </div>
  )
}
