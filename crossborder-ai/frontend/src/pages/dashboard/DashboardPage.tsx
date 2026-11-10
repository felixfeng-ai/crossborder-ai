import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  TrendingUp,
  ShoppingCart,
  Bot,
  Loader2,
  CheckCircle2,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  XCircle,
  Clock,
  AlertTriangle,
  MessageSquareText,
  Sparkles,
  ShieldCheck,
  RefreshCw,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { toErrorMessage } from '@/utils/errorMessage'
import apiClient from '@/api/client'
import OnboardingGuide from '@/components/dashboard/OnboardingGuide'
import ImageHistoryGallery from '@/components/dashboard/ImageHistoryGallery'

/** 看板数据类型 */
interface DashboardData {
  products: {
    total: number
    this_month: number
    pending: number
  }
  recent: Array<{
    id: string
    title: string
    price: number | null
    status: string
    created_at: string
  }>
  credits: {
    remaining: number
    used: number
  }
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [input, setInput] = useState('')
  const [showAgentResult, setShowAgentResult] = useState(false)

  // 看板数据
  const { data: dashboard, isLoading } = useQuery<DashboardData>({
    queryKey: ['dashboard'],
    queryFn: async () => {
      const res = await apiClient.get('/analytics/dashboard')
      return res.data
    },
  })

  // ── 品类分析状态 ─────────────────────────────────────
  const [categoryInput, setCategoryInput] = useState('')
  const [report, setReport] = useState<string | null>(null)
  const [analyzing, setAnalyzing] = useState(false)

  // 品类分析
  const handleAnalyze = async () => {
    if (!categoryInput.trim()) return
    setAnalyzing(true)
    setReport(null)
    try {
      const res = await apiClient.get('/analytics/category', { params: { keyword: categoryInput.trim() } })
      setReport(res.data.report)
    } catch (err: any) {
      setReport(`分析失败：${toErrorMessage(err)}`)
    }
    setAnalyzing(false)
  }

  // ── Agent 执行 ──────────────────────────────────────────
  const agentMutation = useMutation({
    mutationFn: async (instruction: string) => {
      const res = await apiClient.post('/agent/run', { instruction })
      return res.data
    },
    onSuccess: () => setShowAgentResult(true),
  })

  const handleSubmit = () => {
    if (!input.trim()) return
    setShowAgentResult(false)
    agentMutation.mutate(input.trim())
  }

  const timeAgo = (dateStr: string) => {
    const diff = Date.now() - new Date(dateStr).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 60) return `${mins} 分钟前`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours} 小时前`
    return `${Math.floor(hours / 24)} 天前`
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const latestProduct = dashboard?.recent?.[0]
  const facts = [
    { label: '商品总数', value: dashboard?.products?.total ?? 0 },
    { label: '待处理', value: dashboard?.products?.pending ?? 0 },
    { label: '剩余积分', value: dashboard?.credits?.remaining ?? 0 },
    { label: '本月新增', value: dashboard?.products?.this_month ?? 0 },
  ]
  const workflow = [
    { label: '来源商品', detail: latestProduct ? '已录入' : '待录入' },
    { label: 'AI Listing', detail: latestProduct?.status === '待补充' ? '待补充' : '待生成' },
    { label: '图片素材', detail: '待生成' },
    { label: 'SKU / 库存', detail: '待配置' },
    { label: '渠道发布', detail: '待发布' },
  ]
  const commands = [
    { icon: ShoppingCart, label: '录入商品', detail: '抓取链接或手动创建', path: '/app/products' },
    { icon: MessageSquareText, label: '生成 Listing', detail: '按平台生成并合规审查', path: '/app/content' },
    { icon: Sparkles, label: 'AI 图片', detail: '主图、白底图与场景图', path: '/app/images' },
    { icon: Bot, label: 'AI 助手', detail: '直接下达经营任务', path: '/app/agent' },
  ]

  return (
    <div
      className="mx-auto max-w-[1280px] space-y-8"
      data-dashboard-protagonist="product-pipeline"
    >
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="micro-label">经营总览</p>
          <h1 className="page-title mt-1">经营决策</h1>
          <p className="mt-1 max-w-[62ch] text-sm text-muted-foreground">
            从来源商品到多平台发布，围绕当前对象完成内容、素材、库存与渠道判断。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => navigate('/app/agent')}>
            <Bot className="mr-2 h-4 w-4" />
            AI 助手
          </Button>
          <Button
            onClick={() => navigate(latestProduct ? `/app/products/${latestProduct.id}` : '/app/products')}
          >
            {latestProduct ? '继续处理' : '录入第一个商品'}
          </Button>
        </div>
      </header>

      <section className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(300px,0.75fr)]">
        <div className="space-y-4">
          <Card className="overflow-hidden">
          <CardHeader className="flex-row items-start justify-between space-y-0 border-b border-border">
            <div>
              <CardTitle className="section-title">当前商品链路</CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                {latestProduct ? '最近录入的商品与下一步动作' : '还没有商品，从一条来源链接开始'}
              </p>
            </div>
            <Badge variant={latestProduct ? 'secondary' : 'outline'}>
              {latestProduct ? '进行中' : '未开始'}
            </Badge>
          </CardHeader>
          <CardContent className="p-0">
            {latestProduct ? (
              <>
                <div className="flex flex-col gap-3 border-b border-border px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <p className="truncate text-[15px] font-medium">{latestProduct.title || '无标题商品'}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      更新于 {timeAgo(latestProduct.created_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-4">
                    {latestProduct.price != null && (
                      <span className="metric-number text-lg font-medium">
                        ¥{latestProduct.price.toFixed(2)}
                      </span>
                    )}
                    <Button variant="outline" size="sm" onClick={() => navigate(`/app/products/${latestProduct.id}`)}>
                      打开商品
                    </Button>
                  </div>
                </div>

                <div className="grid gap-px bg-border sm:grid-cols-5">
                  {workflow.map((step, index) => (
                    <div key={step.label} className="min-w-0 bg-card px-4 py-4">
                      <span className="metric-number text-[11px] text-muted-foreground">
                        {String(index + 1).padStart(2, '0')}
                      </span>
                      <p className="mt-2 text-[13px] font-medium">{step.label}</p>
                      <p className="mt-1 text-xs text-muted-foreground">{step.detail}</p>
                    </div>
                  ))}
                </div>

                <div className="flex flex-col gap-3 border-t border-border px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-xs text-muted-foreground">
                    接下来从商品详情检查内容、图片和 SKU，再选择发布渠道。
                  </p>
                  <Button size="sm" onClick={() => navigate(`/app/products/${latestProduct.id}`)}>
                    继续处理
                  </Button>
                </div>
              </>
            ) : (
              <div className="flex min-h-64 flex-col items-center justify-center px-6 py-12 text-center">
                <ShoppingCart className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
                <p className="mt-3 text-sm font-medium">还没有商品链路</p>
                <p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">
                  粘贴 1688 商品链接，系统会先抓取商品，再进入 Listing、图片和库存流程。
                </p>
                <Button className="mt-4" onClick={() => navigate('/app/products')}>
                  录入第一个商品
                </Button>
              </div>
            )}
          </CardContent>
          </Card>

          <OnboardingGuide />
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader className="border-b border-border pb-4">
              <CardTitle className="text-sm font-medium text-muted-foreground">经营事实</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="grid grid-cols-2">
                {facts.map((fact, index) => (
                  <div
                    key={fact.label}
                    className={`px-5 py-4 ${index > 1 ? 'border-t border-border' : ''}`}
                  >
                    <p className="metric-number text-[24px] font-medium leading-none">{fact.value}</p>
                    <p className="mt-2 text-xs text-muted-foreground">{fact.label}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">直接开始</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 p-2 pt-0">
              {commands.map((command) => (
                <button
                  key={command.label}
                  type="button"
                  onClick={() => navigate(command.path)}
                  className="flex w-full items-center gap-3 rounded px-3 py-2 text-left hover:bg-accent"
                >
                  <command.icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-medium">{command.label}</span>
                    <span className="block truncate text-[11px] text-muted-foreground">
                      {command.detail}
                    </span>
                  </span>
                  <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
                </button>
              ))}
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <TrendingUp className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
              AI 品类分析
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              输入品类名，分析市场容量、竞争格局和利润空间。
            </p>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                id="category-input"
                value={categoryInput}
                onChange={(e) => setCategoryInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAnalyze()}
                placeholder="例如：蓝牙耳机、瑜伽裤、智能手表…"
                className="h-10 flex-1"
              />
              <Button size="sm" className="shrink-0 sm:h-10" onClick={handleAnalyze} disabled={analyzing}>
                {analyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : <TrendingUp className="mr-2 h-4 w-4" />}
                AI 分析
              </Button>
            </div>

            {analyzing && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                AI 正在分析市场数据…
              </div>
            )}
            {report && (
              <div className="max-h-80 overflow-y-auto rounded border border-border bg-[var(--factory-ground)] p-3 text-xs leading-relaxed">
                {report.slice(0, 2500).split('\n').map((line, i) => {
                  if (!line.trim()) return <p key={i} className="my-1" />
                  if (line.startsWith('# ')) return <p key={i} className="mt-3 text-sm font-semibold text-foreground">{line.replace('# ', '')}</p>
                  if (line.startsWith('## ')) return <p key={i} className="mt-2 text-sm font-medium text-foreground">{line.replace('## ', '')}</p>
                  if (line.startsWith('|')) return <p key={i} className="font-mono text-[11px] text-muted-foreground">{line}</p>
                  if (line.match(/^\d+\./)) return <p key={i} className="ml-2 text-[11px] text-muted-foreground">{line}</p>
                  if (line.startsWith('-')) return <p key={i} className="ml-2 text-[11px] text-muted-foreground">{line}</p>
                  if (line.includes('**')) return <p key={i} className="text-[11px] text-foreground"><strong>{line.replace(/\*\*/g, '')}</strong></p>
                  return <p key={i} className="text-[11px] text-muted-foreground">{line}</p>
                })}
                {report.length > 2500 && <p className="mt-2 text-[11px] text-muted-foreground">报告较长，已截取前 2500 字</p>}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <Bot className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
              AI 指令
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              粘贴商品链接，或直接描述要完成的经营任务。
            </p>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2">
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
                placeholder="例如：帮我算利润、检查合规、抓取商品…"
                className="h-10 flex-1"
              />
              <Button onClick={handleSubmit} disabled={!input.trim() || agentMutation.isPending} className="h-10 px-4">
                {agentMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Bot className="h-4 w-4" />}
              </Button>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {['帮我算利润', '检查合规', '抓取商品'].map((hint) => (
                <button
                  key={hint}
                  type="button"
                  className="rounded border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
                  onClick={() => { setInput(hint); handleSubmit() }}
                >
                  {hint}
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
      </section>

      {agentMutation.data && showAgentResult && (
        <AgentResult data={agentMutation.data} onClose={() => setShowAgentResult(false)} />
      )}

      <section className="grid gap-4 xl:grid-cols-2">
        <StoreCheckSection timeAgo={timeAgo} />
        <ImageHistoryGallery />
      </section>

      {/* ── 最近操作 ──────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" />
            最近操作
          </CardTitle>
        </CardHeader>
        <CardContent>
          {dashboard?.recent && dashboard.recent.length > 0 ? (
            <div className="space-y-2">
              {dashboard.recent.map((p) => (
                <div
                  key={p.id}
                  className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-muted/50 cursor-pointer text-sm"
                  onClick={() => navigate(`/app/products/${p.id}`)}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    {p.status === '待补充' ? (
                      <AlertCircle className="h-4 w-4 text-amber-500 shrink-0" />
                    ) : (
                      <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                    )}
                    <span className="truncate">{p.title}</span>
                    {p.price != null && <span className="text-muted-foreground shrink-0">¥{p.price}</span>}
                  </div>
                  <span className="text-xs text-muted-foreground shrink-0 ml-2">{timeAgo(p.created_at)}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-6 text-sm text-muted-foreground">
              还没有商品，点击上方「录入商品」开始
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * StoreCheckSection - 整店巡检（5.0 定时 Agent）
 *
 * 展示每日自动巡检 + 手动巡检的结果：
 * 最近一次巡检的健康状态、问题商品列表、历史记录。
 */
interface StoreCheckIssue {
  id: string
  title: string
  issues: string[]
}
interface StoreCheckLogItem {
  id: string
  total: number
  healthy: number
  issue_count: number
  issues: StoreCheckIssue[]
  created_at: string
}

function StoreCheckSection({ timeAgo }: { timeAgo: (d: string) => string }) {
  const queryClient = useQueryClient()
  const [runError, setRunError] = useState('')

  // 巡检历史
  const { data, isLoading } = useQuery<{ items: StoreCheckLogItem[] }>({
    queryKey: ['store-check-history'],
    queryFn: async () => {
      const res = await apiClient.get('/analytics/store-check-history')
      return res.data
    },
  })

  // 立即巡检（手动触发，扣 1 积分，写一条巡检记录）
  const mutation = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post('/analytics/store-check')
      return res.data
    },
    onSuccess: () => {
      setRunError('')
      queryClient.invalidateQueries({ queryKey: ['store-check-history'] })
    },
    onError: (err: any) => {
      setRunError(toErrorMessage(err, '巡检失败，请稍后重试'))
    },
  })

  const items = data?.items ?? []
  const latest = items[0]

  return (
    <Card className="border-emerald-500/20">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-emerald-500" />
            整店巡检
          </CardTitle>
          <Button
            size="sm"
            variant="outline"
            className="h-8 gap-1.5 text-xs"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || isLoading}
          >
            {mutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
            立即巡检
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          每天凌晨自动检查商品健康状态，也可手动触发
        </p>
      </CardHeader>
      <CardContent>
        {runError && (
          <div className="mb-3 flex items-center gap-2 text-xs text-destructive">
            <AlertCircle className="h-4 w-4 shrink-0" />
            {runError}
          </div>
        )}

        {isLoading ? (
          <div className="flex items-center justify-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : items.length === 0 ? (
          <div className="text-center py-6 text-sm text-muted-foreground">
            <ShieldCheck className="h-6 w-6 mx-auto mb-2 text-muted-foreground/50" />
            还没有巡检记录
            <p className="text-xs mt-1">点击「立即巡检」，马上检查商品健康状态</p>
          </div>
        ) : (
          <div className="space-y-3">
            {/* 最近一次巡检 */}
            <div className="rounded-lg border bg-muted/30 p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-muted-foreground">
                  最近巡检 · {timeAgo(latest.created_at)}
                </span>
                {latest.issue_count > 0 ? (
                  <Badge variant="warning">需处理 {latest.issue_count}</Badge>
                ) : (
                  <Badge variant="success">全部正常</Badge>
                )}
              </div>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div>
                  <p className="text-lg font-bold">{latest.total}</p>
                  <p className="text-[11px] text-muted-foreground">商品总数</p>
                </div>
                <div>
                  <p className="text-lg font-bold text-emerald-600">{latest.healthy}</p>
                  <p className="text-[11px] text-muted-foreground">正常</p>
                </div>
                <div>
                  <p className="text-lg font-bold text-amber-600">{latest.issue_count}</p>
                  <p className="text-[11px] text-muted-foreground">需处理</p>
                </div>
              </div>

              {/* 问题商品列表 */}
              {latest.issue_count > 0 && (
                <div className="mt-2 space-y-1.5">
                  {latest.issues.map((issue) => (
                    <div
                      key={issue.id}
                      className="flex items-start justify-between gap-2 text-xs rounded-md bg-background px-2 py-1.5"
                    >
                      <div className="flex items-center gap-1.5 min-w-0">
                        <AlertCircle className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                        <span className="truncate">{issue.title}</span>
                      </div>
                      <span className="text-muted-foreground shrink-0">
                        {issue.issues.join('、')}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* 历史记录 */}
            {items.length > 1 && (
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1.5">历史记录</p>
                <div className="space-y-1">
                  {items.slice(1, 6).map((log) => (
                    <div
                      key={log.id}
                      className="flex items-center justify-between text-xs px-2 py-1.5 rounded-md hover:bg-muted/50"
                    >
                      <div className="flex items-center gap-2">
                        {log.issue_count > 0 ? (
                          <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
                        ) : (
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                        )}
                        <span className="text-muted-foreground">{timeAgo(log.created_at)}</span>
                      </div>
                      <span className="text-muted-foreground">
                        {log.total} 个 · 正常 {log.healthy} · 需处理 {log.issue_count}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/**
 * AgentResult - AI 智能助手执行结果
 */
function AgentResult({ data, onClose }: { data: any; onClose: () => void }) {
  const [expanded, setExpanded] = useState(false)

  const statusIcon = (s: string) => {
    if (s === 'success') return <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
    if (s === 'failed') return <XCircle className="h-4 w-4 text-destructive shrink-0" />
    return <Loader2 className="h-4 w-4 animate-spin shrink-0" />
  }

  const actionLabel = (a: string) => {
    const labels: Record<string, string> = {
      scrape_1688: '抓取 1688 商品',
      create_product: '创建商品',
      generate_listing: 'AI 生成 Listing',
      compliance_check: '合规审查',
      calculate_profit: '净利计算',
      answer: '回答',
    }
    return labels[a] || a
  }

  return (
    <Card className={`${data.status === 'success' ? 'border-emerald-500/30' : 'border-destructive/30'}`}>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-2">
            {data.status === 'success' ? (
              <CheckCircle2 className="h-5 w-5 text-emerald-500 mt-0.5" />
            ) : (
              <XCircle className="h-5 w-5 text-destructive mt-0.5" />
            )}
            <div>
              <p className="text-sm font-medium">AI 执行结果</p>
              <p className="text-sm text-muted-foreground mt-0.5">{data.summary}</p>
            </div>
          </div>
          <div className="flex gap-1">
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setExpanded(!expanded)}>
              {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            </Button>
            <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground" onClick={onClose}>
              <XCircle className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </CardHeader>
      {expanded && data.steps && (
        <CardContent className="space-y-1.5 pt-0">
          {data.steps.map((step: any, i: number) => (
            <div key={i} className="flex items-start gap-2 text-sm">
              {statusIcon(step.status)}
              <div>
                <span className="text-xs font-medium">{actionLabel(step.action)}</span>
                {step.summary && <p className="text-xs text-muted-foreground">{step.summary}</p>}
                {step.error && <p className="text-xs text-destructive">{step.error}</p>}
              </div>
            </div>
          ))}
        </CardContent>
      )}
    </Card>
  )
}
