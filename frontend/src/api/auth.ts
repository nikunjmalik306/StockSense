/**
 * Auth API functions.
 * All calls go through the shared apiClient instance.
 */
import { apiClient } from './client'
import type { TokenResponse, AccessTokenResponse, User, LoginRequest, RegisterRequest } from '../types'

export const authApi = {
  login: (data: LoginRequest) =>
    apiClient.post<TokenResponse>('/auth/login', data).then((r) => r.data),

  register: (data: RegisterRequest) =>
    apiClient.post<User>('/auth/register', data).then((r) => r.data),

  logout: (refreshToken: string) =>
    apiClient.post('/auth/logout', { refresh_token: refreshToken }).then((r) => r.data),

  refresh: (refreshToken: string) =>
    apiClient
      .post<AccessTokenResponse>('/auth/refresh', { refresh_token: refreshToken })
      .then((r) => r.data),

  me: () => apiClient.get<User>('/auth/me').then((r) => r.data),
}
