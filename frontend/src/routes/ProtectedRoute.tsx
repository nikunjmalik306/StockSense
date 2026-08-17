/**
 * ProtectedRoute — wraps routes that require authentication.
 *
 * If not authenticated: redirect to /login (preserves the intended path
 * in location.state so we can redirect back after login).
 *
 * If a requiredRoles array is provided: render a 403 Forbidden view
 * if the user's role isn't in the list. This gives clear feedback
 * instead of a silent redirect.
 */
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

interface ProtectedRouteProps {
  requiredRoles?: string[]
}

export function ProtectedRoute({ requiredRoles }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, hasRole } = useAuth()
  const location = useLocation()

  // While restoring session from storage, show nothing (avoids flash of login page)
  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand-500 border-t-transparent" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (requiredRoles && requiredRoles.length > 0 && !hasRole(...requiredRoles)) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4">
        <div className="text-6xl">🔒</div>
        <h1 className="text-2xl font-semibold text-slate-800">Access Denied</h1>
        <p className="text-slate-500">
          You need the{' '}
          <span className="font-medium text-slate-700">{requiredRoles.join(' or ')}</span>{' '}
          role to view this page.
        </p>
      </div>
    )
  }

  return <Outlet />
}
