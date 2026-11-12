import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  CreditCard,
  FileText,
  Film,
  Image as ImageIcon,
  Loader2,
  Mic2,
  PackageCheck,
  Play,
  Search,
  Sparkles,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import apiClient from '@/api/client'
import { creditBreakdownLabel, formatCreditTotal } from '@/lib/billing/balance'
import { useAuthStore } from '@/stores/authStore'
import { cn } from '@/utils/cn'

type BillingCycle = 'monthly' | 'annual'
type OutputMode = 'video' | 'image' | 'listing'

interface Plan {
  id: string
  name: string
  price: number
  price_label: string
  first_month_price: number
  first_month_bonus_credits: number
  annual_price: number
  annual_full_price: number
  description: string
  features: string[]
  validity_days: number
  recommended: boolean
}

interface Campaign {
  code: string
  name: string
  active: boolean
  starts_at: string
  ends_at: string
  first_month_eligible: boolean
  trial_pack_eligible: boolean
  plans: Plan[]
}

interface WalletInfo {
  plan: string
  plan_credits: number
  purchased_credits: number
  total_credits: number
  plan_expires_at: string | null
  subscription_status: string
}

interface CreditPack {
  id: string
  name: string
  credits: number
  price: number
  trial_once?: boolean
}

interface UpgradeRecord {
  id: string
  plan: string
  contact: string
  order_id: string
  amount: number
  original_amount: number
  billing_cycle: BillingCycle
  promotion_code: string | null
  bonus_credits: number
  duration_days: number
  status: 'pending' | 'approved' | 'rejected'
  note: string
  created_at: string | null
  handled_at: string | null
}

const STATUS_META: Record<
  UpgradeRecord['status'],
  { label: string; variant: 'success' | 'warning' | 'destructive' }
> = {
  pending: { label: '待确认', variant: 'warning' },
  approved: { label: '已开通', variant: 'success' },
  rejected: { label: '已拒绝', variant: 'destructive' },
}

const PLAN_NAMES: Record<string, string> = {
  free: 'Free',
  standard: 'Standard',
  professional: 'Professional',
}

function planView(plan: Plan, cycle: BillingCycle, eligible: boolean) {
  if (plan.id === 'free') {
    return {
      price: '¥0',
      period: '长期',
      original: '',
      note: '注册即得 30 积分，无需绑定信用卡',
      cta: '免费开始',
    }
  }
  if (cycle === 'annual') {
    return {
      price: `¥${plan.annual_price.toLocaleString('zh-CN')}`,
      period: '/ 年',
      original: `原价 ¥${plan.annual_full_price.toLocaleString('zh-CN')}`,
      note: `折合 ¥${(plan.annual_price / 12).toFixed(1)}/月，买 10 个月送 2 个月`,
      cta: `年付 ¥${plan.annual_price.toLocaleString('zh-CN')} 开通`,
    }
  }
  if (eligible) {
    return {
      price: `¥${plan.first_month_price}`,
      period: '/ 首月',
      original: `日常价 ¥${plan.price}`,
      note:
        plan.first_month_bonus_credits > 0
          ? `首月再送 ${plan.first_month_bonus_credits} 积分`
          : '首月自动应用活动价',
      cta: `首月 ¥${plan.first_month_price} 开通`,
    }
  }
  return {
    price: `¥${plan.price}`,
    period: '/ 月',
    original: '',
    note: '当前账号按日常价续费',
    cta: `以 ¥${plan.price} 升级`,
  }
}

function formatCampaignRange(startsAt: string, endsAt: string) {
  const formatter = new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
  })
  const end = new Date(endsAt)
  end.setDate(end.getDate() - 1)
  return `${formatter.format(new Date(startsAt))} 至 ${formatter.format(end)}`
}

const PLAN_ROLES: Record<string, string> = {
  free: '验证一条链路',
  standard: '日常运营提效',
  professional: '稳定生产内容',
}

const OUTPUT_OPTIONS: Array<{
  id: OutputMode
  label: string
  icon: typeof Film
  count: string
  unit: string
  detail: string
}> = [
  {
    id: 'video',
    label: '营销成片',
    icon: Film,
    count: '13',
    unit: '条',
    detail: '30 秒 / 768P / 8 镜头',
  },
  {
    id: 'image',
    label: '商品图',
    icon: ImageIcon,
    count: '666',
    unit: '张',
    detail: '3 积分 / 张',
  },
  {
    id: 'listing',
    label: 'Listing',
    icon: FileText,
    count: '2,000',
    unit: '份',
    detail: '1 积分 / 份',
  },
]

export default function BillingPage() {
  const { user } = useAuthStore()
  const queryClient = useQueryClient()
  const [billingCycle, setBillingCycle] = useState<BillingCycle>('monthly')
  const [outputMode, setOutputMode] = useState<OutputMode>('video')
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null)
  const [selectedPack, setSelectedPack] = useState<string | null>(null)
  const [contact, setContact] = useState('')
  const upgradeSectionRef = useRef<HTMLDivElement>(null)

  const campaignQuery = useQuery<Campaign>({
    queryKey: ['billing-campaign'],
    queryFn: async () => {
      const response = await apiClient.get('/billing/campaign')
      return response.data
    },
  })
  const campaign = campaignQuery.data

  const walletQuery = useQuery<WalletInfo>({
    queryKey: ['billing-wallet'],
    queryFn: async () => {
      const response = await apiClient.get('/billing/wallet')
      return response.data
    },
  })
  const wallet = walletQuery.data

  const packsQuery = useQuery<CreditPack[]>({
    queryKey: ['credit-packs'],
    queryFn: async () => {
      const response = await apiClient.get('/billing/credit-packs')
      return response.data.packs || []
    },
  })
  const packs = packsQuery.data || []

  const upgradesQuery = useQuery<UpgradeRecord[]>({
    queryKey: ['my-upgrades'],
    queryFn: async () => {
      const response = await apiClient.get('/billing/upgrades')
      return response.data.items || []
    },
  })
  const upgrades = upgradesQuery.data || []

  const upgradeMutation = useMutation({
    mutationFn: async (planId: string) => {
      const response = await apiClient.post('/billing/upgrade', {
        plan: planId,
        contact,
        billing_cycle: billingCycle,
      })
      return response.data as UpgradeRecord & { message: string; account?: unknown }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-upgrades'] })
      queryClient.invalidateQueries({ queryKey: ['billing-campaign'] })
    },
  })

  const packMutation = useMutation({
    mutationFn: async (packId: string) => {
      const response = await apiClient.post('/billing/credit-packs/purchase', {
        pack_id: packId,
        contact,
      })
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['billing-campaign'] })
    },
  })

  useEffect(() => {
    if (!selectedPlan) return
    const frame = window.requestAnimationFrame(() => {
      upgradeSectionRef.current?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [selectedPlan])

  if (!user) return null

  const plans = campaign?.plans || []
  const currentPlanName = PLAN_NAMES[user.plan] || 'Free'
  const currentPlan = plans.find((plan) => plan.id === user.plan)
  const packageExpires = wallet?.plan_expires_at
    ? new Date(wallet.plan_expires_at).toLocaleDateString('zh-CN')
    : '长期'
  const campaignActive = Boolean(campaign?.active)
  const firstMonthEligible = Boolean(campaign?.first_month_eligible)
  const trialEligible = Boolean(campaign?.trial_pack_eligible)

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="mx-auto max-w-[1120px] space-y-6"
    >
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-semibold leading-tight">账单与套餐</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            选择计划、查看积分消耗，并确认每一笔升级
          </p>
        </div>
        {campaignActive && (
          <span className="inline-flex items-center gap-2 border border-[color:var(--factory-accent)]/35 px-3 py-2 text-xs text-[color:var(--factory-accent)]">
            <Sparkles className="h-3.5 w-3.5" />
            {campaign && formatCampaignRange(campaign.starts_at, campaign.ends_at)}
          </span>
        )}
      </div>

      <section className="grid grid-cols-2 overflow-hidden rounded-lg border border-border bg-[var(--factory-surface)] xl:grid-cols-4" aria-label="当前账户状态">
        {[
          ['当前套餐', currentPlanName],
          ['套餐积分', formatCreditTotal(wallet?.plan_credits ?? 0)],
          ['购买积分', formatCreditTotal(wallet?.purchased_credits ?? 0)],
          ['套餐到期', currentPlan?.id === 'free' ? '长期' : packageExpires],
        ].map(([label, value], index) => (
          <div
            key={label}
            className={cn(
              'min-w-0 px-4 py-3',
              index % 2 === 1 && 'border-l border-border',
              index > 1 && 'border-t border-border',
              'xl:border-l xl:border-t-0',
              index === 0 && 'xl:border-l-0',
            )}
          >
            <p className="text-[10px] text-muted-foreground">{label}</p>
            <p className="metric-number mt-1 text-sm font-medium">{value}</p>
          </div>
        ))}
      </section>

      <section className="overflow-hidden rounded-lg border border-[color:var(--factory-accent)]/35 bg-[var(--factory-surface-raised)] lg:grid lg:grid-cols-[minmax(0,1.08fr)_minmax(360px,0.92fr)]">
        <div className="min-w-0 p-5 md:p-7">
          <div className="flex items-center gap-2 text-xs font-medium text-[color:var(--factory-accent)]">
            <Sparkles className="h-3.5 w-3.5" />
            {campaignActive ? `${campaign?.name} · 新客首月` : 'Professional 月度套餐'}
          </div>
          <h2 className="mt-3 max-w-[620px] text-balance text-[clamp(28px,3vw,42px)] font-semibold leading-[1.2]">
            把积分换成能发布的内容
          </h2>
          <p className="mt-2 max-w-[620px] text-sm leading-7 text-muted-foreground">
            从商品图、Listing 到营销成片，额度直接对应可执行产出。首月优惠、年付折扣与首购体验包规则清晰可见。
          </p>

          <div className="mt-5 flex flex-wrap items-end gap-x-3 gap-y-1">
            <strong className="metric-number text-[44px] font-semibold leading-none">
              {firstMonthEligible ? '¥199' : '¥249'}
            </strong>
            <span className="pb-1.5 text-xs text-muted-foreground">
              {firstMonthEligible ? '/ 首月' : '/ 月'}
            </span>
            {firstMonthEligible && (
              <span className="pb-1.5 text-xs text-muted-foreground">
                日常价 <s>¥249</s>
              </span>
            )}
          </div>

          <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
            <span className="border border-[color:var(--factory-accent)]/30 bg-[color:var(--factory-accent)]/10 px-2.5 py-1 text-[color:var(--factory-accent)]">
              {firstMonthEligible ? '首月最高省 ¥50' : '2,000 AI 积分'}
            </span>
            <span className="border border-border px-2.5 py-1 text-muted-foreground">
              年付买 10 个月送 2 个月
            </span>
            <span className="border border-border px-2.5 py-1 text-muted-foreground">
              {firstMonthEligible ? '再送 100 积分' : '购买积分长期保留'}
            </span>
          </div>

          <div className="mt-5 flex flex-wrap gap-2">
            <Button
              size="sm"
              onClick={() => {
                setBillingCycle('monthly')
                setSelectedPlan('professional')
              }}
            >
              以活动价升级
              <ChevronRight className="ml-1.5 h-3.5 w-3.5" />
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                document.getElementById('plan-comparison')?.scrollIntoView({
                  behavior: 'smooth',
                  block: 'start',
                })
              }}
            >
              比较全部套餐
            </Button>
          </div>
          <p className="mt-3 text-[10px] leading-5 text-muted-foreground">
            首月优惠每账号限一次，年付与首月优惠不可叠加；正式开通前由人工确认付款。
          </p>
        </div>

        <div className="border-t border-border p-4 md:p-5 lg:border-l lg:border-t-0">
          <div className="flex items-center justify-between gap-3">
            <div className="flex min-w-0 gap-1" role="tablist" aria-label="额度产出预览">
              {OUTPUT_OPTIONS.map((option) => {
                const Icon = option.icon
                return (
                  <button
                    key={option.id}
                    type="button"
                    role="tab"
                    aria-selected={outputMode === option.id}
                    aria-controls="output-preview-panel"
                    onClick={() => setOutputMode(option.id)}
                    className={cn(
                      'inline-flex min-h-8 items-center gap-1.5 rounded px-2.5 text-[11px] transition-colors',
                      outputMode === option.id
                        ? 'bg-foreground font-medium text-background'
                        : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
                    )}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {option.label}
                  </button>
                )
              })}
            </div>
            <span className="shrink-0 text-[10px] text-muted-foreground">示例素材</span>
          </div>

          <div
            id="output-preview-panel"
            role="tabpanel"
            className="mt-3 min-h-[238px] overflow-hidden rounded-md border border-border bg-[var(--factory-ground)]"
          >
            {outputMode === 'video' ? (
              <div className="grid h-[238px] grid-cols-[150px_minmax(0,1fr)]">
                <div className="relative min-h-0 overflow-hidden border-r border-border">
                  <img
                    src="/demo/terra-body-oil.webp"
                    alt="示例商品 Terra Daily Body Oil"
                    className="h-full w-full object-cover"
                  />
                  <div className="absolute inset-0 bg-black/20" />
                  <div className="absolute inset-x-3 bottom-3 text-white">
                    <p className="text-[10px] opacity-80">Terra Daily Body Oil</p>
                    <p className="mt-0.5 text-xs font-medium">冬日礼盒 · 30 秒</p>
                  </div>
                  <span className="absolute left-1/2 top-1/2 grid h-10 w-10 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border border-white/40 bg-black/35">
                    <Play className="h-4 w-4 fill-white text-white" />
                  </span>
                </div>
                <div className="flex min-w-0 flex-col justify-between p-4">
                  <div>
                    <p className="text-[10px] text-muted-foreground">分镜时间轴</p>
                    <div className="mt-3 space-y-2">
                      {[
                        ['01', '门口的快递', '4s'],
                        ['02', '拆开纸箱', '4s'],
                        ['03', '取出礼盒', '4s'],
                        ['04', '检查与轻嗅', '4s'],
                      ].map(([index, label, duration]) => (
                        <div key={index} className="flex items-center gap-2 text-[11px]">
                          <span className="metric-number text-[9px] text-[color:var(--factory-accent)]">{index}</span>
                          <span className="min-w-0 flex-1 truncate text-muted-foreground">{label}</span>
                          <span className="metric-number text-[9px] text-muted-foreground">{duration}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 border-t border-border pt-3 text-[10px] text-muted-foreground">
                    <Mic2 className="h-3 w-3" />
                    字幕、配音与成片素材统一沉淀
                  </div>
                </div>
              </div>
            ) : outputMode === 'image' ? (
              <div className="grid h-[238px] grid-cols-3 gap-2 p-3">
                {[
                  'object-center',
                  'object-left',
                  'object-right',
                ].map((position, index) => (
                  <div key={position} className="relative min-h-0 overflow-hidden border border-border bg-[var(--factory-panel)]">
                    <img
                      src="/demo/terra-body-oil.webp"
                      alt={`示例商品图 ${index + 1}`}
                      className={cn('h-full w-full object-cover', position)}
                    />
                    <span className="absolute left-2 top-2 bg-black/55 px-1.5 py-0.5 text-[9px] text-white">
                      {index === 0 ? 'Amazon' : index === 1 ? 'Shopify' : 'TikTok'}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex h-[238px] flex-col p-4">
                <div className="flex items-center justify-between gap-2 border-b border-border pb-3">
                  <div>
                    <p className="text-[10px] text-muted-foreground">Amazon Listing · 示例输出</p>
                    <p className="mt-1 text-sm font-medium">Terra Daily Body Oil for Winter Gifting</p>
                  </div>
                  <FileText className="h-4 w-4 shrink-0 text-[color:var(--factory-accent)]" />
                </div>
                <ul className="mt-3 grid flex-1 content-start gap-2 text-[11px] leading-5 text-muted-foreground">
                  <li>Lightweight daily body oil with a clean, gift-ready presentation.</li>
                  <li>Product facts, target market and VOC insights stay aligned.</li>
                  <li>Compliance status is attached to the current listing version.</li>
                </ul>
                <div className="flex flex-wrap gap-1.5 border-t border-border pt-3 text-[9px] text-muted-foreground">
                  <span className="border border-border px-1.5 py-0.5">标题</span>
                  <span className="border border-border px-1.5 py-0.5">五点描述</span>
                  <span className="border border-border px-1.5 py-0.5">SEO</span>
                  <span className="border border-border px-1.5 py-0.5">合规</span>
                </div>
              </div>
            )}
          </div>

          {OUTPUT_OPTIONS.map((option) => option.id === outputMode && (
            <div key={option.id} className="mt-3 flex items-end justify-between gap-3">
              <div>
                <p className="text-[10px] text-muted-foreground">Professional 月额度单用于{option.label}</p>
                <p className="mt-1 text-xs text-muted-foreground">{option.detail}</p>
              </div>
              <p className="metric-number shrink-0 text-lg font-semibold">
                {option.count}
                <span className="ml-1 text-[10px] font-normal text-muted-foreground">{option.unit}</span>
              </p>
            </div>
          ))}
        </div>
      </section>

      <div className="flex flex-wrap items-end justify-between gap-3 pt-2">
        <div>
          <h2 className="text-lg font-semibold">选择适合当前阶段的套餐</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            价格变化后，积分额度和按钮金额同步更新
          </p>
        </div>
        <div className="inline-flex rounded-md border border-border bg-[var(--factory-surface)] p-1" role="group" aria-label="计费周期">
          {([
            ['monthly', '按月', ''],
            ['annual', '按年', '省 16.7%'],
          ] as const).map(([value, label, hint]) => (
            <button
              key={value}
              type="button"
              aria-pressed={billingCycle === value}
              onClick={() => setBillingCycle(value)}
              className={cn(
                'min-h-8 rounded px-3 text-xs transition-colors',
                billingCycle === value
                  ? 'bg-foreground font-medium text-background'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {label}
              {hint && <span className="ml-1.5 text-[10px] opacity-70">{hint}</span>}
            </button>
          ))}
        </div>
      </div>

      <section id="plan-comparison" className="grid scroll-mt-6 overflow-hidden rounded-lg border border-border bg-[var(--factory-surface)] lg:grid-cols-3" aria-label="套餐对比">
        {campaignQuery.isLoading ? (
          <div className="col-span-full flex min-h-64 items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-[color:var(--factory-accent)]" />
          </div>
        ) : campaignQuery.isError ? (
          <div className="col-span-full flex min-h-64 flex-col items-center justify-center gap-3 p-6 text-center">
            <AlertCircle className="h-5 w-5 text-[color:var(--factory-coral)]" />
            <p className="text-sm text-muted-foreground">套餐信息加载失败</p>
            <Button size="sm" variant="outline" onClick={() => campaignQuery.refetch()}>
              重新加载
            </Button>
          </div>
        ) : (
          plans.map((plan, index) => {
            const view = planView(plan, billingCycle, firstMonthEligible)
            const isCurrent = user.plan === plan.id
            return (
              <article
                key={plan.id}
                className={cn(
                  'relative flex min-w-0 flex-col p-5 md:p-6',
                  index > 0 && 'border-t border-border lg:border-l lg:border-t-0',
                  plan.recommended && 'bg-[var(--factory-surface-raised)]',
                )}
              >
                {plan.recommended && (
                  <span className="absolute right-4 top-4 rounded border border-[color:var(--factory-accent)]/35 bg-[color:var(--factory-accent)]/10 px-2 py-0.5 text-[10px] text-[color:var(--factory-accent)]">
                    推荐
                  </span>
                )}
                <h3 className="text-[15px] font-semibold">{plan.name}</h3>
                <p className="mt-1 text-[10px] text-[color:var(--factory-accent)]">
                  {PLAN_ROLES[plan.id] || '按需选择'}
                </p>
                <p className="mt-2 min-h-10 text-xs leading-5 text-muted-foreground">
                  {plan.description}
                </p>
                <div className="mt-4 flex min-h-12 items-end gap-2">
                  <strong className="metric-number text-[34px] font-semibold leading-none">
                    {view.price}
                  </strong>
                  <span className="pb-1 text-xs text-muted-foreground">{view.period}</span>
                </div>
                <p className="mt-2 min-h-5 text-[11px] text-muted-foreground">
                  {view.original && <span className="mr-1 text-[color:var(--factory-accent)]">{view.original}；</span>}
                  {view.note}
                </p>
                <div className="my-4 h-px bg-border" />
                <ul className="space-y-2.5 text-xs leading-5 text-muted-foreground">
                  {plan.features.slice(0, 4).map((feature) => (
                    <li key={feature} className="flex items-start gap-2">
                      <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[color:var(--factory-mint)]" />
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>
                {plan.features.length > 4 && (
                  <details className="mt-3 text-[11px] text-muted-foreground">
                    <summary className="cursor-pointer list-none text-[color:var(--factory-accent)] hover:underline">
                      查看其余 {plan.features.length - 4} 项权益
                    </summary>
                    <ul className="mt-2 space-y-2">
                      {plan.features.slice(4).map((feature) => (
                        <li key={feature} className="flex items-start gap-2">
                          <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[color:var(--factory-mint)]" />
                          <span>{feature}</span>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
                <Button
                  size="sm"
                  className="mt-auto w-full"
                  variant={plan.recommended ? 'default' : 'outline'}
                  disabled={isCurrent}
                  onClick={() => {
                    upgradeMutation.reset()
                    setSelectedPlan(plan.id)
                  }}
                >
                  {isCurrent ? '当前套餐' : view.cta}
                  {!isCurrent && plan.id !== 'free' && <ArrowRight className="ml-2 h-3.5 w-3.5" />}
                </Button>
              </article>
            )
          })
        )}
      </section>

      <div ref={upgradeSectionRef}>
        {selectedPlan && (
          <section className="rounded-lg border border-[color:var(--factory-accent)]/35 bg-[var(--factory-surface)] p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold">
                  申请升级到 {planDisplayName(selectedPlan)}
                </h2>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  {billingCycle === 'annual' ? '年付' : '按月'}提交后由客服核对付款并开通，本页不会立即扣款。
                </p>
              </div>
              <button
                type="button"
                className="text-xs text-muted-foreground hover:text-foreground"
                onClick={() => {
                  setSelectedPlan(null)
                  upgradeMutation.reset()
                }}
              >
                取消
              </button>
            </div>
            {!upgradeMutation.data ? (
              <div className="mt-4 space-y-3">
                <input
                  value={contact}
                  onChange={(event) => setContact(event.target.value)}
                  placeholder="微信号 / 手机号"
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                  aria-label="联系方式"
                />
                <Button
                  className="w-full"
                  disabled={!contact.trim() || upgradeMutation.isPending}
                  onClick={() => upgradeMutation.mutate(selectedPlan)}
                >
                  {upgradeMutation.isPending ? (
                    <><Loader2 className="mr-2 h-4 w-4 animate-spin" />提交中</>
                  ) : (
                    '提交升级申请'
                  )}
                </Button>
                {upgradeMutation.error && (
                  <p className="text-xs text-destructive">
                    {upgradeMutation.error instanceof Error
                      ? upgradeMutation.error.message
                      : '升级申请提交失败'}
                  </p>
                )}
              </div>
            ) : (
              <div className="mt-4 space-y-3">
                <p className="border border-[color:var(--factory-mint)]/30 bg-[color:var(--factory-mint)]/10 px-3 py-2 text-xs text-[color:var(--factory-mint)]">
                  {upgradeMutation.data.message}
                </p>
                <div className="border border-border p-3 text-xs leading-6 text-muted-foreground">
                  <p>应付金额：<strong className="metric-number text-foreground">¥{upgradeMutation.data.amount}</strong></p>
                  <p>订单号：<code>{upgradeMutation.data.order_id}</code></p>
                  <p>计费周期：{upgradeMutation.data.billing_cycle === 'annual' ? '年付' : '按月'}</p>
                  {upgradeMutation.data.bonus_credits > 0 && (
                    <p>额外赠送：{upgradeMutation.data.bonus_credits} 积分</p>
                  )}
                </div>
              </div>
            )}
          </section>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.35fr_1fr]">
        <section className="rounded-lg border border-border bg-[var(--factory-surface)]">
          <div className="border-b border-border px-4 py-3">
            <h2 className="text-sm font-semibold">补充积分包</h2>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              购买积分长期保留，不随套餐月度额度重置
            </p>
          </div>
          <div className="px-4">
            {packs.map((pack) => {
              const trialUnavailable = Boolean(pack.trial_once && !trialEligible)
              return (
                <button
                  key={pack.id}
                  type="button"
                  disabled={trialUnavailable}
                  onClick={() => {
                    packMutation.reset()
                    setSelectedPack(pack.id)
                  }}
                  className={cn(
                    'grid min-h-14 w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-border py-2.5 text-left last:border-b-0',
                    trialUnavailable
                      ? 'cursor-not-allowed opacity-45'
                      : 'hover:text-[color:var(--factory-accent)]',
                  )}
                >
                  <span className="min-w-0">
                    <span className="block text-xs font-medium">
                      {pack.name}
                      {pack.trial_once && <span className="ml-2 text-[10px] text-[color:var(--factory-accent)]">首购一次</span>}
                    </span>
                    <span className="mt-0.5 block text-[10px] text-muted-foreground">
                      {trialUnavailable ? '当前账号已使用首购资格' : `${pack.credits.toLocaleString('zh-CN')} 积分`}
                    </span>
                  </span>
                  <span className="metric-number text-sm font-semibold">¥{pack.price}</span>
                </button>
              )
            })}
          </div>
          {selectedPack && (
            <div className="space-y-3 border-t border-border p-4">
              <input
                value={contact}
                onChange={(event) => setContact(event.target.value)}
                placeholder="微信 / 手机，用于付款确认"
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                aria-label="积分包联系方式"
              />
              <Button
                className="w-full"
                disabled={contact.trim().length < 2 || packMutation.isPending}
                onClick={() => packMutation.mutate(selectedPack)}
              >
                {packMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                提交积分包购买申请
              </Button>
              {packMutation.data && (
                <p className="text-xs text-[color:var(--factory-mint)]">{packMutation.data.message}</p>
              )}
              {packMutation.error && (
                <p className="text-xs text-[color:var(--factory-coral)]">
                  {packMutation.error instanceof Error ? packMutation.error.message : '提交失败'}
                </p>
              )}
            </div>
          )}
        </section>

        <section className="rounded-lg border border-border bg-[var(--factory-surface)]">
          <div className="border-b border-border px-4 py-3">
            <h2 className="text-sm font-semibold">积分怎么花</h2>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              高成本能力单独计价，文本能力保持低门槛
            </p>
          </div>
          <div className="grid grid-cols-2">
            {[
              ['AI Listing', '1 积分'],
              ['AI 图片', '3 积分 / 张'],
              ['480P 视频', '12 积分 / 4 秒'],
              ['768P 视频', '18 积分 / 4 秒'],
              ['AI 配音', '1 积分 / 100 字符'],
              ['配音最低消耗', '3 积分'],
            ].map(([label, value], index) => (
              <div
                key={label}
                className={cn(
                  'min-w-0 px-4 py-3',
                  index % 2 === 0 && 'border-r border-border',
                  index < 4 && 'border-b border-border',
                )}
              >
                <p className="text-[10px] text-muted-foreground">{label}</p>
                <p className="metric-number mt-1 text-xs font-medium">{value}</p>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="border-t border-border pt-4">
        <div className="grid gap-3 text-xs sm:grid-cols-4">
          <div>
            <p className="text-muted-foreground">套餐额度</p>
            <p className="metric-number mt-1">{wallet?.plan_credits ?? 0}</p>
          </div>
          <div>
            <p className="text-muted-foreground">购买积分</p>
            <p className="metric-number mt-1">{wallet?.purchased_credits ?? 0}</p>
          </div>
          <div>
            <p className="text-muted-foreground">套餐到期</p>
            <p className="mt-1">{packageExpires}</p>
          </div>
          <div>
            <p className="text-muted-foreground">当前额度构成</p>
            <p className="mt-1 text-muted-foreground">
              {wallet ? creditBreakdownLabel(wallet) : currentPlan?.name || '套餐额度 + 购买积分'}
            </p>
          </div>
        </div>
      </section>

      {upgrades.length > 0 && (
        <section className="rounded-lg border border-border bg-[var(--factory-surface)]">
          <div className="border-b border-border px-4 py-3">
            <h2 className="text-sm font-semibold">我的升级申请</h2>
          </div>
          <div className="divide-y divide-border px-4">
            {upgrades.map((item) => {
              const meta = STATUS_META[item.status]
              return (
                <div key={item.id} className="flex items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-medium">{planDisplayName(item.plan)} 套餐</p>
                      <Badge variant={meta.variant}>{meta.label}</Badge>
                      <span className="text-[10px] text-muted-foreground">
                        {item.billing_cycle === 'annual' ? '年付' : '月付'}
                      </span>
                    </div>
                    <p className="mt-1 truncate text-xs text-muted-foreground">
                      订单号 <code>{item.order_id}</code> · ¥{item.amount}
                      {item.bonus_credits > 0 ? ` · 赠 ${item.bonus_credits} 积分` : ''}
                      {item.note ? ` · ${item.note}` : ''}
                    </p>
                  </div>
                  <CreditCard className="h-4 w-4 shrink-0 text-muted-foreground" />
                </div>
              )
            })}
          </div>
        </section>
      )}
    </motion.div>
  )
}

function planDisplayName(planId: string) {
  return PLAN_NAMES[planId] || '套餐'
}
