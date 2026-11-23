import {
  AlertCircle,
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

export default function TodayPage() {
  const navigate = useNavigate()
  const workspaceId = useWorkspaceContextStore(
    (state) => state.activeWorkspaceId,
  )
  const activeWorkspace = useWorkspaceContextStore((state) =>
    state.workspaces.find((workspace) => workspace.id === state.activeWorkspaceId),
  )
  const plan = useDailyPlanQuery(workspaceId)
  const timeline = useTimelineQuery(workspaceId)
  const isLoading = (plan.isLoading && !plan.data) || (timeline.isLoading && !timeline.data)
  const error = plan.error ?? timeline.error

  const refresh = () => {
    void plan.refetch()
    void timeline.refetch()
  }

  if (isLoading) {
    return (
      <div className="flex min-h-[420px] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-[var(--factory-accent)]" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="mx-auto max-w-2xl border border-border bg-[var(--factory-panel)] p-6">
        <AlertCircle className="h-5 w-5 text-[var(--factory-coral)]" />
        <h1 className="mt-3 text-lg font-semibold">今日工作暂时无法同步</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          当前不会把加载失败显示成“今天没有任务”。
        </p>
        <Button className="mt-4" variant="outline" onClick={refresh}>
          <RefreshCw className="mr-2 h-4 w-4" />
          重新加载
        </Button>
      </div>
    )
  }

  const planItems = plan.data?.items ?? []
  const timelineItems = timeline.data?.items ?? []
  const stats = [
    ['待你决定', plan.data?.decision_count ?? 0, CalendarDays],
    ['Agent 执行', plan.data?.auto_count ?? 0, Bot],
    ['需要关注', plan.data?.monitor_count ?? 0, AlertCircle],
    ['昨日结转', plan.data?.carryover_count ?? 0, Sparkles],
  ] as const

  return (
    <div className="mx-auto max-w-6xl space-y-8" data-agent-today="true">
      <header className="flex flex-col justify-between gap-4 border-b border-border pb-6 sm:flex-row sm:items-end">
        <div>
          <div className="flex items-center gap-2 text-xs font-medium text-[var(--factory-accent)]">
            <CalendarDays className="h-4 w-4" />
            {activeWorkspace?.name ?? '当前工作区'}
          </div>
          <h1 className="page-title mt-2">今日 Agent</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            {plan.data?.overview ||
              'Agent 会把需要决定、正在执行和需要关注的工作集中到今天。'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={refresh}>
            <RefreshCw className="mr-2 h-4 w-4" />
            刷新
          </Button>
          <Button onClick={() => navigate('/app/agent')}>
            <Bot className="mr-2 h-4 w-4" />
            打开 Agent
          </Button>
        </div>
      </header>

      <section className="grid grid-cols-2 border border-border bg-[var(--factory-panel)] lg:grid-cols-4">
        {stats.map(([label, value, Icon], index) => (
          <div
            key={label}
            className={`p-4 ${index === 1 || index === 3 ? 'border-l border-border' : ''} ${index >= 2 ? 'border-t border-border lg:border-t-0' : ''} ${index === 2 ? 'lg:border-l' : ''}`}
          >
            <div className="flex items-center justify-between gap-3">
              <span className="text-xs text-muted-foreground">{label}</span>
              <Icon className="h-4 w-4 text-[var(--factory-accent)]" />
            </div>
            <p className="metric-number mt-3 text-3xl font-semibold">{value}</p>
          </div>
        ))}
      </section>

      {workspaceId && <CrossSurfaceComposer workspaceId={workspaceId} />}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.08fr)_minmax(360px,0.92fr)]">
        <section className="border border-border bg-[var(--factory-panel)]">
          <header className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
            <div>
              <h2 className="section-title">今天的计划</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                需要决定的工作排在前面，其次才是自动执行和巡检。
              </p>
            </div>
            <Badge variant="outline">{planItems.length} 项</Badge>
          </header>
          <div className="px-5">
            {planItems.length ? (
              planItems.map((item) => (
                <PlanRow
                  key={item.id}
                  item={item}
                  onOpen={() => navigate(`/app/tasks/${item.work_item_id}`)}
                />
              ))
            ) : (
              <div className="py-14 text-center">
                <ShieldCheck className="mx-auto h-8 w-8 text-[var(--factory-success)]" />
                <p className="mt-3 text-sm font-medium">今天还没有待办计划</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Agent 发现需要你决定或持续关注的工作后会出现在这里。
                </p>
              </div>
            )}
          </div>
        </section>

        <section className="border border-border bg-[var(--factory-panel)]">
          <header className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
            <div>
              <h2 className="section-title">最近工作流</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                执行、失败和需要确认的状态与 App 保持一致。
              </p>
            </div>
            <Badge variant="outline">{timelineItems.length} 项</Badge>
          </header>
          <div className="px-5">
            {timelineItems.length ? (
              timelineItems.slice(0, 12).map((item) => (
                <TimelineRow
                  key={item.id}
                  item={item}
                  onOpen={() => navigate(`/app/tasks/${item.id}`)}
                />
              ))
            ) : (
              <div className="py-14 text-center">
                <Clock3 className="mx-auto h-8 w-8 text-muted-foreground" />
                <p className="mt-3 text-sm font-medium">今天还没有工作记录</p>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
