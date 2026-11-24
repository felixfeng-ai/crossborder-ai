"""生产版移动端聚合接口。"""

import asyncio
import hashlib
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, Response, StreamingResponse
from PIL import Image as PILImage, UnidentifiedImageError
from sqlalchemy import desc, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.crypto import encrypt_value
from app.core.database import get_db
from app.core.security import create_access_token, decode_token_safe
from app.dependencies import (
    WorkspaceContext,
    get_current_user,
    get_current_workspace,
    require_workspace_role,
)
from app.models.user import User
from app.models.audio_asset import AudioAsset
from app.models.image_asset import ImageAsset
from app.models.agent_work import WorkItem, WorkItemEvent
from app.models.notification import NotificationOutbox
from app.models.integration_event import IntegrationEvent
from app.models.platform_connection import PlatformConnection
from app.models.shopify_channel import ShopifyChannel
from app.models.image_generation_task import ImageGenerationTask
from app.models.video_generation_task import VideoGenerationTask
from app.models.customer_channel import (
    CustomerAttachment,
    CustomerChannel,
    CustomerMessage,
    CustomerOrderLink,
    CustomerThread,
    ReplyDraft,
)
from app.models.action_run import ActionRun
from app.models.agent_policy import AgentAutonomyPolicy
from app.models.workspace import WorkspaceAuditLog
from app.schemas.mobile import (
    ActionRunSummary,
    AgentControlResponse,
    AgentControlUpdateRequest,
    AgentPolicySummary,
    AgentPolicyUpsertRequest,
    AgentTurnRequest,
    AgentTurnResponse,
    AgentStepSummary,
    AgentTurnDetailResponse,
    AvailableAction,
    BootstrapResponse,
    CommerceStoreSummary,
    CustomerContext,
    CustomerAttachmentSummary,
    CustomerOrderLinkRequest,
    CustomerOrderCandidate,
    CustomerOrderContext,
    CustomerOrderSelectionResponse,
    CustomerTakeoverResponse,
    CustomerChannelCreateRequest,
    CustomerChannelSummary,
    DailyPlanItemSummary,
    DailyPlanResponse,
    DeviceRegistrationRequest,
    ImageAssetCategoryRequest,
    ImageAssetReorderRequest,
    NotificationItem,
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
    PublicImageAssetResponse,
    ReplyDraftRequest,
    ReplyDraftResponse,
    MediaResult,
    MediaReferenceAsset,
    MediaRegenerateRequest,
    MediaRegenerateResponse,
    MobileImageAssetResponse,
    MobileMediaSaveResponse,
    MobileVoiceTranscriptionResponse,
    TimelineCommerce,
    TimelineItem,
    TimelineResponse,
    WorkItemCommandRequest,
    WorkItemCommandResponse,
    WorkItemDetailResponse,
    WorkspaceSummary,
)
from app.services.action_runtime import (
    ActionRunStateError,
    confirm_action_run,
    get_action_definition,
    list_action_runs_for_work_item,
    plan_action_run,
    retry_action_run,
)
from app.services.agent_policy import (
    normalize_conditions,
    set_agent_paused,
    workspace_is_paused,
)
from app.services.action_previews import build_action_preview
from app.services.public_image_storage import publish_public_image_asset
from app.services.audio_storage import get_audio_storage
from app.services.agent_turns import (
    AgentTurnAssetError,
    AgentTurnConflict,
    create_agent_turn,
    get_agent_turn_detail,
)
from app.services.mobile_events import stream_workspace_events
from app.services.image_processing import normalize_uploaded_image
from app.services.generated_image_assets import materialize_image_task_assets
from app.services.email_channel_service import sync_customer_inbox
from app.services.customer_reply_adapter import (
    create_reply_draft,
    create_translated_reply_draft,
)
from app.services.customer_intent import classify_customer_message
from app.services.customer_order_link import apply_customer_order_selection
from app.services.judge_me_review_service import (
    normalize_judge_me_credentials,
    sync_judge_me_reviews,
)
from app.services.language_service import detect_language
from app.services.speech_transcription import (
    SpeechTranscriptionError,
    transcribe_mobile_audio,
)
from app.services.daily_plan import (
    build_daily_plan,
    close_daily_plan,
    get_agent_day,
    get_daily_plan,
)
from app.services.integration_events import retry_integration_event
from app.services.notifications import (
    create_notification,
    get_notification_preference,
    register_mobile_device,
    update_notification_preference,
)
from app.services.work_items import (
    WorkItemCommandConflict,
    WorkItemStateError,
    WorkItemVersionConflict,
    get_work_item,
    list_work_items_for_date,
    submit_work_item_command,
)
from app.services.workspaces import list_user_workspaces
from app.services.business_time import business_date_in_timezone


router = APIRouter(prefix="/api/mobile/v1", tags=["Mobile App"])

ACTION_LABELS = {
    "confirm": "确认处理",
    "choose": "选择方案",
    "input": "补充信息",
    "retry": "重新处理",
}

AGENT_STEP_LABELS = {
    "select_products": "选品分析",
    "analyze_category": "品类分析",
    "analyze_product_decision": "商品判断",
    "find_1688_sources": "1688 找货源",
    "generate_listing": "生成 Listing",
    "check_compliance": "合规检查",
    "store_check": "店铺巡检",
    "monitor_products": "商品监控",
}

AUDIO_CONTENT_TYPES = {
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/m4a": "m4a",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "application/octet-stream": "m4a",
}


def _validate_audio_signature(raw: bytes, content_type: str) -> None:
    """拒绝伪造 MIME 的非音频文件。"""

    if content_type in {"audio/mp4", "audio/x-m4a", "audio/m4a"}:
        valid = len(raw) >= 12 and raw[4:8] == b"ftyp"
    elif content_type in {"audio/wav", "audio/x-wav"}:
        valid = len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WAVE"
    elif content_type == "audio/mpeg":
        valid = raw[:3] == b"ID3" or (
            len(raw) >= 2 and raw[0] == 0xFF and raw[1] & 0xE0 == 0xE0
        )
    elif content_type == "audio/webm":
        valid = raw[:4] == b"\x1aE\xdf\xa3"
    elif content_type == "audio/ogg":
        valid = raw[:4] == b"OggS"
    else:
        # application/octet-stream 仅接受标准 M4A 容器头。
        valid = len(raw) >= 12 and raw[4:8] == b"ftyp"
    if not valid:
        raise HTTPException(status_code=400, detail="音频文件内容无效")


def _mobile_asset_path(storage_key: str) -> Path:
    """确保移动端写入路径始终位于配置的素材目录内。"""

    root = Path(settings.IMAGE_STORAGE_DIR).resolve()
    target = (root / storage_key).resolve()
    if target != root and root not in target.parents:
        raise ValueError("素材路径非法")
    return target


def _mobile_jpeg_path(source: Path) -> Path:
    """为 Android 生成可内联显示的 JPEG 缓存，兼容 WebP 解码差异。"""

    target = source.with_name(f"{source.stem}.mobile.jpg")
    if target.is_file() and target.stat().st_mtime >= source.stat().st_mtime:
        return target
    temp = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        with PILImage.open(source) as image:
            if "A" in image.getbands():
                rgba = image.convert("RGBA")
                rendered = PILImage.new("RGB", rgba.size, "white")
                rendered.paste(rgba, mask=rgba.getchannel("A"))
            else:
                rendered = image.convert("RGB")
            rendered.save(temp, format="JPEG", quality=88, optimize=True)
        os.replace(temp, target)
    except (UnidentifiedImageError, OSError):
        temp.unlink(missing_ok=True)
        raise HTTPException(status_code=404, detail="素材文件无法转换") from None
    return target


async def _normalize_mobile_image(file: UploadFile) -> tuple[bytes, int, int]:
    """读取并统一转换 App 图片，限制解码炸弹和超大文件。"""

    raw = await file.read(settings.MAX_IMAGE_UPLOAD_BYTES + 1)
    try:
        return await run_in_threadpool(
            normalize_uploaded_image,
            raw,
            settings.MAX_IMAGE_UPLOAD_BYTES,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _mobile_image_response(
    asset: ImageAsset,
    *,
    workspace_id: UUID,
) -> MobileImageAssetResponse:
    return MobileImageAssetResponse(
        id=asset.id,
        name=asset.name,
        url=(
            f"/api/mobile/v1/workspaces/{workspace_id}"
            f"/assets/images/{asset.id}/file?format=jpeg"
        ),
        content_type=asset.content_type,
        width=asset.width,
        height=asset.height,
        file_size=asset.file_size,
        sort_order=asset.sort_order,
        category=asset.category,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


def _date_in_timezone(timezone_name: str) -> date:
    try:
        return datetime.now(ZoneInfo(timezone_name)).date()
    except ZoneInfoNotFoundError:
        return datetime.now(timezone.utc).date()


def _available_actions(item) -> list[AvailableAction]:
    if item.status != "waiting_user" or item.requires_action == "none":
        return []
    kind = item.requires_action
    if kind not in ACTION_LABELS:
        return []
    return [
        AvailableAction(
            id="primary",
            kind=kind,
            label=ACTION_LABELS[kind],
            risk="medium" if item.priority != "urgent" else "high",
            expires_at=item.expires_at,
        )
    ]


def _agent_policy_summary(policy: AgentAutonomyPolicy) -> AgentPolicySummary:
    try:
        conditions = json.loads(policy.conditions_json or "{}")
    except json.JSONDecodeError:
        conditions = {}
    return AgentPolicySummary(
        id=policy.id,
        action_id=policy.action_id,
        autonomy_level=policy.autonomy_level,
        conditions=conditions if isinstance(conditions, dict) else {},
        enabled=policy.enabled,
        version=policy.version,
    )


def _action_policy_snapshot(run: ActionRun) -> dict:
    try:
        snapshot = json.loads(run.policy_snapshot_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return snapshot if isinstance(snapshot, dict) else {}


def _result_object(raw: str | None) -> dict | None:
    """只向 App 暴露结构化结果，损坏数据不能拖垮详情接口。"""

    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


async def _media_result(
    db: AsyncSession,
    *,
    item,
    workspace_owner_id: UUID,
    viewer_user_id: UUID,
) -> MediaResult | None:
    result = _result_object(item.result_json)
    if not result or not result.get("task_id"):
        return None
    try:
        task_id = UUID(str(result["task_id"]))
    except (TypeError, ValueError):
        return None
    media_type = str(result.get("media_type") or "image")
    task = await db.get(
        ImageGenerationTask if media_type == "image" else VideoGenerationTask,
        task_id,
    )
    if task is None or task.user_id not in {
        workspace_owner_id,
        viewer_user_id,
    }:
        return None
    images: list[str] = []
    if media_type == "image":
        try:
            parsed = json.loads(task.image_urls or "[]")
            if isinstance(parsed, list):
                images = [str(url) for url in parsed if url]
        except (TypeError, json.JSONDecodeError):
            images = []
    video_url = None
    reference_assets: list[MediaReferenceAsset] = []
    if media_type == "image":
        try:
            reference_ids = json.loads(task.reference_assets_json or "[]")
        except (TypeError, json.JSONDecodeError):
            reference_ids = []
        if isinstance(reference_ids, list) and reference_ids:
            valid_reference_ids: list[UUID] = []
            for reference_id in reference_ids:
                try:
                    valid_reference_ids.append(UUID(str(reference_id)))
                except (TypeError, ValueError):
                    continue
            references = (
                await db.execute(
                    select(ImageAsset).where(
                        ImageAsset.workspace_id == item.workspace_id,
                        ImageAsset.id.in_(valid_reference_ids),
                        ImageAsset.deleted_at.is_(None),
                    )
                )
            ).scalars().all()
            reference_assets = [
                MediaReferenceAsset(
                    id=asset.id,
                    name=asset.name,
                    url=(
                        f"/api/mobile/v1/workspaces/{item.workspace_id}"
                        f"/assets/images/{asset.id}/file"
                    ),
                )
                for asset in references
            ]
    if (
        media_type == "video"
        and task.status == "succeeded"
        and getattr(task, "storage_key", None)
    ):
        access_token = create_access_token(
            subject=str(task.user_id),
            extra_claims={"scope": "video_file"},
            expires_delta=timedelta(minutes=10),
        )
        video_url = (
            f"/api/mobile/v1/media/video/{task.id}/file"
            f"?access_token={access_token}"
        )
    return MediaResult(
        media_type=media_type,
        task_id=task.id,
        task_status=task.status,
        prompt=task.prompt,
        reference_assets=reference_assets,
        images=images,
        video_url=video_url,
        error=getattr(task, "error", None),
        can_retry=task.status in {"failed", "canceled"},
    )


async def _customer_context(
    db: AsyncSession,
    item,
    *,
    viewer_user_id: UUID,
) -> CustomerContext | None:
    """只读取当前工作项关联的客户线程，避免把客服收件箱搬进 App。"""

    if item.source_type != "customer_thread" or not item.source_id:
        return None
    try:
        thread_id = UUID(item.source_id)
    except (TypeError, ValueError):
        return None
    thread = (
        await db.execute(
            select(CustomerThread).where(
                CustomerThread.workspace_id == item.workspace_id,
                CustomerThread.id == thread_id,
            )
        )
    ).scalar_one_or_none()
    if thread is None:
        return None
    message = (
        await db.execute(
            select(CustomerMessage)
            .where(
                CustomerMessage.workspace_id == item.workspace_id,
                CustomerMessage.thread_id == thread.id,
                CustomerMessage.direction == "inbound",
            )
            .order_by(desc(CustomerMessage.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    draft = (
        await db.execute(
            select(ReplyDraft)
            .where(
                ReplyDraft.workspace_id == item.workspace_id,
                ReplyDraft.thread_id == thread.id,
            )
            .order_by(desc(ReplyDraft.version))
            .limit(1)
        )
    ).scalar_one_or_none()
    result = _result_object(item.result_json) or {}
    if message is not None and not result.get("risk_level"):
        assessment = classify_customer_message(
            message.body_text,
            is_review=thread.thread_type == "review",
            rating=(
                int(result["rating"])
                if isinstance(result.get("rating"), int)
                else None
            ),
        )
        result = {**result, **assessment.to_dict()}
    attachments = []
    if message is not None:
        attachment_rows = (
            await db.execute(
                select(CustomerAttachment)
                .where(
                    CustomerAttachment.workspace_id == item.workspace_id,
                    CustomerAttachment.message_id == message.id,
                )
                .order_by(CustomerAttachment.created_at)
            )
        ).scalars().all()
        attachments = [
            CustomerAttachmentSummary(
                id=attachment.id,
                file_name=attachment.file_name,
                content_type=attachment.content_type,
                file_size=attachment.file_size,
                url=(
                    f"/api/mobile/v1/workspaces/{item.workspace_id}"
                    f"/customer-attachments/{attachment.id}/file"
                ),
            )
            for attachment in attachment_rows
        ]
    order_link = (
        await db.execute(
            select(CustomerOrderLink).where(
                CustomerOrderLink.workspace_id == item.workspace_id,
                CustomerOrderLink.thread_id == thread.id,
            )
        )
    ).scalar_one_or_none()
    order_context = (
        CustomerOrderContext(
            order_name=order_link.order_name,
            financial_status=order_link.financial_status,
            fulfillment_status=order_link.fulfillment_status,
            tracking_company=order_link.tracking_company,
            tracking_number=order_link.tracking_number,
            tracking_url=order_link.tracking_url,
        )
        if order_link is not None
        else None
    )
    order_candidates = []
    for candidate in result.get("order_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        try:
            order_candidates.append(
                CustomerOrderCandidate(**candidate)
            )
        except Exception:
            continue
    return CustomerContext(
        thread_id=thread.id,
        subject=thread.subject,
        customer_message=message.body_text if message else None,
        draft_id=draft.id if draft else None,
        draft_version=draft.version if draft else None,
        draft_text=draft.body_text if draft else None,
        draft_status=draft.status if draft else None,
        language=draft.language if draft else thread.language,
        intent=result.get("intent"),
        risk_level=result.get("risk_level"),
        auto_reply_candidate=bool(
            result.get("auto_reply_candidate", False)
        ),
        requires_human=bool(result.get("requires_human", False)),
        assigned_to_me=(
            thread.assigned_user_id == viewer_user_id
            if thread.assigned_user_id is not None
            else False
        ),
        attachments=attachments,
        order=order_context,
        order_candidates=order_candidates,
    )


async def _daily_plan_response(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    day,
    items,
) -> DailyPlanResponse:
    work_ids = [item.work_item_id for item in items]
    work_items = (
        await db.execute(
            select(WorkItem).where(WorkItem.id.in_(work_ids))
        )
    ).scalars().all() if work_ids else []
    by_id = {item.id: item for item in work_items}
    counts = {
        category: sum(1 for item in items if item.category == category)
        for category in ("decision", "auto", "monitor", "carryover")
    }
    try:
        brief = json.loads(day.morning_brief_json or "{}")
    except json.JSONDecodeError:
        brief = {}
    return DailyPlanResponse(
        business_date=day.business_date.isoformat(),
        status=day.status,
        overview=brief.get("overview") or "今天的计划已准备",
        decision_count=counts["decision"],
        auto_count=counts["auto"],
        monitor_count=counts["monitor"],
        carryover_count=counts["carryover"],
        items=[
            DailyPlanItemSummary(
                id=item.id,
                work_item_id=item.work_item_id,
                title=(
                    by_id[item.work_item_id].title
                    if item.work_item_id in by_id
                    else item.reason
                ),
                category=item.category,
                priority_score=item.priority_score,
                reason=item.reason,
                expected_action=item.expected_action,
                status=item.status,
            )
            for item in items
        ],
    )


@router.get("/bootstrap", response_model=BootstrapResponse)
async def bootstrap(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspaces = await list_user_workspaces(db, user_id=current_user.id)
    display_name = current_user.username or current_user.email.split("@", 1)[0]
    return BootstrapResponse(
        user_id=current_user.id,
        display_name=display_name,
        avatar_url=current_user.avatar_url,
        workspaces=[
            WorkspaceSummary(
                id=workspace.id,
                name=workspace.name,
                type=workspace.type,
                role=member.role,
            )
            for workspace, member in workspaces
        ],
    )


@router.post("/devices", status_code=status.HTTP_201_CREATED)
async def register_device(
    payload: DeviceRegistrationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        device = await register_mobile_device(
            db,
            user_id=current_user.id,
            expo_push_token=payload.expo_push_token,
            platform=payload.platform,
            device_name=payload.device_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": str(device.id), "status": device.status}


@router.get(
    "/workspaces/{workspace_id}/notifications",
    response_model=list[NotificationItem],
)
async def list_notifications(
    channel_type: str | None = Query(default=None),
    channel_id: str | None = Query(default=None),
    context: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    statement = select(NotificationOutbox).where(
        NotificationOutbox.workspace_id == context.workspace.id,
        NotificationOutbox.user_id == context.membership.user_id,
    )
    if channel_type and channel_id:
        statement = statement.join(
            WorkItem,
            NotificationOutbox.work_item_id == WorkItem.id,
        ).where(
            WorkItem.channel_type == channel_type,
            WorkItem.channel_id == channel_id,
        )
    notifications = (
        await db.execute(
            statement.order_by(desc(NotificationOutbox.created_at)).limit(100)
        )
    ).scalars().all()
    return [
        NotificationItem(
            id=item.id,
            notification_type=item.notification_type,
            title=item.title,
            body=item.body,
            deep_link=item.deep_link,
            work_item_id=item.work_item_id,
            status=item.status,
            created_at=item.created_at,
            read_at=item.read_at,
        )
        for item in notifications
    ]


@router.post("/workspaces/{workspace_id}/notifications/read-all")
async def mark_all_notifications_read(
    context: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """把当前用户在这个工作区的未读通知一次性标记为已读。"""

    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(NotificationOutbox)
        .where(
            NotificationOutbox.workspace_id == context.workspace.id,
            NotificationOutbox.user_id == context.membership.user_id,
            NotificationOutbox.read_at.is_(None),
        )
        .values(read_at=now)
    )
    await db.commit()
    return {"marked": int(result.rowcount or 0), "read_at": now.isoformat()}


@router.post("/workspaces/{workspace_id}/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: UUID,
    context: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """只把当前用户的一条通知标记为已读。"""

    notification = (
        await db.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.id == notification_id,
                NotificationOutbox.workspace_id == context.workspace.id,
                NotificationOutbox.user_id == context.membership.user_id,
            )
        )
    ).scalar_one_or_none()
    if notification is None:
        raise HTTPException(status_code=404, detail="通知不存在")
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        await db.commit()
    return {
        "id": str(notification.id),
        "read_at": notification.read_at.isoformat(),
    }


@router.get("/workspaces/{workspace_id}/integration-events/dead-letter")
async def list_dead_letter_events(
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin")
    ),
    db: AsyncSession = Depends(get_db),
):
    events = (
        await db.execute(
            select(IntegrationEvent)
            .where(
                IntegrationEvent.workspace_id == context.workspace.id,
                IntegrationEvent.status == "dead_letter",
            )
            .order_by(desc(IntegrationEvent.received_at))
            .limit(100)
        )
    ).scalars().all()
    return [
        {
            "id": str(event.id),
            "provider": event.provider,
            "event_type": event.event_type,
            "external_event_id": event.external_event_id,
            "attempts": event.attempts,
            "error_code": event.error_code,
            "received_at": event.received_at,
        }
        for event in events
    ]


@router.post(
    "/workspaces/{workspace_id}/integration-events/{event_id}/replay",
)
async def replay_integration_event(
    event_id: UUID,
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin")
    ),
    db: AsyncSession = Depends(get_db),
):
    try:
        event = await retry_integration_event(
            db,
            workspace_id=context.workspace.id,
            event_id=event_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"id": str(event.id), "status": event.status}


@router.get(
    "/workspaces/{workspace_id}/notification-preferences",
    response_model=NotificationPreferenceResponse,
)
async def read_notification_preferences(
    context: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    preference = await get_notification_preference(
        db,
        user_id=context.membership.user_id,
        workspace_id=context.workspace.id,
    )
    return NotificationPreferenceResponse(
        morning_brief=preference.morning_brief,
        day_closeout=preference.day_closeout,
        needs_action=preference.needs_action,
        action_failed=preference.action_failed,
        authorization_expired=preference.authorization_expired,
        quiet_start_hour=preference.quiet_start_hour,
        quiet_end_hour=preference.quiet_end_hour,
        timezone=preference.timezone,
    )


@router.put(
    "/workspaces/{workspace_id}/notification-preferences",
    response_model=NotificationPreferenceResponse,
)
async def save_notification_preferences(
    payload: NotificationPreferenceUpdate,
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin", "operator")
    ),
    db: AsyncSession = Depends(get_db),
):
    preference = await update_notification_preference(
        db,
        user_id=context.membership.user_id,
        workspace_id=context.workspace.id,
        values=payload.model_dump(exclude_none=True),
    )
    return NotificationPreferenceResponse(
        morning_brief=preference.morning_brief,
        day_closeout=preference.day_closeout,
        needs_action=preference.needs_action,
        action_failed=preference.action_failed,
        authorization_expired=preference.authorization_expired,
        quiet_start_hour=preference.quiet_start_hour,
        quiet_end_hour=preference.quiet_end_hour,
        timezone=preference.timezone,
    )


@router.post(
    "/workspaces/{workspace_id}/assets/images",
    response_model=MobileImageAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_mobile_image_asset(
    file: UploadFile = File(...),
    category: str = Form(
        default="other",
        pattern="^(product|scene|photography|other)$",
    ),
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin", "operator")
    ),
    db: AsyncSession = Depends(get_db),
):
    """上传 Agent 输入图片，并同时绑定用户和工作区。"""

    normalized, width, height = await _normalize_mobile_image(file)

    asset_id = uuid.uuid4()
    storage_key = (
        f"mobile/{context.workspace.id}/"
        f"{context.membership.user_id}/{asset_id}.webp"
    )
    target = _mobile_asset_path(storage_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(normalized)
    max_sort_order = (
        await db.execute(
            select(func.max(ImageAsset.sort_order)).where(
                ImageAsset.workspace_id == context.workspace.id,
                ImageAsset.deleted_at.is_(None),
            )
        )
    ).scalar()

    asset = ImageAsset(
        id=asset_id,
        user_id=context.membership.user_id,
        workspace_id=context.workspace.id,
        name=(Path(file.filename or "商品图片").stem or "商品图片")[:255],
        kind="upload",
        storage_key=storage_key,
        content_type="image/webp",
        width=width,
        height=height,
        file_size=len(normalized),
        category=category,
        sort_order=int(max_sort_order or 0) + 1,
        created_at=datetime.now(timezone.utc),
    )
    db.add(asset)
    await db.flush()
    return _mobile_image_response(
        asset,
        workspace_id=context.workspace.id,
    )


@router.post(
    "/workspaces/{workspace_id}/assets/images/{asset_id}/public-url",
    response_model=PublicImageAssetResponse,
)
async def publish_mobile_image_public_url(
    asset_id: UUID,
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin", "operator")
    ),
    db: AsyncSession = Depends(get_db),
):
    """把工作区图片显式发布到公共 CDN/S3，返回持久 HTTPS URL。"""

    asset = (
        await db.execute(
            select(ImageAsset).where(
                ImageAsset.id == asset_id,
                ImageAsset.workspace_id == context.workspace.id,
                ImageAsset.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    try:
        public_url = await publish_public_image_asset(asset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return PublicImageAssetResponse(
        asset_id=asset.id,
        public_url=public_url,
    )


@router.get(
    "/workspaces/{workspace_id}/assets/images",
    response_model=list[MobileImageAssetResponse],
)
async def list_mobile_image_assets(
    category: str | None = Query(
        default=None,
        pattern="^(product|scene|photography|other)$",
    ),
    context: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """按卖家自定义顺序读取当前工作区素材库，可按分类筛选。"""

    filters = [
        ImageAsset.workspace_id == context.workspace.id,
        ImageAsset.deleted_at.is_(None),
    ]
    if category:
        filters.append(ImageAsset.category == category)
    assets = (
        await db.execute(
            select(ImageAsset)
            .where(*filters)
            .order_by(ImageAsset.sort_order, ImageAsset.created_at.desc())
            .limit(200)
        )
    ).scalars().all()
    return [
        _mobile_image_response(
            asset,
            workspace_id=context.workspace.id,
        )
        for asset in assets
    ]


@router.patch(
    "/workspaces/{workspace_id}/assets/images/{asset_id}/category",
    response_model=MobileImageAssetResponse,
)
async def update_mobile_image_asset_category(
    asset_id: UUID,
    payload: ImageAssetCategoryRequest,
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin", "operator")
    ),
    db: AsyncSession = Depends(get_db),
):
    """按用户选择改素材分类；不做内容识别猜测。"""

    asset = (
        await db.execute(
            select(ImageAsset).where(
                ImageAsset.id == asset_id,
                ImageAsset.workspace_id == context.workspace.id,
                ImageAsset.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    asset.category = payload.category
    asset.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(asset)
    return _mobile_image_response(asset, workspace_id=context.workspace.id)


@router.put(
    "/workspaces/{workspace_id}/assets/images/reorder",
    response_model=list[MobileImageAssetResponse],
)
async def reorder_mobile_image_assets(
    payload: ImageAssetReorderRequest,
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin", "operator")
    ),
    db: AsyncSession = Depends(get_db),
):
    """只重排明确列出的素材；未列出的素材保持原位。"""

    if len(set(payload.asset_ids)) != len(payload.asset_ids):
        raise HTTPException(status_code=422, detail="素材顺序中存在重复图片")
    assets = (
        await db.execute(
            select(ImageAsset).where(
                ImageAsset.workspace_id == context.workspace.id,
                ImageAsset.deleted_at.is_(None),
                ImageAsset.id.in_(payload.asset_ids),
            )
        )
    ).scalars().all()
    by_id = {asset.id: asset for asset in assets}
    if len(by_id) != len(payload.asset_ids):
        raise HTTPException(status_code=404, detail="部分素材不存在")
    for index, asset_id in enumerate(payload.asset_ids, start=1):
        by_id[asset_id].sort_order = index
        by_id[asset_id].updated_at = datetime.now(timezone.utc)
    await db.flush()
    return [
        _mobile_image_response(
            by_id[asset_id],
            workspace_id=context.workspace.id,
        )
        for asset_id in payload.asset_ids
    ]


@router.post(
    "/workspaces/{workspace_id}/assets/images/{asset_id}/replace",
    response_model=MobileImageAssetResponse,
)
async def replace_mobile_image_asset(
    asset_id: UUID,
    file: UploadFile = File(...),
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin", "operator")
    ),
    db: AsyncSession = Depends(get_db),
):
    """替换图片内容但保留素材编号，避免已引用位置失效。"""

    asset = (
        await db.execute(
            select(ImageAsset).where(
                ImageAsset.id == asset_id,
                ImageAsset.workspace_id == context.workspace.id,
                ImageAsset.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    normalized, width, height = await _normalize_mobile_image(file)
    replacement_key = (
        f"mobile/{context.workspace.id}/"
        f"{context.membership.user_id}/{uuid.uuid4()}.webp"
    )
    target = _mobile_asset_path(replacement_key)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(normalized)
    old_path = _mobile_asset_path(asset.storage_key)
    asset.storage_key = replacement_key
    asset.name = (Path(file.filename or "商品图片").stem or "商品图片")[:255]
    asset.content_type = "image/webp"
    asset.width = width
    asset.height = height
    asset.file_size = len(normalized)
    asset.updated_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        target.unlink(missing_ok=True)
        raise
    # 新记录提交后才删除旧文件，避免数据库失败时素材彻底丢失。
    if old_path != target:
        old_path.unlink(missing_ok=True)
    await db.refresh(asset)
    return _mobile_image_response(
        asset,
        workspace_id=context.workspace.id,
    )


@router.delete("/workspaces/{workspace_id}/assets/images/{asset_id}")
async def delete_mobile_image_asset(
    asset_id: UUID,
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin", "operator")
    ),
    db: AsyncSession = Depends(get_db),
):
    """从素材库移除图片，但保留文件和编号供历史 Listing 继续引用。"""

    asset = (
        await db.execute(
            select(ImageAsset).where(
                ImageAsset.id == asset_id,
                ImageAsset.workspace_id == context.workspace.id,
                ImageAsset.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    asset.deleted_at = datetime.now(timezone.utc)
    asset.updated_at = asset.deleted_at
    await db.flush()
    return {"deleted": True}


@router.get("/workspaces/{workspace_id}/assets/images/{asset_id}/file")
async def get_mobile_image_asset_file(
    asset_id: UUID,
    delivery_format: str = Query(
        "original",
        alias="format",
        pattern="^(original|jpeg)$",
    ),
    context: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """私有素材文件只允许当前工作区成员读取。"""

    asset = (
        await db.execute(
            select(ImageAsset).where(
                ImageAsset.id == asset_id,
                ImageAsset.workspace_id == context.workspace.id,
            )
        )
    ).scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    try:
        path = _mobile_asset_path(asset.storage_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="素材文件不存在") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="素材文件不存在")
    if delivery_format == "jpeg":
        delivery = await run_in_threadpool(_mobile_jpeg_path, path)
        return FileResponse(
            delivery,
            media_type="image/jpeg",
            headers={
                "Content-Disposition": f'inline; filename="asset-{asset.id}.jpg"',
                "Cache-Control": "private, max-age=3600",
            },
        )
    return FileResponse(
        path,
        media_type=asset.content_type,
        headers={
            "Content-Disposition": f'inline; filename="asset-{asset.id}.webp"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.post(
    "/workspaces/{workspace_id}/audio/transcriptions",
    response_model=MobileVoiceTranscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def transcribe_mobile_voice(
    file: UploadFile = File(...),
    duration_ms: int = Form(default=0),
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=8,
    ),
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin", "operator")
    ),
    db: AsyncSession = Depends(get_db),
):
    """上传短语音并同步转写，返回可提交给 Agent 的私有素材。"""

    if duration_ms < 0 or duration_ms > 120_000:
        raise HTTPException(status_code=400, detail="语音时长必须在 2 分钟以内")
    raw = await file.read(settings.MAX_AUDIO_UPLOAD_BYTES + 1)
    if not raw:
        raise HTTPException(status_code=400, detail="没有收到有效语音")
    if len(raw) > settings.MAX_AUDIO_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="语音文件过大")

    content_type = (file.content_type or "").split(";", 1)[0].lower().strip()
    extension = AUDIO_CONTENT_TYPES.get(content_type)
    if extension is None:
        raise HTTPException(status_code=400, detail="不支持的语音格式")
    _validate_audio_signature(raw, content_type)
    digest = hashlib.sha256(raw).hexdigest()
    existing = (
        await db.execute(
            select(AudioAsset).where(
                AudioAsset.workspace_id == context.workspace.id,
                AudioAsset.user_id == context.membership.user_id,
                AudioAsset.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.sha256 != digest:
            raise HTTPException(
                status_code=409,
                detail="相同幂等键对应不同语音",
            )
        return MobileVoiceTranscriptionResponse(
            asset_id=existing.id,
            transcript=existing.transcript,
            language=existing.detected_language,
            duration_ms=existing.duration_ms,
            expires_at=existing.expires_at,
            provider=existing.provider,
            model=existing.model,
        )

    try:
        transcription = await transcribe_mobile_audio(
            audio=raw,
            content_type=content_type,
            filename=file.filename or f"voice.{extension}",
        )
    except SpeechTranscriptionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    asset_id = uuid.uuid4()
    relative_key = (
        f"mobile/{context.workspace.id}/"
        f"{context.membership.user_id}/{asset_id}.{extension}"
    )
    prefix = settings.AUDIO_OBJECT_PREFIX.strip("/")
    storage_key = f"{prefix}/{relative_key}" if prefix else relative_key
    try:
        audio_storage = await asyncio.to_thread(get_audio_storage)
        await audio_storage.put_bytes(
            storage_key,
            raw,
            content_type=content_type,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="语音存储暂时不可用",
        ) from exc
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=max(settings.AUDIO_RETENTION_HOURS, 1))
    safe_name = Path(
        (file.filename or "voice").replace("\\", "/")
    ).name or "voice"
    asset = AudioAsset(
        id=asset_id,
        user_id=context.membership.user_id,
        workspace_id=context.workspace.id,
        original_name=safe_name[:255],
        storage_key=storage_key,
        content_type=content_type,
        duration_ms=duration_ms,
        file_size=len(raw),
        sha256=digest,
        transcript=transcription.transcript,
        detected_language=transcription.language,
        provider=transcription.provider,
        model=transcription.model,
        status="ready",
        idempotency_key=idempotency_key,
        expires_at=expires_at,
        created_at=now,
        updated_at=now,
    )
    db.add(asset)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        try:
            await audio_storage.delete(storage_key)
        except (RuntimeError, ValueError):
            pass
        existing = (
            await db.execute(
                select(AudioAsset).where(
                    AudioAsset.workspace_id == context.workspace.id,
                    AudioAsset.user_id == context.membership.user_id,
                    AudioAsset.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is None or existing.sha256 != digest:
            raise HTTPException(
                status_code=409,
                detail="语音上传发生冲突，请重新录制",
            ) from exc
        return MobileVoiceTranscriptionResponse(
            asset_id=existing.id,
            transcript=existing.transcript,
            language=existing.detected_language,
            duration_ms=existing.duration_ms,
            expires_at=existing.expires_at,
            provider=existing.provider,
            model=existing.model,
        )
    return MobileVoiceTranscriptionResponse(
        asset_id=asset.id,
        transcript=asset.transcript,
        language=asset.detected_language,
        duration_ms=asset.duration_ms,
        expires_at=asset.expires_at,
        provider=asset.provider,
        model=asset.model,
    )


@router.get("/media/video/{task_id}/file")
async def get_mobile_video_file(
    task_id: UUID,
    access_token: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """通过短期签名 URL 提供视频预览，不在系统播放器里暴露长期登录令牌。"""

    payload = decode_token_safe(access_token or "")
    if not payload or payload.get("scope") != "video_file":
        raise HTTPException(status_code=401, detail="视频访问已失效")
    task = await db.get(VideoGenerationTask, task_id)
    if (
        task is None
        or str(task.user_id) != str(payload.get("sub"))
        or task.status != "succeeded"
        or not task.storage_key
    ):
        raise HTTPException(status_code=404, detail="视频不存在")
    base = Path(settings.VIDEO_STORAGE_DIR).resolve()
    path = (base / task.storage_key).resolve()
    if path != base and base not in path.parents:
        raise HTTPException(status_code=404, detail="视频不存在")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="视频不存在")
    return FileResponse(
        path,
        media_type=task.mime or "video/mp4",
        filename=f"veyaship-{task.id}.mp4",
    )


@router.post(
    "/workspaces/{workspace_id}/customer-channels",
    response_model=CustomerChannelSummary,
    status_code=status.HTTP_201_CREATED,
)
async def create_customer_channel(
    payload: CustomerChannelCreateRequest,
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin")
    ),
    db: AsyncSession = Depends(get_db),
):
    """保存客服渠道凭据；接口只返回渠道摘要，不回传密码。"""

    credentials = payload.credentials
    if payload.provider == "judge_me":
        try:
            credentials = normalize_judge_me_credentials(credentials)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    channel = CustomerChannel(
        workspace_id=context.workspace.id,
        created_by_user_id=context.membership.user_id,
        provider=payload.provider,
        external_account_id=payload.external_account_id.strip().lower(),
        display_name=payload.display_name.strip(),
        credentials_ciphertext=encrypt_value(
            json.dumps(credentials, ensure_ascii=False)
        ),
        status="active",
    )
    db.add(channel)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="该客服渠道已经绑定到当前工作区",
        ) from exc
    return CustomerChannelSummary(
        id=channel.id,
        provider=channel.provider,
        external_account_id=channel.external_account_id,
        display_name=channel.display_name,
        status=channel.status,
    )


@router.get(
    "/workspaces/{workspace_id}/customer-channels",
    response_model=list[CustomerChannelSummary],
)
async def list_customer_channels(
    context: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    channels = (
        await db.execute(
            select(CustomerChannel)
            .where(
                CustomerChannel.workspace_id == context.workspace.id,
            )
            .order_by(CustomerChannel.created_at, CustomerChannel.id)
        )
    ).scalars().all()
    return [
        CustomerChannelSummary(
            id=channel.id,
            provider=channel.provider,
            external_account_id=channel.external_account_id,
            display_name=channel.display_name,
            status=channel.status,
        )
        for channel in channels
    ]


@router.get(
    "/workspaces/{workspace_id}/agent-control",
    response_model=AgentControlResponse,
)
async def get_agent_control(
    context: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """返回 App 需要的暂停状态和已有自主策略。"""

    policies = (
        await db.execute(
            select(AgentAutonomyPolicy)
            .where(
                AgentAutonomyPolicy.workspace_id == context.workspace.id
            )
            .order_by(
                AgentAutonomyPolicy.action_id,
                AgentAutonomyPolicy.id,
            )
        )
    ).scalars().all()
    return AgentControlResponse(
        paused=workspace_is_paused(context.workspace),
        policies=[_agent_policy_summary(policy) for policy in policies],
    )


@router.patch(
    "/workspaces/{workspace_id}/agent-control",
    response_model=AgentControlResponse,
)
async def update_agent_control(
    payload: AgentControlUpdateRequest,
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin")
    ),
    db: AsyncSession = Depends(get_db),
):
    """暂停或恢复 Agent；暂停会冻结尚未执行的自动动作。"""

    workspace, frozen = await set_agent_paused(
        db,
        workspace_id=context.workspace.id,
        actor_user_id=context.membership.user_id,
        paused=payload.paused,
    )
    policies = (
        await db.execute(
            select(AgentAutonomyPolicy)
            .where(
                AgentAutonomyPolicy.workspace_id == context.workspace.id
            )
            .order_by(AgentAutonomyPolicy.action_id)
        )
    ).scalars().all()
    return AgentControlResponse(
        paused=workspace_is_paused(workspace),
        frozen_action_count=frozen,
        policies=[_agent_policy_summary(policy) for policy in policies],
    )


@router.put(
    "/workspaces/{workspace_id}/agent-control/policies/{action_id}",
    response_model=AgentPolicySummary,
)
async def upsert_agent_policy(
    action_id: str,
    payload: AgentPolicyUpsertRequest,
    context: WorkspaceContext = Depends(
        require_workspace_role("owner")
    ),
    db: AsyncSession = Depends(get_db),
):
    """保存有限的确定性规则，不允许模型自行扩大授权。"""

    try:
        definition = get_action_definition(action_id)
        conditions = normalize_conditions(payload.conditions)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    policy = (
        await db.execute(
            select(AgentAutonomyPolicy).where(
                AgentAutonomyPolicy.workspace_id == context.workspace.id,
                AgentAutonomyPolicy.action_id == action_id,
            )
        )
    ).scalar_one_or_none()
    before = {}
    if policy is None:
        policy = AgentAutonomyPolicy(
            workspace_id=context.workspace.id,
            action_id=action_id,
            autonomy_level=payload.autonomy_level,
            conditions_json=json.dumps(
                conditions,
                ensure_ascii=False,
                sort_keys=True,
            ),
            enabled=payload.enabled,
            version=1,
            created_by_user_id=context.membership.user_id,
        )
        db.add(policy)
    else:
        before = {
            "autonomy_level": policy.autonomy_level,
            "conditions": _agent_policy_summary(policy).conditions,
            "enabled": policy.enabled,
        }
        policy.autonomy_level = payload.autonomy_level
        policy.conditions_json = json.dumps(
            conditions,
            ensure_ascii=False,
            sort_keys=True,
        )
        policy.enabled = payload.enabled
        policy.version += 1
    await db.flush()
    db.add(
        WorkspaceAuditLog(
            workspace_id=context.workspace.id,
            actor_user_id=context.membership.user_id,
            action="agent.policy.upsert",
            resource_type="agent_autonomy_policy",
            resource_id=str(policy.id),
            before_json=json.dumps(before, ensure_ascii=False),
            after_json=json.dumps(
                {
                    "action_id": action_id,
                    "platform": definition.platform,
                    "autonomy_level": payload.autonomy_level,
                    "conditions": conditions,
                    "enabled": payload.enabled,
                    "version": policy.version,
                },
                ensure_ascii=False,
            ),
        )
    )
    return _agent_policy_summary(policy)


@router.delete(
    "/workspaces/{workspace_id}/agent-control/policies/{action_id}",
)
async def delete_agent_policy(
    action_id: str,
    context: WorkspaceContext = Depends(
        require_workspace_role("owner")
    ),
    db: AsyncSession = Depends(get_db),
):
    """删除自定义策略并恢复动作默认的保守级别。"""

    policy = (
        await db.execute(
            select(AgentAutonomyPolicy).where(
                AgentAutonomyPolicy.workspace_id == context.workspace.id,
                AgentAutonomyPolicy.action_id == action_id,
            )
        )
    ).scalar_one_or_none()
    if policy is None:
        raise HTTPException(status_code=404, detail="自主策略不存在")
    policy_id = policy.id
    before = {
        "autonomy_level": policy.autonomy_level,
        "conditions": _agent_policy_summary(policy).conditions,
        "enabled": policy.enabled,
        "version": policy.version,
    }
    await db.delete(policy)
    db.add(
        WorkspaceAuditLog(
            workspace_id=context.workspace.id,
            actor_user_id=context.membership.user_id,
            action="agent.policy.delete",
            resource_type="agent_autonomy_policy",
            resource_id=str(policy_id),
            before_json=json.dumps(before, ensure_ascii=False),
            after_json=None,
        )
    )
    return {"deleted": True}


@router.post(
    "/workspaces/{workspace_id}/customer-channels/{channel_id}/sync",
)
async def sync_customer_channel(
    channel_id: UUID,
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin", "operator")
    ),
    db: AsyncSession = Depends(get_db),
):
    channel = (
        await db.execute(
            select(CustomerChannel).where(
                CustomerChannel.id == channel_id,
                CustomerChannel.workspace_id == context.workspace.id,
            )
        )
    ).scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=404, detail="客服渠道不存在")
    if channel.provider == "judge_me":
        return await sync_judge_me_reviews(db, channel=channel)
    return await sync_customer_inbox(db, channel=channel)


@router.post(
    "/workspaces/{workspace_id}/customer-threads/{thread_id}/reply-drafts",
    response_model=ReplyDraftResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_reply_draft(
    thread_id: UUID,
    payload: ReplyDraftRequest,
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin", "operator")
    ),
    db: AsyncSession = Depends(get_db),
):
    thread = (
        await db.execute(
            select(CustomerThread).where(
                CustomerThread.workspace_id == context.workspace.id,
                CustomerThread.id == thread_id,
            )
        )
    ).scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=404, detail="客户会话不存在")
    latest_inbound = (
        await db.execute(
            select(CustomerMessage)
            .where(
                CustomerMessage.workspace_id == context.workspace.id,
                CustomerMessage.thread_id == thread.id,
                CustomerMessage.direction == "inbound",
            )
            .order_by(desc(CustomerMessage.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    if payload.mode == "translate":
        if not payload.seller_instruction:
            raise HTTPException(status_code=422, detail="请填写中文回复指令")
        draft = await create_translated_reply_draft(
            db,
            workspace_id=context.workspace.id,
            thread_id=thread.id,
            seller_instruction=payload.seller_instruction,
            customer_message=(
                latest_inbound.body_text if latest_inbound else ""
            ),
            target_language=payload.target_language,
            language=payload.language,
        )
    else:
        body_text = (payload.body_text or "").strip()
        if not body_text:
            raise HTTPException(status_code=422, detail="回复正文不能为空")
        draft = await create_reply_draft(
            db,
            workspace_id=context.workspace.id,
            thread_id=thread.id,
            body_text=body_text,
            language=payload.language or thread.language,
            source_language=detect_language(body_text),
            risk_level="medium",
        )
    # 修改草稿后同步更新尚未执行的回复动作，避免确认时仍发送旧版本。
    pending_actions = (
        await db.execute(
            select(ActionRun)
            .where(
                ActionRun.workspace_id == context.workspace.id,
                ActionRun.target_id == str(thread.id),
                ActionRun.action_id.in_(
                    [
                        "messages.reply",
                        "orders.delay_notice",
                        "reviews.reply",
                    ]
                ),
                ActionRun.status.in_(["planned", "awaiting_confirmation"]),
            )
            .order_by(desc(ActionRun.created_at))
        )
    ).scalars().all()
    for action in pending_actions:
        try:
            action_input = json.loads(action.input_json or "{}")
        except json.JSONDecodeError:
            action_input = {}
        action_input["draft_id"] = str(draft.id)
        action.input_json = json.dumps(action_input, ensure_ascii=False)
        action.version += 1
    return ReplyDraftResponse(
        id=draft.id,
        thread_id=draft.thread_id,
        version=draft.version,
        language=draft.language,
        source_language=draft.source_language,
        body_text=draft.body_text,
        status=draft.status,
    )


@router.get(
    "/workspaces/{workspace_id}/customer-attachments/{attachment_id}/file",
)
async def get_customer_attachment_file(
    attachment_id: UUID,
    context: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """客户附件只允许当前工作区成员通过鉴权接口读取。"""

    attachment = (
        await db.execute(
            select(CustomerAttachment).where(
                CustomerAttachment.id == attachment_id,
                CustomerAttachment.workspace_id == context.workspace.id,
            )
        )
    ).scalar_one_or_none()
    if attachment is None:
        raise HTTPException(status_code=404, detail="附件不存在")
    try:
        data = await get_audio_storage().get_bytes(
            attachment.storage_key
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail="附件文件不存在") from exc
    safe_name = attachment.file_name.replace('"', "")
    return Response(
        content=data,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.post(
    "/workspaces/{workspace_id}/customer-threads/{thread_id}/takeover",
    response_model=CustomerTakeoverResponse,
)
async def take_over_customer_thread(
    thread_id: UUID,
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin", "operator")
    ),
    db: AsyncSession = Depends(get_db),
):
    """高风险会话交给真实成员后，Agent 停止自动回复。"""

    thread = (
        await db.execute(
            select(CustomerThread).where(
                CustomerThread.id == thread_id,
                CustomerThread.workspace_id == context.workspace.id,
            )
        )
    ).scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=404, detail="客户会话不存在")
    thread.assigned_user_id = context.membership.user_id
    thread.status = "waiting_user"
    thread.priority = "urgent"

    item = (
        await db.execute(
            select(WorkItem)
            .where(
                WorkItem.workspace_id == context.workspace.id,
                WorkItem.source_type == "customer_thread",
                WorkItem.source_id == str(thread.id),
            )
            .order_by(desc(WorkItem.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if item is not None:
        try:
            result = json.loads(item.result_json or "{}")
        except json.JSONDecodeError:
            result = {}
        result.update(
            {
                "manual_takeover": True,
                "assigned_user_id": str(context.membership.user_id),
            }
        )
        item.assignee_user_id = context.membership.user_id
        item.status = "waiting_user"
        item.priority = "urgent"
        item.requires_action = "none"
        item.current_step = "你已接管，Agent 暂停自动回复"
        item.result_json = json.dumps(result, ensure_ascii=False)
        item.version += 1
        db.add(
            WorkItemEvent(
                workspace_id=context.workspace.id,
                work_item_id=item.id,
                event_type="customer_thread.takeover",
                actor_user_id=context.membership.user_id,
                payload_json=json.dumps(
                    {
                        "thread_id": str(thread.id),
                        "assigned_user_id": str(
                            context.membership.user_id
                        ),
                    },
                    ensure_ascii=False,
                ),
            )
        )
    await db.flush()
    return CustomerTakeoverResponse(
        thread_id=thread.id,
        assigned_user_id=context.membership.user_id,
        assigned_to_me=True,
        status=thread.status,
        priority=thread.priority,
    )


@router.post(
    "/workspaces/{workspace_id}/customer-threads/{thread_id}/orders/link",
    response_model=CustomerOrderSelectionResponse,
)
async def select_customer_thread_order(
    thread_id: UUID,
    payload: CustomerOrderLinkRequest,
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin", "operator")
    ),
    db: AsyncSession = Depends(get_db),
):
    """卖家重新校验并选择唯一订单，旧草稿和动作同时失效。"""

    thread = (
        await db.execute(
            select(CustomerThread).where(
                CustomerThread.id == thread_id,
                CustomerThread.workspace_id == context.workspace.id,
            )
        )
    ).scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=404, detail="客户会话不存在")
    item = (
        await db.execute(
            select(WorkItem)
            .where(
                WorkItem.workspace_id == context.workspace.id,
                WorkItem.kind == "customer_reply",
                WorkItem.source_type == "customer_thread",
                WorkItem.source_id == str(thread.id),
            )
            .order_by(desc(WorkItem.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="客户回复任务不存在")
    try:
        resolution = await apply_customer_order_selection(
            db,
            workspace_id=context.workspace.id,
            thread=thread,
            work_item=item,
            shopify_channel_id=payload.shopify_channel_id,
            external_order_id=payload.external_order_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if resolution.status != "linked":
        raise HTTPException(
            status_code=409,
            detail="所选订单已变化，请刷新候选订单后重试",
        )
    link = (
        await db.execute(
            select(CustomerOrderLink).where(
                CustomerOrderLink.workspace_id == context.workspace.id,
                CustomerOrderLink.thread_id == thread.id,
            )
        )
    ).scalar_one()
    return CustomerOrderSelectionResponse(
        status=resolution.status,
        order=CustomerOrderContext(
            order_name=link.order_name,
            financial_status=link.financial_status,
            fulfillment_status=link.fulfillment_status,
            tracking_company=link.tracking_company,
            tracking_number=link.tracking_number,
            tracking_url=link.tracking_url,
        ),
        work_item_status=item.status,
        requires_action=item.requires_action,
    )


def _timeline_commerce(raw: str | None) -> TimelineCommerce | None:
    """从工作项的 result_json 取交易事实（金额、订单数、缩略图）。

    只认结构化的 commerce 子树，不从 summary 里正则抠金额：文案改一个字
    就会静默失效，宁可返回 None 让前端不渲染，也不要显示错的数字。
    """
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    value = data.get("commerce")
    if not isinstance(value, dict):
        return None

    amount = value.get("amount")
    amount = str(amount).strip() if amount is not None else ""
    currency = value.get("currency")
    currency = str(currency).strip().upper() if currency else ""

    try:
        order_count = (
            int(value["order_count"]) if value.get("order_count") is not None else None
        )
    except (TypeError, ValueError, KeyError):
        order_count = None

    raw_thumbs = value.get("thumbnails")
    thumbnails = [
        str(item).strip()
        for item in (raw_thumbs if isinstance(raw_thumbs, list) else [])
        if isinstance(item, str)
        and str(item).strip().startswith(("http://", "https://"))
    ][:3]

    if not amount and not thumbnails and order_count is None:
        return None

    return TimelineCommerce(
        amount=amount or None,
        currency=currency or None,
        order_count=order_count,
        thumbnails=thumbnails,
    )


@router.get(
    "/workspaces/{workspace_id}/timeline",
    response_model=TimelineResponse,
)
async def get_timeline(
    business_date: date | None = Query(default=None, alias="date"),
    timezone_name: str = Query(default="Asia/Shanghai", alias="timezone"),
    channel_type: str | None = Query(default=None),
    channel_id: str | None = Query(default=None),
    _context: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    selected_date = business_date or business_date_in_timezone(timezone_name)
    items = await list_work_items_for_date(
        db,
        workspace_id=_context.workspace.id,
        business_date=selected_date,
        timezone_name=timezone_name,
        channel_type=channel_type,
        channel_id=channel_id,
    )
    return TimelineResponse(
        business_date=selected_date.isoformat(),
        items=[
            TimelineItem(
                id=item.id,
                kind=item.kind,
                title=item.title,
                summary=item.summary,
                status=item.status,
                priority=item.priority,
                current_step=item.current_step,
                requires_action=item.requires_action,
                version=item.version,
                due_at=item.due_at,
                occurred_at=item.created_at,
                commerce=_timeline_commerce(item.result_json),
            )
            for item in items
        ],
    )


@router.get(
    "/workspaces/{workspace_id}/commerce-stores",
    response_model=list[CommerceStoreSummary],
)
async def list_commerce_stores(
    context: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """返回当前工作区可筛选店铺，只下发非敏感连接元信息。"""

    shopify_channels = (
        await db.execute(
            select(ShopifyChannel)
            .where(
                ShopifyChannel.workspace_id == context.workspace.id,
                ShopifyChannel.is_active.is_(True),
            )
            .order_by(ShopifyChannel.shop_name)
        )
    ).scalars().all()
    # 旧平台连接仍按用户存储，没有工作区字段；只在个人所有者场景展示，
    # 避免把同用户的 Amazon/Temu 连接泄漏到团队工作区筛选器。
    if (
        context.workspace.type == "personal"
        and context.membership.user_id == context.workspace.owner_user_id
    ):
        platform_channels = (
            await db.execute(
                select(PlatformConnection)
                .where(
                    PlatformConnection.user_id
                    == context.workspace.owner_user_id,
                    PlatformConnection.platform.in_(("amazon", "temu")),
                    PlatformConnection.status == "active",
                )
                .order_by(
                    PlatformConnection.platform,
                    PlatformConnection.account_name,
                )
            )
        ).scalars().all()
    else:
        platform_channels = []
    stores = [
        CommerceStoreSummary(
            channel_type="shopify",
            channel_id=str(channel.id),
            name=channel.shop_name.replace(".myshopify.com", ""),
            status="active" if channel.is_active else "inactive",
        )
        for channel in shopify_channels
    ]
    stores.extend(
        CommerceStoreSummary(
            channel_type=connection.platform,
            channel_id=str(connection.id),
            name=connection.account_name,
            status=connection.status,
        )
        for connection in platform_channels
    )
    return stores


@router.get(
    "/workspaces/{workspace_id}/daily-plan",
    response_model=DailyPlanResponse,
)
async def get_workspace_daily_plan(
    business_date: date | None = Query(default=None, alias="date"),
    timezone_name: str = Query(default="Asia/Shanghai", alias="timezone"),
    channel_type: str | None = Query(default=None),
    channel_id: str | None = Query(default=None),
    context: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    selected_date = business_date or _date_in_timezone(timezone_name)
    day = await get_agent_day(
        db,
        workspace_id=context.workspace.id,
        business_date=selected_date,
    )
    if day is None:
        day = await build_daily_plan(
            db,
            workspace_id=context.workspace.id,
            business_date=selected_date,
            timezone_name=timezone_name,
        )
    items = await get_daily_plan(
        db,
        workspace_id=context.workspace.id,
        business_date=selected_date,
    )
    if channel_type and channel_id:
        work_items = (
            await db.execute(
                select(WorkItem.id).where(
                    WorkItem.workspace_id == context.workspace.id,
                    WorkItem.channel_type == channel_type,
                    WorkItem.channel_id == channel_id,
                )
            )
        ).scalars().all()
        allowed = set(work_items)
        items = [item for item in items if item.work_item_id in allowed]
    return await _daily_plan_response(
        db,
        workspace_id=context.workspace.id,
        day=day,
        items=items,
    )


@router.post(
    "/workspaces/{workspace_id}/daily-plan/close",
    response_model=DailyPlanResponse,
)
async def close_workspace_daily_plan(
    business_date: date | None = Query(default=None, alias="date"),
    timezone_name: str = Query(default="Asia/Shanghai", alias="timezone"),
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin", "operator")
    ),
    db: AsyncSession = Depends(get_db),
):
    selected_date = business_date or _date_in_timezone(timezone_name)
    day = await get_agent_day(
        db,
        workspace_id=context.workspace.id,
        business_date=selected_date,
    )
    if day is None:
        day = await build_daily_plan(
            db,
            workspace_id=context.workspace.id,
            business_date=selected_date,
            timezone_name=timezone_name,
        )
    day = await close_daily_plan(
        db,
        workspace_id=context.workspace.id,
        business_date=selected_date,
    )
    items = await get_daily_plan(
        db,
        workspace_id=context.workspace.id,
        business_date=selected_date,
    )
    return await _daily_plan_response(
        db,
        workspace_id=context.workspace.id,
        day=day,
        items=items,
    )


@router.get("/workspaces/{workspace_id}/stream")
async def stream_events(
    cursor: int = Query(default=0, ge=0),
    once: bool = Query(default=False),
    _context: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """用 SSE 推送工作区变更，客户端按 event_id 断线续传。"""

    return StreamingResponse(
        stream_workspace_events(
            db,
            workspace_id=_context.workspace.id,
            cursor=cursor,
            once=once,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/workspaces/{workspace_id}/work-items/{work_item_id}",
    response_model=WorkItemDetailResponse,
)
async def get_work_item_detail(
    work_item_id: UUID,
    _context: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    item = await get_work_item(
        db,
        workspace_id=_context.workspace.id,
        work_item_id=work_item_id,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="工作项不存在")
    action_runs = await list_action_runs_for_work_item(
        db,
        workspace_id=_context.workspace.id,
        work_item_id=work_item_id,
    )
    action_preview = build_action_preview(
        action_runs[-1] if action_runs else None,
        fallback_title=item.title,
    )
    customer_context = await _customer_context(
        db,
        item,
        viewer_user_id=_context.membership.user_id,
    )
    media_result = await _media_result(
        db,
        item=item,
        workspace_owner_id=_context.workspace.owner_user_id,
        viewer_user_id=_context.membership.user_id,
    )
    return WorkItemDetailResponse(
        id=item.id,
        version=item.version,
        kind=item.kind,
        title=item.title,
        summary=item.summary,
        status=item.status,
        priority=item.priority,
        current_step=item.current_step,
        requires_action=item.requires_action,
        available_actions=_available_actions(item),
        action_runs=[
            ActionRunSummary(
                id=run.id,
                action_id=run.action_id,
                platform=run.platform,
                target_type=run.target_type,
                target_id=run.target_id,
                status=run.status,
                risk_level=run.risk_level,
                autonomy_level=run.autonomy_level,
                policy_reason=_action_policy_snapshot(run).get("reason"),
                requires_dual_approval=bool(
                    _action_policy_snapshot(run).get(
                        "requires_dual_approval"
                    )
                ),
                attempt=run.attempt,
                external_id=run.external_id,
                error_code=run.error_code,
                created_at=run.created_at,
                started_at=run.started_at,
                finished_at=run.finished_at,
            )
            for run in action_runs
        ],
        action_preview=action_preview,
        result=_result_object(item.result_json),
        customer_context=customer_context,
        media_result=media_result,
        due_at=item.due_at,
        expires_at=item.expires_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post(
    "/workspaces/{workspace_id}/work-items/{work_item_id}/media/save-to-library",
    response_model=MobileMediaSaveResponse,
)
async def save_generated_media_to_library(
    work_item_id: UUID,
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin", "operator")
    ),
    db: AsyncSession = Depends(get_db),
):
    """把已完成图片任务的变体幂等写入当前工作区素材库。"""

    item = await get_work_item(
        db,
        workspace_id=context.workspace.id,
        work_item_id=work_item_id,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="工作项不存在")
    result = _result_object(item.result_json)
    if result is None or result.get("media_type") != "image":
        raise HTTPException(status_code=422, detail="当前任务不是图片素材")
    try:
        task_id = UUID(str(result.get("task_id") or ""))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="图片任务编号无效") from None
    task = await db.get(ImageGenerationTask, task_id)
    if task is None or task.workspace_id != context.workspace.id:
        raise HTTPException(status_code=404, detail="图片任务不存在")
    if task.user_id not in {
        context.workspace.owner_user_id,
        context.membership.user_id,
    }:
        raise HTTPException(status_code=403, detail="无权保存该图片任务")
    if task.status != "completed":
        raise HTTPException(status_code=409, detail="图片任务尚未完成")
    try:
        image_urls = json.loads(task.image_urls or "[]")
    except (TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="图片结果格式不正确") from None
    if not isinstance(image_urls, list) or not image_urls:
        raise HTTPException(status_code=422, detail="图片任务没有可保存的结果")

    assets = await materialize_image_task_assets(
        db,
        user_id=task.user_id or context.membership.user_id,
        workspace_id=context.workspace.id,
        task_id=task.id,
        prompt=task.prompt,
        image_urls=[str(url) for url in image_urls if str(url).strip()],
    )
    await db.commit()
    return MobileMediaSaveResponse(
        asset_ids=[asset.id for asset in assets],
    )


@router.post(
    "/workspaces/{workspace_id}/work-items/{work_item_id}/media/regenerate",
    response_model=MediaRegenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def regenerate_media_with_user_input(
    work_item_id: UUID,
    payload: MediaRegenerateRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8),
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin", "operator")
    ),
    db: AsyncSession = Depends(get_db),
):
    """基于新描述和参考图创建新图片动作，不覆盖历史结果。"""

    existing = (
        await db.execute(
            select(ActionRun).where(
                ActionRun.workspace_id == context.workspace.id,
                ActionRun.action_id == "media.generate_image",
                ActionRun.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        item = await get_work_item(
            db,
            workspace_id=context.workspace.id,
            work_item_id=existing.work_item_id,
        )
        return MediaRegenerateResponse(
            action_run_id=existing.id,
            status=existing.status,
            work_item_version=item.version if item else payload.expected_version,
        )

    item = await get_work_item(
        db,
        workspace_id=context.workspace.id,
        work_item_id=work_item_id,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="工作项不存在")
    if item.version != payload.expected_version:
        raise HTTPException(status_code=409, detail="工作项已被其他人更新")
    result = _result_object(item.result_json)
    if result is None or result.get("media_type") != "image":
        raise HTTPException(status_code=422, detail="当前任务不是图片素材")
    try:
        task_id = UUID(str(result.get("task_id") or ""))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="图片任务编号无效") from None
    task = await db.get(ImageGenerationTask, task_id)
    if task is None or task.workspace_id != context.workspace.id:
        raise HTTPException(status_code=404, detail="图片任务不存在")

    reference_ids = [str(asset_id) for asset_id in payload.reference_asset_ids]
    if reference_ids:
        references = (
            await db.execute(
                select(ImageAsset).where(
                    ImageAsset.workspace_id == context.workspace.id,
                    ImageAsset.id.in_(payload.reference_asset_ids),
                    ImageAsset.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        if len(references) != len(set(reference_ids)):
            raise HTTPException(status_code=422, detail="参考图不存在或已移除")

    input_data = {
        "prompt": payload.prompt.strip(),
        "negative_prompt": task.negative_prompt or "",
        "num_outputs": task.num_outputs or 1,
        "mode": task.mode,
        "quality_tier": task.quality_tier,
        "aspect_ratio": task.aspect_ratio or "1:1",
        "style_preset": task.style_preset,
        "use_brand_persona": task.use_brand_persona,
        "provider": task.provider,
        "reference_asset_ids": reference_ids,
        "estimated_credits": task.credits_cost,
    }
    try:
        run = await plan_action_run(
            db,
            workspace_id=context.workspace.id,
            actor_user_id=context.membership.user_id,
            work_item_id=item.id,
            action_id="media.generate_image",
            platform="internal",
            target_type="media_task",
            target_id=str(task.id),
            input_data=input_data,
            idempotency_key=idempotency_key,
        )
        if run.status == "awaiting_confirmation":
            run = await confirm_action_run(
                db,
                workspace_id=context.workspace.id,
                action_run_id=run.id,
                actor_user_id=context.membership.user_id,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    return MediaRegenerateResponse(
        action_run_id=run.id,
        status=run.status,
        work_item_version=item.version,
    )


@router.post(
    "/workspaces/{workspace_id}/work-items/{work_item_id}/commands",
    response_model=WorkItemCommandResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_command(
    work_item_id: UUID,
    payload: WorkItemCommandRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8),
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin", "operator")
    ),
    db: AsyncSession = Depends(get_db),
):
    action_run_id: UUID | None = None
    try:
        command = await submit_work_item_command(
            db,
            workspace_id=context.workspace.id,
            work_item_id=work_item_id,
            actor_user_id=context.membership.user_id,
            action=payload.action,
            expected_version=payload.expected_version,
            payload=payload.payload,
            idempotency_key=idempotency_key,
        )
        action_runs = await list_action_runs_for_work_item(
            db,
            workspace_id=context.workspace.id,
            work_item_id=work_item_id,
        )
        latest_action_run = action_runs[-1] if action_runs else None
        if latest_action_run is not None and payload.action in {"confirm", "retry"}:
            if (
                payload.action == "confirm"
                and latest_action_run.status in {"awaiting_confirmation", "planned"}
            ):
                latest_action_run = await confirm_action_run(
                    db,
                    workspace_id=context.workspace.id,
                    action_run_id=latest_action_run.id,
                    actor_user_id=context.membership.user_id,
                )
            elif (
                payload.action == "retry"
                and latest_action_run.status in {"retryable_failed", "blocked"}
            ):
                latest_action_run = await retry_action_run(
                    db,
                    workspace_id=context.workspace.id,
                    action_run_id=latest_action_run.id,
                    actor_user_id=context.membership.user_id,
                )
            action_run_id = latest_action_run.id
    except WorkItemVersionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WorkItemCommandConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WorkItemStateError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ActionRunStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    accepted_at = command.created_at or datetime.now(timezone.utc)
    return WorkItemCommandResponse(
        command_id=command.id,
        work_item_id=command.work_item_id,
        status=command.status,
        action_run_id=action_run_id,
        accepted_at=accepted_at,
    )


@router.post(
    "/workspaces/{workspace_id}/agent-turns",
    response_model=AgentTurnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_turn(
    payload: AgentTurnRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8),
    context: WorkspaceContext = Depends(
        require_workspace_role("owner", "admin", "operator")
    ),
    db: AsyncSession = Depends(get_db),
):
    try:
        turn, _task, work_item = await create_agent_turn(
            db,
            workspace_id=context.workspace.id,
            actor_user_id=context.membership.user_id,
            input_type=payload.input_type,
            text=payload.text,
            source_url=payload.source_url,
            asset_ids=payload.asset_ids,
            audio_asset_id=payload.audio_asset_id,
            idempotency_key=idempotency_key,
            parent_work_item_id=payload.work_item_id,
        )
    except AgentTurnConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AgentTurnAssetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return AgentTurnResponse(
        agent_turn_id=turn.id,
        status=turn.status,
        created_work_item_ids=[work_item.id],
        stream_url=f"/api/mobile/v1/workspaces/{context.workspace.id}/stream",
    )


@router.get(
    "/workspaces/{workspace_id}/agent-turns/{turn_id}",
    response_model=AgentTurnDetailResponse,
)
async def get_turn_detail(
    turn_id: UUID,
    context: WorkspaceContext = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    result = await get_agent_turn_detail(
        db,
        workspace_id=context.workspace.id,
        turn_id=turn_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Agent 输入不存在")
    turn, task, work_item = result
    created_work_item_ids: list[UUID] = []
    if work_item is not None:
        created_work_item_ids.append(work_item.id)
    if task is not None:
        pending_items = (
            await db.execute(
                select(WorkItem).where(
                    WorkItem.workspace_id == context.workspace.id,
                    WorkItem.source_type == "agent_pending_action",
                    WorkItem.source_id.like(f"{task.id}:%"),
                )
            )
        ).scalars().all()
        created_work_item_ids.extend(item.id for item in pending_items)
    steps: list[AgentStepSummary] = []
    result_summary = None
    if task is not None:
        try:
            progress = json.loads(task.progress or "{}")
            raw_steps = progress.get("steps") if isinstance(progress, dict) else []
            if isinstance(raw_steps, list):
                for step in raw_steps:
                    if isinstance(step, dict):
                        action = str(step.get("action") or "").strip() or None
                        label = str(
                            step.get("label")
                            or AGENT_STEP_LABELS.get(action or "", "")
                            or action
                            or ""
                        ).strip()
                        if not label:
                            continue
                        step_data = step.get("data")
                        structured = (
                            step_data.get("structured")
                            if isinstance(step_data, dict)
                            and action == "find_1688_sources"
                            and isinstance(step_data.get("structured"), dict)
                            else None
                        )
                        steps.append(
                            AgentStepSummary(
                                label=label,
                                status=str(step.get("status") or "pending"),
                                action=action,
                                duration_ms=(
                                    int(step["duration_ms"])
                                    if isinstance(step.get("duration_ms"), (int, float))
                                    else None
                                ),
                                structured=structured,
                            )
                        )
        except (TypeError, json.JSONDecodeError):
            steps = []
        try:
            task_result = json.loads(task.result or "{}")
            if isinstance(task_result, dict):
                result_summary = (
                    str(task_result["summary"])
                    if task_result.get("summary")
                    else None
                )
        except (TypeError, json.JSONDecodeError):
            result_summary = None
    return AgentTurnDetailResponse(
        agent_turn_id=turn.id,
        status=turn.status,
        input_type=turn.input_type,
        text=turn.text,
        task_status=task.status if task else None,
        result_summary=result_summary,
        error=task.error if task else None,
        steps=steps,
        created_work_item_ids=created_work_item_ids,
    )
