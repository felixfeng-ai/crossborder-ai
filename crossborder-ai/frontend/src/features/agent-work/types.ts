export interface TimelineItem {
  id: string
  kind: string
  title: string
  summary: string
  status: string
  priority: 'urgent' | 'attention' | 'normal' | string
  current_step: string
  requires_action: string
  version: number
  due_at: string | null
  occurred_at: string
}

export interface TimelineResponse {
  business_date: string
  items: TimelineItem[]
  next_cursor: string | null
}

export interface DailyPlanItem {
  id: string
  work_item_id: string
  title: string
  category: 'decision' | 'auto' | 'monitor' | 'carryover' | string
  priority_score: number
  reason: string
  expected_action: string | null
  status: string
}

export interface DailyPlanResponse {
  business_date: string
  status: string
  overview: string
  decision_count: number
  auto_count: number
  monitor_count: number
  carryover_count: number
  items: DailyPlanItem[]
}

export interface AvailableAction {
  id: string
  kind: 'confirm' | 'choose' | 'input' | 'retry'
  label: string
  risk: 'low' | 'medium' | 'high' | string
  expires_at: string | null
}

export interface ActionRunSummary {
  id: string
  action_id: string
  platform: string
  target_type: string
  target_id: string
  status: string
  risk_level: string
  autonomy_level: string
  policy_reason?: string | null
  requires_dual_approval?: boolean
  attempt: number
  external_id: string | null
  error_code: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface ActionPreview {
  action_id: string
  platform: string
  target_type: string
  target_id: string
  title: string
  description: string
  risk: 'low' | 'medium' | 'high' | string
  fields: Array<{
    label: string
    value: string
    emphasis?: boolean
  }>
  warning: string | null
}

export interface WorkItemDetail {
  id: string
  version: number
  kind: string
  title: string
  summary: string
  status: string
  priority: string
  current_step: string
  requires_action: string
  available_actions: AvailableAction[]
  action_runs: ActionRunSummary[]
  action_preview?: ActionPreview | null
  result: Record<string, unknown> | null
  customer_context: Record<string, unknown> | null
  media_result: Record<string, unknown> | null
  due_at: string | null
  expires_at: string | null
  created_at: string
  updated_at: string
}

export interface CommandResponse {
  command_id: string
  work_item_id: string
  status: string
  action_run_id: string | null
  accepted_at: string
}

export interface WorkItemCommandInput {
  action: 'confirm' | 'choose' | 'input' | 'retry'
  actionId: string
  idempotencyKey: string
  payload?: Record<string, unknown>
}

export interface WorkItemCommandPayload {
  action: WorkItemCommandInput['action']
  action_id: string
  expected_version: number
  payload: Record<string, unknown>
  idempotency_key: string
}

export interface ImageAsset {
  id: string
  name: string
  url: string
  content_type: string
  width: number
  height: number
  file_size: number
  sort_order: number
  category: string
  created_at: string
  updated_at: string
}

export interface AgentTurnResponse {
  agent_turn_id: string
  status: string
  created_work_item_ids: string[]
  stream_url: string | null
  contract_version: string
}

export interface AgentTurnDetail {
  agent_turn_id: string
  status: string
  input_type: string
  text: string | null
  task_status: string | null
  result_summary: string | null
  error: string | null
  steps: Array<{
    label?: string
    status?: string
    action?: string
    summary?: string
  }>
  created_work_item_ids: string[]
}
