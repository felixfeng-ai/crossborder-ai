import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Package,
  Image,
  ShoppingBag,
  CreditCard,
  Settings,
  ChevronLeft,
  Bot,
  X,
  Layers,
  Activity,
  Clapperboard,
  FolderOpen,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '@/utils/cn'
import { Button } from '@/components/ui/button'
import { useState } from 'react'
import { BrandMark } from '@/components/brand/BrandMark'
import { NAVIGATION_GROUPS } from '@/lib/navigation'

const NAV_ICONS: Record<string, LucideIcon> = {
  '/app/dashboard': LayoutDashboard,
  '/app/products': Package,
  '/app/catalog': Layers,
  '/app/agent': Bot,
  '/app/images': Image,
  '/app/videos': Clapperboard,
  '/app/assets': FolderOpen,
  '/app/operations': Activity,
  '/app/shopify': ShoppingBag,
  '/app/billing': CreditCard,
  '/app/settings': Settings,
}

export function Sidebar({ onClose }: { onClose?: () => void }) {
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)

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
          <div className="flex h-8 w-8 shrink-0 items-center justify-center border border-border bg-secondary">
            <BrandMark className="h-5 w-5 text-foreground" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <span className="block whitespace-nowrap text-[14px] font-semibold leading-5">
                VeyaShip
              </span>
              <span className="block whitespace-nowrap text-[11px] leading-4 text-muted-foreground">
                AI 跨境运营台
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
      <nav className="flex-1 overflow-y-auto px-2 py-2">
        {NAVIGATION_GROUPS.map((group, groupIndex) => (
          <section
            key={group.id}
            className={cn(
              groupIndex > 0 && 'mt-2 border-t border-border/60 pt-2',
            )}
          >
            {!collapsed && (
              <p className="px-2.5 pb-1 pt-1 text-[10px] leading-4 text-[var(--factory-faint)]">
                {group.label}
              </p>
            )}
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const Icon = NAV_ICONS[item.path]
                if (!Icon) return null
                const listingRouteActive =
                  item.path === '/app/catalog' &&
                  location.pathname.startsWith('/app/content')
                return (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    onClick={onClose}
                    title={item.label}
                    className={({ isActive }) =>
                      cn(
                        'flex min-h-9 items-center gap-3 rounded px-2.5 text-[13px]',
                        isActive || listingRouteActive
                          ? 'bg-secondary font-medium text-foreground'
                          : 'text-muted-foreground hover:bg-accent hover:text-foreground',
                        collapsed && 'justify-center px-2',
                      )
                    }
                  >
                    <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                    {!collapsed && <span>{item.label}</span>}
                  </NavLink>
                )
              })}
            </div>
          </section>
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
