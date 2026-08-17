import { apiClient } from './client'
import type {
  Product,
  ProductListItem,
  ProductCreateRequest,
  ProductUpdateRequest,
} from '../types'
import type { PaginatedResponse } from '../types'

export interface ListProductsParams {
  search?: string
  category_id?: string
  supplier_id?: string
  is_active?: boolean
  risk_level?: string
  low_stock_only?: boolean
  sort_by?: string
  sort_order?: 'asc' | 'desc'
  page?: number
  page_size?: number
}

export const productsApi = {
  list: (params?: ListProductsParams) =>
    apiClient
      .get<PaginatedResponse<ProductListItem>>('/products', { params })
      .then((r) => r.data),

  get: (id: string) =>
    apiClient.get<Product>(`/products/${id}`).then((r) => r.data),

  create: (data: ProductCreateRequest) =>
    apiClient.post<Product>('/products', data).then((r) => r.data),

  update: (id: string, data: ProductUpdateRequest) =>
    apiClient.put<Product>(`/products/${id}`, data).then((r) => r.data),

  delete: (id: string) =>
    apiClient.delete(`/products/${id}`).then((r) => r.data),
}
