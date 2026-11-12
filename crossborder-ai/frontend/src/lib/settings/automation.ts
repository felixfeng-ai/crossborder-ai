export type AutomationStatus = 'never' | 'success' | 'failed' | string

export type AutomationTaskKey =
  | 'store_check'
  | 'operations_monitor'
  | 'shopify_sync'
  | 'ab_evaluation'

export const AUTOMATION_FIELD_BY_TASK: Record<
  AutomationTaskKey,
  | 'daily_store_check'
  | 'daily_operations_monitor'
  | 'shopify_auto_sync'
  | 'ab_auto_pause'
> = {
  store_check: 'daily_store_check',
  operations_monitor: 'daily_operations_monitor',
  shopify_sync: 'shopify_auto_sync',
  ab_evaluation: 'ab_auto_pause',
}

export interface AutomationTask {
  key: AutomationTaskKey
  title: string
  description: string
  schedule: string
  enabled: boolean
  effective_enabled: boolean
  last_run_at: string | null
  status: AutomationStatus
  error: string | null
}

export interface AutomationSettingsResponse {
  eligible: boolean
  plan: string
  tasks: AutomationTask[]
}

export function automationStatusLabel(status: AutomationStatus): string {
  if (status === 'success') return '成功'
  if (status === 'failed') return '失败'
  if (status === 'skipped') return '已跳过'
  return '未运行'
}

export function effectiveAutomationEnabled(
  plan: string,
  enabled: boolean,
): boolean {
  return ['standard', 'professional'].includes(plan) && enabled
}
