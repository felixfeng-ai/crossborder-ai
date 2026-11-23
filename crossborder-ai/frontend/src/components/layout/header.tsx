import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Building2,
  Bell,
  Check,
  ChevronDown,
  CreditCard,
  Globe,
  Languages,
  LogOut,
  Menu,
  MessageSquareText,
  Monitor,
  Moon,
  MoreHorizontal,
  Settings,
  ShieldCheck,
  Store,
  Sun,
  Waves,
} from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/authStore'
import { useStoreStore } from '@/stores/storeStore'
import apiClient from '@/api/client'
import { getHeaderContext } from '@/lib/navigation'
import { normalizeLanguageCode } from '@/i18n/language'
import { DownloadAppDialog } from '@/components/layout/DownloadAppDialog'
import { useWorkspaceContextStore } from '@/features/workspace-context/workspace-context-store'
import { workspaceTypeLabel } from '@/features/workspace-context/workspace-context'
import { useNotificationsQuery } from '@/features/notifications/queries'
import { unreadNotificationCount } from '@/features/notifications/notifications'
import { UserAvatar } from '@/components/account/UserAvatar'
import { appQueryClient } from '@/lib/queryClient'
import { useThemeStore } from '@/stores/themeStore'
import { THEME_OPTIONS, type ThemeMode } from '@/utils/themes'

const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'zh', label: '中文' },
  { code: 'ja', label: '日本語' },
  { code: 'ko', label: '한국어' },
  { code: 'es', label: 'Español' },
  { code: 'fr', label: 'Français' },
  { code: 'de', label: 'Deutsch' },
  { code: 'pt', label: 'Português' },
  { code: 'ru', label: 'Русский' },
]

const THEME_ICONS = {
  graphite: Moon,
  paper: Sun,
  harbor: Waves,
  system: Monitor,
} satisfies Record<ThemeMode, typeof Moon>

interface BillingWalletSummary {
  plan_credits: number
  purchased_credits: number
  total_credits: number
}

export function Header({ onOpenMenu }: { onOpenMenu?: () => void }) {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()
  const { t, i18n } = useTranslation()
  const [downloadOpen, setDownloadOpen] = useState(false)
  const { mode: themeMode, setMode: setThemeMode } = useThemeStore()
  const { stores, currentStoreId, setStores, setCurrentStore } = useStoreStore()
  const workspaces = useWorkspaceContextStore((state) => state.workspaces)
  const activeWorkspaceId = useWorkspaceContextStore(
    (state) => state.activeWorkspaceId,
  )
  const setActiveWorkspace = useWorkspaceContextStore(
    (state) => state.setActiveWorkspace,
  )
  const workspaceDisplayName = useWorkspaceContextStore(
    (state) => state.displayName,
  )
  const workspaceAvatarUrl = useWorkspaceContextStore(
    (state) => state.avatarUrl,
  )
  const notifications = useNotificationsQuery(activeWorkspaceId)
  const headerContext = getHeaderContext(location.pathname)
  const activeWorkspace =
    workspaces.find((workspace) => workspace.id === activeWorkspaceId) ??
    workspaces[0] ??
    null
  const unreadNotifications = unreadNotificationCount(notifications.data ?? [])

  // 加载店铺列表
  useQuery({
    queryKey: ['header-shopify-channels', activeWorkspaceId],
    queryFn: async () => {
      const r = await apiClient.get('/shopify/channels')
      const channels = (r.data || []).map((c: any) => ({
        id: c.id,
        name: c.shop_name,
        platform: 'shopify' as const,
      }))
      // 空结果也必须覆盖旧缓存，避免切换工作区后继续显示上一工作区的店铺。
      setStores(channels)
      return channels
    },
    enabled: Boolean(user && activeWorkspaceId),
    retry: false,
  })

  const currentLanguageCode = normalizeLanguageCode(i18n.language)
  const currentLang =
    LANGUAGES.find((language) => language.code === currentLanguageCode) ||
    LANGUAGES.find((language) => language.code === 'zh') ||
    LANGUAGES[0]
  const currentTheme =
    THEME_OPTIONS.find((theme) => theme.value === themeMode) ??
    THEME_OPTIONS[0]
  const CurrentThemeIcon = THEME_ICONS[currentTheme.value]
  const walletQuery = useQuery<BillingWalletSummary>({
    queryKey: ['header-billing-wallet'],
    queryFn: async () => {
      const response = await apiClient.get('/billing/wallet')
      return response.data
    },
    enabled: Boolean(user),
    staleTime: 30_000,
    retry: false,
  })
  const displayedCredits = walletQuery.data?.total_credits ?? user?.credits ?? 0
  const creditTitle = walletQuery.data
    ? `套餐积分 ${walletQuery.data.plan_credits.toLocaleString('zh-CN')}，购买积分 ${walletQuery.data.purchased_credits.toLocaleString('zh-CN')}。点击查看账单`
    : '点击查看套餐与积分明细'

  const switchLanguage = (code: string) => {
    i18n.changeLanguage(code)
  }

  const switchWorkspace = (workspaceId: string) => {
    if (!workspaceId || workspaceId === activeWorkspaceId) return
    setActiveWorkspace(workspaceId)
    // 工作区切换必须重建所有页面查询，避免旧工作区缓存短暂串入新工作区。
    appQueryClient.clear()
    window.location.reload()
  }

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const displayName =
    user?.username ||
    user?.full_name ||
    user?.email ||
    workspaceDisplayName ||
    'U'
  const avatarUser =
    user ??
    (workspaceDisplayName
      ? {
          username: workspaceDisplayName,
          avatar_url: workspaceAvatarUrl,
        }
      : null)

  return (
    <header className="flex h-[58px] shrink-0 items-center justify-between border-b border-border bg-[var(--factory-side)] px-4 lg:px-6">
      {/* Left */}
      <div className="flex min-w-0 items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden"
          onClick={onOpenMenu}
          aria-label="打开导航"
        >
          <Menu className="h-4 w-4" />
        </Button>
        <div className="min-w-0">
          <p className="truncate text-[11px] leading-4 text-muted-foreground">
            {headerContext.group}
          </p>
          <p className="truncate text-[13px] font-medium leading-5">
            {headerContext.title}
          </p>
        </div>
      </div>

      {/* Right */}
      <div className="flex items-center gap-2 lg:gap-4">
        {workspaces.length > 0 && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="flex items-center gap-1.5 px-2 text-muted-foreground"
                aria-label={`当前工作区：${activeWorkspace?.name ?? '选择工作区'}`}
              >
                <Building2 className="h-4 w-4" />
                <span className="hidden max-w-[150px] truncate text-xs lg:inline">
                  {activeWorkspace?.name ?? '选择工作区'}
                </span>
                <ChevronDown className="hidden h-3 w-3 lg:block" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              <DropdownMenuLabel className="text-xs text-muted-foreground">
                当前工作区
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              {workspaces.map((workspace) => (
                <DropdownMenuItem
                  key={workspace.id}
                  className="items-start gap-2"
                  onClick={() => switchWorkspace(workspace.id)}
                >
                  <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center">
                    {workspace.id === activeWorkspaceId && (
                      <Check className="h-3.5 w-3.5 text-[var(--factory-accent)]" />
                    )}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate text-sm">
                      {workspace.name}
                    </span>
                    <span className="mt-0.5 block text-[11px] text-muted-foreground">
                      {workspaceTypeLabel(workspace.type)}
                    </span>
                  </span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        )}

        <Button
          variant="ghost"
          size="icon"
          className="relative"
          aria-label={
            unreadNotifications
              ? `通知，${unreadNotifications} 条未读`
              : '通知'
          }
          title="通知"
          onClick={() => navigate('/app/activity')}
        >
          <Bell className="h-4 w-4" />
          {unreadNotifications > 0 && (
            <span className="absolute right-1 top-1 flex min-h-4 min-w-4 items-center justify-center rounded-full bg-[var(--factory-coral)] px-1 text-[11px] font-semibold leading-4 text-white">
              {unreadNotifications > 99 ? '99+' : unreadNotifications}
            </span>
          )}
        </Button>

        {/* App 下载是增长入口，保留在顶栏；低频设置收进工具菜单。 */}
        <DownloadAppDialog
          open={downloadOpen}
          onOpenChange={setDownloadOpen}
          triggerClassName="gap-1.5 px-3 text-foreground"
        />

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label="工具与偏好"
              title="工具与偏好"
            >
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-64">
            <DropdownMenuLabel className="text-xs text-muted-foreground">
              工具与偏好
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            {user && (
              <DropdownMenuItem
                className="justify-between gap-3"
                onClick={() => navigate('/app/billing')}
                title={creditTitle}
              >
                <span className="flex items-center gap-2">
                  <CreditCard className="h-4 w-4 text-muted-foreground" />
                  积分与账单
                </span>
                <span className="metric-number text-xs font-medium">
                  {displayedCredits.toLocaleString('zh-CN')}
                </span>
              </DropdownMenuItem>
            )}
            <DropdownMenuSub>
              <DropdownMenuSubTrigger className="gap-2">
                <Languages className="h-4 w-4 text-muted-foreground" />
                <span className="flex-1">语言</span>
                <span className="text-xs text-muted-foreground">
                  {currentLang.label}
                </span>
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent className="w-44">
                {LANGUAGES.map((lang) => (
                  <DropdownMenuItem
                    key={lang.code}
                    className="justify-between"
                    onClick={() => switchLanguage(lang.code)}
                  >
                    {lang.label}
                    {currentLanguageCode === lang.code && (
                      <Check className="h-3.5 w-3.5 text-[var(--factory-accent)]" />
                    )}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuSubContent>
            </DropdownMenuSub>
            <DropdownMenuSub>
              <DropdownMenuSubTrigger className="gap-2">
                <CurrentThemeIcon className="h-4 w-4 text-muted-foreground" />
                <span className="flex-1">界面主题</span>
                <span className="text-xs text-muted-foreground">
                  {currentTheme.label}
                </span>
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent className="w-52">
                {THEME_OPTIONS.map((theme) => {
                  const Icon = THEME_ICONS[theme.value]
                  return (
                    <DropdownMenuItem
                      key={theme.value}
                      className="gap-2"
                      onClick={() => setThemeMode(theme.value)}
                    >
                      <Icon className="h-4 w-4 text-muted-foreground" />
                      <span className="flex-1">{theme.label}</span>
                      {themeMode === theme.value && (
                        <Check className="h-3.5 w-3.5 text-[var(--factory-accent)]" />
                      )}
                    </DropdownMenuItem>
                  )
                })}
              </DropdownMenuSubContent>
            </DropdownMenuSub>
            {stores.length > 0 && (
              <DropdownMenuSub>
                <DropdownMenuSubTrigger className="gap-2">
                  <Store className="h-4 w-4 text-muted-foreground" />
                  <span className="flex-1">当前店铺</span>
                  <span className="max-w-24 truncate text-xs text-muted-foreground">
                    {stores.find((store) => store.id === currentStoreId)?.name ||
                      '选择店铺'}
                  </span>
                </DropdownMenuSubTrigger>
                <DropdownMenuSubContent className="w-56">
                  {stores.map((store) => (
                    <DropdownMenuItem
                      key={store.id}
                      className="justify-between gap-2"
                      onClick={() => setCurrentStore(store.id)}
                    >
                      <span className="truncate">{store.name}</span>
                      {currentStoreId === store.id && (
                        <Check className="h-3.5 w-3.5 text-[var(--factory-accent)]" />
                      )}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuSubContent>
              </DropdownMenuSub>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="gap-2"
              onClick={() => navigate('/app/tutorial')}
            >
              <Globe className="h-4 w-4 text-muted-foreground" />
              使用教程
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* User menu */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="flex items-center gap-2 px-2">
              <UserAvatar user={avatarUser} className="h-7 w-7 text-[11px]" />
              <span className="hidden text-sm font-medium md:inline-block max-w-[120px] truncate">
                {displayName}
              </span>
              <ChevronDown className="hidden h-3 w-3 text-muted-foreground sm:block shrink-0" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuLabel>
              <div className="flex flex-col">
                <span className="font-medium truncate max-w-[180px]">{displayName}</span>
                <span className="text-xs text-muted-foreground truncate max-w-[180px]">
                  {user?.email}
                </span>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            {user?.is_admin && (
              <DropdownMenuItem onClick={() => navigate('/admin/overview')}>
                <ShieldCheck className="mr-2 h-4 w-4" />
                运营后台
              </DropdownMenuItem>
            )}
            <DropdownMenuItem onClick={() => navigate('/app/feedback')}>
              <MessageSquareText className="mr-2 h-4 w-4" />
              用户反馈
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => navigate('/app/settings')}>
              <Settings className="mr-2 h-4 w-4" />
              {t('header.settings')}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => navigate('/app/billing')}>
              <CreditCard className="mr-2 h-4 w-4" />
              {t('header.billing')}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={handleLogout}>
              <LogOut className="mr-2 h-4 w-4" />
              {t('header.logout')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
