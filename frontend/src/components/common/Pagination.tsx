interface PaginationProps {
  page: number
  pages: number
  total: number
  pageSize: number
  onPageChange: (page: number) => void
}

export function Pagination({
  page,
  pages,
  total,
  pageSize,
  onPageChange,
}: PaginationProps) {
  if (pages <= 1) return null

  const start = (page - 1) * pageSize + 1
  const end = Math.min(page * pageSize, total)

  return (
    <div className="flex items-center justify-between border-t border-slate-200 bg-white px-4 py-3">
      <p className="text-sm text-slate-500">
        Showing <span className="font-medium text-slate-700">{start}–{end}</span>{' '}
        of <span className="font-medium text-slate-700">{total}</span> results
      </p>
      <div className="flex items-center gap-1">
        <PaginationButton
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          label="Previous"
        >
          ←
        </PaginationButton>

        {/* Show at most 5 page numbers */}
        {getPageNumbers(page, pages).map((p, i) =>
          p === '…' ? (
            <span key={`ellipsis-${i}`} className="px-2 text-slate-400">…</span>
          ) : (
            <button
              key={p}
              onClick={() => onPageChange(p as number)}
              className={`min-w-[32px] rounded-md px-2 py-1 text-sm font-medium transition-colors ${
                p === page
                  ? 'bg-brand-600 text-white'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              {p}
            </button>
          ),
        )}

        <PaginationButton
          onClick={() => onPageChange(page + 1)}
          disabled={page >= pages}
          label="Next"
        >
          →
        </PaginationButton>
      </div>
    </div>
  )
}

function PaginationButton({
  children,
  onClick,
  disabled,
  label,
}: {
  children: React.ReactNode
  onClick: () => void
  disabled: boolean
  label: string
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className="rounded-md px-2 py-1 text-sm text-slate-600 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  )
}

/** Build a window of page numbers with ellipsis for large ranges. */
function getPageNumbers(current: number, total: number): (number | '…')[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  if (current <= 4) return [1, 2, 3, 4, 5, '…', total]
  if (current >= total - 3) return [1, '…', total - 4, total - 3, total - 2, total - 1, total]
  return [1, '…', current - 1, current, current + 1, '…', total]
}
