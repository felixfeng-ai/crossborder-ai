export type WorkspaceSummary = {
  id: string;
  name: string;
  type: "personal" | "team";
  role: "owner" | "admin" | "operator" | "viewer";
};

export type BootstrapResponse = {
  user_id: string;
  display_name: string;
  workspaces: WorkspaceSummary[];
  contract_version: string;
};

export type CommerceStore = {
  channel_type: string;
  channel_id: string;
  name: string;
  status: string;
};

/**
 * 交易类事实。amount 是字符串：金额用 float 传会丢精度，
 * currency 必须和它同行，否则前端只能瞎猜该拼 ¥ 还是 $。
 */
export type TimelineCommerce = {
  amount: string | null;
  currency: string | null;
  order_count: number | null;
  thumbnails: string[];
};

export type TimelineItem = {
  id: string;
  kind: string;
  title: string;
  summary: string;
  status: string;
  priority: "urgent" | "attention" | "normal" | string;
  current_step: string;
  requires_action: string;
  version: number;
  due_at: string | null;
  occurred_at: string;
  commerce?: TimelineCommerce | null;
};

export type TimelineResponse = {
  business_date: string;
  items: TimelineItem[];
  next_cursor: string | null;
};

export type AvailableAction = {
  id: string;
  kind: "confirm" | "choose" | "input" | "retry";
  label: string;
  risk: "low" | "medium" | "high";
  expires_at: string | null;
};

export type ActionRunSummary = {
  id: string;
  action_id: string;
  platform: string;
  target_type: string;
  target_id: string;
  status:
    | "planned"
    | "preflight"
    | "awaiting_confirmation"
    | "queued"
    | "executing"
    | "verifying"
    | "succeeded"
    | "retryable_failed"
    | "blocked"
    | "cancelled"
    | "compensated"
    | string;
  risk_level: "low" | "medium" | "high" | string;
  autonomy_level: "suggest" | "confirm" | "auto" | string;
  policy_reason?: string | null;
  requires_dual_approval?: boolean;
  attempt: number;
  external_id: string | null;
  error_code: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type ActionPreview = {
  action_id: string;
  platform: string;
  target_type: string;
  target_id: string;
  title: string;
  description: string;
  risk: "low" | "medium" | "high" | string;
  fields: {
    label: string;
    value: string;
    emphasis?: boolean;
  }[];
  warning: string | null;
};

export type WorkItemDetail = {
  id: string;
  version: number;
  kind: string;
  title: string;
  summary: string;
  status: string;
  priority: string;
  current_step: string;
  requires_action: string;
  available_actions: AvailableAction[];
  action_runs: ActionRunSummary[];
  action_preview?: ActionPreview | null;
  result: Record<string, unknown> | null;
  customer_context: {
    thread_id: string;
    subject: string | null;
    customer_message: string | null;
    draft_id: string | null;
    draft_version: number | null;
    draft_text: string | null;
    draft_status: string | null;
    language: string | null;
    intent: string | null;
    risk_level: string | null;
    auto_reply_candidate: boolean;
    requires_human: boolean;
    assigned_to_me: boolean;
    attachments: {
      id: string;
      file_name: string;
      content_type: string;
      file_size: number;
      url: string;
    }[];
    order: {
      order_name: string | null;
      financial_status: string | null;
      fulfillment_status: string | null;
      tracking_company: string | null;
      tracking_number: string | null;
      tracking_url: string | null;
    } | null;
    order_candidates: {
      shopify_channel_id: string | null;
      external_order_id: string;
      order_name: string | null;
      financial_status: string | null;
      fulfillment_status: string | null;
      order_created_at: string | null;
      tracking_company: string | null;
      tracking_number: string | null;
      tracking_url: string | null;
      // 后端可按订单回填商品名与金额；缺失时前端降级只显示现有字段。
      product_title?: string | null;
      total_price?: string | null;
      currency?: string | null;
    }[];
  } | null;
  media_result: {
    media_type: "image" | "video" | string;
    task_id: string;
    task_status: string;
    prompt: string | null;
    reference_assets: {
      id: string;
      name: string;
      url: string;
    }[];
    images: string[];
    video_url: string | null;
    error: string | null;
    can_retry: boolean;
  } | null;
  due_at: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
};

export type CommandResponse = {
  command_id: string;
  work_item_id: string;
  status: string;
  action_run_id: string | null;
  accepted_at: string;
};

export type ReplyDraft = {
  id: string;
  thread_id: string;
  version: number;
  language: string;
  source_language: string | null;
  body_text: string;
  status: string;
};

export type AgentTurnResponse = {
  agent_turn_id: string;
  status: string;
  created_work_item_ids: string[];
  stream_url: string | null;
  contract_version: string;
};

export type AgentPolicy = {
  id: string;
  action_id: string;
  autonomy_level: "suggest" | "confirm" | "auto";
  conditions: Record<string, number | boolean>;
  enabled: boolean;
  version: number;
};

export type AgentControl = {
  paused: boolean;
  frozen_action_count: number;
  policies: AgentPolicy[];
};

export type ImageCategory = "product" | "scene" | "photography" | "other";

export type ImageAsset = {
  id: string;
  name: string;
  url: string;
  content_type: string;
  width: number;
  height: number;
  file_size: number;
  sort_order: number;
  category: ImageCategory;
  created_at: string;
  updated_at: string;
};

export type CustomerTakeoverResponse = {
  thread_id: string;
  assigned_user_id: string;
  assigned_to_me: boolean;
  status: string;
  priority: string;
};

export type CustomerOrderSelectionResponse = {
  status: string;
  order: {
    order_name: string | null;
    financial_status: string | null;
    fulfillment_status: string | null;
    tracking_company: string | null;
    tracking_number: string | null;
    tracking_url: string | null;
  } | null;
  work_item_status: string | null;
  requires_action: string | null;
};

export type VoiceTranscriptionResponse = {
  asset_id: string;
  transcript: string;
  language: string;
  duration_ms: number;
  expires_at: string;
};

export type AgentStep = {
  label: string;
  status: string;
};

export type AgentTurnDetail = {
  agent_turn_id: string;
  status: string;
  input_type: string;
  text: string | null;
  task_status: string | null;
  result_summary: string | null;
  error: string | null;
  steps: AgentStep[];
  created_work_item_ids: string[];
};

export type DailyPlanItem = {
  id: string;
  work_item_id: string;
  title: string;
  category: "decision" | "auto" | "monitor" | "carryover" | string;
  priority_score: number;
  reason: string;
  expected_action: string | null;
  status: string;
};

export type DailyPlanResponse = {
  business_date: string;
  status: string;
  overview: string;
  decision_count: number;
  auto_count: number;
  monitor_count: number;
  carryover_count: number;
  items: DailyPlanItem[];
};

export type NotificationItem = {
  id: string;
  notification_type: string;
  title: string;
  body: string;
  deep_link: string;
  work_item_id: string | null;
  status: string;
  created_at: string;
  read_at: string | null;
};

export type NotificationPreferences = {
  morning_brief: boolean;
  day_closeout: boolean;
  needs_action: boolean;
  action_failed: boolean;
  authorization_expired: boolean;
  quiet_start_hour: number | null;
  quiet_end_hour: number | null;
  timezone: string;
};
