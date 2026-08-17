/**
 * Inventory API functions — stock-in, stock-out, adjustment, batches.
 * All paths match the existing Block 3 backend routers exactly.
 */
import { apiClient } from './client'
import type {
  AdjustmentRequest, AdjustmentResponse,
  InventoryBatch, InventoryBatchPatch,
  StockInRequest, StockInResponse,
  StockOutRequest, StockOutResponse,
  StockTransaction,
} from '../types'
import type { PaginatedResponse } from '../types'

export interface ListBatchesParams {
  product_id?: string
  include_depleted?: boolean
  expiring_within_days?: number
  page?: number
  page_size?: number
}

export interface ListTransactionsParams {
  product_id?: string
  transaction_type?: string
  date_from?: string
  date_to?: string
  sort_by?: 'transaction_at' | 'created_at'
  sort_order?: 'asc' | 'desc'
  page?: number
  page_size?: number
}

export const inventoryApi = {
  // --- Stock mutations ---
  stockIn: (data: StockInRequest) =>
    apiClient.post<StockInResponse>('/transactions/stock-in', data).then((r) => r.data),

  stockOut: (data: StockOutRequest) =>
    apiClient.post<StockOutResponse>('/transactions/stock-out', data).then((r) => r.data),

  adjustment: (data: AdjustmentRequest) =>
    apiClient.post<AdjustmentResponse>('/transactions/adjustment', data).then((r) => r.data),

  // --- Transaction history ---
  listTransactions: (params?: ListTransactionsParams) =>
    apiClient
      .get<PaginatedResponse<StockTransaction>>('/transactions', { params })
      .then((r) => r.data),

  getTransaction: (id: string) =>
    apiClient.get<StockTransaction>(`/transactions/${id}`).then((r) => r.data),

  // --- Batches ---
  listBatches: (params?: ListBatchesParams) =>
    apiClient
      .get<PaginatedResponse<InventoryBatch>>('/inventory/batches', { params })
      .then((r) => r.data),

  getBatch: (id: string) =>
    apiClient.get<InventoryBatch>(`/inventory/batches/${id}`).then((r) => r.data),

  patchBatch: (id: string, data: InventoryBatchPatch) =>
    apiClient.patch<InventoryBatch>(`/inventory/batches/${id}`, data).then((r) => r.data),

  // --- Product-scoped ---
  getProductBatches: (productId: string, params?: { include_depleted?: boolean; page?: number; page_size?: number }) =>
    apiClient
      .get<PaginatedResponse<InventoryBatch>>(`/products/${productId}/batches`, { params })
      .then((r) => r.data),

  getProductTransactions: (productId: string, params?: { transaction_type?: string; page?: number; page_size?: number }) =>
    apiClient
      .get<PaginatedResponse<StockTransaction>>(`/products/${productId}/transactions`, { params })
      .then((r) => r.data),
}
