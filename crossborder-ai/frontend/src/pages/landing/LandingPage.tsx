import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/authStore'
import {
  Sparkles, Globe, ShoppingBag, Bot, DollarSign, ShieldCheck, TrendingUp, ImageIcon,
  ArrowRight, CheckCircle2, Zap, MessageSquareQuote, Clapperboard, FolderOpen,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { BrandMark } from '@/components/brand/BrandMark'
import PublicLegalFooter from '@/components/legal/PublicLegalFooter'
import apiClient from '@/api/client'
import {
  FALLBACK_CREDIT_PACKS,
  FALLBACK_PLANS,
  LANDING_AGENT_EXAMPLES,
  LANDING_FEATURES,
  LANDING_FLOW,
  LANDING_PIPELINE,
  SUPPORTED_COPY_PLATFORMS,
  planDisplayName,
  planPriceLabel,
  planValidityLabel,
  type LandingCreditPack,
  type LandingFeatureIcon,
  type LandingPlan,
} from '@/lib/landing/content'

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.08 } },
}
const item = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.25, 0.1, 0.25, 1] } },
}

const FEATURE_ICONS: Record<LandingFeatureIcon, LucideIcon> = {
  agent: Bot,
  market: TrendingUp,
  compliance: ShieldCheck,
  media: ImageIcon,
  channel: ShoppingBag,
  ops: Zap,
}

const PIPELINE_ICONS: Record<(typeof LANDING_PIPELINE)[number]['icon'], LucideIcon> = {
  source: Globe,
  market: TrendingUp,
  voice: MessageSquareQuote,
  media: ImageIcon,
  channel: ShoppingBag,
}

const FLOW_ICONS: LucideIcon[] = [
  TrendingUp,
  DollarSign,
  MessageSquareQuote,
  Clapperboard,
  ShoppingBag,
]

export default function LandingPage() {
  const navigate = useNavigate()
  const isLoggedIn = useAuthStore((s) => s.isAuthenticated)
  const [keyword, setKeyword] = useState('')
  const plansQuery = useQuery<LandingPlan[]>({
    queryKey: ['public-plans'],
    queryFn: async () => {
      const response = await apiClient.get('/billing/plans')
      return response.data.plans || []
    },
  })
  const creditPacksQuery = useQuery<LandingCreditPack[]>({
    queryKey: ['public-credit-packs'],
    queryFn: async () => {
      const response = await apiClient.get('/billing/credit-packs')
      return response.data.packs || []
    },
  })
  const plans = plansQuery.data?.length ? plansQuery.data : FALLBACK_PLANS
  const creditPacks = creditPacksQuery.data?.length
    ? creditPacksQuery.data
    : FALLBACK_CREDIT_PACKS

  /** 真实品类分析需要登录（后端接口要求鉴权），首页这里只做引流 */
  const handleAnalyze = () => {
    if (!keyword.trim()) return
    navigate(isLoggedIn ? '/app/dashboard' : '/register')
  }

  return (
    <div className="relative min-h-[100dvh] overflow-hidden bg-[var(--factory-ground)] text-foreground">
      {/* ── 导航 ────────────────────────────────────────── */}
      <header className="sticky top-0 z-50 border-b border-border bg-[var(--factory-side)]">
        <div className="max-w-5xl mx-auto flex items-center justify-between h-14 px-4 md:px-6">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded border border-border bg-secondary">
              <BrandMark className="h-4 w-4 text-foreground" />
            </div>
            <span className="text-sm font-semibold">VeyaShip</span>
          </div>
          <div className="flex items-center gap-2">
            {isLoggedIn ? (
              <Button size="sm" onClick={() => navigate('/app/dashboard')}>进入应用</Button>
            ) : (
              <>
                <Button variant="ghost" size="sm" onClick={() => navigate('/login')}>登录</Button>
                <Button size="sm" onClick={() => navigate('/register')}>免费注册</Button>
              </>
            )}
          </div>
        </div>
      </header>

      <main className="relative z-10">
        {/* ── HERO ─────────────────────────────────────────── */}
        <section className="relative overflow-hidden">
          <div className="max-w-6xl mx-auto px-4 pt-20 pb-14 relative">
            <motion.div
              variants={container}
              initial="hidden"
              animate="show"
              className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_360px] lg:items-center"
            >
              <div className="max-w-2xl space-y-6">
                <motion.div variants={item}>
                  <span className="inline-flex items-center gap-1.5 rounded border border-border bg-card px-3.5 py-1 text-xs font-medium text-muted-foreground">
                    <Sparkles className="h-3 w-3" /> 跨境电商 AI 决策与执行工作台
                  </span>
                </motion.div>

                <motion.div variants={item} className="space-y-4">
                  <h1 className="text-3xl font-bold leading-[1.16] tracking-normal text-foreground sm:text-4xl md:text-5xl">
                    <span className="block">从选品判断到合规上架</span>
                    <span className="block">的一体化 AI 运营台</span>
                  </h1>
                  <p className="max-w-xl text-sm leading-relaxed text-muted-foreground sm:text-base">
                    输入品类、商品链接或买家评论，AI Agent 串起市场判断、VOC、Listing、合规、商品素材、SKU 与店铺执行，并把每一步结果留成可复核记录。
                  </p>
                </motion.div>

                {/* AI 分析输入框（真实入口，分析在登录后运行） */}
                <motion.div variants={item} className="w-full max-w-xl space-y-3">
                  <div className="flex items-center gap-2 rounded-lg border border-border bg-card p-1.5">
                    <input
                      value={keyword}
                      onChange={(e) => setKeyword(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleAnalyze()}
                      placeholder="输入品类名，如：蓝牙耳机、瑜伽裤、智能手表..."
                      className="h-10 min-w-0 flex-1 rounded bg-transparent px-3 text-sm outline-none"
                    />
                    <Button onClick={handleAnalyze} className="h-10 shrink-0 gap-1.5 px-4">
                      <Sparkles className="h-4 w-4" /> AI 分析
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">Free 每月含 30 积分 · 注册后运行真实 AI 市场分析</p>
                </motion.div>

                <motion.div variants={item} className="flex flex-wrap items-center gap-5 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1"><CheckCircle2 className="h-3 w-3 text-[var(--factory-mint)]" />无需信用卡</span>
                  <span className="flex items-center gap-1"><CheckCircle2 className="h-3 w-3 text-[var(--factory-mint)]" />无需配置模型 Key</span>
                  <span className="flex items-center gap-1"><CheckCircle2 className="h-3 w-3 text-[var(--factory-mint)]" />结果可追溯</span>
                </motion.div>

                <motion.div variants={item} className="flex flex-wrap items-center gap-2 pt-1">
                  {SUPPORTED_COPY_PLATFORMS.map((p) => (
                    <span key={p} className="rounded-md border border-border bg-card px-2.5 py-1 text-xs text-muted-foreground">
                      {p}
                    </span>
                  ))}
                </motion.div>
                <motion.p variants={item} className="text-[11px] leading-5 text-muted-foreground">
                  11 个平台支持 Listing 文案生成；Shopify 支持草稿发布，Amazon 已完成 SP-API 授权连接。
                </motion.p>
              </div>

              {/* 右栏展示真实决策链路，填满首屏空白并给出下一段内容的视觉锚点。 */}
              <motion.div
                variants={item}
                className="border-t border-border pt-7 lg:border-l lg:border-t-0 lg:pl-8"
                aria-label="AI 商品决策链路"
              >
                <div className="mb-5 flex items-center justify-between gap-4">
                  <div>
                    <p className="text-sm font-medium text-foreground">从商品证据到上架</p>
                    <p className="mt-1 text-xs text-muted-foreground">每一步都留下可复核结果</p>
                  </div>
                  <span className="font-mono text-[11px] text-[var(--factory-accent)]">05 STEPS</span>
                </div>
                <ol className="space-y-4">
                  {LANDING_PIPELINE.map((itemData) => {
                    const Icon = PIPELINE_ICONS[itemData.icon]
                    return (
                      <li key={itemData.step} className="grid grid-cols-[32px_28px_minmax(0,1fr)] items-start gap-2">
                        <span className="font-mono text-[11px] leading-6 text-muted-foreground">{itemData.step}</span>
                        <Icon className="mt-1 h-4 w-4 text-[var(--factory-accent)]" />
                        <div className="min-w-0 border-b border-border/70 pb-3">
                          <p className="text-sm font-medium text-foreground">{itemData.title}</p>
                          <p className="mt-0.5 text-xs text-muted-foreground">{itemData.detail}</p>
                        </div>
                      </li>
                    )
                  })}
                </ol>
              </motion.div>
            </motion.div>
          </div>
        </section>

        {/* ── 流程 ────────────────────────────────────────── */}
        <section className="max-w-4xl mx-auto px-4 py-16">
          <h2 className="text-lg font-semibold text-center text-slate-100 mb-1">从判断到执行，一条链路完成</h2>
          <p className="text-sm text-slate-500 text-center mb-8">市场与利润 → VOC → Listing → 图片视频 → 店铺发布与巡检</p>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            {LANDING_FLOW.map((step, index) => {
              const Icon = FLOW_ICONS[index]
              return (
                <motion.div key={step.step} initial={false}
                  className="text-center p-4 rounded-xl bg-white/5 border border-white/10 shadow-sm">
                  <div className="text-xs font-mono text-amber-400 mb-2">{step.step}</div>
                  <Icon className="h-5 w-5 text-amber-400 mx-auto mb-2" />
                  <h3 className="font-medium text-sm text-slate-200 mb-0.5">{step.title}</h3>
                  <p className="text-xs text-slate-500">{step.desc}</p>
                </motion.div>
              )
            })}
          </div>
        </section>

        {/* ── 功能 ────────────────────────────────────────── */}
        <section className="max-w-5xl mx-auto px-4 py-16">
          <h2 className="text-lg font-semibold text-center text-slate-100 mb-1">从真实反馈到店铺执行，覆盖完整运营链路</h2>
          <p className="text-sm text-slate-500 text-center mb-8">选品、评论洞察、内容、素材、发布和巡检使用同一套商品与任务上下文</p>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            {LANDING_FEATURES.map((feature) => {
              const Icon = FEATURE_ICONS[feature.icon]
              return (
                <motion.div key={feature.title} initial={false}
                  className="rounded-xl bg-white/5 border border-white/10 p-5 hover:shadow-md transition-shadow">
                  <div className="h-8 w-8 rounded-lg bg-amber-500/10 flex items-center justify-center mb-3">
                    <Icon className="h-4 w-4 text-amber-400" />
                  </div>
                  <h3 className="font-medium text-sm text-slate-100 mb-1">{feature.title}</h3>
                  <p className="text-sm text-slate-500 leading-relaxed">{feature.desc}</p>
                </motion.div>
              )
            })}
          </div>
        </section>

        {/* ── AI 智能助手 ──────────────────────────────────── */}
        <section className="max-w-5xl mx-auto px-4 py-16">
          <h2 className="text-lg font-semibold text-center text-slate-100 mb-1">AI 智能助手，说一句话就干活</h2>
          <p className="text-sm text-slate-500 text-center mb-8">评论分析、Listing、营销视频和店铺任务都可以直接交给 Agent</p>
          <div className="grid md:grid-cols-3 gap-4">
            {LANDING_AGENT_EXAMPLES.map((example) => (
              <motion.div key={example.prompt} initial={false}
                className="rounded-xl bg-white/5 border border-white/10 p-5">
                <div className="flex items-start gap-2">
                  <Bot className="h-4 w-4 text-amber-400 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-slate-100">{example.prompt}</p>
                    <p className="text-xs text-slate-500 mt-2 leading-relaxed">{example.steps}</p>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </section>

        {/* ── 产品展示 ────────────────────────────────────── */}
        <section className="max-w-5xl mx-auto px-4 py-16">
          <h2 className="text-lg font-semibold text-center text-slate-100 mb-1">从真实评论证据到 Listing</h2>
          <p className="text-sm text-slate-500 text-center mb-8">VOC 提炼买家关注点，结果自动进入后续 Listing 生成上下文</p>
          <div className="grid md:grid-cols-2 gap-4">
            <motion.div initial={false}
              className="rounded-xl border border-white/10 bg-white/5 p-4 shadow-sm">
              <div className="flex items-center justify-between gap-2 mb-3">
                <div className="text-xs font-medium text-slate-500 uppercase tracking-wide">VOC 示例输入</div>
                <span className="text-[10px] text-slate-500">示例数据</span>
              </div>
              <div className="space-y-3 text-sm">
                <div className="flex gap-3">
                  <div className="w-12 h-12 rounded-lg bg-white/10 flex items-center justify-center text-slate-400">
                    <FolderOpen className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="font-medium text-slate-100">通勤耳机 · 3 条评论导入</p>
                    <p className="text-slate-500 text-xs mt-1">评论、CSV 和商品事实在同一个工作区</p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {['续航够用', '久戴夹耳', '地铁降噪一般', '连接稳定'].map((tag) => (
                    <span key={tag} className="border border-white/10 px-2 py-1 text-[11px] text-slate-400">
                      {tag}
                    </span>
                  ))}
                </div>
                <p className="text-xs leading-5 text-slate-500">
                  AI 自动聚合痛点、卖点、成交异议、关键词与情感倾向，并只保存聚合洞察。
                </p>
              </div>
            </motion.div>
            <motion.div initial={false}
              className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 shadow-sm">
              <div className="flex items-center justify-between mb-3">
                <div className="text-xs font-medium text-amber-400 uppercase tracking-wide">VOC + Listing 输出</div>
                <span className="text-xs text-emerald-400 bg-emerald-500/20 px-2 py-0.5 rounded-full">上下文已复用</span>
              </div>
              <div className="space-y-3 text-sm">
                <div>
                  <p className="text-[11px] text-amber-400">买家最在意</p>
                  <p className="mt-1 text-slate-200">舒适佩戴、稳定连接和日常续航</p>
                </div>
                <div>
                  <p className="text-[11px] text-amber-400">Listing 生成策略</p>
                  <p className="mt-1 text-sm leading-6 text-slate-200">
                    优先表达真实使用场景，避免未经验证的绝对降噪和长时间无压宣称。
                  </p>
                </div>
                <div className="flex flex-wrap gap-1.5 border-t border-amber-500/20 pt-3 text-[11px] text-slate-400">
                  <span>痛点反哺卖点</span>
                  <span>·</span>
                  <span>异议进入合规检查</span>
                  <span>·</span>
                  <span>可切换 11 个平台</span>
                </div>
              </div>
            </motion.div>
          </div>
          <p className="text-xs text-slate-500 text-center mt-3">示例仅展示输入与输出结构；实际结果取决于商品事实和导入评论</p>
        </section>

        {/* ── 定价 ────────────────────────────────────────── */}
        <section className="max-w-3xl mx-auto px-4 py-16">
          <h2 className="text-lg font-semibold text-center text-slate-100 mb-1">简单透明的定价</h2>
          <p className="text-sm text-slate-500 text-center mb-8">
            Free 30 积分起；套餐积分按 30 天周期发放，购买积分不随月度额度重置
          </p>
          <div className="grid md:grid-cols-3 gap-4">
            {plans.map((plan) => (
              <motion.div
                key={plan.id}
                initial={false}
                className={
                  plan.recommended
                    ? 'rounded-xl border-2 border-amber-500/30 bg-amber-500/10 p-6 relative'
                    : 'rounded-xl border border-white/10 bg-white/5 p-6'
                }
              >
                {plan.recommended && (
                  <div className="absolute -top-2.5 right-4 bg-amber-500 text-white text-xs px-3 py-0.5 rounded-full">
                    推荐
                  </div>
                )}
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-semibold text-slate-100">{planDisplayName(plan.id)}</h3>
                    <p className="mt-1 text-[11px] text-slate-500">{plan.description}</p>
                  </div>
                  <span className="shrink-0 border border-white/10 px-2 py-1 text-[10px] text-slate-500">
                    {planValidityLabel(plan)}
                  </span>
                </div>
                <p className="text-2xl font-bold text-slate-100 mt-3">
                  {planPriceLabel(plan)}
                  {plan.price > 0 && <span className="text-sm font-normal text-slate-500">/月</span>}
                </p>
                <ul className="mt-4 space-y-2 text-sm text-slate-400">
                  {plan.features.map((feature) => (
                    <li key={feature} className="flex items-start gap-2">
                      <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>
                <Button
                  size="sm"
                  onClick={() => navigate(
                    isLoggedIn
                      ? plan.id === 'free' ? '/app/dashboard' : '/app/billing'
                      : '/register',
                  )}
                  className="w-full mt-6"
                >
                  {isLoggedIn
                    ? plan.id === 'free' ? '进入应用' : `选择 ${plan.name}`
                    : plan.id === 'free' ? '免费开始' : `选择 ${plan.name}`}
                </Button>
              </motion.div>
            ))}
          </div>
          <div className="mt-8 border-t border-white/10 pt-6">
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <h3 className="text-sm font-semibold text-slate-100">超额积分包</h3>
                <p className="mt-1 text-xs text-slate-500">套餐额度不足时补充，购买积分不随月度额度重置</p>
              </div>
              <span className="text-[11px] text-slate-500">视频最低 10 积分/次</span>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              {creditPacks.map((pack) => (
                <div key={pack.id} className="flex items-center justify-between border border-white/10 bg-white/[0.03] px-3 py-2.5">
                  <div>
                    <p className="text-xs font-medium text-slate-200">{pack.name}</p>
                    <p className="metric-number mt-0.5 text-[11px] text-slate-500">{pack.credits.toLocaleString('zh-CN')} 积分</p>
                  </div>
                  <p className="metric-number text-sm font-semibold text-amber-400">¥{pack.price}</p>
                </div>
              ))}
            </div>
            <p className="mt-3 text-[11px] leading-5 text-slate-500">
              套餐到期后自动回到 Free，未使用的购买积分继续保留。图片、视频、配音等高成本能力按实际用量扣减积分。
            </p>
          </div>
        </section>

        {/* ── 数据指标 ────────────────────────────────────── */}
        <section className="max-w-3xl mx-auto px-4 py-12">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { value: '20', label: 'AI 业务工具', tone: 'text-slate-100' },
              { value: '6', label: '预设工作流', tone: 'text-amber-400' },
              { value: '11', label: '平台文案支持', tone: 'text-emerald-400' },
              { value: '2', label: '真实店铺连接', tone: 'text-amber-400' },
            ].map((s) => (
              <div key={s.label} className="rounded-xl border border-white/10 bg-white/5 p-4 text-center shadow-sm">
                <p className={`text-2xl font-bold font-mono ${s.tone}`}>{s.value}</p>
                <p className="text-xs text-slate-500 mt-1">{s.label}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ── CTA ──────────────────────────────────────────── */}
        <section className="max-w-lg mx-auto px-4 py-16 text-center">
          <motion.div initial={false}
            className="space-y-4 rounded-lg border border-border bg-card p-8">
            <h2 className="text-lg font-semibold text-foreground">开始免费使用</h2>
            <p className="text-sm text-muted-foreground">无需信用卡，无需配置 API Key</p>
            <Button size="lg" onClick={() => navigate(isLoggedIn ? '/app/dashboard' : '/register')} className="h-11 px-6 text-sm gap-1.5 shadow-sm">
              {isLoggedIn ? '进入应用' : '创建免费账号'} <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </motion.div>
        </section>
      </main>

      <PublicLegalFooter />
    </div>
  )
}

function LinkIcon() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  )
}
