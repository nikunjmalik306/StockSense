import { clsx } from 'clsx'

type BadgeVariant =
  | 'default'
  | 'green'
  | 'red'
  | 'amber'
  | 'orange'
  | 'blue'
  | 'slate'
  | 'LOW'
  | 'MEDIUM'
  | 'HIGH'
  | 'CRITICAL'

interface BadgeProps {
  children: React.ReactNode
  variant?: BadgeVariant
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const VARIANT_CLASSES: Record<BadgeVariant, string> = {
  default: 'bg-slate-100 text-slate-600 ring-slate-200/80',
  green: 'bg-emerald-50 text-emerald-700 ring-emerald-200/80',
  red: 'bg-red-50 text-red-700 ring-red-200/80',
  amber: 'bg-amber-50 text-amber-700 ring-amber-200/80',
  orange: 'bg-orange-50 text-orange-700 ring-orange-200/80',
  blue: 'bg-brand-50 text-brand-700 ring-brand-200/80',
  slate: 'bg-slate-100 text-slate-500 ring-slate-200/80',
  LOW: 'bg-emerald-50 text-emerald-700 ring-emerald-200/80',
  MEDIUM: 'bg-amber-50 text-amber-700 ring-amber-200/80',
  HIGH: 'bg-orange-50 text-orange-700 ring-orange-200/80',
  CRITICAL: 'bg-red-50 text-red-700 ring-red-200/80',
}

const SIZE_CLASSES = {
  sm: 'text-[11px] px-2 py-0.5',
  md: 'text-xs px-2 py-0.5',
  lg: 'text-xs px-2.5 py-1',
}

export function Badge({ children, variant = 'default', size = 'md', className }: BadgeProps) {
  const isRiskLevel = typeof children === 'string' && ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].includes(children as string)

  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-md font-medium ring-1 ring-inset',
        isRiskLevel && 'uppercase tracking-wide',
        VARIANT_CLASSES[variant],
        SIZE_CLASSES[size],
        className,
      )}
    >
      {children}
    </span>
  )
}

export function StatusBadge({ active }: { active: boolean }) {
  return (
    <Badge variant={active ? 'green' : 'slate'}>
      {active ? 'Active' : 'Inactive'}
    </Badge>
  )
}
