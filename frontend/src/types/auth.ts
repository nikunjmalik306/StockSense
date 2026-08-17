// Mirrors backend app/schemas/auth.py

export interface User {
  id: string
  email: string
  username: string
  full_name: string | null
  role: 'ADMIN' | 'MANAGER' | 'STAFF'
  is_active: boolean
  created_at: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface AccessTokenResponse {
  access_token: string
  token_type: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  email: string
  username: string
  password: string
  full_name?: string
}

export type RoleName = 'ADMIN' | 'MANAGER' | 'STAFF'
