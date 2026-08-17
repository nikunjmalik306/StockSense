/**
 * AuthContext — global authentication state.
 *
 * Stores: current User object, loading state, login/logout helpers.
 *
 * On mount, attempts to restore session from a stored refresh token
 * so the user doesn't get logged out on page refresh.
 *
 * Listens to the custom 'auth:logout' event dispatched by the axios
 * interceptor when a refresh fails — this keeps the UI in sync even
 * when a token expires mid-session.
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react'
import { authApi } from '../api/auth'
import { tokenStore } from '../api/client'
import type { User, LoginRequest } from '../types'

interface AuthContextValue {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (data: LoginRequest) => Promise<void>
  logout: () => Promise<void>
  hasRole: (...roles: string[]) => boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true) // true until initial session check
  const logoutRef = useRef<() => Promise<void>>(null!)

  // ------------------------------------------------------------------
  // Logout — clear tokens, user state, and redirect handled by caller
  // ------------------------------------------------------------------
  const logout = useCallback(async () => {
    const refreshToken = tokenStore.getRefreshToken()
    if (refreshToken) {
      try {
        // Best-effort: blacklist the token on the server
        await authApi.logout(refreshToken)
      } catch {
        // If the server call fails we still clear local state
      }
    }
    tokenStore.clearTokens()
    setUser(null)
  }, [])

  // Keep ref in sync so the event listener below always calls latest version
  logoutRef.current = logout

  // ------------------------------------------------------------------
  // Login
  // ------------------------------------------------------------------
  const login = useCallback(async (data: LoginRequest) => {
    const tokens = await authApi.login(data)
    tokenStore.setTokens(tokens.access_token, tokens.refresh_token)
    const me = await authApi.me()
    setUser(me)
  }, [])

  // ------------------------------------------------------------------
  // Restore session on mount
  // ------------------------------------------------------------------
  useEffect(() => {
    tokenStore.loadFromStorage()

    async function restoreSession() {
      const refreshToken = tokenStore.getRefreshToken()
      if (!refreshToken) {
        setIsLoading(false)
        return
      }
      try {
        const { access_token } = await authApi.refresh(refreshToken)
        tokenStore.setTokens(access_token, refreshToken)
        const me = await authApi.me()
        setUser(me)
      } catch {
        // Refresh token expired or invalid — silently log out
        tokenStore.clearTokens()
      } finally {
        setIsLoading(false)
      }
    }

    restoreSession()
  }, [])

  // ------------------------------------------------------------------
  // Listen for forced logout events (fired by axios interceptor)
  // ------------------------------------------------------------------
  useEffect(() => {
    const handle = () => {
      logoutRef.current()
    }
    window.addEventListener('auth:logout', handle)
    return () => window.removeEventListener('auth:logout', handle)
  }, [])

  // ------------------------------------------------------------------
  // Role helpers
  // ------------------------------------------------------------------
  const hasRole = useCallback(
    (...roles: string[]) => {
      if (!user) return false
      return roles.includes(user.role)
    },
    [user],
  )

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        logout,
        hasRole,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>')
  return ctx
}
