// Types mirroring backend schemas for categories, suppliers, and products.
// Kept in sync with app/schemas/category.py, supplier.py, product.py

// ---------------------------------------------------------------------------
// Category
// ---------------------------------------------------------------------------

export interface Category {
  id: string
  name: string
  description: string | null
  created_at: string
  updated_at: string
  product_count?: number
}

export interface CategoryCreateRequest {
  name: string
  description?: string
}

export interface CategoryUpdateRequest {
  name?: string
  description?: string
}

// ---------------------------------------------------------------------------
// Supplier
// ---------------------------------------------------------------------------

export interface Supplier {
  id: string
  name: string
  contact_name: string | null
  email: string | null
  phone: string | null
  address: string | null
  lead_time_days: number
  is_active: boolean
  created_at: string
  updated_at: string
  product_count?: number
}

export interface SupplierCreateRequest {
  name: string
  contact_name?: string
  email?: string
  phone?: string
  address?: string
  lead_time_days?: number
}

export interface SupplierUpdateRequest {
  name?: string
  contact_name?: string
  email?: string
  phone?: string
  address?: string
  lead_time_days?: number
  is_active?: boolean
}

// ---------------------------------------------------------------------------
// Product
// ---------------------------------------------------------------------------

export interface CategorySummary {
  id: string
  name: string
}

export interface SupplierSummary {
  id: string
  name: string
  lead_time_days: number
}

export interface Product {
  id: string
  sku: string
  name: string
  description: string | null
  category: CategorySummary
  supplier: SupplierSummary | null
  unit: string
  reorder_point: number
  reorder_quantity: number
  max_stock_level: number | null
  expiry_alert_days: number
  current_stock: number
  last_risk_score: number | null
  last_risk_level: RiskLevel | null
  is_active: boolean
  created_at: string
  updated_at: string
}

// Lightweight shape returned from the list endpoint
export interface ProductListItem {
  id: string
  sku: string
  name: string
  unit: string
  category_id: string
  category_name: string
  supplier_id: string | null
  supplier_name: string | null
  reorder_point: number
  max_stock_level: number | null
  current_stock: number
  last_risk_score: number | null
  last_risk_level: RiskLevel | null
  is_active: boolean
}

export interface ProductCreateRequest {
  sku: string
  name: string
  description?: string
  category_id: string
  supplier_id?: string
  unit?: string
  reorder_point?: number
  reorder_quantity?: number
  max_stock_level?: number
  expiry_alert_days?: number
}

export interface ProductUpdateRequest {
  name?: string
  description?: string
  category_id?: string
  supplier_id?: string
  unit?: string
  reorder_point?: number
  reorder_quantity?: number
  max_stock_level?: number
  expiry_alert_days?: number
  is_active?: boolean
}

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'

// ---------------------------------------------------------------------------
// Inventory Batch
// ---------------------------------------------------------------------------

export interface InventoryBatch {
  id: string
  product_id: string
  batch_number: string | null
  quantity: number
  remaining_qty: number
  cost_per_unit: number
  expiry_date: string | null   // ISO date string "YYYY-MM-DD"
  manufacture_date: string | null
  received_at: string
  notes: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface InventoryBatchPatch {
  batch_number?: string
  notes?: string
  expiry_date?: string
  manufacture_date?: string
  is_active?: boolean
}

// ---------------------------------------------------------------------------
// Stock transactions
// ---------------------------------------------------------------------------

export interface StockTransaction {
  id: string
  product_id: string
  batch_id: string | null
  transaction_type: TransactionType
  quantity: number
  unit_cost: number | null
  reference_type: string | null
  reference_id: string | null
  notes: string | null
  performed_by: string
  transaction_at: string
  created_at: string
}

export type TransactionType = 'STOCK_IN' | 'STOCK_OUT' | 'ADJUSTMENT' | 'WRITE_OFF' | 'TRANSFER'

// ---------------------------------------------------------------------------
// Stock-In
// ---------------------------------------------------------------------------

export interface StockInRequest {
  product_id: string
  quantity: number
  cost_per_unit: number
  batch_number?: string
  expiry_date?: string
  manufacture_date?: string
  notes?: string
  reference_type?: string
  reference_id?: string
}

export interface StockInResponse {
  transaction: StockTransaction
  batch: InventoryBatch
  updated_stock: number
}

// ---------------------------------------------------------------------------
// Stock-Out
// ---------------------------------------------------------------------------

export interface StockOutRequest {
  product_id: string
  quantity: number
  notes?: string
  reference_type?: string
  reference_id?: string
}

export interface BatchAllocation {
  batch_id: string
  batch_number: string | null
  quantity_taken: number
  cost_per_unit: number
  expiry_date: string | null
}

export interface StockOutResponse {
  transactions: StockTransaction[]
  allocations: BatchAllocation[]
  updated_stock: number
  total_quantity: number
}

// ---------------------------------------------------------------------------
// Adjustment
// ---------------------------------------------------------------------------

export interface AdjustmentRequest {
  product_id: string
  quantity_delta: number
  reason: string
  batch_id?: string
}

export interface AdjustmentResponse {
  transaction: StockTransaction
  updated_stock: number
  batch_updated: boolean
}

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

export interface InventoryOverview {
  total_products: number
  total_inventory_units: number
  inventory_value: number
  low_stock_count: number
  expiring_soon_count: number
  out_of_stock_count: number
}

export interface CategoryDistributionItem {
  category_id: string
  category_name: string
  product_count: number
  total_units: number
  total_value: number
}

export interface StockStatusItem {
  product_id: string
  sku: string
  name: string
  unit: string
  category_name: string
  current_stock: number
  reorder_point: number
  max_stock_level: number | null
  inventory_value: number
  is_low_stock: boolean
  nearest_expiry: string | null
  last_risk_level: RiskLevel | null
}

export interface RecentTransactionItem {
  id: string
  product_id: string
  product_name: string
  product_sku: string
  transaction_type: TransactionType
  quantity: number
  transaction_at: string
  performed_by_username: string
}

// ---------------------------------------------------------------------------
// Risk Types (Block 5)
// ---------------------------------------------------------------------------

export interface ContributingFactor {
  name: string
  score: number
  weight: number
  explanation: string
}

export interface RiskSummary {
  product_id: string
  sku: string
  name: string
  current_stock: number
  risk_score: number
  risk_level: RiskLevel
  average_daily_demand: number
  days_of_stock_remaining: number | null
  recommended_action: string
}

export interface ProductRiskDetail {
  product_id: string
  sku: string
  name: string
  unit: string
  current_stock: number
  reorder_point: number
  max_stock_level: number | null
  
  // Demand
  average_daily_demand: number
  recent_daily_demand: number
  demand_velocity_trend: string
  days_of_stock_remaining: number | null
  projected_stockout_date: string | null
  
  // Overall risk
  risk_score: number
  risk_level: RiskLevel
  
  // Sub-scores
  stockout_risk_score: number
  expiry_risk_score: number
  overstock_risk_score: number
  demand_velocity_score: number
  
  // Expiry
  earliest_expiry_date: string | null
  estimated_waste_value: number
  
  // Action
  recommended_action: string
  contributing_factors: ContributingFactor[]
}

export interface RiskDistribution {
  low: number
  medium: number
  high: number
  critical: number
  total: number
}

export interface DemandMetrics {
  average_daily: number
  recent_daily: number
  days_remaining: number | null
  velocity_trend: string
}

export interface ExpiringBatch {
  batch_id: string
  product_id: string
  sku: string
  product_name: string
  unit: string
  batch_number: string | null
  expiry_date: string
  days_until_expiry: number
  remaining_qty: number
  estimated_value: number
}
