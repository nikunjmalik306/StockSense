import { apiClient } from './client'
import type {
  Supplier,
  SupplierCreateRequest,
  SupplierUpdateRequest,
} from '../types'
import type { PaginatedResponse } from '../types'

export interface ListSuppliersParams {
  search?: string
  is_active?: boolean
  page?: number
  page_size?: number
}

export const suppliersApi = {
  list: (params?: ListSuppliersParams) =>
    apiClient
      .get<PaginatedResponse<Supplier>>('/suppliers', { params })
      .then((r) => r.data),

  get: (id: string) =>
    apiClient.get<Supplier>(`/suppliers/${id}`).then((r) => r.data),

  create: (data: SupplierCreateRequest) =>
    apiClient.post<Supplier>('/suppliers', data).then((r) => r.data),

  update: (id: string, data: SupplierUpdateRequest) =>
    apiClient.put<Supplier>(`/suppliers/${id}`, data).then((r) => r.data),

  delete: (id: string) =>
    apiClient.delete(`/suppliers/${id}`).then((r) => r.data),
}
