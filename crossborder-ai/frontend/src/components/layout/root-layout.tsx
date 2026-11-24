import { Suspense, useState } from 'react'
import { Outlet, Navigate, useLocation } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { Sidebar } from './sidebar'
import { Header } from './header'
import { AgentSidecar } from '@/components/agent/AgentSidecar'
import { WorkspaceGate } from '@/components/layout/workspace-gate'
import { useAuthStore } from '@/stores/authStore'
import { useAgentSidecarStore } from '@/stores/agentSidecarStore'
import { RouteFallback } from '@/components/common/RouteFallback'
import { useEffect } from 'react'
import { appQueryClient } from '@/lib/queryClient'
import { useWorkspaceContextStore } from '@/features/workspace-context/workspace-context-store'
import { isAgentFullPage } from '@/lib/agent/sidecar'

const DEFAULT_MAIN_CLASS =
  'flex-1 overflow-y-auto p-4 pb-28 md:p-6 md:pb-28 lg:p-8 lg:pb-28'
const AGENT_MAIN_CLASS =
  'flex min-h-0 flex-1 flex-col overflow-hidden p-4 pb-4 md:p-6 md:pb-6 lg:p-8 lg:pb-8'

export function RootLayout() {
  const location = useLocation()
  const { isAuthenticated, loadUser, isLoading, token } = useAuthStore()
  const [mobileSidebar, setMobileSidebar] = useState(false)
  const agentSidecarOpen = useAgentSidecarStore((state) => state.isOpen)
  const agentFullPage = isAgentFullPage(location.pathname)

  useEffect(() => {
    if (token && !useAuthStore.getState().user) {
      loadUser()
    }
  }, [token, loadUser])

  useEffect(() => {
    const clearRuntime = () => {
      useWorkspaceContextStore.getState().clear()
      appQueryClient.clear()
    }
    window.addEventListener('veyaship:session-cleared', clearRuntime)
    return () =>
      window.removeEventListener('veyaship:session-cleared', clearRuntime)
  }, [])

  // 移动端导航或 AI 底部抽屉打开时禁止背景滚动。
  useEffect(() => {
    const media = window.matchMedia('(max-width: 1023px)')
    const syncOverflow = () => {
      document.body.style.overflow =
        mobileSidebar || (agentSidecarOpen && media.matches) ? 'hidden' : ''
    }
    syncOverflow()
    media.addEventListener('change', syncOverflow)
    return () => {
      media.removeEventListener('change', syncOverflow)
      document.body.style.overflow = ''
    }
  }, [mobileSidebar, agentSidecarOpen])

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return (
    <QueryClientProvider client={appQueryClient}>
      <WorkspaceGate>
        <div
          data-app-shell="graphite-decision-desk"
          className="app-canvas flex h-[100dvh] min-h-[100dvh] overflow-hidden"
        >
      {/* 桌面端侧边栏 */}
      <div className="hidden w-[232px] shrink-0 lg:flex">
        <Sidebar />
      </div>

      {/* 移动端侧边栏（遮罩） */}
      {mobileSidebar && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-black/60"
            aria-label="关闭导航"
            onClick={() => setMobileSidebar(false)}
          />
          <div className="absolute left-0 top-0 h-full">
            <Sidebar onClose={() => setMobileSidebar(false)} />
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Header onOpenMenu={() => setMobileSidebar(true)} />
        <main className={agentFullPage ? AGENT_MAIN_CLASS : DEFAULT_MAIN_CLASS}>
          <Suspense fallback={<RouteFallback />}>
            <Outlet />
          </Suspense>
        </main>
      </div>

          <AgentSidecar />
        </div>
      </WorkspaceGate>
    </QueryClientProvider>
  )
}
