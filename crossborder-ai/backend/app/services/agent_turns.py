"""移动端 Agent 输入转持久任务。"""

import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_task import AgentTask
from app.models.agent_work import (
    AgentTurn,
    AgentTurnInput,
    WorkItem,
    WorkItemEvent,
)
from app.models.audio_asset import AudioAsset
from app.models.image_asset import ImageAsset
from app.services.agent_result_state import result_needs_user_input
from app.services.work_items import (
    complete_work_item_from_agent_task,
    create_work_item,
)


class AgentTurnConflict(ValueError):
    """相同幂等键对应不同输入。"""


class AgentTurnAssetError(ValueError):
    """输入素材不属于当前用户或已经失效。"""


TURN_STATUS_BY_TASK_STATUS = {
    "pending": "pending",
    "running": "running",
    "succeeded": "succeeded",
    "partial": "partial",
    "failed": "failed",
}

INPUT_STATUS_BY_TASK_STATUS = {
    "pending": "received",
    "running": "processing",
    "succeeded": "completed",
    "partial": "completed",
    "failed": "failed",
}


async def sync_agent_turn_status(
    db: AsyncSession,
    *,
    turn: AgentTurn,
    task_status: str,
    task_result: dict | None = None,
) -> bool:
    """把后台任务状态同步到移动端 AgentTurn 和输入明细。

    执行器完成时调用一次；详情接口也会调用，用于修复历史任务或进程在提交前中断
    造成的 pending/running 残留。
    """

    needs_user_input = (
        task_status == "succeeded"
        and result_needs_user_input(task_result)
    )
    turn_status = (
        "waiting_user"
        if needs_user_input
        else TURN_STATUS_BY_TASK_STATUS.get(task_status)
    )
    if turn_status is None:
        return False
    changed = turn.status != turn_status
    turn.status = turn_status

    input_status = (
        "waiting_user"
        if needs_user_input
        else INPUT_STATUS_BY_TASK_STATUS[task_status]
    )
    inputs = (
        await db.execute(
            select(AgentTurnInput).where(
                AgentTurnInput.workspace_id == turn.workspace_id,
                AgentTurnInput.agent_turn_id == turn.id,
            )
        )
    ).scalars().all()
    for item in inputs:
        if item.status != input_status:
            item.status = input_status
            changed = True
    if changed:
        await db.flush()
    return changed


async def create_agent_turn(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    input_type: str,
    text: str | None,
    source_url: str | None,
    asset_ids: list[UUID],
    idempotency_key: str,
    audio_asset_id: UUID | None = None,
    parent_work_item_id: UUID | None = None,
) -> tuple[AgentTurn, AgentTask, WorkItem]:
    audio_asset: AudioAsset | None = None
    final_text = text
    if audio_asset_id is not None:
        if input_type != "voice":
            raise AgentTurnAssetError("语音素材只能用于语音输入")
        audio_asset = await db.get(AudioAsset, audio_asset_id)
        now = datetime.now(timezone.utc)
        expires_at = audio_asset.expires_at if audio_asset else None
        if (
            audio_asset is None
            or audio_asset.user_id != actor_user_id
            or audio_asset.workspace_id != workspace_id
            or audio_asset.status != "ready"
            or expires_at is None
            or (
                expires_at.replace(tzinfo=timezone.utc)
                if expires_at.tzinfo is None
                else expires_at
            )
            <= now
        ):
            raise AgentTurnAssetError("语音素材不存在、已过期或不属于当前用户")
        final_text = (text or audio_asset.transcript).strip()
        if not final_text:
            raise AgentTurnAssetError("语音内容为空")
    elif input_type == "voice":
        raise AgentTurnAssetError("语音输入缺少已转写的语音素材")

    unique_asset_ids = list(dict.fromkeys(asset_ids))
    if unique_asset_ids:
        owned_assets = (
            await db.execute(
                select(ImageAsset.id).where(
                    ImageAsset.id.in_(unique_asset_ids),
                    ImageAsset.user_id == actor_user_id,
                    ImageAsset.workspace_id == workspace_id,
                )
            )
        ).scalars().all()
        if len(owned_assets) != len(unique_asset_ids):
            raise AgentTurnAssetError("素材不存在或不属于当前用户")

    existing = (
        await db.execute(
            select(AgentTurn).where(
                AgentTurn.workspace_id == workspace_id,
                AgentTurn.created_by_user_id == actor_user_id,
                AgentTurn.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.input_type != input_type or (existing.text or "") != (
            final_text or ""
        ):
            raise AgentTurnConflict("相同幂等键对应不同输入")
        if audio_asset_id is not None:
            existing_input = (
                await db.execute(
                    select(AgentTurnInput).where(
                        AgentTurnInput.workspace_id == workspace_id,
                        AgentTurnInput.agent_turn_id == existing.id,
                        AgentTurnInput.input_type == "voice",
                    )
                )
            ).scalar_one_or_none()
            if (
                existing_input is None
                or existing_input.asset_id != audio_asset_id
            ):
                raise AgentTurnConflict("相同幂等键对应不同语音输入")
        task = (
            await db.execute(
                select(AgentTask).where(
                    AgentTask.user_id == actor_user_id,
                    AgentTask.idempotency_key == f"mobile:{existing.id}",
                )
            )
        ).scalar_one()
        work_item = (
            await db.execute(
                select(WorkItem).where(
                    WorkItem.workspace_id == workspace_id,
                    WorkItem.source_type == "agent_task",
                    WorkItem.source_id == str(task.id),
                )
            )
        ).scalar_one()
        return existing, task, work_item

    turn = AgentTurn(
        workspace_id=workspace_id,
        created_by_user_id=actor_user_id,
        input_type=input_type,
        text=final_text,
        status="pending",
        idempotency_key=idempotency_key,
    )
    db.add(turn)
    await db.flush()

    if final_text and input_type != "voice":
        db.add(
            AgentTurnInput(
                workspace_id=workspace_id,
                agent_turn_id=turn.id,
                input_type="text",
                text_content=final_text,
                status="received",
            )
        )
    if audio_asset is not None:
        db.add(
            AgentTurnInput(
                workspace_id=workspace_id,
                agent_turn_id=turn.id,
                input_type="voice",
                text_content=final_text,
                transcript=audio_asset.transcript,
                asset_id=audio_asset.id,
                status="received",
            )
        )
    if source_url:
        db.add(
            AgentTurnInput(
                workspace_id=workspace_id,
                agent_turn_id=turn.id,
                input_type="link",
                source_url=source_url,
                status="received",
            )
        )
    for asset_id in unique_asset_ids:
        db.add(
            AgentTurnInput(
                workspace_id=workspace_id,
                agent_turn_id=turn.id,
                input_type="image" if input_type == "image" else "asset",
                asset_id=asset_id,
                status="received",
            )
        )
    await db.flush()

    instruction = final_text or source_url or f"移动端 {input_type} 输入"
    task = AgentTask(
        user_id=actor_user_id,
        task_type="agent_run",
        status="pending",
        input=json.dumps(
            {
                "instruction": instruction,
                "conversation_id": None,
                "workspace": "general",
                "page_context": {
                    "source": "mobile_app",
                    "agent_turn_id": str(turn.id),
                    "input_type": input_type,
                    "source_url": source_url,
                    "asset_ids": [str(asset_id) for asset_id in unique_asset_ids],
                    "audio_asset_id": (
                        str(audio_asset.id) if audio_asset is not None else None
                    ),
                    "audio_language": (
                        audio_asset.detected_language
                        if audio_asset is not None
                        else None
                    ),
                },
            },
            ensure_ascii=False,
        ),
        idempotency_key=f"mobile:{turn.id}",
        cost=1,
    )
    db.add(task)
    await db.flush()

    work_item = await create_work_item(
        db,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        kind="agent_request",
        source="agent",
        title=(final_text or "Agent 已接收新指令")[:60],
        summary=(
            "Agent 正在理解并处理你的语音指令。"
            if audio_asset is not None
            else "Agent 正在理解并处理你的输入。"
        ),
        priority="normal",
        requires_action="none",
        status="running",
        current_step="Agent 正在处理",
        source_type="agent_task",
        source_id=str(task.id),
    )
    if parent_work_item_id is not None:
        parent_work_item = await db.get(WorkItem, parent_work_item_id)
        if (
            parent_work_item is not None
            and parent_work_item.workspace_id == workspace_id
            and parent_work_item.status == "waiting_user"
        ):
            parent_work_item.status = "succeeded"
            parent_work_item.requires_action = "none"
            parent_work_item.current_step = "已继续处理"
            parent_work_item.version += 1
            db.add(
                WorkItemEvent(
                    workspace_id=workspace_id,
                    work_item_id=parent_work_item.id,
                    event_type="work_item.follow_up.started",
                    actor_user_id=actor_user_id,
                    payload_json=json.dumps(
                        {
                            "agent_turn_id": str(turn.id),
                            "version": parent_work_item.version,
                        },
                        ensure_ascii=False,
                    ),
                )
            )
    await db.flush()
    return turn, task, work_item


async def get_agent_turn_detail(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    turn_id: UUID,
) -> tuple[AgentTurn, AgentTask | None, WorkItem | None] | None:
    """读取移动 Agent 任务的状态、步骤和关联工作项。"""

    turn = (
        await db.execute(
            select(AgentTurn).where(
                AgentTurn.workspace_id == workspace_id,
                AgentTurn.id == turn_id,
            )
        )
    ).scalar_one_or_none()
    if turn is None:
        return None
    task = (
        await db.execute(
            select(AgentTask).where(
                AgentTask.user_id == turn.created_by_user_id,
                AgentTask.idempotency_key == f"mobile:{turn.id}",
            )
        )
    ).scalar_one_or_none()
    if task is not None:
        try:
            task_result = json.loads(task.result) if task.result else None
        except (TypeError, json.JSONDecodeError):
            task_result = None
        changed = await sync_agent_turn_status(
            db,
            turn=turn,
            task_status=task.status,
            task_result=task_result,
        )
        if task.status in {"succeeded", "partial", "failed"}:
            synced_work_item = await complete_work_item_from_agent_task(
                db,
                agent_task_id=task.id,
                status=task.status,
                summary=str((task_result or {}).get("summary") or ""),
                error=task.error,
                task_result=task_result,
            )
            changed = changed or synced_work_item is not None
        if changed:
            await db.commit()
    work_item = None
    if task is not None:
        work_item = (
            await db.execute(
                select(WorkItem).where(
                    WorkItem.workspace_id == workspace_id,
                    WorkItem.source_type == "agent_task",
                    WorkItem.source_id == str(task.id),
                )
            )
        ).scalar_one_or_none()
    return turn, task, work_item
