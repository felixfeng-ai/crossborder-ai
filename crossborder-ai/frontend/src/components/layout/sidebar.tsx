import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  LayoutDashboard,
  Package,
  FileText,
  Image,
  ShoppingBag,
  BarChart3,
  CreditCard,
  Settings,
  Globe,
  ChevronLeft,
  Sparkles,
  Upload,
  Bot,
  X,
  Layers,
  Activity,
  Video,
  Clapperboard,
} from 'lucide-react'
import { cn } from '@/utils/cn'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/authStore'
import { useState } from 'react'
import { ShieldCheck } from 'lucide-react'

export function Sidebar({ onClose }: { onClose?: () => void }) {
  const { t } = useTranslation()
  const { user } = useAuthStore()
  const [collapsed, setCollapsed] = useState(false)

  const navItems = [
    { icon: LayoutDashboard, label: t('nav.dashboard'), path: '/app/dashboard' },
    { icon: Package, label: t('nav.products'), path: '/app/products' },
    { icon: Layers, label: 'SKU 与 Listing', path: '/app/catalog' },
    { icon: Activity, label: '运营监控', path: '/app/operations' },
    { icon: Sparkles, label: t('nav.content'), path: '/app/content' },
    { icon: Bot, label: t('nav.agent'), path: '/app/agent' },
    { icon: Image, label: t('nav.images'), path: '/app/images' },
    { icon: Clapperboard, label: 'AI 营销视频', path: '/app/marketing-videos' },
    { icon: Video, label: '单镜头视频', path: '/app/videos' },
    { icon: Upload, label: t('nav.batch'), path: '/app/batch' },
    { icon: Globe, label: t('nav.shopify'), path: '/app/shopify' },
    { icon: CreditCard, label: t('nav.billing'), path: '/app/billing' },
    ...(user?.is_admin
      ? [{ icon: ShieldCheck, label: '升级审核', path: '/app/admin/upgrades' }]
      : []),
    { icon: Settings, label: t('nav.settings'), path: '/app/settings' },
  ]

  return (
    <aside
      className={cn(
        'flex h-full flex-col border-r border-border bg-[var(--factory-side)]',
        collapsed ? 'w-16' : 'w-[232px]',
      )}
    >
      {/* Logo */}
      <div className="flex h-[58px] items-center justify-between border-b border-border px-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded border border-border bg-secondary shrink-0">
            <Globe className="h-4 w-4 text-foreground" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <span className="block whitespace-nowrap text-[14px] font-semibold leading-5">
                VeyaShip
              </span>
              <span className="block whitespace-nowrap text-[11px] leading-4 text-muted-foreground">
                跨境决策台
              </span>
            </div>
          )}
        </div>
        {onClose && (
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={onClose}
            aria-label="关闭导航"
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            onClick={onClose}
            title={item.label}
            className={({ isActive }) =>
              cn(
                'flex min-h-9 items-center gap-3 rounded px-2.5 text-[13px]',
                isActive
                  ? 'bg-secondary font-medium text-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-foreground',
                collapsed && 'justify-center px-2',
              )
            }
          >
            <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
            {!collapsed && <span>{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Collapse toggle */}
      <div className="border-t border-border p-2">
        <Button
          variant="ghost"
          size="icon"
          className={cn('w-full', collapsed && 'mx-auto')}
          onClick={() => setCollapsed(!collapsed)}
          aria-label={collapsed ? '展开侧栏' : '收起侧栏'}
        >
          <ChevronLeft
            className={cn(
              'h-4 w-4 transition-transform duration-150',
              collapsed && 'rotate-180',
            )}
          />
        </Button>
      </div>
    </aside>
  )
}
