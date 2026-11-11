import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/authStore'
import {
  Sparkles, Globe, ShoppingBag, Bot, DollarSign, ShieldCheck, TrendingUp,
  ArrowRight, CheckCircle2, Zap,
} from 'lucide-react'
import { BrandMark } from '@/components/brand/BrandMark'
import PublicLegalFooter from '@/components/legal/PublicLegalFooter'

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.08 } },
}
const item = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.25, 0.1, 0.25, 1] } },
}

const FEATURES = [
  { icon: Bot, title: 'AI 智能助手', desc: '说一句话就能干活："帮我选蓝牙耳机的品""检查一下我的店铺"。AI 自动拆解任务、调用工具、多步执行、生成结果。' },
  { icon: TrendingUp, title: 'AI 选品决策', desc: '告诉 AI 你想做的品类，自动分析 Amazon 市场容量、竞争格局、利润空间，判断这个品到底能不能做。' },
  { icon: DollarSign, title: '利润自动计算', desc: 'AI 自动获取 1688 供货价，结合平台费率、运费、广告成本，算出真实净利润和利润率。' },
  { icon: Zap, title: 'AI 生成 Listing', desc: '确定商品后自动生成 Amazon / Shopify 的标题、描述、卖点、SEO，多语言翻译对照可查验。' },
  { icon: ShieldCheck, title: '整店巡检', desc: '每天自动检查商品资料、Listing、素材、SKU、发布和运营风险，并生成可追溯待办。' },
  { icon: ShoppingBag, title: 'Shopify 一键发布', desc: 'AI 生成内容并合规通过后，可直接发布到绑定的 Shopify 店铺；Amazon、Temu、SHEIN 当前支持文案生成。' },
]

const PLATFORMS = ['Amazon', 'Shopify', 'eBay', 'Etsy', 'Temu', 'TikTok Shop', 'Walmart', 'AliExpress']

export default function LandingPage() {
  const navigate = useNavigate()
  const isLoggedIn = useAuthStore((s) => s.isAuthenticated)
  const [keyword, setKeyword] = useState('')

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
                    <Sparkles className="h-3 w-3" /> 跨境电商 AI 决策引擎 · AI Agent 自动化
                  </span>
                </motion.div>

                <motion.div variants={item} className="space-y-4">
                  <h1 className="text-3xl font-bold leading-[1.15] tracking-tight text-foreground sm:text-4xl md:text-5xl">
                    <span className="block">这个品能不能做？</span>
                    <span className="block">AI 帮你做跨境决策</span>
                  </h1>
                  <p className="max-w-xl text-sm leading-relaxed text-muted-foreground sm:text-base">
                    说一句话，AI Agent 帮你从选品到上架一条龙完成：选品分析 → 生成 Listing → 合规检查 → Shopify 一键发布，每天自动巡检你的店铺。
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
                  <p className="text-xs text-muted-foreground">免费注册即可使用 · 输入品类运行真实 AI 市场分析</p>
                </motion.div>

                <motion.div variants={item} className="flex flex-wrap items-center gap-5 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1"><CheckCircle2 className="h-3 w-3 text-[var(--factory-mint)]" />无需信用卡</span>
                  <span className="flex items-center gap-1"><CheckCircle2 className="h-3 w-3 text-[var(--factory-mint)]" />无需配置 API</span>
                  <span className="flex items-center gap-1"><CheckCircle2 className="h-3 w-3 text-[var(--factory-mint)]" />注册即用</span>
                </motion.div>

                <motion.div variants={item} className="flex flex-wrap items-center gap-2 pt-1">
                  {PLATFORMS.map((p) => (
                    <span key={p} className="rounded-md border border-border bg-card px-2.5 py-1 text-xs text-muted-foreground">
                      {p}
                    </span>
                  ))}
                </motion.div>
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
                  <span className="font-mono text-[11px] text-[var(--factory-accent)]">04 STEPS</span>
                </div>
                <ol className="space-y-4">
                  {[
                    { step: '01', icon: Globe, title: '来源商品', detail: '链接、CSV 或手动录入' },
                    { step: '02', icon: TrendingUp, title: '市场判断', detail: '竞争、利润与风险' },
                    { step: '03', icon: Sparkles, title: 'Listing', detail: '标题、详情、卖点与 SEO' },
                    { step: '04', icon: ShoppingBag, title: '渠道发布', detail: '合规通过后上架' },
                  ].map((itemData) => (
                    <li key={itemData.step} className="grid grid-cols-[32px_28px_minmax(0,1fr)] items-start gap-2">
                      <span className="font-mono text-[11px] leading-6 text-muted-foreground">{itemData.step}</span>
                      <itemData.icon className="mt-1 h-4 w-4 text-[var(--factory-accent)]" />
                      <div className="min-w-0 border-b border-border/70 pb-3">
                        <p className="text-sm font-medium text-foreground">{itemData.title}</p>
                        <p className="mt-0.5 text-xs text-muted-foreground">{itemData.detail}</p>
                      </div>
                    </li>
                  ))}
                </ol>
              </motion.div>
            </motion.div>
          </div>
        </section>

        {/* ── 流程 ────────────────────────────────────────── */}
        <section className="max-w-4xl mx-auto px-4 py-16">
          <h2 className="text-lg font-semibold text-center text-slate-100 mb-1">从选品到上架，四步完成</h2>
          <p className="text-sm text-slate-500 text-center mb-8">AI 分析品类 → 决定能不能做 → 生成 Listing → 发布到店铺</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { icon: Bot, step: '01', title: 'AI 选品分析', desc: '输入品类，AI 分析市场机会' },
              { icon: DollarSign, step: '02', title: '利润测算', desc: '自动算净利和利润率' },
              { icon: Sparkles, step: '03', title: 'AI 生成 Listing', desc: '自动写标题描述卖点' },
              { icon: ShoppingBag, step: '04', title: '发布 Shopify 草稿', desc: '完整同步内容、SKU 与素材' },
            ].map((s, i) => (
              <motion.div key={i} initial={false}
                className="text-center p-4 rounded-xl bg-white/5 border border-white/10 shadow-sm">
                <div className="text-xs font-mono text-amber-400 mb-2">{s.step}</div>
                <s.icon className="h-5 w-5 text-amber-400 mx-auto mb-2" />
                <h3 className="font-medium text-sm text-slate-200 mb-0.5">{s.title}</h3>
                <p className="text-xs text-slate-500">{s.desc}</p>
              </motion.div>
            ))}
          </div>
        </section>

        {/* ── 功能 ────────────────────────────────────────── */}
        <section className="max-w-5xl mx-auto px-4 py-16">
          <h2 className="text-lg font-semibold text-center text-slate-100 mb-1">覆盖跨境卖家核心决策链路</h2>
          <p className="text-sm text-slate-500 text-center mb-8">选品分析 → 利润测算 → Listing 生成 → 上架发布，一个平台完成</p>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            {FEATURES.map((f, i) => (
              <motion.div key={i} initial={false}
                className="rounded-xl bg-white/5 border border-white/10 p-5 hover:shadow-md transition-shadow">
                <div className="h-8 w-8 rounded-lg bg-amber-500/10 flex items-center justify-center mb-3">
                  <f.icon className="h-4 w-4 text-amber-400" />
                </div>
                <h3 className="font-medium text-sm text-slate-100 mb-1">{f.title}</h3>
                <p className="text-sm text-slate-500 leading-relaxed">{f.desc}</p>
              </motion.div>
            ))}
          </div>
        </section>

        {/* ── AI 智能助手 ──────────────────────────────────── */}
        <section className="max-w-5xl mx-auto px-4 py-16">
          <h2 className="text-lg font-semibold text-center text-slate-100 mb-1">AI 智能助手，说一句话就干活</h2>
          <p className="text-sm text-slate-500 text-center mb-8">不用记操作步骤，像跟同事说话一样，AI 自动完成整个流程</p>
          <div className="grid md:grid-cols-3 gap-4">
            {[
              { prompt: '"我想做蓝牙耳机，帮我选品"', steps: 'AI 分析市场 → 推荐值得做的商品 → 算利润 → 生成 Listing' },
              { prompt: '"把这款 1688 商品上架到 Shopify"', steps: '抓取商品 → 翻译 → 生成 Listing → 合规检查 → 一键发布' },
              { prompt: '"检查一下我的店铺"', steps: '整店巡检 → 找出缺信息的问题商品 → 生成待办清单' },
            ].map((c, i) => (
              <motion.div key={i} initial={false}
                className="rounded-xl bg-white/5 border border-white/10 p-5">
                <div className="flex items-start gap-2">
                  <Bot className="h-4 w-4 text-amber-400 mt-0.5 shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-slate-100">{c.prompt}</p>
                    <p className="text-xs text-slate-500 mt-2 leading-relaxed">{c.steps}</p>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </section>

        {/* ── 产品展示 ────────────────────────────────────── */}
        <section className="max-w-5xl mx-auto px-4 py-16">
          <h2 className="text-lg font-semibold text-center text-slate-100 mb-1">看看 AI 生成的效果</h2>
          <p className="text-sm text-slate-500 text-center mb-8">AI 分析品类数据 → 给出选品建议 → 生成 Listing</p>
          <div className="grid md:grid-cols-2 gap-4">
            <motion.div initial={false}
              className="rounded-xl border border-white/10 bg-white/5 p-4 shadow-sm">
              <div className="text-xs font-medium text-slate-500 mb-3 uppercase tracking-wide">1688 商品信息</div>
              <div className="space-y-2 text-sm">
                <div className="flex gap-3">
                  <div className="w-12 h-12 rounded-lg bg-white/10 flex items-center justify-center text-slate-400 text-xs">图片</div>
                  <div>
                    <p className="font-medium text-slate-100">无线蓝牙耳机 5.3 降噪 高音质</p>
                    <p className="text-slate-500">价格：¥36.50 | 已售 12,000+</p>
                    <p className="text-slate-500 text-xs mt-1">店铺：深圳市华强北科技有限公司</p>
                  </div>
                </div>
              </div>
            </motion.div>
            <motion.div initial={false}
              className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 shadow-sm">
              <div className="flex items-center justify-between mb-3">
                <div className="text-xs font-medium text-amber-400 uppercase tracking-wide">AI 生成的 Amazon Listing</div>
                <span className="text-xs text-emerald-400 bg-emerald-500/20 px-2 py-0.5 rounded-full">已翻译 英文</span>
              </div>
              <div className="space-y-2 text-sm">
                <p className="font-medium text-slate-100">Wireless Bluetooth 5.3 Headphones, Over-Ear Noise Cancelling, Hi-Fi Sound Quality, 40H Battery Life, Comfort Fit for Work Travel</p>
                <ul className="text-slate-400 text-xs space-y-1 mt-2">
                  <li>• Bluetooth 5.3 technology for stable, lag-free connection</li>
                  <li>• Active noise cancellation blocks up to 35dB ambient noise</li>
                  <li>• Hi-Fi stereo sound with deep bass and clear treble</li>
                  <li>• 40-hour battery life for all-day use</li>
                  <li>• Lightweight ergonomic design for comfortable wear</li>
                </ul>
              </div>
            </motion.div>
          </div>
          <p className="text-xs text-slate-500 text-center mt-3">左侧为 1688 原始商品数据，右侧为 AI 自动生成的 Amazon Listing</p>
        </section>

        {/* ── 定价 ────────────────────────────────────────── */}
        <section className="max-w-3xl mx-auto px-4 py-16">
          <h2 className="text-lg font-semibold text-center text-slate-100 mb-1">简单透明的定价</h2>
          <p className="text-sm text-slate-500 text-center mb-8">
            免费开始，按需升级；积分按实际功能扣减，视频生成最低 10 积分
          </p>
          <div className="grid md:grid-cols-3 gap-4">
            <motion.div initial={false}
              className="rounded-xl border border-white/10 bg-white/5 p-6">
              <h3 className="font-semibold text-slate-100">免费版</h3>
              <p className="text-2xl font-bold text-slate-100 mt-2">¥0<span className="text-sm font-normal text-slate-500">/月</span></p>
              <ul className="mt-4 space-y-2 text-sm text-slate-400">
                <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />每月 30 AI 积分</li>
                <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />AI 品类分析</li>
                <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />利润计算器</li>
                <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />合规审查</li>
              </ul>
              <Button size="sm" onClick={() => navigate(isLoggedIn ? '/app/dashboard' : '/register')} className="w-full mt-6">{isLoggedIn ? '进入应用' : '免费开始'}</Button>
            </motion.div>
            <motion.div initial={false}
              className="rounded-xl border-2 border-amber-500/30 bg-amber-500/10 p-6 relative">
              <div className="absolute -top-2.5 right-4 bg-amber-500 text-white text-xs px-3 py-0.5 rounded-full">推荐</div>
              <h3 className="font-semibold text-slate-100">Standard</h3>
              <p className="text-2xl font-bold text-slate-100 mt-2">¥99<span className="text-sm font-normal text-slate-500">/月</span></p>
              <ul className="mt-4 space-y-2 text-sm text-slate-400">
                <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />每月 99,999 AI 积分</li>
                <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />AI 智能助手（Agent）</li>
                <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />Shopify 一键发布</li>
                <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />批量 AI 处理</li>
              </ul>
              <Button size="sm" onClick={() => navigate(isLoggedIn ? '/app/dashboard' : '/register')} className="w-full mt-6">{isLoggedIn ? '进入应用' : '选择 Standard'}</Button>
            </motion.div>
            <motion.div initial={false}
              className="rounded-xl border border-white/10 bg-white/5 p-6">
              <h3 className="font-semibold text-slate-100">Professional</h3>
              <p className="text-2xl font-bold text-slate-100 mt-2">¥249<span className="text-sm font-normal text-slate-500">/月</span></p>
              <ul className="mt-4 space-y-2 text-sm text-slate-400">
                <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />所有 Standard 功能</li>
                <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />每月 99,999 AI 积分</li>
                <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />AI 商品主图生成</li>
                <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />AI 商品视频生成</li>
                <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />优先技术支持</li>
              </ul>
              <Button size="sm" onClick={() => navigate(isLoggedIn ? '/app/dashboard' : '/register')} className="w-full mt-6">{isLoggedIn ? '进入应用' : '选择 Professional'}</Button>
            </motion.div>
          </div>
        </section>

        {/* ── 数据指标 ────────────────────────────────────── */}
        <section className="max-w-3xl mx-auto px-4 py-12">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { value: '9', label: 'AI 业务工具', tone: 'text-slate-100' },
              { value: '6', label: '自动化工作流', tone: 'text-amber-400' },
              { value: '4', label: '端到端闭环', tone: 'text-emerald-400' },
              { value: '8', label: '支持平台', tone: 'text-amber-400' },
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
