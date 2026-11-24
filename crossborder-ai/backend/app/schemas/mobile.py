"""移动端聚合接口契约。"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class WorkspaceSummary(BaseModel):
    id: UUID
    name: str
    type: str
    role: str


class BootstrapResponse(BaseModel):
    user_id: UUID
    display_name: str
    avatar_url: str | None = None
    workspaces: list[WorkspaceSummary]
    contract_version: str = "1"


class CommerceStoreSummary(BaseModel):
    """移动端店铺筛选的安全连接摘要。"""

    channel_type: str
    channel_id: str
    name: str
    status: str


class TimelineCommerce(BaseModel):
    """金额一律以字符串传输并带币种。

    用 float 会丢精度，而且前端拼 ¥ 时无法判断这笔钱到底是人民币还是美元，
    所以币种必须和金额同进同出。
    """

    amount: str | None = None
    currency: str | None = None
    order_count: int | None = None
    thumbnails: list[str] = Field(default_factory=list)


class TimelineItem(BaseModel):
    id: UUID
    kind: str
    title: str
    summary: str
    status: str
    priority: str
    current_step: str
    requires_action: str
    version: int
    due_at: datetime | None = None
    occurred_at: datetime
    # 交易类事实（金额/订单数/缩略图）。非交易类任务为 null，前端据此决定是否渲染。
    commerce: TimelineCommerce | None = None


class TimelineResponse(BaseModel):
    business_date: str
    items: list[TimelineItem]
    next_cursor: str | None = None


class AvailableAction(BaseModel):
    id: str
    kind: Literal["confirm", "choose", "input", "retry"]
    label: str
    risk: Literal["low", "medium", "high"] = "medium"
    expires_at: datetime | None = None


class ActionRunSummary(BaseModel):
    """App 需要的动作轨迹摘要，不暴露平台凭据和内部提示词。"""

    id: UUID
    action_id: str
    platform: str
    target_type: str
    target_id: str
    status: str
    risk_level: str
    autonomy_level: str
    policy_reason: str | None = None
    requires_dual_approval: bool = False
    attempt: int
    external_id: str | None = None
    error_code: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ActionPreviewField(BaseModel):
    label: str
    value: str
    emphasis: bool = False


class ActionPreview(BaseModel):
    """高风险动作确认前可公开给卖家的结构化事实。"""

    action_id: str
    platform: str
    target_type: str
    target_id: str
    title: str
    description: str
    risk: str
    fields: list[ActionPreviewField] = Field(default_factory=list)
    warning: str | None = None


class CustomerAttachmentSummary(BaseModel):
    id: UUID
    file_name: str
    content_type: str
    file_size: int
    url: str


class CustomerOrderContext(BaseModel):
    order_name: str | None = None
    financial_status: str | None = None
    fulfillment_status: str | None = None
    tracking_company: str | None = None
    tracking_number: str | None = None
    tracking_url: str | None = None


class CustomerOrderLinkRequest(BaseModel):
    shopify_channel_id: UUID
    external_order_id: str = Field(min_length=1, max_length=128)


class CustomerOrderSelectionResponse(BaseModel):
    status: str
    order: CustomerOrderContext | None = None
    work_item_status: str | None = None
    requires_action: str | None = None


class CustomerOrderCandidate(BaseModel):
    shopify_channel_id: str | None = None
    external_order_id: str
    order_name: str | None = None
    financial_status: str | None = None
    fulfillment_status: str | None = None
    order_created_at: str | None = None
    tracking_company: str | None = None
    tracking_number: str | None = None
    tracking_url: str | None = None


class CustomerContext(BaseModel):
    """客服工作项需要的客户原文与最新回复草稿。"""

    thread_id: UUID
    subject: str | None = None
    customer_message: str | None = None
    draft_id: UUID | None = None
    draft_version: int | None = None
    draft_text: str | None = None
    draft_status: str | None = None
    language: str | None = None
    intent: str | None = None
    risk_level: str | None = None
    auto_reply_candidate: bool = False
    requires_human: bool = False
    assigned_to_me: bool = False
    attachments: list[CustomerAttachmentSummary] = Field(default_factory=list)
    order: CustomerOrderContext | None = None
    order_candidates: list[CustomerOrderCandidate] = Field(
        default_factory=list
    )


class MediaReferenceAsset(BaseModel):
    id: UUID
    name: str
    url: str


class MediaResult(BaseModel):
    media_type: str
    task_id: UUID
    task_status: str
    prompt: str | None = None
    reference_assets: list[MediaReferenceAsset] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    video_url: str | None = None
    error: str | None = None
    can_retry: bool = False


class MediaRegenerateRequest(BaseModel):
    """素材重新生成的用户输入；参考图只接受当前工作区素材。"""

    expected_version: int = Field(ge=1)
    prompt: str = Field(min_length=5, max_length=4000)
    reference_asset_ids: list[UUID] = Field(default_factory=list, max_length=4)


class MediaRegenerateResponse(BaseModel):
    action_run_id: UUID
    status: str
    work_item_version: int


class CustomerChannelCreateRequest(BaseModel):
    provider: Literal["imap_smtp", "judge_me"]
    external_account_id: str = Field(min_length=3, max_length=255)
    display_name: str = Field(min_length=1, max_length=120)
    credentials: dict = Field(default_factory=dict)


class CustomerChannelSummary(BaseModel):
    id: UUID
    provider: str
    external_account_id: str
    display_name: str
    status: str


class AgentPolicyUpsertRequest(BaseModel):
    autonomy_level: Literal["suggest", "confirm", "auto"]
    conditions: dict = Field(default_factory=dict)
    enabled: bool = True


class AgentPolicySummary(BaseModel):
    id: UUID
    action_id: str
    autonomy_level: str
    conditions: dict = Field(default_factory=dict)
    enabled: bool
    version: int


class AgentControlUpdateRequest(BaseModel):
    paused: bool


class AgentControlResponse(BaseModel):
    paused: bool
    frozen_action_count: int = 0
    policies: list[AgentPolicySummary] = Field(default_factory=list)


class ReplyDraftRequest(BaseModel):
    mode: Literal["edit", "translate"] = "edit"
    body_text: str | None = Field(default=None, max_length=12000)
    seller_instruction: str | None = Field(default=None, max_length=8000)
    language: str | None = Field(default=None, max_length=20)
    target_language: str | None = Field(default=None, max_length=20)


class ReplyDraftResponse(BaseModel):
    id: UUID
    thread_id: UUID
    version: int
    language: str
    source_language: str | None = None
    body_text: str
    status: str


class CustomerTakeoverResponse(BaseModel):
    thread_id: UUID
    assigned_user_id: UUID
    assigned_to_me: bool
    status: str
    priority: str


class DailyPlanItemSummary(BaseModel):
    id: UUID
    work_item_id: UUID
    title: str
    category: str
    priority_score: int
    reason: str
    expected_action: str | None = None
    status: str


class DailyPlanResponse(BaseModel):
    business_date: str
    status: str
    overview: str
    decision_count: int
    auto_count: int
    monitor_count: int
    carryover_count: int
    items: list[DailyPlanItemSummary]


class DeviceRegistrationRequest(BaseModel):
    expo_push_token: str = Field(min_length=10, max_length=500)
    platform: Literal["ios", "android", "web"]
    device_name: str | None = Field(default=None, max_length=120)


class NotificationItem(BaseModel):
    id: UUID
    notification_type: str
    title: str
    body: str
    deep_link: str
    work_item_id: UUID | None = None
    status: str
    created_at: datetime
    read_at: datetime | None = None


class NotificationPreferenceUpdate(BaseModel):
    morning_brief: bool | None = None
    day_closeout: bool | None = None
    needs_action: bool | None = None
    action_failed: bool | None = None
    authorization_expired: bool | None = None
    quiet_start_hour: int | None = Field(default=None, ge=0, le=23)
    quiet_end_hour: int | None = Field(default=None, ge=0, le=23)
    timezone: str | None = Field(default=None, max_length=64)


class NotificationPreferenceResponse(BaseModel):
    morning_brief: bool
    day_closeout: bool
    needs_action: bool
    action_failed: bool
    authorization_expired: bool
    quiet_start_hour: int | None = None
    quiet_end_hour: int | None = None
    timezone: str


class WorkItemDetailResponse(BaseModel):
    id: UUID
    version: int
    kind: str
    title: str
    summary: str
    status: str
    priority: str
    current_step: str
    requires_action: str
    available_actions: list[AvailableAction]
    action_runs: list[ActionRunSummary] = Field(default_factory=list)
    action_preview: ActionPreview | None = None
    result: dict | None = None
    customer_context: CustomerContext | None = None
    media_result: MediaResult | None = None
    due_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WorkItemCommandRequest(BaseModel):
    action: Literal["confirm", "choose", "input", "retry"]
    action_id: str = Field(min_length=1, max_length=40)
    expected_version: int = Field(ge=1)
    payload: dict = Field(default_factory=dict)


class WorkItemCommandResponse(BaseModel):
    command_id: UUID
    work_item_id: UUID
    status: str
    action_run_id: UUID | None = None
    accepted_at: datetime


class MobileImageAssetResponse(BaseModel):
    """移动端素材库中的图片摘要。"""

    id: UUID
    name: str
    url: str
    content_type: str
    width: int
    height: int
    file_size: int
    sort_order: int
    category: str
    created_at: datetime
    updated_at: datetime


class MobileMediaSaveResponse(BaseModel):
    """生成媒体写入素材库后的稳定结果。"""

    asset_ids: list[UUID]


class PublicImageAssetResponse(BaseModel):
    """私有素材显式发布后的持久公共地址。"""

    asset_id: UUID
    public_url: str
    expires_at: datetime | None = None


class ImageAssetReorderRequest(BaseModel):
    asset_ids: list[UUID] = Field(min_length=1, max_length=100)


class ImageAssetCategoryRequest(BaseModel):
    """把素材归到某一类；只接受素材库筛选用的四个值。"""

    category: str = Field(pattern="^(product|scene|photography|other)$")


class MobileVoiceTranscriptionResponse(BaseModel):
    """移动端语音上传后的可复用转写结果。"""

    asset_id: UUID
    transcript: str
    language: str
    duration_ms: int
    expires_at: datetime
    provider: str
    model: str


class AgentTurnRequest(BaseModel):
    input_type: Literal["text", "voice", "image", "link"]
    text: str | None = Field(default=None, max_length=8000)
    source_url: str | None = Field(default=None, max_length=4000)
    asset_ids: list[UUID] = Field(default_factory=list, max_length=8)
    audio_asset_id: UUID | None = None
    work_item_id: UUID | None = None


class AgentTurnResponse(BaseModel):
    agent_turn_id: UUID
    status: str
    created_work_item_ids: list[UUID]
    stream_url: str | None = None
    contract_version: str = "1"


class AgentStepSummary(BaseModel):
    label: str
    status: str
    action: str | None = None
    structured: dict[str, Any] | None = None


class AgentTurnDetailResponse(BaseModel):
    agent_turn_id: UUID
    status: str
    input_type: str
    text: str | None = None
    task_status: str | None = None
    result_summary: str | None = None
    error: str | None = None
    steps: list[AgentStepSummary] = Field(default_factory=list)
    created_work_item_ids: list[UUID] = Field(default_factory=list)
