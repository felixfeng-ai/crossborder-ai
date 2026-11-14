import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { RouteFallback } from '@/components/common/RouteFallback'
import { useAuthStore } from '@/stores/authStore'
import { AdminGuard } from '@/pages/admin/AdminGuard'

const PUBLIC_LEGAL_PATHS = [
  '/terms',
  '/privacy',
  '/data-processing',
  '/ai-disclosure',
  '/security',
  '/report',
  '/contact',
]

const RootLayout = lazy(() =>
  import('@/components/layout/root-layout').then((module) => ({
    default: module.RootLayout,
  })),
)
const LandingPage = lazy(() => import('@/pages/landing/LandingPage'))
const LoginPage = lazy(() => import('@/pages/auth/LoginPage'))
const RegisterPage = lazy(() => import('@/pages/auth/RegisterPage'))
const DashboardPage = lazy(() => import('@/pages/dashboard/DashboardPage'))
const ProductsPage = lazy(() => import('@/pages/products/ProductsPage'))
const ProductDetailPage = lazy(() => import('@/pages/products/ProductDetailPage'))
const SettingsPage = lazy(() => import('@/pages/settings/SettingsPage'))
const ContentPage = lazy(() => import('@/pages/content/ContentPage'))
const BillingPage = lazy(() => import('@/pages/billing/BillingPage'))
const AdminUpgradesPage = lazy(() => import('@/pages/billing/AdminUpgradesPage'))
const ShopifyPage = lazy(() => import('@/pages/shopify/ShopifyPage'))
const BatchPage = lazy(() => import('@/pages/batch/BatchPage'))
const RadarPage = lazy(() => import('@/pages/radar/RadarPage'))
const LedgerPage = lazy(() => import('@/pages/ledger/LedgerPage'))
const AgentPage = lazy(() => import('@/pages/agent/AgentPage'))
const ImagesPage = lazy(() => import('@/pages/images/ImagesPage'))
const VideoWorkspacePage = lazy(() => import('@/pages/videos/VideoWorkspacePage'))
const MaterialsPage = lazy(() => import('@/pages/assets/MaterialsPage'))
const CatalogPage = lazy(() => import('@/pages/catalog/CatalogPage'))
const OperationsPage = lazy(() => import('@/pages/operations/OperationsPage'))
const TutorialPage = lazy(() => import('@/pages/tutorial/TutorialPage'))
const LegalDocumentPage = lazy(() => import('@/pages/legal/LegalPage'))
const FeedbackPage = lazy(() => import('@/pages/feedback/FeedbackPage'))
const AdminLayout = lazy(() => import('@/pages/admin/AdminLayout'))
const AdminOverviewPage = lazy(() => import('@/pages/admin/AdminOverviewPage'))
const AdminAnalyticsPage = lazy(() => import('@/pages/admin/AdminAnalyticsPage'))
const AdminPerformancePage = lazy(() => import('@/pages/admin/AdminPerformancePage'))
const AdminPlansPage = lazy(() => import('@/pages/admin/AdminPlansPage'))
const AdminFeedbackPage = lazy(() => import('@/pages/admin/AdminFeedbackPage'))
const AdminAuditPage = lazy(() => import('@/pages/admin/AdminAuditPage'))

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Suspense fallback={<RouteFallback fullScreen />}>
      <Routes>
      {/* 公开页面 */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      {PUBLIC_LEGAL_PATHS.map((path) => (
        <Route
          key={path}
          path={path}
          element={<LegalDocumentPage path={path} />}
        />
      ))}

      {/* 独立管理员后台 */}
      <Route
        path="/admin"
        element={
          <AdminGuard>
            <AdminLayout />
          </AdminGuard>
        }
      >
        <Route index element={<Navigate to="/admin/overview" replace />} />
        <Route path="overview" element={<AdminOverviewPage />} />
        <Route path="analytics" element={<AdminAnalyticsPage />} />
        <Route path="performance" element={<AdminPerformancePage />} />
        <Route path="plans" element={<AdminPlansPage />} />
        <Route path="orders" element={<AdminUpgradesPage />} />
        <Route path="feedback" element={<AdminFeedbackPage />} />
        <Route path="audit" element={<AdminAuditPage />} />
      </Route>

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
         <Route path="feedback" element={<FeedbackPage />} />
         <Route
           path="admin/upgrades"
           element={<Navigate to="/admin/orders" replace />}
         />
        <Route path="settings" element={<SettingsPage />} />
      </Route>

      {/* 未匹配 → 跳首页 */}
      <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}
