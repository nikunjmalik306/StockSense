/**
 * AppLayout — authenticated application shell.
 */
import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { formatRole } from '../../utils/format'

interface NavItem {
  to: string
  label: string
  icon: React.ReactNode
  roles?: string[]
}

interface NavGroup {
  title: string
  items: NavItem[]
}

function IconDashboard() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z" />
    </svg>
  )
}

function IconRisk() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
    </svg>
  )
}

function IconForecast() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
    </svg>
  )
}

function IconInventory() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
    </svg>
  )
}

function IconTransactions() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
    </svg>
  )
}

function IconProducts() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
    </svg>
  )
}

function IconCategories() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
    </svg>
  )
}

function IconSuppliers() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
    </svg>
  )
}

const NAV_GROUPS: NavGroup[] = [
  {
    title: 'Overview',
    items: [{ to: '/dashboard', label: 'Dashboard', icon: <IconDashboard /> }],
  },
  {
    title: 'Intelligence',
    items: [
      { to: '/analytics/risk', label: 'Risk Analysis', icon: <IconRisk /> },
      { to: '/analytics/forecast', label: 'Demand Forecast', icon: <IconForecast /> },
    ],
  },
  {
    title: 'Operations',
    items: [
      { to: '/inventory', label: 'Inventory', icon: <IconInventory /> },
      { to: '/transactions', label: 'Transactions', icon: <IconTransactions /> },
    ],
  },
  {
    title: 'Catalog',
    items: [
      { to: '/products', label: 'Products', icon: <IconProducts />, roles: ['ADMIN', 'MANAGER'] },
      { to: '/categories', label: 'Categories', icon: <IconCategories />, roles: ['ADMIN', 'MANAGER'] },
      { to: '/suppliers', label: 'Suppliers', icon: <IconSuppliers />, roles: ['ADMIN', 'MANAGER'] },
    ],
  },
]

function UserAvatar({ name }: { name: string }) {
  const initials = name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()

  return (
    <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-brand-600 text-xs font-medium text-white">
      {initials}
    </span>
  )
}

export function AppLayout() {
  const { user, logout, hasRole } = useAuth()
  const { toast } = useToast()
  const navigate = useNavigate()
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const displayName = user?.full_name ?? user?.username ?? 'User'

  const handleLogout = async () => {
    await logout()
    toast.success('Logged out successfully.')
    navigate('/login')
  }

  const visibleGroups = NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => !item.roles || hasRole(...item.roles)),
  })).filter((group) => group.items.length > 0)

  return (
    <div className="flex h-screen overflow-hidden bg-slate-100">
      <aside
        className={`sidebar-shell ${
          sidebarOpen ? 'w-56' : 'w-14'
        } transition-all duration-200`}
      >
        <div className="flex h-14 items-center gap-2.5 overflow-hidden border-b border-sidebar-border px-3">
          <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md bg-brand-600 text-[11px] font-semibold text-white shadow-glow">
            SS
          </span>
          {sidebarOpen && (
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-white">StockSense</p>
              <p className="truncate text-[11px] text-sidebar-faint">Inventory intelligence</p>
            </div>
          )}
        </div>

        <nav className="flex-1 overflow-y-auto px-2 py-3" aria-label="Main navigation">
          {visibleGroups.map((group) => (
            <div key={group.title} className="mb-4 last:mb-0">
              {sidebarOpen && <p className="nav-group-label">{group.title}</p>}
              {group.items.map(({ to, label, icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  title={!sidebarOpen ? label : undefined}
                  className={({ isActive }) =>
                    `nav-item ${isActive ? 'nav-item-active' : ''} ${!sidebarOpen ? 'justify-center px-0' : ''}`
                  }
                >
                  <span className="flex-shrink-0">{icon}</span>
                  {sidebarOpen && <span className="truncate">{label}</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        {sidebarOpen && (
          <div className="sidebar-user-card">
            <div className="flex items-center gap-2.5">
              <UserAvatar name={displayName} />
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-white">{displayName}</p>
                <p className="truncate text-xs text-sidebar-muted">{formatRole(user?.role)}</p>
              </div>
            </div>
          </div>
        )}

        <button
          onClick={() => setSidebarOpen((v) => !v)}
          className="flex h-10 w-full items-center justify-center border-t border-sidebar-border text-sidebar-faint transition-colors hover:bg-sidebar-hover hover:text-slate-200"
          aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
            {sidebarOpen ? (
              <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
            )}
          </svg>
        </button>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="z-10 flex h-14 flex-shrink-0 items-center justify-between border-b border-slate-200 bg-white px-5">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-slate-900">{displayName}</p>
            <p className="truncate text-xs text-slate-500">{user?.email}</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs font-medium text-slate-600 sm:inline">
              {formatRole(user?.role)}
            </span>
            <UserAvatar name={displayName} />
            <button
              onClick={handleLogout}
              className="btn-ghost text-slate-500"
            >
              Sign out
            </button>
          </div>
        </header>

        <main className="app-shell">
          <div className="mx-auto max-w-7xl px-5 py-6 sm:px-6">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
