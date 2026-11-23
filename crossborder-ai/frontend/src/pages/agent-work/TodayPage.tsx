import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  Bot,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { CrossSurfaceComposer } from '@/components/agent-work/CrossSurfaceComposer'
import { useWorkspaceContextStore } from '@/features/workspace-context/workspace-context-store'
import {
  useDailyPlanQuery,
  useTimelineQuery,
} from '@/features/agent-work/queries'
import {
  workItemNeedsAttention,
  workItemStatusMeta,
} from '@/features/agent-work/work-item'
import type { DailyPlanItem, TimelineItem } from '@/features/agent-work/types'

const PLAN_CATEGORY_LABELS: Record<string, string> = {
  decision: '待决定',
  auto: '自动执行',
  monitor: '需关注',
  carryover: '结转',
}

function categoryTone(category: string) {
  if (category === 'decision') return 'warning' as const
  if (category === 'monitor') return 'destructive' as const
  if (category === 'auto') return 'success' as const
  return 'secondary' as const
}

function greetingForHour(hour: number): string {
  if (hour < 6) return '夜深了'
  if (hour < 12) return '早上好'
  if (hour < 18) return '下午好'
  return '晚上好'
}

function formatToday(): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  }).format(new Date())
}

function PlanRow({
  item,
  onOpen,
}: {
  item: DailyPlanItem
  onOpen: () => void
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group grid w-full gap-3 border-b border-border py-4 text-left transition-colors last:border-b-0 hover:bg-accent/45 sm:grid-cols-[92px_minmax(0,1fr)_auto] sm:items-start"
    >
      <Badge
        variant={categoryTone(item.category)}
        className="w-fit text-[11px]"
      >
        {PLAN_CATEGORY_LABELS[item.category] ?? item.category}
      </Badge>
      <span className="min-w-0">
        <span className="block text-sm font-medium text-foreground">
          {item.title}
        </span>
        <span className="mt-1 block text-xs leading-5 text-muted-foreground">
          {item.reason}
        </span>
        {item.expected_action && (
          <span className="mt-1.5 block text-[11px] text-[var(--factory-accent)]">
            {item.expected_action}
          </span>
        )}
      </span>
      <span className="flex items-center gap-2 text-[11px] text-muted-foreground">
        {item.status}
        <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
      </span>
    </button>
  )
}

function TimelineRow({
  item,
  onOpen,
}: {
  item: TimelineItem
  onOpen: () => void
}) {
  const status = workItemStatusMeta(item.status)
  const needsAttention = workItemNeedsAttention(item)

  return (
    <button
      type="button"
      onClick={onOpen}
      className="grid w-full gap-3 border-b border-border py-4 text-left last:border-b-0 hover:bg-accent/45 sm:grid-cols-[28px_minmax(0,1fr)_auto]"
    >
      <span className="mt-0.5 flex h-6 w-6 items-center justify-center border border-border bg-background">
        {status.tone === 'success' ? (
          <CheckCircle2 className="h-3.5 w-3.5 text-[var(--factory-success)]" />
        ) : needsAttention ? (
          <AlertCircle className="h-3.5 w-3.5 text-[var(--factory-coral)]" />
        ) : (
          <Clock3 className="h-3.5 w-3.5 text-muted-foreground" />
        )}
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-medium">{item.title}</span>
        <span className="mt-1 block text-xs leading-5 text-muted-foreground">
          {item.summary}
        </span>
      </span>
      <Badge
        variant={
          status.tone === 'success'
            ? 'success'
            : status.tone === 'danger'
              ? 'destructive'
              : status.tone === 'warning'
                ? 'warning'
                : 'outline'
        }
        className="h-fit w-fit text-[11px]"
      >
        {status.label}
      </Badge>
    </button>
  )
}

function SyncNotice({
  onRetry,
  retrying,
}: {
  onRetry: () => void
  retrying: boolean
}) {
  return (
    <div
      role="status"
      className="flex flex-col gap-3 border border-[color:rgba(217,139,112,0.32)] bg-[color:rgba(217,139,112,0.08)] px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
    >
      <p className="flex items-start gap-2 text-xs leading-5 text-[var(--factory-coral)]">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        部分今日数据暂时未同步，页面会保留最近一次成功结果。
      </p>
      <Button
        size="sm"
        variant="ghost"
        className="w-fit text-[var(--factory-coral)]"
        onClick={onRetry}
      >
        <RefreshCw
          className={`mr-2 h-3.5 w-3.5 ${retrying ? 'animate-spin' : ''}`}
        />
        重试同步
      </Button>
    </div>
  )
}

function UnavailableBlock({
  title,
  onRetry,
}: {
  title: string
  onRetry: () => void
}) {
  return (
    <div className="px-5 py-8">
      <p className="text-sm font-medium">{title}</p>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">
        当前没有把它显示成空数据，已有任务不会因这次同步失败被删除。
      </p>
      <Button
        size="sm"
        variant="outline"
        className="mt-4"
        onClick={onRetry}
      >
        <RefreshCw className="mr-2 h-3.5 w-3.5" />
        重新加载
      </Button>
    </div>
  )
}

export default function TodayPage() {
  const navigate = useNavigate()
  const workspaceId = useWorkspaceContextStore(
    (state) => state.activeWorkspaceId,
  )
  const workspaceDisplayName = useWorkspaceContextStore(
    (state) => state.displayName,
  )
  const activeWorkspace = useWorkspaceContextStore((state) =>
    state.workspaces.find((workspace) => workspace.id === state.activeWorkspaceId),
  )
  const plan = useDailyPlanQuery(workspaceId)
  const timeline = useTimelineQuery(workspaceId)
  const planItems = plan.data?.items ?? []
  const timelineItems = timeline.data?.items ?? []
  const planUnavailable = Boolean(plan.error && !plan.data)
  const timelineUnavailable = Boolean(timeline.error && !timeline.data)
  const hasSyncError = Boolean(plan.error || timeline.error)
  const planPending = Boolean(!plan.data && plan.isLoading)
  const timelinePending = Boolean(!timeline.data && timeline.isLoading)
  const loading = planPending || timelinePending
  const retrying = plan.isFetching || timeline.isFetching
  const allEmpty =
    !loading &&
    !planUnavailable &&
    !timelineUnavailable &&
    planItems.length === 0 &&
    timelineItems.length === 0

  const metrics = [
    ['待你决定', plan.data?.decision_count],
    ['Agent 执行', plan.data?.auto_count],
    ['需要关注', plan.data?.monitor_count],
    ['昨日结转', plan.data?.carryover_count],
  ] as const
  const metricTotal = metrics.reduce(
    (sum, [, value]) => sum + Number(value ?? 0),
    0,
  )
  const leadPlan = planItems[0]
  const leadTimeline = timelineItems[0]
  const greeting = greetingForHour(new Date().getHours())
  const refresh = () => {
    void Promise.allSettled([plan.refetch(), timeline.refetch()])
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6" data-agent-today="true">
      <header className="flex flex-col justify-between gap-4 border-b border-border pb-6 sm:flex-row sm:items-end">
        <div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <CalendarDays className="h-4 w-4 text-[var(--factory-accent)]" />
              {formatToday()}
            </span>
            <span>{activeWorkspace?.name ?? '当前工作区'}</span>
          </div>
          <h1 className="page-title mt-3">
            {greeting}，{workspaceDisplayName || '老板'}
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            {plan.data?.overview ||
              (planUnavailable
                ? '今日计划暂时未同步，最近工作流仍会继续显示。'
                : '小 Veya 会先处理明确工作，需要你判断的事情会留在这里。')}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="icon"
            variant="ghost"
            aria-label="刷新今日工作"
            title="刷新今日工作"
            onClick={refresh}
          >
            <RefreshCw
              className={`h-4 w-4 ${retrying ? 'animate-spin' : ''}`}
            />
          </Button>
          <Button
            variant="outline"
            onClick={() => navigate('/app/agent')}
          >
            <Bot className="mr-2 h-4 w-4" />
            完整对话
          </Button>
        </div>
      </header>

      {hasSyncError && (
        <SyncNotice onRetry={refresh} retrying={retrying} />
      )}

      {metricTotal > 0 && (
            <section
              className="flex flex-wrap items-center gap-x-8 gap-y-3 border-y border-border py-3"
              aria-label="今日工作概览"
            >
              {metrics.map(([label, value]) => (
                <span
                  key={label}
                  className="inline-flex items-baseline gap-2 text-xs text-muted-foreground"
                >
                  <span className="metric-number text-lg font-semibold text-foreground">
                    {value ?? '—'}
                  </span>
                  {label}
                </span>
              ))}
            </section>
          )}

          {leadPlan ? (
            <button
              type="button"
              onClick={() => navigate(`/app/tasks/${leadPlan.work_item_id}`)}
              className="group grid w-full gap-5 border border-[color:rgba(216,181,109,0.32)] bg-[var(--factory-side)] p-5 text-left transition-colors hover:border-[var(--factory-accent)] sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end sm:p-6"
            >
              <span className="min-w-0">
                <span className="flex items-center gap-2 text-xs text-[var(--factory-accent)]">
                  <Sparkles className="h-4 w-4" />
                  今天最重要
                </span>
                <span className="mt-3 block text-2xl font-semibold leading-tight text-foreground sm:text-3xl">
                  {leadPlan.title}
                </span>
                <span className="mt-3 block max-w-3xl text-sm leading-6 text-muted-foreground">
                  {leadPlan.reason}
                </span>
              </span>
              <span className="flex items-center gap-3 text-sm font-medium text-foreground">
                处理这件事
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
              </span>
            </button>
          ) : leadTimeline && !timelineUnavailable ? (
            <button
              type="button"
              onClick={() => navigate(`/app/tasks/${leadTimeline.id}`)}
              className="group flex w-full items-center justify-between gap-4 border border-border bg-[var(--factory-panel)] px-5 py-4 text-left hover:border-[var(--factory-accent)]"
            >
              <span className="min-w-0">
                <span className="block text-sm font-medium">
                  {leadTimeline.title}
                </span>
                <span className="mt-1 block text-xs text-muted-foreground">
                  {leadTimeline.summary}
                </span>
              </span>
              <ArrowRight className="h-4 w-4 shrink-0 transition-transform group-hover:translate-x-1" />
            </button>
          ) : null}

          {workspaceId && <CrossSurfaceComposer workspaceId={workspaceId} />}

          {loading ? (
            <section className="border-y border-border py-10 text-center">
              <Loader2 className="mx-auto h-5 w-5 animate-spin text-[var(--factory-accent)]" />
              <p className="mt-3 text-sm font-medium">正在同步今天的工作</p>
              <p className="mt-1 text-xs text-muted-foreground">
                输入区已经可以使用，不需要等待列表加载完成。
              </p>
            </section>
          ) : allEmpty ? (
            <section className="border-y border-border py-12 text-center">
              <ShieldCheck className="mx-auto h-8 w-8 text-[var(--factory-success)]" />
              <p className="mt-3 text-sm font-medium">今天暂时没有待处理工作</p>
              <p className="mt-1 text-xs text-muted-foreground">
                可以直接交给小 Veya 一项任务，或稍后查看 Agent 的处理结果。
              </p>
            </section>
          ) : (
            <div className="grid gap-6 xl:grid-cols-[minmax(0,1.08fr)_minmax(360px,0.92fr)]">
              <section className="border border-border bg-[var(--factory-panel)]">
                <header className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
                  <div>
                    <h2 className="section-title">今天的计划</h2>
                    <p className="mt-1 text-xs text-muted-foreground">
                      需要你决定的工作排在自动执行和巡检之前。
                    </p>
                  </div>
                  <Badge variant="outline">{planItems.length} 项</Badge>
                </header>
                {planUnavailable ? (
                  <UnavailableBlock
                    title="今日计划暂时无法同步"
                    onRetry={() => void plan.refetch()}
                  />
                ) : (
                  <div className="px-5">
                    {planItems.length ? (
                      planItems.map((item) => (
                        <PlanRow
                          key={item.id}
                          item={item}
                          onOpen={() =>
                            navigate(`/app/tasks/${item.work_item_id}`)
                          }
                        />
                      ))
                    ) : (
                      <div className="py-10 text-center text-xs text-muted-foreground">
                        暂无需要你决定的计划
                      </div>
                    )}
                  </div>
                )}
              </section>

              <section className="border border-border bg-[var(--factory-panel)]">
                <header className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
                  <div>
                    <h2 className="section-title">最近工作流</h2>
                    <p className="mt-1 text-xs text-muted-foreground">
                      执行、失败和等待确认的状态会与 App 保持一致。
                    </p>
                  </div>
                  <Badge variant="outline">{timelineItems.length} 项</Badge>
                </header>
                {timelineUnavailable ? (
                  <UnavailableBlock
                    title="工作流暂时无法同步"
                    onRetry={() => void timeline.refetch()}
                  />
                ) : (
                  <div className="px-5">
                    {timelineItems.length ? (
                      timelineItems
                        .slice(0, 12)
                        .map((item) => (
                          <TimelineRow
                            key={item.id}
                            item={item}
                            onOpen={() => navigate(`/app/tasks/${item.id}`)}
                          />
                        ))
                    ) : (
                      <div className="py-10 text-center text-xs text-muted-foreground">
                        今天还没有工作记录
                      </div>
                    )}
                  </div>
                )}
              </section>
            </div>
          )}
    </div>
  )
}
