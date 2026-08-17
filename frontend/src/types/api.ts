// Shared API response shapes

export interface ApiError {
  detail: string
  code?: string
  errors?: Array<{ field: string; message: string }>
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface MessageResponse {
  message: string
}
