import { Routes, Route, Navigate } from 'react-router-dom'
import { RootLayout } from '@/components/layout/root-layout'
import LoginPage from '@/pages/auth/LoginPage'
import RegisterPage from '@/pages/auth/RegisterPage'
import DashboardPage from '@/pages/dashboard/DashboardPage'
import ProductsPage from '@/pages/products/ProductsPage'
import ProductDetailPage from '@/pages/products/ProductDetailPage'
import SettingsPage from '@/pages/settings/SettingsPage'
import LandingPage from '@/pages/landing/LandingPage'
import ContentPage from '@/pages/content/ContentPage'
import BillingPage from '@/pages/billing/BillingPage'
import AdminUpgradesPage from '@/pages/billing/AdminUpgradesPage'
import ShopifyPage from '@/pages/shopify/ShopifyPage'
import BatchPage from '@/pages/batch/BatchPage'
import RadarPage from '@/pages/radar/RadarPage'
import LedgerPage from '@/pages/ledger/LedgerPage'
import AgentPage from '@/pages/agent/AgentPage'
import ImagesPage from '@/pages/images/ImagesPage'
import VideoWorkspacePage from '@/pages/videos/VideoWorkspacePage'
import MaterialsPage from '@/pages/assets/MaterialsPage'
import CatalogPage from '@/pages/catalog/CatalogPage'
import OperationsPage from '@/pages/operations/OperationsPage'
import TutorialPage from '@/pages/tutorial/TutorialPage'
import LegalDocumentPage from '@/pages/legal/LegalPage'
import { LEGAL_DOCUMENTS } from '@/lib/legal'
import { useAuthStore } from '@/stores/authStore'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      {/* 公开页面 */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      {LEGAL_DOCUMENTS.map((document) => (
        <Route
          key={document.path}
          path={document.path}
          element={<LegalDocumentPage document={document} />}
        />
      ))}

      {/* 应用页面（需登录） */}
      <Route
        path="/app"
        element={
          <ProtectedRoute>
            <RootLayout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/app/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="agent" element={<AgentPage />} />
        <Route path="marketing-agent" element={<AgentPage mode="marketing" />} />
        <Route path="products" element={<ProductsPage />} />
        <Route path="products/:id" element={<ProductDetailPage />} />
        <Route path="content" element={<ContentPage />} />
        <Route path="images" element={<ImagesPage />} />
        <Route path="videos" element={<VideoWorkspacePage />} />
        <Route
          path="marketing-videos"
          element={<Navigate to="/app/videos?tab=marketing" replace />}
        />
        <Route path="assets" element={<MaterialsPage />} />
        <Route path="catalog" element={<CatalogPage />} />
        <Route path="operations" element={<OperationsPage />} />
        <Route path="shopify" element={<ShopifyPage />} />
        <Route path="batch" element={<BatchPage />} />
        <Route path="radar" element={<RadarPage />} />
        <Route path="ledger" element={<LedgerPage />} />
        <Route path="billing" element={<BillingPage />} />
        <Route path="tutorial" element={<TutorialPage />} />
        <Route path="admin/upgrades" element={<AdminUpgradesPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>

      {/* 未匹配 → 跳首页 */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
