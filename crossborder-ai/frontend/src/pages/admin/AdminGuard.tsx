import { useEffect, type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'

import { RouteFallback } from '@/components/common/RouteFallback'
import { useAuthStore } from '@/stores/authStore'

/**
 * 管理员路由围栏；后端仍会用 require_admin 做真实权限校验。
 */
export function AdminGuard({ children }: { children: ReactNode }) {
  const { isAuthenticated, user, loadUser, isLoading } = useAuthStore()

  useEffect(() => {
    if (isAuthenticated && !user && !isLoading) {
      void loadUser()
    }
  }, [isAuthenticated, isLoading, loadUser, user])

  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (!user || isLoading) return <RouteFallback fullScreen />
  if (!user.is_admin) return <Navigate to="/app/dashboard" replace />
  return <>{children}</>
}
