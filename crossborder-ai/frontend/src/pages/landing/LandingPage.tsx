import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/authStore'
import {
  Sparkles, Globe, ShoppingBag, Bot, DollarSign, ShieldCheck, TrendingUp, ImageIcon,
  ArrowRight, CheckCircle2, Zap, MessageSquareQuote, Clapperboard, FolderOpen,
  Play, Video,
  BookOpenText, PanelRightOpen,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { BrandMark } from '@/components/brand/BrandMark'
import { AssistantMark } from '@/components/brand/AssistantMark'
import PublicLegalFooter from '@/components/legal/PublicLegalFooter'
import apiClient from '@/api/client'
import {
  FALLBACK_CREDIT_PACKS,
  FALLBACK_PLANS,
  LANDING_ASSISTANT_CONTEXT,
  LANDING_AGENT_EXAMPLES,
  LANDING_FEATURES,
  LANDING_FLOW,
  LANDING_PIPELINE,
  LANDING_STATS,
  LANDING_VIDEO_MODES,
  LANDING_VIDEO_STYLES,
  SUPPORTED_COPY_PLATFORMS,
  planDisplayName,
  planPriceLabel,
  planValidityLabel,
  type LandingCreditPack,
  type LandingFeatureIcon,
  type LandingPlan,
} from '@/lib/landing/content'

const FEATURE_ICONS: Record<LandingFeatureIcon, LucideIcon> = {
  agent: Bot,
  assistant: Bot,
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
  const [plans, setPlans] = useState<LandingPlan[]>(FALLBACK_PLANS)
  const [creditPacks, setCreditPacks] =
    useState<LandingCreditPack[]>(FALLBACK_CREDIT_PACKS)

  useEffect(() => {
    let active = true
    const timer = window.setTimeout(async () => {
      const [plansResult, packsResult] = await Promise.allSettled([
        apiClient.get('/billing/plans'),
        apiClient.get('/billing/credit-packs'),
      ])
      if (!active) return
      if (
        plansResult.status === 'fulfilled' &&
        plansResult.value.data.plans?.length
      ) {
        setPlans(plansResult.value.data.plans)
      }
      if (
        packsResult.status === 'fulfilled' &&
        packsResult.value.data.packs?.length
      ) {
        setCreditPacks(packsResult.value.data.packs)
      }
    }, 1200)
    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [])

  /** 真实品类分析需要登录（后端接口要求鉴权），首页这里只做引流 */
  const handleAnalyze = () => {
    if (!keyword.trim()) return
    navigate(isLoggedIn ? '/app/dashboard' : '/register')
  }

  const openVideoWorkspace = () => {
    navigate(isLoggedIn ? '/app/videos?tab=marketing' : '/register')
  }

  const openTutorial = () => {
    navigate(isLoggedIn ? '/app/tutorial' : '/register')
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
            <Button
              variant="ghost"
              size="sm"
              onClick={openTutorial}
              className="gap-1.5"
            >
              <BookOpenText className="h-3.5 w-3.5" />
              <span className="sm:hidden">教程</span>
              <span className="hidden sm:inline">使用教程</span>
            </Button>
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
            <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_360px] lg:items-center">
              <div className="max-w-2xl space-y-6">
                <div>
                  <span className="inline-flex items-center gap-1.5 rounded border border-border bg-card px-3.5 py-1 text-xs font-medium text-muted-foreground">
                    <Sparkles className="h-3 w-3" /> 跨境电商 AI 决策与执行工作台
                  </span>
                </div>

                <div className="space-y-4">
                  <h1 className="text-3xl font-bold leading-[1.16] tracking-normal text-foreground sm:text-4xl md:text-5xl">
                    <span className="block">从选品判断到合规上架</span>
                    <span className="block">的一体化 AI 运营台</span>
                  </h1>
                  <p className="max-w-xl text-sm leading-relaxed text-muted-foreground sm:text-base">
                    输入品类、商品链接或买家评论，AI Agent 串起市场判断、VOC、Listing、合规、商品图片与视频、SKU 与店铺执行。新增全局 AI 侧栏，让助手在当前页面直接读取任务上下文。
                  </p>
                </div>

                {/* AI 分析输入框（真实入口，分析在登录后运行） */}
                <div className="w-full max-w-xl space-y-3">
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
                  <Button
                    type="button"
                    variant="outline"
                    onClick={openVideoWorkspace}
                    className="h-9 gap-2 border-[color:var(--factory-accent)]/35 px-3 text-xs"
                  >
                    <Clapperboard className="h-3.5 w-3.5" />
                    用商品图生成视频
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={openTutorial}
                    className="h-9 gap-2 px-2 text-xs text-muted-foreground"
                  >
                    <BookOpenText className="h-3.5 w-3.5" />
                    查看完整教程
                  </Button>
                </div>

                <div className="flex flex-wrap items-center gap-5 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1"><CheckCircle2 className="h-3 w-3 text-[var(--factory-mint)]" />无需信用卡</span>
                  <span className="flex items-center gap-1"><CheckCircle2 className="h-3 w-3 text-[var(--factory-mint)]" />无需配置模型 Key</span>
                  <span className="flex items-center gap-1"><CheckCircle2 className="h-3 w-3 text-[var(--factory-mint)]" />结果可追溯</span>
                </div>

                <div className="flex flex-wrap items-center gap-2 pt-1">
                  {SUPPORTED_COPY_PLATFORMS.map((p) => (
                    <span key={p} className="rounded-md border border-border bg-card px-2.5 py-1 text-xs text-muted-foreground">
                      {p}
                    </span>
                  ))}
                </div>
                <p className="text-[11px] leading-5 text-muted-foreground">
                  11 个平台支持 Listing 文案生成；Shopify 支持草稿发布，Amazon 支持 SP-API Listing 发布。
                </p>
              </div>

              {/* 右栏展示真实决策链路，填满首屏空白并给出下一段内容的视觉锚点。 */}
              <div
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
              </div>
            </div>
          </div>
        </section>

        {/* ── 全局 AI 侧栏 ───────────────────────────────── */}
        <section className="deferred-section border-y border-border bg-[var(--factory-side)]">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 py-14 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:items-center lg:py-16">
            <div>
              <div className="flex items-center gap-2 text-xs font-medium text-[var(--factory-accent)]">
                <PanelRightOpen className="h-4 w-4" />
                全局 AI 决策助手
              </div>
              <h2 className="mt-3 text-2xl font-semibold leading-tight sm:text-3xl">
                不离开当前工作，也能随时问 AI
              </h2>
              <p className="mt-3 max-w-xl text-sm leading-7 text-muted-foreground">
                图片、视频、Listing 和运营页面共用同一个右下角入口。打开侧栏后，AI 会读取当前页面、选中素材和工作模式，关闭侧栏也不会取消正在执行的任务。
              </p>
              <div className="mt-6 flex flex-wrap items-center gap-3">
                <Button onClick={openTutorial} className="h-10 gap-2">
                  查看使用教程
                  <ArrowRight className="h-3.5 w-3.5" />
                </Button>
                <span className="text-[11px] text-muted-foreground">
                  快捷键 Alt + A · 支持桌面与移动端
                </span>
              </div>
            </div>

            <div className="relative border border-border bg-[var(--factory-panel)] p-5 sm:p-6">
              <div className="mb-4 flex items-center justify-between gap-4 border-b border-border pb-4">
                <div>
                  <p className="text-sm font-medium">当前页面上下文</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Agent 不再需要你重复说明正在看什么
                  </p>
                </div>
                <div className="flex h-[58px] w-[58px] shrink-0 flex-col items-center justify-center gap-0.5 rounded-full border-[1.5px] border-[rgba(216,181,109,0.9)] bg-[#181b18] text-foreground">
                  <AssistantMark className="h-6 w-6" />
                  <span className="text-[10px] font-semibold leading-3">问 AI</span>
                </div>
              </div>
              <div>
                {LANDING_ASSISTANT_CONTEXT.map((context, index) => (
                  <div
                    key={context.page}
                    className="grid gap-2 border-b border-border py-4 last:border-b-0 sm:grid-cols-[28px_120px_minmax(0,1fr)]"
                  >
                    <span className="font-mono text-[10px] leading-6 text-[var(--factory-faint)]">
                      {String(index + 1).padStart(2, '0')}
                    </span>
                    <div>
                      <p className="text-sm font-medium">{context.page}</p>
                      <p className="mt-0.5 text-[10px] text-[var(--factory-accent)]">
                        {context.detail}
                      </p>
                    </div>
                    <p className="text-xs leading-6 text-muted-foreground">
                      {context.result}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ── 视频工作台 ─────────────────────────────────── */}
        <section
          className="deferred-section max-w-6xl mx-auto px-4 py-14 sm:py-16"
          aria-labelledby="landing-video-title"
        >
          <div className="grid overflow-hidden border border-border bg-[var(--factory-panel)] lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]">
            <div className="relative min-h-[460px] overflow-hidden border-b border-border bg-[var(--factory-ground)] lg:min-h-[560px] lg:border-b-0 lg:border-r">
              <img
                src="/demo/terra-body-oil.webp"
                alt="Terra 身体油商品视频预览"
                loading="lazy"
                decoding="async"
                className="absolute inset-0 h-full w-full object-cover"
              />
              <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(8,9,9,0.08)_0%,rgba(8,9,9,0.22)_42%,rgba(8,9,9,0.94)_100%)]" />

              <div className="absolute left-5 right-5 top-5 flex items-center justify-between gap-3">
                <span className="inline-flex items-center gap-2 border border-white/15 bg-black/45 px-3 py-1.5 text-xs text-white backdrop-blur-sm">
                  <Clapperboard className="h-3.5 w-3.5" />
                  视频工作台
                </span>
                <span className="border border-white/15 bg-black/45 px-2.5 py-1 font-mono text-[10px] text-white/75">
                  9:16 · 768P
                </span>
              </div>

              <div className="absolute inset-x-5 bottom-5">
                <div className="mb-3 flex items-end justify-between gap-4">
                  <div>
                    <p className="text-xs text-white/65">标准商用 · 节日氛围</p>
                    <p className="mt-1 text-lg font-medium text-white">商品使用场景成片</p>
                  </div>
                  <span className="font-mono text-xs text-white/65">00:15</span>
                </div>
                <div className="h-1 overflow-hidden bg-white/20">
                  <div className="h-full w-[62%] bg-[var(--factory-accent)]" />
                </div>
                <div className="mt-3 flex items-center justify-between gap-3">
                  <span className="flex h-9 w-9 items-center justify-center rounded-full border border-white/20 bg-white/10 text-white">
                    <Play className="ml-0.5 h-3.5 w-3.5 fill-current" />
                  </span>
                  <span className="min-w-0 flex-1 truncate text-right text-[10px] text-white/55">
                    多商品图参考 · 三入口统一质量引擎
                  </span>
                </div>
              </div>
            </div>

            <div className="p-6 sm:p-8 lg:p-10">
              <p className="micro-label text-[var(--factory-accent)]">商品视频生产</p>
              <h2
                id="landing-video-title"
                className="mt-3 max-w-xl text-2xl font-semibold leading-tight text-foreground sm:text-3xl"
              >
                一张商品图，直接进入可投放视频
              </h2>
              <p className="mt-3 max-w-xl text-sm leading-7 text-muted-foreground">
                从营销创意到专业脚本，再到单镜头商品动态，三个入口共用商品参考图、质量档位、画面风格和成片素材中心。
              </p>

              <div className="mt-6 border-t border-border">
                {LANDING_VIDEO_MODES.map((mode, index) => {
                  const Icon = index === 0 ? Bot : index === 1 ? Clapperboard : Video
                  return (
                    <div
                      key={mode.id}
                      className="grid grid-cols-[30px_34px_minmax(0,1fr)] gap-3 border-b border-border py-4"
                    >
                      <span className="font-mono text-[10px] leading-7 text-muted-foreground">
                        {String(index + 1).padStart(2, '0')}
                      </span>
                      <Icon className="mt-1 h-4 w-4 text-[var(--factory-accent)]" />
                      <div className="min-w-0">
                        <h3 className="text-sm font-medium text-foreground">{mode.title}</h3>
                        <p className="mt-1 text-xs leading-5 text-muted-foreground">{mode.desc}</p>
                      </div>
                    </div>
                  )
                })}
              </div>

              <div className="mt-5 flex flex-wrap gap-1.5">
                {LANDING_VIDEO_STYLES.map((style) => (
                  <span
                    key={style}
                    className="border border-border bg-background px-2.5 py-1 text-[10px] text-muted-foreground"
                  >
                    {style}
                  </span>
                ))}
              </div>

              <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5">
                <p className="text-[11px] leading-5 text-muted-foreground">
                  自动封面 · 商品名下载 · 逐镜进度 · 历史素材可追溯
                </p>
                <Button onClick={openVideoWorkspace} className="h-9 gap-2 px-4 text-xs">
                  进入视频工作台
                  <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          </div>
        </section>

        {/* ── 流程 ────────────────────────────────────────── */}
        <section className="deferred-section max-w-4xl mx-auto px-4 py-16">
          <h2 className="text-lg font-semibold text-center text-slate-100 mb-1">从判断到执行，一条链路完成</h2>
          <p className="text-sm text-slate-500 text-center mb-8">市场与利润 → VOC → Listing → 图片视频 → 店铺发布与巡检</p>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            {LANDING_FLOW.map((step, index) => {
              const Icon = FLOW_ICONS[index]
              return (
                <div key={step.step}
                  className="text-center p-4 rounded-xl bg-white/5 border border-white/10 shadow-sm">
                  <div className="text-xs font-mono text-amber-400 mb-2">{step.step}</div>
                  <Icon className="h-5 w-5 text-amber-400 mx-auto mb-2" />
                  <h3 className="font-medium text-sm text-slate-200 mb-0.5">{step.title}</h3>
                  <p className="text-xs text-slate-500">{step.desc}</p>
                </div>
              )
            })}
          </div>
        </section>

        {/* ── 功能 ────────────────────────────────────────── */}
        <section className="deferred-section max-w-5xl mx-auto px-4 py-16">
          <h2 className="text-lg font-semibold text-center text-slate-100 mb-1">从真实反馈到店铺执行，覆盖完整运营链路</h2>
          <p className="text-sm text-slate-500 text-center mb-8">选品、评论洞察、内容、素材、发布和巡检使用同一套商品与任务上下文</p>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            {LANDING_FEATURES.map((feature) => {
              const Icon = FEATURE_ICONS[feature.icon]
              return (
                <div key={feature.title}
                  className="rounded-xl bg-white/5 border border-white/10 p-5 hover:shadow-md transition-shadow">
                  <div className="h-8 w-8 rounded-lg bg-amber-500/10 flex items-center justify-center mb-3">
                    <Icon className="h-4 w-4 text-amber-400" />
                  </div>
                  <h3 className="font-medium text-sm text-slate-100 mb-1">{feature.title}</h3>
                  <p className="text-sm text-slate-500 leading-relaxed">{feature.desc}</p>
                </div>
              )
            })}
          </div>
        </section>

        {/* ── AI 智能助手 ──────────────────────────────────── */}
        <section className="deferred-section max-w-5xl mx-auto px-4 py-16">
          <h2 className="text-lg font-semibold text-center text-slate-100 mb-1">从一句经营问题，到可复核的执行结果</h2>
          <p className="text-sm text-slate-500 text-center mb-8">图片检查、Listing 风险、政策依据和视频任务都可以直接交给 Agent</p>
          <div className="grid md:grid-cols-3 gap-4">
            {LANDING_AGENT_EXAMPLES.map((example) => (
              <div key={example.prompt}
                className="rounded-xl bg-white/5 border border-white/10 p-5">
                <div className="flex items-start gap-2">
                  <Bot className="h-4 w-4 text-amber-400 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-slate-100">{example.prompt}</p>
                    <p className="text-xs text-slate-500 mt-2 leading-relaxed">{example.steps}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ── 产品展示 ────────────────────────────────────── */}
        <section className="deferred-section max-w-5xl mx-auto px-4 py-16">
          <h2 className="text-lg font-semibold text-center text-slate-100 mb-1">从真实评论证据到 Listing</h2>
          <p className="text-sm text-slate-500 text-center mb-8">VOC 提炼买家关注点，结果自动进入后续 Listing 生成上下文</p>
          <div className="grid md:grid-cols-2 gap-4">
            <div className="rounded-xl border border-white/10 bg-white/5 p-4 shadow-sm">
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
            </div>
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 shadow-sm">
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
            </div>
          </div>
          <p className="text-xs text-slate-500 text-center mt-3">示例仅展示输入与输出结构；实际结果取决于商品事实和导入评论</p>
        </section>

        {/* ── 定价 ────────────────────────────────────────── */}
        <section className="deferred-section max-w-3xl mx-auto px-4 py-16">
          <h2 className="text-lg font-semibold text-center text-slate-100 mb-1">简单透明的定价</h2>
          <p className="text-sm text-slate-500 text-center mb-8">
            Free 30 积分起；套餐积分按 30 天周期发放，购买积分不随月度额度重置
          </p>
          <div className="grid md:grid-cols-3 gap-4">
            {plans.map((plan) => (
              <div
                key={plan.id}
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
              </div>
            ))}
          </div>
          <div className="mt-8 border-t border-white/10 pt-6">
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <h3 className="text-sm font-semibold text-slate-100">超额积分包</h3>
                <p className="mt-1 text-xs text-slate-500">套餐额度不足时补充，购买积分不随月度额度重置</p>
              </div>
              <span className="text-[11px] text-slate-500">视频最低 12 积分/4 秒</span>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
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
        <section className="deferred-section max-w-3xl mx-auto px-4 py-12">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {LANDING_STATS.map((s) => (
              <div key={s.label} className="rounded-xl border border-white/10 bg-white/5 p-4 text-center shadow-sm">
                <p className={`text-2xl font-bold font-mono ${s.tone}`}>{s.value}</p>
                <p className="text-xs text-slate-500 mt-1">{s.label}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ── CTA ──────────────────────────────────────────── */}
        <section className="deferred-section max-w-lg mx-auto px-4 py-16 text-center">
          <div className="space-y-4 rounded-lg border border-border bg-card p-8">
            <h2 className="text-lg font-semibold text-foreground">开始免费使用</h2>
            <p className="text-sm text-muted-foreground">无需信用卡，无需配置 API Key</p>
            <Button size="lg" onClick={() => navigate(isLoggedIn ? '/app/dashboard' : '/register')} className="h-11 px-6 text-sm gap-1.5 shadow-sm">
              {isLoggedIn ? '进入应用' : '创建免费账号'} <ArrowRight className="h-3.5 w-3.5" />
            </Button>
            <Button variant="outline" size="sm" onClick={openTutorial} className="gap-1.5">
              <BookOpenText className="h-3.5 w-3.5" />
              先看使用教程
            </Button>
          </div>
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
