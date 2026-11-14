import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/authStore'
import {
  Sparkles, ShoppingBag, Bot, DollarSign, ShieldCheck, TrendingUp, ImageIcon,
  ArrowRight, CheckCircle2, Zap, MessageSquareQuote, Clapperboard, FolderOpen,
  Play, Video,
  BookOpenText, PanelRightOpen,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { BrandMark } from '@/components/brand/BrandMark'
import { AssistantMark } from '@/components/brand/AssistantMark'
import PublicLegalFooter from '@/components/legal/PublicLegalFooter'
import { LandingDecisionPreview } from '@/components/landing/LandingDecisionPreview'
import { LandingPlatformStrip } from '@/components/landing/LandingPlatformStrip'
import { ThemeSwitcher } from '@/components/theme/ThemeSwitcher'
import apiClient from '@/api/client'
import {
  FALLBACK_CREDIT_PACKS,
  FALLBACK_PLANS,
  LANDING_ASSISTANT_CONTEXT,
  LANDING_AGENT_EXAMPLES,
  LANDING_FEATURES,
  LANDING_FLOW,
  LANDING_STATS,
  LANDING_VIDEO_MODES,
  LANDING_VIDEO_STYLES,
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
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 md:px-6">
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
            <ThemeSwitcher />
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
        <section data-landing-hero>
          <div className="mx-auto grid max-w-6xl gap-10 px-4 py-16 sm:px-6 lg:grid-cols-[minmax(0,1.08fr)_minmax(380px,0.92fr)] lg:items-center lg:py-20">
            <div className="min-w-0 max-w-2xl">
              <h1 className="text-[38px] font-semibold leading-[1.1] text-foreground sm:text-5xl md:text-[56px]">
                <span className="block">从选品判断到合规上架</span>
                <span className="block text-[var(--factory-accent)]">让 AI 跑完整条运营链路</span>
              </h1>
              <p className="mt-6 max-w-xl text-base leading-7 text-muted-foreground">
                输入商品链接、品类或买家评论，自动完成市场判断、利润测算、Listing、合规、图片视频与渠道发布。
              </p>

              <div className="mt-7 flex max-w-xl items-center gap-2 border border-[var(--factory-line-strong)] bg-[var(--factory-panel)] p-2">
                <input
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                  onKeyDown={(event) => event.key === 'Enter' && handleAnalyze()}
                  placeholder="输入商品链接、品类或买家评论..."
                  className="h-11 min-w-0 flex-1 rounded bg-transparent px-3 text-sm text-foreground outline-none placeholder:text-[var(--factory-faint)]"
                  aria-label="商品链接、品类或买家评论"
                />
                <Button onClick={handleAnalyze} className="h-11 shrink-0 gap-1.5 px-5">
                  <Sparkles className="h-4 w-4" />
                  开始 AI 分析
                </Button>
              </div>

              <p className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <span>Free 每月含 30 积分</span>
                <span>无需信用卡</span>
                <span>无需配置模型 Key</span>
              </p>

              <div className="mt-5 flex flex-wrap items-center gap-5">
                <button
                  type="button"
                  onClick={openVideoWorkspace}
                  className="inline-flex items-center gap-1.5 text-xs font-medium text-foreground hover:text-[var(--factory-accent)]"
                >
                  <Clapperboard className="h-3.5 w-3.5" />
                  用商品图生成视频
                </button>
                <button
                  type="button"
                  onClick={openTutorial}
                  className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
                >
                  <BookOpenText className="h-3.5 w-3.5" />
                  查看完整教程
                </button>
              </div>
            </div>

            <LandingDecisionPreview onContinue={openVideoWorkspace} />
          </div>
        </section>

        <LandingPlatformStrip />

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
                <div className="flex h-[58px] w-[58px] shrink-0 flex-col items-center justify-center gap-0.5 rounded-full border-[1.5px] border-[var(--factory-accent)] bg-[var(--factory-panel)] text-foreground">
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
                <span className="inline-flex items-center gap-2 border border-white/15 bg-black/65 px-3 py-1.5 text-xs text-white">
                  <Clapperboard className="h-3.5 w-3.5" />
                  视频工作台
                </span>
                <span className="border border-white/15 bg-black/65 px-2.5 py-1 font-mono text-[10px] text-white/75">
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
          <h2 className="mb-1 text-center text-lg font-semibold text-foreground">从判断到执行，一条链路完成</h2>
          <p className="mb-8 text-center text-sm text-muted-foreground">市场与利润 → VOC → Listing → 图片视频 → 店铺发布与巡检</p>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            {LANDING_FLOW.map((step, index) => {
              const Icon = FLOW_ICONS[index]
              return (
                <div key={step.step}
                  className="landing-panel rounded-lg p-4 text-center">
                  <div className="mb-2 font-mono text-xs text-[var(--factory-accent)]">{step.step}</div>
                  <Icon className="mx-auto mb-2 h-5 w-5 text-[var(--factory-accent)]" />
                  <h3 className="mb-0.5 text-sm font-medium text-foreground">{step.title}</h3>
                  <p className="text-xs text-muted-foreground">{step.desc}</p>
                </div>
              )
            })}
          </div>
        </section>

        {/* ── 功能 ────────────────────────────────────────── */}
        <section className="deferred-section max-w-5xl mx-auto px-4 py-16">
          <h2 className="mb-1 text-center text-lg font-semibold text-foreground">从真实反馈到店铺执行，覆盖完整运营链路</h2>
          <p className="mb-8 text-center text-sm text-muted-foreground">选品、评论洞察、内容、素材、发布和巡检使用同一套商品与任务上下文</p>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            {LANDING_FEATURES.map((feature) => {
              const Icon = FEATURE_ICONS[feature.icon]
              return (
                <div key={feature.title}
                  className="landing-panel rounded-lg p-5 transition-colors hover:border-[var(--factory-line-strong)]">
                  <div className="mb-3 flex h-8 w-8 items-center justify-center rounded-md bg-[color-mix(in_srgb,var(--factory-accent)_9%,transparent)]">
                    <Icon className="h-4 w-4 text-[var(--factory-accent)]" />
                  </div>
                  <h3 className="mb-1 text-sm font-medium text-foreground">{feature.title}</h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">{feature.desc}</p>
                </div>
              )
            })}
          </div>
        </section>

        {/* ── AI 智能助手 ──────────────────────────────────── */}
        <section className="deferred-section max-w-5xl mx-auto px-4 py-16">
          <h2 className="mb-1 text-center text-lg font-semibold text-foreground">从一句经营问题，到可复核的执行结果</h2>
          <p className="mb-8 text-center text-sm text-muted-foreground">图片检查、Listing 风险、政策依据和视频任务都可以直接交给 Agent</p>
          <div className="grid md:grid-cols-3 gap-4">
            {LANDING_AGENT_EXAMPLES.map((example) => (
              <div key={example.prompt}
                className="landing-panel rounded-lg p-5">
                <div className="flex items-start gap-2">
                  <Bot className="mt-0.5 h-4 w-4 shrink-0 text-[var(--factory-accent)]" />
                  <div>
                    <p className="text-sm font-medium text-foreground">{example.prompt}</p>
                    <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{example.steps}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ── 产品展示 ────────────────────────────────────── */}
        <section className="deferred-section max-w-5xl mx-auto px-4 py-16">
          <h2 className="mb-1 text-center text-lg font-semibold text-foreground">从真实评论证据到 Listing</h2>
          <p className="mb-8 text-center text-sm text-muted-foreground">VOC 提炼买家关注点，结果自动进入后续 Listing 生成上下文</p>
          <div className="grid md:grid-cols-2 gap-4">
            <div className="landing-panel rounded-lg p-4">
              <div className="flex items-center justify-between gap-2 mb-3">
                <div className="text-xs font-medium text-muted-foreground">VOC 示例输入</div>
                <span className="text-[10px] text-muted-foreground">示例数据</span>
              </div>
              <div className="space-y-3 text-sm">
                <div className="flex gap-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-[var(--factory-raised)] text-muted-foreground">
                    <FolderOpen className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="font-medium text-foreground">通勤耳机 · 3 条评论导入</p>
                    <p className="mt-1 text-xs text-muted-foreground">评论、CSV 和商品事实在同一个工作区</p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {['续航够用', '久戴夹耳', '地铁降噪一般', '连接稳定'].map((tag) => (
                    <span key={tag} className="landing-chip px-2 py-1 text-[11px]">
                      {tag}
                    </span>
                  ))}
                </div>
                <p className="text-xs leading-5 text-muted-foreground">
                  AI 自动聚合痛点、卖点、成交异议、关键词与情感倾向，并只保存聚合洞察。
                </p>
              </div>
            </div>
            <div className="landing-accent-panel rounded-lg p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="text-xs font-medium text-[var(--factory-accent)]">VOC + Listing 输出</div>
                <span className="rounded bg-[color-mix(in_srgb,var(--factory-success)_14%,transparent)] px-2 py-0.5 text-xs text-[var(--factory-success)]">上下文已复用</span>
              </div>
              <div className="space-y-3 text-sm">
                <div>
                  <p className="text-[11px] text-[var(--factory-accent)]">买家最在意</p>
                  <p className="mt-1 text-foreground">舒适佩戴、稳定连接和日常续航</p>
                </div>
                <div>
                  <p className="text-[11px] text-[var(--factory-accent)]">Listing 生成策略</p>
                  <p className="mt-1 text-sm leading-6 text-foreground">
                    优先表达真实使用场景，避免未经验证的绝对降噪和长时间无压宣称。
                  </p>
                </div>
                <div className="flex flex-wrap gap-1.5 border-t border-[color-mix(in_srgb,var(--factory-accent)_24%,transparent)] pt-3 text-[11px] text-muted-foreground">
                  <span>痛点反哺卖点</span>
                  <span>·</span>
                  <span>异议进入合规检查</span>
                  <span>·</span>
                  <span>可切换 11 个平台</span>
                </div>
              </div>
            </div>
          </div>
          <p className="mt-3 text-center text-xs text-muted-foreground">示例仅展示输入与输出结构；实际结果取决于商品事实和导入评论</p>
        </section>

        {/* ── 定价 ────────────────────────────────────────── */}
        <section className="deferred-section max-w-3xl mx-auto px-4 py-16">
          <h2 className="mb-1 text-center text-lg font-semibold text-foreground">简单透明的定价</h2>
          <p className="mb-8 text-center text-sm text-muted-foreground">
            Free 30 积分起；套餐积分按 30 天周期发放，购买积分不随月度额度重置
          </p>
          <div className="grid md:grid-cols-3 gap-4">
            {plans.map((plan) => (
              <div
                key={plan.id}
                className={
                  plan.recommended
                    ? 'landing-accent-panel relative rounded-lg border-2 p-6'
                    : 'landing-panel rounded-lg p-6'
                }
              >
                {plan.recommended && (
                  <div className="absolute -top-2.5 right-4 rounded bg-[var(--factory-accent)] px-3 py-0.5 text-xs text-[var(--factory-ground)]">
                    推荐
                  </div>
                )}
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="font-semibold text-foreground">{planDisplayName(plan.id)}</h3>
                    <p className="mt-1 text-[11px] text-muted-foreground">{plan.description}</p>
                  </div>
                  <span className="landing-chip shrink-0 px-2 py-1 text-[10px]">
                    {planValidityLabel(plan)}
                  </span>
                </div>
                <p className="mt-3 text-2xl font-semibold text-foreground">
                  {planPriceLabel(plan)}
                  {plan.price > 0 && <span className="text-sm font-normal text-muted-foreground">/月</span>}
                </p>
                <ul className="mt-4 space-y-2 text-sm text-muted-foreground">
                  {plan.features.map((feature) => (
                    <li key={feature} className="flex items-start gap-2">
                      <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--factory-success)]" />
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
          <div className="mt-8 border-t border-border pt-6">
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <h3 className="text-sm font-semibold text-foreground">超额积分包</h3>
                <p className="mt-1 text-xs text-muted-foreground">套餐额度不足时补充，购买积分不随月度额度重置</p>
              </div>
              <span className="text-[11px] text-muted-foreground">视频最低 12 积分/4 秒</span>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {creditPacks.map((pack) => (
                <div key={pack.id} className="landing-panel flex items-center justify-between rounded-md px-3 py-2.5">
                  <div>
                    <p className="text-xs font-medium text-foreground">{pack.name}</p>
                    <p className="metric-number mt-0.5 text-[11px] text-muted-foreground">{pack.credits.toLocaleString('zh-CN')} 积分</p>
                  </div>
                  <p className="metric-number text-sm font-semibold text-[var(--factory-accent)]">¥{pack.price}</p>
                </div>
              ))}
            </div>
            <p className="mt-3 text-[11px] leading-5 text-muted-foreground">
              套餐到期后自动回到 Free，未使用的购买积分继续保留。图片、视频、配音等高成本能力按实际用量扣减积分。
            </p>
          </div>
        </section>

        {/* ── 数据指标 ────────────────────────────────────── */}
        <section className="deferred-section max-w-3xl mx-auto px-4 py-12">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {LANDING_STATS.map((s) => (
              <div key={s.label} className="landing-panel rounded-lg p-4 text-center">
                <p className={`font-mono text-2xl font-semibold ${s.tone}`}>{s.value}</p>
                <p className="mt-1 text-xs text-muted-foreground">{s.label}</p>
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
