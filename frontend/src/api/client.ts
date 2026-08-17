/**
 * Axios instance with automatic JWT token refresh.
 *
 * How it works:
 * 1. Every request attaches the access token from memory.
 * 2. On a 401 response, the interceptor attempts one silent refresh.
 * 3. If the refresh succeeds, the original request is retried once.
 * 4. If the refresh fails (expired, blacklisted), the user is logged out.
 *
 * Access token is stored in memory (not localStorage) to reduce XSS risk.
 * Refresh token is sent in the request body (could be upgraded to httpOnly
 * cookie in production).
 */
import axios, {
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'

// ---------------------------------------------------------------------------
// Token store — in-memory only, cleared on page refresh (intentional)
// ---------------------------------------------------------------------------

let _accessToken: string | null = null
let _refreshToken: string | null = null

export const tokenStore = {
  getAccessToken: () => _accessToken,
  getRefreshToken: () => _refreshToken,

  setTokens: (access: string, refresh: string) => {
    _accessToken = access
    _refreshToken = refresh
    // Persist refresh token to sessionStorage so it survives page refresh
    // but is cleared when the browser tab closes
    sessionStorage.setItem('refresh_token', refresh)
  },

  clearTokens: () => {
    _accessToken = null
    _refreshToken = null
    sessionStorage.removeItem('refresh_token')
  },

  loadFromStorage: () => {
    // Restore refresh token from sessionStorage on app start
    const stored = sessionStorage.getItem('refresh_token')
    if (stored) _refreshToken = stored
  },
}

// ---------------------------------------------------------------------------
// Axios instance
// ---------------------------------------------------------------------------

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export const apiClient: AxiosInstance = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000,
})

// ---------------------------------------------------------------------------
// Request interceptor — attach access token
// ---------------------------------------------------------------------------

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStore.getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ---------------------------------------------------------------------------
// Response interceptor — handle 401 with silent refresh
// ---------------------------------------------------------------------------

let _isRefreshing = false
let _failedQueue: Array<{
  resolve: (value: unknown) => void
  reject: (reason?: unknown) => void
}> = []

function processQueue(error: unknown, token: string | null = null) {
  _failedQueue.forEach(({ resolve, reject }) => {
    if (error) {
      reject(error)
    } else {
      resolve(token)
    }
  })
  _failedQueue = []
}

apiClient.interceptors.response.use(
  // Pass successful responses straight through
  (response) => response,

  async (error) => {
    const originalRequest = error.config as AxiosRequestConfig & {
      _retry?: boolean
    }

    // Only handle 401 once per request (prevent infinite retry loop)
    if (error.response?.status !== 401 || originalRequest._retry) {
      return Promise.reject(normalizeError(error))
    }

    // Don't try to refresh if the failing request IS the refresh endpoint
    if (originalRequest.url?.includes('/auth/refresh')) {
      tokenStore.clearTokens()
      window.dispatchEvent(new CustomEvent('auth:logout'))
      return Promise.reject(normalizeError(error))
    }

    if (_isRefreshing) {
      // Another refresh is already in progress — queue this request
      return new Promise((resolve, reject) => {
        _failedQueue.push({ resolve, reject })
      }).then((token) => {
        if (originalRequest.headers) {
          originalRequest.headers['Authorization'] = `Bearer ${token}`
        }
        return apiClient(originalRequest)
      })
    }

    originalRequest._retry = true
    _isRefreshing = true

    const refreshToken = tokenStore.getRefreshToken()
    if (!refreshToken) {
      tokenStore.clearTokens()
      window.dispatchEvent(new CustomEvent('auth:logout'))
      _isRefreshing = false
      return Promise.reject(normalizeError(error))
    }

    try {
      const { data } = await axios.post(`${BASE_URL}/api/v1/auth/refresh`, {
        refresh_token: refreshToken,
      })

      const newAccessToken: string = data.access_token
      tokenStore.setTokens(newAccessToken, refreshToken)

      processQueue(null, newAccessToken)
      if (originalRequest.headers) {
        originalRequest.headers['Authorization'] = `Bearer ${newAccessToken}`
      }
      return apiClient(originalRequest)
    } catch (refreshError) {
      processQueue(refreshError, null)
      tokenStore.clearTokens()
      window.dispatchEvent(new CustomEvent('auth:logout'))
      return Promise.reject(normalizeError(refreshError))
    } finally {
      _isRefreshing = false
    }
  },
)

// ---------------------------------------------------------------------------
// Error normaliser — ensures consistent error shape for UI
// ---------------------------------------------------------------------------

export interface NormalizedError {
  message: string
  code?: string
  status?: number
  fieldErrors?: Record<string, string>
}

function normalizeError(error: unknown): NormalizedError {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data
    const status = error.response?.status

    // Collect field-level errors from Pydantic validation failures
    const fieldErrors: Record<string, string> = {}
    if (Array.isArray(data?.errors)) {
      for (const e of data.errors) {
        if (e.field) fieldErrors[e.field] = e.message
      }
    }

    return {
      message: data?.detail ?? error.message ?? 'An error occurred.',
      code: data?.code,
      status,
      fieldErrors: Object.keys(fieldErrors).length > 0 ? fieldErrors : undefined,
    }
  }
  return { message: String(error) }
}
