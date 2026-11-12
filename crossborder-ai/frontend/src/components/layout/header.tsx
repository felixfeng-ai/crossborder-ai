import { useQuery } from '@tanstack/react-query'
import { LogOut, Settings, CreditCard, ChevronDown, Globe, Store, Menu, ShieldCheck } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/authStore'
import { useStoreStore } from '@/stores/storeStore'
import { Badge } from '@/components/ui/badge'
import apiClient from '@/api/client'
import { getHeaderContext } from '@/lib/navigation'
import { normalizeLanguageCode } from '@/i18n/language'

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
  const { stores, currentStoreId, setStores, setCurrentStore } = useStoreStore()
  const headerContext = getHeaderContext(location.pathname)

  // 加载店铺列表
  useQuery({
    queryKey: ['header-shopify-channels'],
    queryFn: async () => {
      const r = await apiClient.get('/shopify/channels')
      const channels = (r.data || []).map((c: any) => ({
        id: c.id,
        name: c.shop_name,
        platform: 'shopify' as const,
      }))
      if (channels.length > 0) setStores(channels)
      return channels
    },
    enabled: !!user,
    retry: false,
  })

  const currentLanguageCode = normalizeLanguageCode(i18n.language)
  const currentLang =
    LANGUAGES.find((language) => language.code === currentLanguageCode) ||
    LANGUAGES.find((language) => language.code === 'zh') ||
    LANGUAGES[0]
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

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  // 头像显示优先级：username > full_name > email
  const displayName = user?.username || user?.full_name || user?.email || 'U'
  const avatarLetter = displayName.charAt(0).toUpperCase()

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
          <p className="truncate text-[10px] leading-4 text-muted-foreground">
            {headerContext.group}
          </p>
          <p className="truncate text-[13px] font-medium leading-5">
            {headerContext.title}
          </p>
        </div>
      </div>

      {/* Right */}
      <div className="flex items-center gap-2 lg:gap-4">
        {/* Language Switcher */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="flex items-center gap-1.5 px-2 text-muted-foreground">
              <Globe className="h-4 w-4" />
              <span className="hidden text-xs md:inline-block">{currentLang.label}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-44">
            <DropdownMenuLabel className="text-xs text-muted-foreground">
              {t('common.language')}
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            {LANGUAGES.map((lang) => (
              <DropdownMenuItem
                key={lang.code}
                className={i18n.language === lang.code ? 'bg-accent font-medium' : ''}
                onClick={() => switchLanguage(lang.code)}
              >
                {lang.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        {/* 店铺切换 */}
        {stores.length > 0 && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="flex items-center gap-1.5 px-2 text-muted-foreground">
                <Store className="h-4 w-4" />
                <span className="hidden text-xs md:inline-block">
                  {stores.find(s => s.id === currentStoreId)?.name || '选择店铺'}
                </span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-44">
              <DropdownMenuLabel className="text-xs text-muted-foreground">切换店铺</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {stores.map((s) => (
                <DropdownMenuItem
                  key={s.id}
                  className={currentStoreId === s.id ? 'bg-accent font-medium' : ''}
                  onClick={() => setCurrentStore(s.id)}
                >
                  <Store className="mr-2 h-3.5 w-3.5" />
                  {s.name}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        )}

        {/* Credits badge */}
        {user && (
          <button
            type="button"
            onClick={() => navigate('/app/billing')}
            title={creditTitle}
            aria-label={`${displayedCredits} 积分，${creditTitle}`}
            className="rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Badge variant="secondary" className="metric-number gap-1 px-2 py-1 text-xs">
              <CreditCard className="h-3 w-3" />
              <span>{displayedCredits.toLocaleString('zh-CN')}</span>
              <span className="hidden sm:inline">{t('header.credits')}</span>
            </Badge>
          </button>
        )}

        {/* User menu */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="flex items-center gap-2 px-2">
              <div className="metric-number flex h-7 w-7 items-center justify-center rounded border border-border bg-secondary text-[11px] font-medium text-foreground">
                {avatarLetter}
              </div>
              <span className="hidden text-sm font-medium md:inline-block max-w-[120px] truncate">
                {displayName}
              </span>
              <ChevronDown className="h-3 w-3 text-muted-foreground shrink-0" />
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
              <DropdownMenuItem onClick={() => navigate('/app/admin/upgrades')}>
                <ShieldCheck className="mr-2 h-4 w-4" />
                升级审核
              </DropdownMenuItem>
            )}
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
