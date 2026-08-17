import { Modal } from './Modal'
import { Spinner } from './Spinner'

interface ConfirmDialogProps {
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  message: string
  confirmLabel?: string
  isLoading?: boolean
  /** 'danger' shows a red confirm button — use for destructive actions */
  variant?: 'danger' | 'primary'
}

/**
 * Reusable confirmation dialog.
 * Used before any destructive action (delete category, supplier, product).
 */
export function ConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = 'Confirm',
  isLoading = false,
  variant = 'danger',
}: ConfirmDialogProps) {
  const confirmClass =
    variant === 'danger'
      ? 'bg-red-600 hover:bg-red-700 focus:ring-red-500'
      : 'bg-brand-600 hover:bg-brand-700 focus:ring-brand-500'

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={title} size="sm">
      <p className="text-sm text-slate-600">{message}</p>
      <div className="mt-6 flex justify-end gap-3">
        <button
          onClick={onClose}
          disabled={isLoading}
          className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
          disabled={isLoading}
          className={`inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-semibold text-white focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-60 transition-colors ${confirmClass}`}
        >
          {isLoading && <Spinner size="sm" className="border-white/40 border-t-white" />}
          {confirmLabel}
        </button>
      </div>
    </Modal>
  )
}
