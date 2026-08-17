/**
 * AppRouter — all application routes.
 */
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { ProtectedRoute } from './ProtectedRoute'
import { AppLayout } from '../components/layout/AppLayout'
import { LoginPage } from '../pages/auth/LoginPage'
import { RegisterPage } from '../pages/auth/RegisterPage'
import { DashboardPage } from '../pages/dashboard/DashboardPage'
import { CategoriesPage } from '../pages/inventory/CategoriesPage'
import { SuppliersPage } from '../pages/inventory/SuppliersPage'
import { ProductsPage } from '../pages/inventory/ProductsPage'
import { InventoryPage } from '../pages/inventory/InventoryPage'
import { TransactionsPage } from '../pages/inventory/TransactionsPage'
import { InventoryRiskPage } from '../pages/analytics/InventoryRiskPage'
import { DemandForecastPage } from '../pages/analytics/DemandForecastPage'

function LegacyRiskForecastRedirect() {
  const location = useLocation()
  return <Navigate to={`/analytics/risk${location.search}`} replace />
}

export function AppRouter() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Protected — any authenticated user */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/inventory" element={<InventoryPage />} />
          <Route path="/transactions" element={<TransactionsPage />} />
          <Route path="/products" element={<ProductsPage />} />
          <Route path="/categories" element={<CategoriesPage />} />
          <Route path="/suppliers" element={<SuppliersPage />} />
          <Route path="/analytics/risk" element={<InventoryRiskPage />} />
          <Route path="/analytics/forecast" element={<DemandForecastPage />} />
          {/* Legacy combined route */}
          <Route path="/analytics/risk-forecast" element={<LegacyRiskForecastRedirect />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
