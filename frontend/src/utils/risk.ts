import type { RiskLevel } from '../types'

/**
 * Returns Tailwind CSS classes for a risk level badge.
 * Used consistently across Products, Dashboard, and Risk views.
 */
export function riskLevelClasses(level: RiskLevel | null | undefined): string {
  switch (level) {
    case 'LOW':
      return 'bg-green-100 text-green-700 ring-green-200'
    case 'MEDIUM':
      return 'bg-amber-100 text-amber-700 ring-amber-200'
    case 'HIGH':
      return 'bg-orange-100 text-orange-700 ring-orange-200'
    case 'CRITICAL':
      return 'bg-red-100 text-red-700 ring-red-200'
    default:
      return 'bg-slate-100 text-slate-500 ring-slate-200'
  }
}

/**
 * Returns a human-readable label for a risk level.
 */
export function riskLevelLabel(level: RiskLevel | null | undefined): string {
  return level ?? 'N/A'
}
