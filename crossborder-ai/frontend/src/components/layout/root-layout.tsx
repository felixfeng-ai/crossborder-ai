import { useState } from 'react'
import { Outlet, Navigate } from 'react-router-dom'
import { Sidebar } from './sidebar'
import { Header } from './header'
import { useAuthStore } from '@/stores/authStore'
import { useEffect } from 'react'

export function RootLayout() {
  const { isAuthenticated, loadUser, isLoading, token } = useAuthStore()
  const [mobileSidebar, setMobileSidebar] = useState(false)

  useEffect(() => {
    if (token && !useAuthStore.getState().user) {
      loadUser()
    }
  }, [token, loadUser])

  // 移动端：侧边栏打开时禁止滚动
  useEffect(() => {
    document.body.style.overflow = mobileSidebar ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [mobileSidebar])

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return (
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
        <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
