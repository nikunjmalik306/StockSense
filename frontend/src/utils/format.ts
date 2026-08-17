/**
 * Shared formatting utilities.
 * Keep these pure functions — no React imports, no side effects.
 */

/**
 * Format an ISO date string to a readable date.
 * e.g. "2025-01-15T10:30:00Z" → "Jan 15, 2025"
 */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

/**
 * Format a number as currency.
 * e.g. 1234.5 → "$1,234.50"
 */
export function formatCurrency(
  value: number | null | undefined,
  currency = 'USD',
): string {
  if (value == null) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
  }).format(value)
}

/**
 * Format a number with commas.
 * e.g. 12345 → "12,345"
 */
export function formatNumber(value: number | null | undefined): string {
  if (value == null) return '—'
  return new Intl.NumberFormat('en-US').format(value)
}

/**
 * Truncate a string to maxLength characters with ellipsis.
 */
export function truncate(str: string | null | undefined, maxLength = 60): string {
  if (!str) return '—'
  return str.length > maxLength ? str.slice(0, maxLength) + '…' : str
}

/** Format a backend role enum for display. e.g. "ADMIN" → "Admin" */
export function formatRole(role: string | null | undefined): string {
  if (!role) return 'User'
  return role.charAt(0) + role.slice(1).toLowerCase()
}
