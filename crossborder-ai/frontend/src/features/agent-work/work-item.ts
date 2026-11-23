import type {
  AvailableAction,
  WorkItemCommandInput,
  WorkItemCommandPayload,
  WorkItemDetail,
} from './types'

export type WorkItemTone = 'neutral' | 'warning' | 'danger' | 'success'

export interface WorkItemStatusMeta {
  label: string
  tone: WorkItemTone
}

const STATUS_META: Record<string, WorkItemStatusMeta> = {
  planned: { label: '执行方案已准备', tone: 'neutral' },
  waiting_user: { label: '等待你处理', tone: 'warning' },
  needs_action: { label: '等待你处理', tone: 'warning' },
  awaiting_confirmation: { label: '等待你确认', tone: 'warning' },
  running: { label: '正在执行', tone: 'neutral' },
  queued: { label: '已排队，等待执行', tone: 'neutral' },
  preflight: { label: '正在检查执行条件', tone: 'neutral' },
  executing: { label: '正在执行平台动作', tone: 'neutral' },
  verifying: { label: '正在回读平台结果', tone: 'neutral' },
  succeeded: { label: '已完成', tone: 'success' },
  completed: { label: '已完成', tone: 'success' },
  retryable_failed: { label: '执行失败，可重试', tone: 'danger' },
  failed: { label: '执行失败', tone: 'danger' },
  error: { label: '执行失败', tone: 'danger' },
  blocked: { label: '已阻断', tone: 'danger' },
  cancelled: { label: '已取消', tone: 'neutral' },
  compensated: { label: '已补偿', tone: 'warning' },
}

export function workItemStatusMeta(status?: string | null): WorkItemStatusMeta {
  return (
    STATUS_META[status ?? ''] ?? {
      label: status || '等待同步',
      tone: 'neutral',
    }
  )
}

export function primaryWorkItemAction(
  item: Pick<WorkItemDetail, 'available_actions'>,
): AvailableAction | null {
  const priority: AvailableAction['kind'][] = [
    'confirm',
    'retry',
    'input',
    'choose',
  ]
  for (const kind of priority) {
    const action = item.available_actions.find((entry) => entry.kind === kind)
    if (action) return action
  }
  return item.available_actions[0] ?? null
}

export function buildWorkItemCommand(
  item: Pick<WorkItemDetail, 'version'>,
  input: WorkItemCommandInput,
): WorkItemCommandPayload {
  return {
    action: input.action,
    action_id: input.actionId,
    expected_version: item.version,
    payload: input.payload ?? {},
    idempotency_key: input.idempotencyKey,
  }
}

export function workItemNeedsAttention(
  item: Pick<WorkItemDetail, 'requires_action' | 'status'>,
): boolean {
  return (
    item.requires_action !== 'none' &&
    item.status !== 'succeeded' &&
    item.status !== 'cancelled'
  )
}
