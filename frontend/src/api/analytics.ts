import { apiClient } from './client'
import type {
  CategoryDistributionItem,
  InventoryOverview,
  RecentTransactionItem,
  StockStatusItem,
  RiskSummary,
  ProductRiskDetail,
  RiskDistribution,
  DemandMetrics,
  ExpiringBatch,
} from '../types'
import type { PaginatedResponse } from '../types'

export interface StockStatusParams {
  search?: string
  category_id?: string
  low_stock_only?: boolean
  page?: number
  page_size?: number
}

export interface RiskParams {
  risk_level?: string
  search?: string
  page?: number
  page_size?: number
}

export interface ExpiringParams {
  days?: number
  page?: number
  page_size?: number
}

export const analyticsApi = {
  getOverview: () =>
    apiClient.get<InventoryOverview>('/analytics/overview').then((r) => r.data),

  getCategoryDistribution: () =>
    apiClient
      .get<CategoryDistributionItem[]>('/analytics/category-distribution')
      .then((r) => r.data),

  getStockStatus: (params?: StockStatusParams) =>
    apiClient
      .get<PaginatedResponse<StockStatusItem>>('/analytics/stock-status', { params })
      .then((r) => r.data),

  getRecentTransactions: (limit = 10) =>
    apiClient
      .get<RecentTransactionItem[]>('/analytics/recent-transactions', { params: { limit } })
      .then((r) => r.data),

  // Risk endpoints
  getInventoryRisk: (params?: RiskParams) =>
    apiClient
      .get<PaginatedResponse<RiskSummary>>('/analytics/inventory-risk', { params })
      .then((r) => r.data),

  getProductRisk: (productId: string) =>
    apiClient
      .get<ProductRiskDetail>(`/analytics/inventory-risk/${productId}`)
      .then((r) => r.data),

  getRiskDistribution: () =>
    apiClient.get<RiskDistribution>('/analytics/risk-distribution').then((r) => r.data),

  getExpiringBatches: (params?: ExpiringParams) =>
    apiClient
      .get<PaginatedResponse<ExpiringBatch>>('/analytics/expiring', { params })
      .then((r) => r.data),

  getLowStock: (params?: { page?: number; page_size?: number }) =>
    apiClient
      .get<PaginatedResponse<StockStatusItem>>('/analytics/low-stock', { params })
      .then((r) => r.data),

  refreshRiskScores: () =>
    apiClient.post<{ updated: number; message: string }>('/analytics/inventory-risk/refresh').then((r) => r.data),

  getDemandMetrics: (productId: string) =>
    apiClient.get<DemandMetrics>(`/analytics/demand/${productId}`).then((r) => r.data),
}
