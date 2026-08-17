import { apiClient } from './client'
import type {
  Category,
  CategoryCreateRequest,
  CategoryUpdateRequest,
} from '../types'
import type { PaginatedResponse } from '../types'

export interface ListCategoriesParams {
  search?: string
  page?: number
  page_size?: number
}

export const categoriesApi = {
  list: (params?: ListCategoriesParams) =>
    apiClient
      .get<PaginatedResponse<Category>>('/categories', { params })
      .then((r) => r.data),

  get: (id: string) =>
    apiClient.get<Category>(`/categories/${id}`).then((r) => r.data),

  create: (data: CategoryCreateRequest) =>
    apiClient.post<Category>('/categories', data).then((r) => r.data),

  update: (id: string, data: CategoryUpdateRequest) =>
    apiClient.put<Category>(`/categories/${id}`, data).then((r) => r.data),

  delete: (id: string) =>
    apiClient.delete(`/categories/${id}`).then((r) => r.data),
}
