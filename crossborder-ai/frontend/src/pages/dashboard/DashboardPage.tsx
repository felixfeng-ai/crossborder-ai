import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import {
  TrendingUp,
  ShoppingCart,
  Bot,
  Loader2,
  CheckCircle2,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Clock,
  AlertTriangle,
  MessageSquareText,
  Sparkles,
  ShieldCheck,
  RefreshCw,
  ArrowUpRight,
  Image as ImageIcon,
  PackageSearch,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import Markdown from '@/components/common/Markdown'
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
  pipeline: {
    product: {
      id: string
      title: string
      price: number | null
      main_image_url: string | null
      created_at: string
      updated_at: string
    } | null
    stages: Array<{
      id: string
      label: string
      status: 'completed' | 'current' | 'blocked' | 'pending'
      detail: string
      href: string
    }>
    next_action: {
      stage: string
      label: string
      href: string
    }
    progress: { completed: number; total: number }
  }
  facts: Array<{
    id: 'content' | 'media' | 'sku' | 'operations'
    label: string
    value: number
    detail: string
    tone: 'neutral' | 'warning' | 'danger' | 'success'
    href: string
  }>
  recent_operations: Array<{
    id: string
    kind: string
    title: string
    detail: string
    href: string
    created_at: string
    tone: 'neutral' | 'ai' | 'success' | 'danger'
  }>
  credits: {
    remaining: number
  }
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()

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

  const pipeline = dashboard?.pipeline
  const pipelineProduct = pipeline?.product || null
  const nextAction = pipeline?.next_action || {
    stage: 'product',
    label: '录入第一个商品',
    href: '/app/products',
  }
  const facts = dashboard?.facts || []
  const recentOperations = dashboard?.recent_operations || []
  const commands = [
    { icon: ShoppingCart, label: '录入商品', detail: '抓取链接或手动创建', path: '/app/products' },
    { icon: MessageSquareText, label: '生成 Listing', detail: '按平台生成并合规审查', path: '/app/content' },
    { icon: ImageIcon, label: '商品图片', detail: '主图、白底图与场景图', path: '/app/images' },
    { icon: PackageSearch, label: 'SKU 与库存', detail: '变体、售价与补货风险', path: '/app/catalog' },
    { icon: Bot, label: 'AI 助手', detail: '直接下达经营任务', path: '/app/agent' },
  ]

  return (
    <div
      className="mx-auto max-w-[1280px] space-y-8"
      data-dashboard-protagonist="product-pipeline"
    >
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <h1 className="page-title">经营总览</h1>
          <p className="mt-1 max-w-[62ch] text-sm text-muted-foreground">
            {pipelineProduct
              ? `${pipelineProduct.title} 当前停在「${
                  pipeline?.stages.find((stage) => stage.id === nextAction.stage)?.label
                  || '后续环节'
                }」，先完成这一步再继续。`
              : '从来源商品开始，依次完成 Listing、素材、SKU 与渠道发布。'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => navigate('/app/agent')}>
            <Bot className="mr-2 h-4 w-4" />
            AI 助手
          </Button>
          <Button onClick={() => navigate(nextAction.href)}>
            {nextAction.label}
            <ChevronRight className="ml-1.5 h-4 w-4" />
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
                {pipelineProduct ? '最近更新的商品与下一步动作' : '还没有商品，从一条来源链接开始'}
              </p>
            </div>
            <Badge variant={pipelineProduct ? 'secondary' : 'outline'}>
              {pipelineProduct
                ? `${pipeline?.progress.completed || 0}/${pipeline?.progress.total || 5} 已完成`
                : '未开始'}
            </Badge>
          </CardHeader>
          <CardContent className="p-0">
            {pipelineProduct ? (
              <>
                <div className="flex flex-col gap-3 border-b border-border px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <p className="truncate text-[15px] font-medium">
                      {pipelineProduct.title || '无标题商品'}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      更新于 {timeAgo(pipelineProduct.updated_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-4">
                    {pipelineProduct.price != null && (
                      <div className="text-right">
                        <p className="text-[11px] text-muted-foreground">采购/供货参考价</p>
                        <span className="metric-number text-lg font-medium text-[var(--factory-ink)]">
                          ¥{pipelineProduct.price.toFixed(2)}
                        </span>
                      </div>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => navigate(`/app/products/${pipelineProduct.id}`)}
                    >
                      打开商品
                    </Button>
                  </div>
                </div>

                <div className="divide-y divide-border sm:hidden">
                  {pipeline?.stages.map((stage) => (
                    <Link
                      key={stage.id}
                      to={stage.href}
                      className="flex min-h-14 items-center gap-3 px-4 py-3"
                    >
                      <span className={`h-2 w-2 shrink-0 rounded-full ${stageDotClass(stage.status)}`} />
                      <span className="min-w-0 flex-1">
                        <span className="block text-[13px] font-medium">{stage.label}</span>
                        <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                          {stage.detail}
                        </span>
                      </span>
                      <span className={`shrink-0 text-[10px] font-medium ${stageTextClass(stage.status)}`}>
                        {stageStatusLabel(stage.status)}
                      </span>
                      <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/70" />
                    </Link>
                  ))}
                </div>

                <div className="hidden gap-px bg-border sm:grid sm:grid-cols-5">
                  {pipeline?.stages.map((stage) => {
                    const content = (
                      <>
                        <div className="flex items-center justify-between gap-2">
                          <span className={`h-2 w-2 rounded-full ${stageDotClass(stage.status)}`} />
                          <span className={`text-[10px] font-medium ${stageTextClass(stage.status)}`}>
                            {stageStatusLabel(stage.status)}
                          </span>
                        </div>
                        <p className="mt-3 text-[13px] font-medium">{stage.label}</p>
                        <p className="mt-1 min-h-8 text-xs leading-4 text-muted-foreground">
                          {stage.detail}
                        </p>
                        <ArrowUpRight className="mt-2 h-3.5 w-3.5 text-muted-foreground/70" />
                      </>
                    )
                    return stage.href ? (
                      <Link
                        key={stage.id}
                        to={stage.href}
                        className={`min-w-0 px-4 py-4 transition-colors hover:bg-[var(--factory-raised)] ${stageSurfaceClass(stage.status)}`}
                      >
                        {content}
                      </Link>
                    ) : (
                      <div key={stage.id} className="min-w-0 bg-card px-4 py-4">
                        {content}
                      </div>
                    )
                  })}
                </div>

                <div className="flex flex-col gap-3 border-t border-border px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <p className="text-sm font-medium text-[var(--factory-ink)]">
                      下一步：{nextAction.label}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      已完成 {pipeline?.progress.completed || 0}/{pipeline?.progress.total || 5} 个环节
                    </p>
                  </div>
                  <Button size="sm" onClick={() => navigate(nextAction.href)}>
                    {nextAction.label}
                    <ChevronRight className="ml-1.5 h-4 w-4" />
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
              <CardTitle className="text-sm font-medium">待办与风险</CardTitle>
              <p className="mt-1 text-xs text-muted-foreground">
                先处理会影响内容和上架的事项
              </p>
            </CardHeader>
            <CardContent className="p-0">
              {facts.map((fact, index) => (
                <Link
                  key={fact.id}
                  to={fact.href}
                  className={`flex items-center gap-3 px-4 py-3 transition-colors hover:bg-[var(--factory-raised)] ${
                    index ? 'border-t border-border' : ''
                  }`}
                >
                  <FactIcon fact={fact.id} tone={fact.tone} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-medium">{fact.label}</span>
                    <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                      {fact.detail}
                    </span>
                  </span>
                  <span className={`metric-number text-xl font-medium ${factValueClass(fact.tone)}`}>
                    {fact.value}
                  </span>
                  <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                </Link>
              ))}
              {!facts.length && (
                <p className="px-4 py-6 text-center text-xs text-muted-foreground">
                  暂无待办
                </p>
              )}
              <div className="flex items-center justify-between border-t border-border px-4 py-2.5 text-[11px] text-muted-foreground">
                <span>剩余 AI 积分</span>
                <span className="metric-number text-foreground">
                  {(dashboard?.credits.remaining ?? 0).toLocaleString()}
                </span>
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

      <section className="grid items-start gap-4 xl:grid-cols-2">
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
                <Markdown content={report.slice(0, 2500)} />
                {report.length > 2500 && <p className="mt-2 text-[11px] text-muted-foreground">报告较长，已截取前 2500 字</p>}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <Bot className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
              让 Agent 继续处理
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              进入完整对话工作台，执行、流式反馈和结果留痕都在同一处完成。
            </p>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button
              className="w-full justify-between"
              onClick={() => navigate('/app/agent')}
            >
              <span className="flex items-center gap-2">
                <Bot className="h-4 w-4" />
                打开 AI 助手
              </span>
              <ArrowUpRight className="h-4 w-4" />
            </Button>
            <div className="space-y-1">
              {[
                '生成当前商品 Listing',
                '规划营销成片分镜',
                '同步 Shopify 销量和库存',
              ].map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  className="flex min-h-10 w-full items-center justify-between gap-3 rounded-md px-3 text-left text-xs text-muted-foreground transition-colors hover:bg-[var(--factory-raised)] hover:text-foreground"
                  onClick={() =>
                    navigate(`/app/agent?prompt=${encodeURIComponent(prompt)}`)
                  }
                >
                  <span>{prompt}</span>
                  <ChevronRight className="h-3.5 w-3.5 shrink-0" />
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <StoreCheckSection timeAgo={timeAgo} />
        <ImageHistoryGallery />
      </section>

      {/* ── 最近操作 ──────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Clock className="h-4 w-4 text-muted-foreground" />
            最近业务动作
          </CardTitle>
        </CardHeader>
        <CardContent>
          {recentOperations.length > 0 ? (
            <div className="divide-y divide-border">
              {recentOperations.map((operation) => {
                const row = (
                  <>
                    <OperationIcon kind={operation.kind} tone={operation.tone} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{operation.title}</span>
                      <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                        {operation.detail}
                      </span>
                    </span>
                    <span className="shrink-0 text-[11px] text-muted-foreground">
                      {timeAgo(operation.created_at)}
                    </span>
                    <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  </>
                )
                const className = "flex min-h-12 items-center gap-3 px-2 py-2.5 transition-colors hover:bg-[var(--factory-raised)]"
                return operation.href.startsWith('http') ? (
                  <a
                    key={`${operation.kind}-${operation.id}`}
                    href={operation.href}
                    target="_blank"
                    rel="noreferrer"
                    className={className}
                  >
                    {row}
                  </a>
                ) : (
                  <Link
                    key={`${operation.kind}-${operation.id}`}
                    to={operation.href}
                    className={className}
                  >
                    {row}
                  </Link>
                )
              })}
            </div>
          ) : (
            <div className="text-center py-6 text-sm text-muted-foreground">
              还没有业务动作，从录入商品或生成 Listing 开始
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
interface StoreCheckIssueDetail {
  code: string
  label: string
  severity: 'info' | 'warning' | 'error' | 'critical'
  action_href: string
}
interface StoreCheckIssue {
  id: string
  title: string
  severity: 'info' | 'warning' | 'error' | 'critical'
  action_href: string
  issues: StoreCheckIssueDetail[]
}
interface StoreCheckLogItem {
  id: string
  total: number
  healthy: number
  issue_count: number
  issues: StoreCheckIssue[]
  checked_scopes?: string[]
  created_at: string
}

function StoreCheckSection({ timeAgo }: { timeAgo: (d: string) => string }) {
  const queryClient = useQueryClient()
  const [runError, setRunError] = useState('')
  const [expandedLogId, setExpandedLogId] = useState('')

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
  const toggleLog = (logId: string) => {
    setExpandedLogId((current) => (current === logId ? '' : logId))
  }

  return (
    <Card className="border-[color:var(--factory-line)]">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-[var(--factory-success)]" />
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
          检查商品资料、Listing、素材、SKU、发布与运营风险
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
            <div className="overflow-hidden rounded-md border bg-muted/30">
              <button
                type="button"
                className="w-full p-3 text-left transition-colors hover:bg-[var(--factory-raised)]"
                aria-expanded={expandedLogId === latest.id}
                aria-controls={`store-check-detail-${latest.id}`}
                onClick={() => toggleLog(latest.id)}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs font-medium text-muted-foreground">
                    最近巡检 · {timeAgo(latest.created_at)}
                  </span>
                  {latest.issue_count > 0 ? (
                    <Badge variant="warning">需处理 {latest.issue_count}</Badge>
                  ) : (
                    <Badge variant="success">全部通过</Badge>
                  )}
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                  <CheckMetric label="商品总数" value={latest.total} />
                  <CheckMetric
                    label="正常"
                    value={latest.healthy}
                    tone="success"
                  />
                  <CheckMetric
                    label="需处理"
                    value={latest.issue_count}
                    tone={latest.issue_count ? 'danger' : 'neutral'}
                  />
                </div>
                <div className="mt-3 flex items-center justify-between border-t border-border pt-2 text-[11px] text-muted-foreground">
                  <span>
                    {latest.issue_count
                      ? summarizeCheckIssues(latest)
                      : '检查范围内未发现问题'}
                  </span>
                  <span className="flex shrink-0 items-center gap-1">
                    巡检详情
                    <ChevronDown
                      className={`h-3.5 w-3.5 transition-transform ${
                        expandedLogId === latest.id ? 'rotate-180' : ''
                      }`}
                    />
                  </span>
                </div>
              </button>
              {expandedLogId === latest.id && (
                <div id={`store-check-detail-${latest.id}`}>
                  <StoreCheckDetail log={latest} />
                </div>
              )}
            </div>

            {/* 历史记录 */}
            {items.length > 1 && (
              <div>
                <p className="mb-1.5 text-xs font-medium text-muted-foreground">巡检历史</p>
                <div className="space-y-1">
                  {items.slice(1, 6).map((log) => (
                    <div key={log.id} className="overflow-hidden rounded-md border">
                      <button
                        type="button"
                        className="flex min-h-11 w-full items-center justify-between gap-3 px-2.5 py-2 text-left text-xs transition-colors hover:bg-[var(--factory-raised)]"
                        aria-expanded={expandedLogId === log.id}
                        aria-controls={`store-check-detail-${log.id}`}
                        onClick={() => toggleLog(log.id)}
                      >
                        <span className="flex min-w-0 items-center gap-2">
                          {log.issue_count > 0 ? (
                            <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-[var(--factory-warning)]" />
                          ) : (
                            <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-[var(--factory-success)]" />
                          )}
                          <span className="text-muted-foreground">{timeAgo(log.created_at)}</span>
                        </span>
                        <span className="flex shrink-0 items-center gap-2 text-muted-foreground">
                          <span>
                            {log.total} 个 · 正常 {log.healthy} · 需处理 {log.issue_count}
                          </span>
                          <ChevronDown
                            className={`h-3.5 w-3.5 transition-transform ${
                              expandedLogId === log.id ? 'rotate-180' : ''
                            }`}
                          />
                        </span>
                      </button>
                      {expandedLogId === log.id && (
                        <div id={`store-check-detail-${log.id}`}>
                          <StoreCheckDetail log={log} />
                        </div>
                      )}
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

function stageSurfaceClass(status: string): string {
  if (status === 'completed') return 'bg-[color:var(--factory-success)]/5'
  if (status === 'current') return 'bg-[color:var(--factory-accent)]/7'
  if (status === 'blocked') return 'bg-[color:var(--factory-danger)]/7'
  return 'bg-card'
}

function stageDotClass(status: string): string {
  if (status === 'completed') return 'bg-[var(--factory-success)]'
  if (status === 'current') return 'bg-[var(--factory-accent)]'
  if (status === 'blocked') return 'bg-[var(--factory-danger)]'
  return 'bg-[var(--factory-faint)]'
}

function stageTextClass(status: string): string {
  if (status === 'completed') return 'text-[var(--factory-success)]'
  if (status === 'current') return 'text-[var(--factory-accent)]'
  if (status === 'blocked') return 'text-[var(--factory-danger)]'
  return 'text-muted-foreground'
}

function stageStatusLabel(status: string): string {
  if (status === 'completed') return '已完成'
  if (status === 'current') return '进行中'
  if (status === 'blocked') return '需处理'
  return '未开始'
}

function factValueClass(tone: string): string {
  if (tone === 'danger') return 'text-[var(--factory-danger)]'
  if (tone === 'warning') return 'text-[var(--factory-warning)]'
  if (tone === 'success') return 'text-[var(--factory-success)]'
  return 'text-[var(--factory-ink)]'
}

function FactIcon({
  fact,
  tone,
}: {
  fact: 'content' | 'media' | 'sku' | 'operations'
  tone: string
}) {
  const Icon =
    fact === 'content'
      ? MessageSquareText
      : fact === 'media'
        ? ImageIcon
        : fact === 'sku'
          ? PackageSearch
          : AlertTriangle
  return <Icon className={`h-4 w-4 shrink-0 ${factValueClass(tone)}`} aria-hidden="true" />
}

function OperationIcon({ kind, tone }: { kind: string; tone: string }) {
  const Icon =
    kind === 'listing'
      ? MessageSquareText
      : kind === 'image'
        ? ImageIcon
        : kind === 'video' || kind === 'marketing'
          ? Sparkles
          : kind === 'publication'
            ? ShoppingCart
            : Clock
  return <Icon className={`h-4 w-4 shrink-0 ${factValueClass(tone)}`} aria-hidden="true" />
}

function severityLabel(severity: string): string {
  if (severity === 'critical') return '严重'
  if (severity === 'error') return '错误'
  if (severity === 'warning') return '需处理'
  return '提示'
}

function summarizeCheckIssues(log: StoreCheckLogItem): string {
  const labels = Array.from(
    new Set(
      log.issues
        .flatMap((item) => item.issues)
        .map((item) => item.label)
        .filter(Boolean),
    ),
  )
  return labels.slice(0, 3).join(' · ')
}

function CheckMetric({
  label,
  value,
  tone = 'default',
}: {
  label: string
  value: number
  tone?: 'default' | 'success' | 'danger' | 'neutral'
}) {
  const toneClass =
    tone === 'success'
      ? 'text-[var(--factory-success)]'
      : tone === 'danger'
        ? 'text-[var(--factory-danger)]'
        : tone === 'neutral'
          ? 'text-muted-foreground'
          : 'text-[var(--factory-ink)]'
  return (
    <div>
      <p className={`metric-number text-lg font-medium ${toneClass}`}>{value}</p>
      <p className="text-[11px] text-muted-foreground">{label}</p>
    </div>
  )
}

function StoreCheckDetail({ log }: { log: StoreCheckLogItem }) {
  const scopeLabels: Record<string, string> = {
    basic: '商品资料',
    listing: 'Listing',
    media: '素材',
    sku: 'SKU 与库存',
    publication: '渠道发布',
    operations: '运营预警',
  }
  return (
    <div className="space-y-3 border-t border-border bg-background p-3">
      <div className="flex flex-wrap gap-1.5">
        {(log.checked_scopes || []).map((scope) => (
          <Badge key={scope} variant="outline" className="text-[10px] font-normal">
            {scopeLabels[scope] || scope}
          </Badge>
        ))}
      </div>
      {log.issue_count === 0 ? (
        <div className="flex items-center gap-2 rounded-md bg-[color:var(--factory-success)]/8 px-3 py-2 text-xs text-[var(--factory-success)]">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          本次巡检覆盖范围内未发现问题
        </div>
      ) : (
        <div className="space-y-2">
          {log.issues.map((issue) => (
            <div key={issue.id} className="rounded-md border border-border p-2.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Link
                  to={issue.action_href}
                  className="truncate text-xs font-medium hover:text-[var(--factory-accent)]"
                >
                  {issue.title}
                </Link>
                <Badge
                  variant={issue.severity === 'critical' || issue.severity === 'error' ? 'destructive' : 'warning'}
                  className="text-[10px]"
                >
                  {severityLabel(issue.severity)}
                </Badge>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {issue.issues.map((item) => (
                  <Link
                    key={item.code}
                    to={item.action_href}
                    className="rounded border border-border px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:border-[color:var(--factory-line-strong)] hover:text-foreground"
                  >
                    {item.label}
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
