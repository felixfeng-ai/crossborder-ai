import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  Activity,
  ArrowLeft,
  BarChart3,
  ClipboardList,
  Gauge,
  Inbox,
  Menu,
  Package,
  ScrollText,
  X,
} from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

import { BrandMark } from '@/components/brand/BrandMark'
import { cn } from '@/utils/cn'

const adminQueryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30 * 1000,
    },
  },
})

const NAV_ITEMS = [
  { to: '/admin/overview', label: '运营总览', icon: Gauge },
  { to: '/admin/analytics', label: '访问分析', icon: BarChart3 },
  { to: '/admin/performance', label: '页面性能', icon: Activity },
  { to: '/admin/plans', label: '套餐管理', icon: Package },
  { to: '/admin/orders', label: '订单审核', icon: ClipboardList },
  { to: '/admin/feedback', label: '反馈收件箱', icon: Inbox },
  { to: '/admin/audit', label: '操作审计', icon: ScrollText },
]

function AdminNavigation({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="space-y-1" aria-label="管理员导航">
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon
        return (
          <NavLink
            key={item.to}
            to={item.to}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                'flex min-h-9 items-center gap-2.5 rounded-md px-3 text-sm transition-colors',
                isActive
                  ? 'bg-secondary font-medium text-foreground'
                  : 'text-muted-foreground hover:bg-secondary/70 hover:text-foreground',
              )
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            <span>{item.label}</span>
          </NavLink>
        )
      })}
    </nav>
  )
}

export default function AdminLayout() {
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <QueryClientProvider client={adminQueryClient}>
      <div data-admin-shell className="min-h-[100dvh] bg-[var(--factory-ground)] text-foreground">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[232px] border-r border-border bg-[var(--factory-side)] lg:flex lg:flex-col">
        <div className="flex h-[58px] items-center gap-2.5 border-b border-border px-4">
          <BrandMark className="h-6 w-6 text-foreground" />
          <div>
            <p className="text-sm font-semibold">VeyaShip Ops</p>
            <p className="text-[11px] text-muted-foreground">跨境运营控制台</p>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-3 py-4">
          <p className="mb-2 px-3 text-xs text-[var(--factory-faint)]">平台运营</p>
          <AdminNavigation />
        </div>
        <div className="border-t border-border p-3">
          <NavLink
            to="/app/dashboard"
            className="flex min-h-9 items-center gap-2 rounded-md px-3 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            返回卖家工作台
          </NavLink>
        </div>
      </aside>

      <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-border bg-[var(--factory-side)] px-4 lg:hidden">
        <div className="flex items-center gap-2">
          <BrandMark className="h-5 w-5" />
          <span className="text-sm font-semibold">VeyaShip Ops</span>
        </div>
        <button
          type="button"
          className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-border"
          aria-label={mobileOpen ? '关闭管理员导航' : '打开管理员导航'}
          onClick={() => setMobileOpen((value) => !value)}
        >
          {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </header>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-black/70"
            aria-label="关闭管理员导航"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="absolute inset-y-0 left-0 w-[min(84vw,320px)] border-r border-border bg-[var(--factory-side)] p-4">
            <div className="mb-5 flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold">VeyaShip Ops</p>
                <p className="text-xs text-muted-foreground">跨境运营控制台</p>
              </div>
              <button
                type="button"
                className="inline-flex h-10 w-10 items-center justify-center"
                aria-label="关闭管理员导航"
                onClick={() => setMobileOpen(false)}
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <AdminNavigation onNavigate={() => setMobileOpen(false)} />
            <NavLink
              to="/app/dashboard"
              className="mt-5 flex min-h-10 items-center gap-2 border-t border-border pt-4 text-sm text-muted-foreground"
            >
              <ArrowLeft className="h-4 w-4" />
              返回卖家工作台
            </NavLink>
          </aside>
        </div>
      )}

      <main className="lg:pl-[232px]">
        <div className="mx-auto w-full max-w-[1480px] px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </div>
      </main>
      </div>
    </QueryClientProvider>
  )
}
