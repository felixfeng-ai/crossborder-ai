import { useRef, useState } from 'react'
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Clock3,
  Loader2,
  Play,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'

import ConfirmDialog from '@/components/common/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useWorkspaceContextStore } from '@/features/workspace-context/workspace-context-store'
import {
  createOperationIdempotencyKey,
  useConfirmWorkItemMutation,
  useWorkItemQuery,
} from '@/features/agent-work/queries'
import {
  primaryWorkItemAction,
  workItemStatusMeta,
} from '@/features/agent-work/work-item'
import type { AvailableAction } from '@/features/agent-work/types'

function statusVariant(tone: ReturnType<typeof workItemStatusMeta>['tone']) {
  if (tone === 'success') return 'success' as const
  if (tone === 'danger') return 'destructive' as const
  if (tone === 'warning') return 'warning' as const
  return 'outline' as const
}

export default function WorkItemPage() {
  const navigate = useNavigate()
  const { workItemId = '' } = useParams()
  const workspaceId = useWorkspaceContextStore(
    (state) => state.activeWorkspaceId,
  )
  const query = useWorkItemQuery(workspaceId, workItemId)
  const item = query.data
  const mutation = useConfirmWorkItemMutation(workspaceId, item)
  const idempotencyKey = useRef('')
  const [pendingAction, setPendingAction] = useState<AvailableAction | null>(
    null,
  )
  const [submitError, setSubmitError] = useState('')

  if (query.isLoading && !item) {
    return (
      <div className="flex min-h-[420px] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-[var(--factory-accent)]" />
      </div>
    )
  }

  if (query.isError || !item) {
    return (
      <div className="mx-auto max-w-2xl border border-border bg-[var(--factory-panel)] p-6">
        <AlertCircle className="h-5 w-5 text-[var(--factory-coral)]" />
        <h1 className="mt-3 text-lg font-semibold">任务暂时无法同步</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          当前不会显示猜测的任务状态，也不会允许提交操作。
        </p>
        <div className="mt-4 flex gap-2">
          <Button variant="outline" onClick={() => navigate('/app/today')}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            返回今日
          </Button>
          <Button onClick={() => void query.refetch()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            重试
          </Button>
        </div>
      </div>
    )
  }

  const status = workItemStatusMeta(item.status)
  const action = primaryWorkItemAction(item)
  const preview = item.action_preview
  const resultSummary =
    typeof item.result?.summary === 'string' ? item.result.summary : null

  const requestAction = (selected: AvailableAction) => {
    setSubmitError('')
    idempotencyKey.current = ''
    setPendingAction(selected)
  }

  const confirmAction = async () => {
    if (!pendingAction || mutation.isPending) return
    if (!idempotencyKey.current) {
      idempotencyKey.current = createOperationIdempotencyKey()
    }
    try {
      await mutation.mutateAsync({
        action: pendingAction.kind,
        actionId: pendingAction.id,
        idempotencyKey: idempotencyKey.current,
        payload: {},
      })
      idempotencyKey.current = ''
      setPendingAction(null)
    } catch (reason) {
      setPendingAction(null)
      setSubmitError(
        reason instanceof Error
          ? reason.message
          : '任务可能已被其他人处理，请刷新后重试',
      )
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6" data-agent-work-item="true">
      <header className="border-b border-border pb-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button
            variant="ghost"
            size="sm"
            className="-ml-2"
            onClick={() => navigate('/app/today')}
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            今日 Agent
          </Button>
          <div className="flex items-center gap-2">
            <Badge variant={statusVariant(status.tone)}>{status.label}</Badge>
            <span className="font-mono text-[11px] text-muted-foreground">
              V{item.version}
            </span>
          </div>
        </div>
        <h1 className="page-title mt-5 max-w-3xl">{item.title}</h1>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-muted-foreground">
          {item.summary}
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <Clock3 className="h-3.5 w-3.5" />
            {item.current_step}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <ShieldAlert className="h-3.5 w-3.5" />
            {item.priority === 'urgent' ? '紧急' : item.priority === 'attention' ? '需要关注' : '普通'}
          </span>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(300px,0.85fr)]">
        <section className="border border-border bg-[var(--factory-panel)]">
          <header className="border-b border-border px-5 py-4">
            <h2 className="section-title">
              {preview?.title || '动作预览'}
            </h2>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              {preview?.description ||
                'Agent 会根据当前任务事实执行，并在完成后回读平台结果。'}
            </p>
          </header>

          <div className="p-5">
            {preview?.fields.length ? (
              <div className="space-y-3">
                {preview.fields.map((field) => (
                  <div
                    key={`${field.label}-${field.value}`}
                    className="grid gap-1 border-b border-border pb-3 last:border-b-0 last:pb-0 sm:grid-cols-[132px_minmax(0,1fr)]"
                  >
                    <p className="text-xs text-muted-foreground">{field.label}</p>
                    <p
                      className={`text-sm leading-6 ${field.emphasis ? 'font-semibold text-foreground' : 'text-foreground'}`}
                    >
                      {field.value}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm leading-6 text-muted-foreground">
                当前没有结构化预览字段。提交前请核对任务摘要和执行状态。
              </p>
            )}

            {preview?.warning && (
              <div className="mt-5 border border-[color:rgba(217,139,112,0.3)] bg-[color:rgba(217,139,112,0.08)] p-3">
                <p className="flex items-start gap-2 text-xs leading-5 text-[var(--factory-coral)]">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  {preview.warning}
                </p>
              </div>
            )}

            {resultSummary && (
              <div className="mt-5 border border-border bg-background p-4">
                <p className="text-[11px] font-medium text-muted-foreground">
                  执行结果
                </p>
                <p className="mt-2 text-sm leading-6">{resultSummary}</p>
              </div>
            )}
          </div>
        </section>

        <div className="space-y-4">
          <section className="border border-border bg-[var(--factory-panel)] p-5">
            <h2 className="section-title">下一步</h2>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">
              操作会提交到同一工作项，并回写 App、Web 和通知中心。
            </p>
            {action ? (
              <Button
                className="mt-4 w-full"
                onClick={() => requestAction(action)}
                disabled={mutation.isPending}
              >
                <Play className="mr-2 h-4 w-4" />
                {action.label}
              </Button>
            ) : (
              <p className="mt-4 border border-border bg-background px-3 py-2.5 text-xs text-muted-foreground">
                当前没有可提交动作。
              </p>
            )}
            {submitError && (
              <p className="mt-3 text-xs leading-5 text-[var(--factory-coral)]">
                {submitError}
              </p>
            )}
          </section>

          <section className="border border-border bg-[var(--factory-panel)]">
            <header className="border-b border-border px-5 py-4">
              <h2 className="section-title">执行记录</h2>
            </header>
            <div className="px-5">
              {item.action_runs.length ? (
                item.action_runs.map((run) => {
                  const runStatus = workItemStatusMeta(run.status)
                  return (
                    <div
                      key={run.id}
                      className="border-b border-border py-4 last:border-b-0"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-xs font-medium">
                          {run.platform} · {run.target_type}
                        </p>
                        <Badge
                          variant={statusVariant(runStatus.tone)}
                          className="text-[11px]"
                        >
                          {runStatus.label}
                        </Badge>
                      </div>
                      <p className="mt-2 text-[11px] text-muted-foreground">
                        第 {run.attempt} 次 · {run.risk_level} risk
                      </p>
                      {run.policy_reason && (
                        <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
                          {run.policy_reason}
                        </p>
                      )}
                    </div>
                  )
                })
              ) : (
                <div className="flex items-center gap-2 py-8 text-xs text-muted-foreground">
                  <CheckCircle2 className="h-4 w-4" />
                  还没有执行记录
                </div>
              )}
            </div>
          </section>
        </div>
      </div>

      <ConfirmDialog
        open={Boolean(pendingAction)}
        title={preview?.title || pendingAction?.label || '确认执行'}
        description={
          preview?.warning ||
          'Agent 会执行这项操作并回读平台结果。确认后将回写当前工作项。'
        }
        confirmLabel={pendingAction?.label || '确认执行'}
        pending={mutation.isPending}
        destructive={false}
        onCancel={() => setPendingAction(null)}
        onConfirm={() => void confirmAction()}
      />
    </div>
  )
}
