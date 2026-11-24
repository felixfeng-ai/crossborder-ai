"""移动端工作区、时间线和命令接口测试。"""

import io
import json
import uuid
from datetime import date, datetime, timezone

import pytest
from PIL import Image
from sqlalchemy import select
from uuid import UUID

from app.models.user import User
from app.models.audio_asset import AudioAsset
from app.models.agent_work import AgentTurn, AgentTurnInput, WorkItem
from app.models.action_run import ActionRun
from app.models.agent_task import AgentTask
from app.models.image_asset import ImageAsset
from app.models.image_generation_task import ImageGenerationTask
from app.models.video_generation_task import VideoGenerationTask
from app.models.customer_channel import (
    CustomerChannel,
    CustomerMessage,
    CustomerThread,
    ReplyDraft,
)
from app.core.config import settings
from app.services.action_runtime import plan_action_run
from app.services.work_items import create_work_item
from app.services.workspaces import ensure_personal_workspace
from app.services.speech_transcription import SpeechTranscriptionResult
from app.services.business_time import business_day_utc_bounds


async def _register_and_workspace(
    client,
    db_session,
    *,
    email: str,
    username: str,
) -> tuple[dict[str, str], object]:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": username,
            "password": "testpass123",
        },
    )
    assert response.status_code == 201
    headers = {
        "Authorization": f"Bearer {response.json()['access_token']}",
    }
    user = (
        await db_session.execute(select(User).where(User.email == email))
    ).scalar_one()
    workspace = await ensure_personal_workspace(db_session, user)
    await db_session.commit()
    return headers, workspace


@pytest.mark.asyncio
async def test_registration_creates_personal_workspace(client, db_session):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "mobile-bootstrap@example.com",
            "username": "mobile-bootstrap",
            "password": "testpass123",
        },
    )
    assert response.status_code == 201
    headers = {
        "Authorization": f"Bearer {response.json()['access_token']}",
    }

    bootstrap = await client.get(
        "/api/mobile/v1/bootstrap",
        headers=headers,
    )

    assert bootstrap.status_code == 200
    payload = bootstrap.json()
    assert payload["display_name"] == "mobile-bootstrap"
    assert len(payload["workspaces"]) == 1
    assert payload["workspaces"][0]["type"] == "personal"
    assert payload["workspaces"][0]["role"] == "owner"


@pytest.mark.asyncio
async def test_mobile_timeline_and_idempotent_command(
    client,
    db_session,
):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-api@example.com",
        username="mobile-api",
    )
    item = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=workspace.owner_user_id,
        kind="order_exception",
        source="integration",
        title="两个订单四小时后超时",
        summary="供应商尚未揽收。",
        priority="urgent",
        requires_action="confirm",
    )
    await db_session.commit()

    timeline = await client.get(
        f"/api/mobile/v1/workspaces/{workspace.id}/timeline",
        headers=headers,
    )
    assert timeline.status_code == 200
    assert timeline.json()["items"][0]["id"] == str(item.id)

    detail = await client.get(
        f"/api/mobile/v1/workspaces/{workspace.id}/work-items/{item.id}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["available_actions"][0]["kind"] == "confirm"

    command_headers = {**headers, "Idempotency-Key": "mobile-gesture-1"}
    first = await client.post(
        f"/api/mobile/v1/workspaces/{workspace.id}/work-items/{item.id}/commands",
        headers=command_headers,
        json={
            "action": "confirm",
            "action_id": "primary",
            "expected_version": 1,
            "payload": {"decision": "delay_notice"},
        },
    )
    second = await client.post(
        f"/api/mobile/v1/workspaces/{workspace.id}/work-items/{item.id}/commands",
        headers=command_headers,
        json={
            "action": "confirm",
            "action_id": "primary",
            "expected_version": 1,
            "payload": {"decision": "delay_notice"},
        },
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["command_id"] == second.json()["command_id"]


@pytest.mark.asyncio
async def test_timeline_uses_workspace_local_business_date(
    client,
    db_session,
):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-local-date@example.com",
        username="mobile-local-date",
    )
    item = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=workspace.owner_user_id,
        kind="order_exception",
        source="integration",
        title="本地凌晨订单",
        summary="应按上海日期归档。",
        requires_action="confirm",
    )
    local_start, _ = business_day_utc_bounds(
        date(2026, 11, 22),
        "Asia/Shanghai",
    )
    item.created_at = local_start.replace(minute=30)
    await db_session.commit()

    response = await client.get(
        f"/api/mobile/v1/workspaces/{workspace.id}/timeline",
        headers=headers,
        params={
            "date": "2026-11-22",
            "timezone": "Asia/Shanghai",
        },
    )

    assert response.status_code == 200
    assert [entry["id"] for entry in response.json()["items"]] == [
        str(item.id)
    ]


@pytest.mark.asyncio
async def test_mobile_workspace_isolation(client, db_session):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-owner@example.com",
        username="mobile-owner",
    )
    other_headers, other_workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-other@example.com",
        username="mobile-other",
    )

    own = await client.get(
        f"/api/mobile/v1/workspaces/{workspace.id}/timeline",
        headers=headers,
    )
    foreign = await client.get(
        f"/api/mobile/v1/workspaces/{workspace.id}/timeline",
        headers=other_headers,
    )

    assert own.status_code == 200
    assert foreign.status_code == 404
    assert other_workspace.id != workspace.id


@pytest.mark.asyncio
async def test_agent_turn_creates_durable_work(client, db_session):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-turn@example.com",
        username="mobile-turn",
    )
    turn_headers = {**headers, "Idempotency-Key": "turn-gesture-1"}

    first = await client.post(
        f"/api/mobile/v1/workspaces/{workspace.id}/agent-turns",
        headers=turn_headers,
        json={
            "input_type": "text",
            "text": "帮我看看今天哪个订单快超时了",
        },
    )
    second = await client.post(
        f"/api/mobile/v1/workspaces/{workspace.id}/agent-turns",
        headers=turn_headers,
        json={
            "input_type": "text",
            "text": "帮我看看今天哪个订单快超时了",
        },
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["agent_turn_id"] == second.json()["agent_turn_id"]

    turn = (
        await db_session.execute(
            select(AgentTurn).where(
                AgentTurn.id == UUID(first.json()["agent_turn_id"]),
            )
        )
    ).scalar_one()
    assert turn.workspace_id == workspace.id
    assert turn.status == "pending"

    item = (
        await db_session.execute(
            select(WorkItem).where(
                WorkItem.workspace_id == workspace.id,
                WorkItem.source_type == "agent_task",
            )
        )
    ).scalar_one()
    assert item.source_id

    task = (
        await db_session.execute(
            select(AgentTask).where(AgentTask.id == UUID(item.source_id))
        )
    ).scalar_one()
    assert task.status == "pending"


@pytest.mark.asyncio
async def test_mobile_agent_turn_detail_exposes_progress_and_result(
    client,
    db_session,
):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-agent-detail@example.com",
        username="mobile-agent-detail",
    )
    submitted = await client.post(
        f"/api/mobile/v1/workspaces/{workspace.id}/agent-turns",
        headers={**headers, "Idempotency-Key": "agent-detail-turn-1"},
        json={
            "input_type": "text",
            "text": "帮我上架这个商品",
        },
    )
    turn_id = UUID(submitted.json()["agent_turn_id"])
    task = (
        await db_session.execute(
            select(AgentTask).where(
                AgentTask.idempotency_key == f"mobile:{turn_id}",
            )
        )
    ).scalar_one()
    task.status = "succeeded"
    task.progress = json.dumps(
        {
            "steps": [
                {"label": "读取商品信息", "status": "completed"},
                {"label": "准备 Shopify Listing", "status": "completed"},
            ]
        },
        ensure_ascii=False,
    )
    task.result = json.dumps(
        {"summary": "商品草稿已准备好，等待你确认发布。"},
        ensure_ascii=False,
    )
    turn = await db_session.get(AgentTurn, turn_id)
    turn.status = "succeeded"
    await db_session.commit()

    detail = await client.get(
        f"/api/mobile/v1/workspaces/{workspace.id}/agent-turns/{turn_id}",
        headers=headers,
    )

    assert detail.status_code == 200
    payload = detail.json()
    assert payload["status"] == "succeeded"
    assert payload["result_summary"] == "商品草稿已准备好，等待你确认发布。"
    assert payload["steps"][1]["label"] == "准备 Shopify Listing"
    assert payload["created_work_item_ids"]


@pytest.mark.asyncio
async def test_mobile_command_confirms_linked_action_run(client, db_session):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-action@example.com",
        username="mobile-action",
    )
    item = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=workspace.owner_user_id,
        kind="listing_action",
        source="agent",
        title="发布新品",
        summary="商品和图片已准备。",
        requires_action="confirm",
    )
    action_run = await plan_action_run(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=workspace.owner_user_id,
        work_item_id=item.id,
        action_id="listings.publish",
        platform="shopify",
        target_type="product",
        target_id="product-1",
        input_data={"product_id": "product-1"},
        idempotency_key="mobile-action-plan-1",
    )
    await db_session.commit()

    detail = await client.get(
        f"/api/mobile/v1/workspaces/{workspace.id}/work-items/{item.id}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["action_runs"][0]["id"] == str(action_run.id)
    assert detail.json()["action_preview"]["title"] == "即将发布商品"

    response = await client.post(
        f"/api/mobile/v1/workspaces/{workspace.id}/work-items/{item.id}/commands",
        headers={**headers, "Idempotency-Key": "mobile-action-confirm-1"},
        json={
            "action": "confirm",
            "action_id": "primary",
            "expected_version": item.version,
            "payload": {},
        },
    )
    assert response.status_code == 202
    assert response.json()["action_run_id"] == str(action_run.id)


@pytest.mark.asyncio
async def test_agent_image_turn_keeps_owned_asset_in_task_context(
    client,
    db_session,
):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-image-turn@example.com",
        username="mobile-image-turn",
    )
    asset = ImageAsset(
        user_id=workspace.owner_user_id,
        workspace_id=workspace.id,
        name="product-reference",
        kind="upload",
        storage_key=f"{workspace.owner_user_id}/mobile-image.webp",
        content_type="image/webp",
        width=800,
        height=800,
        file_size=1024,
    )
    db_session.add(asset)
    await db_session.commit()
    await db_session.refresh(asset)

    response = await client.post(
        f"/api/mobile/v1/workspaces/{workspace.id}/agent-turns",
        headers={**headers, "Idempotency-Key": "mobile-image-turn-1"},
        json={
            "input_type": "image",
            "asset_ids": [str(asset.id)],
        },
    )

    assert response.status_code == 202
    turn = (
        await db_session.execute(
            select(AgentTurn).where(
                AgentTurn.id == UUID(response.json()["agent_turn_id"])
            )
        )
    ).scalar_one()
    task = (
        await db_session.execute(
            select(AgentTask).where(
                AgentTask.idempotency_key == f"mobile:{turn.id}"
            )
        )
    ).scalar_one()

    assert str(asset.id) in task.input


@pytest.mark.asyncio
async def test_agent_image_turn_rejects_foreign_asset(client, db_session):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-image-owner@example.com",
        username="mobile-image-owner",
    )
    _other_headers, other_workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-image-other@example.com",
        username="mobile-image-other",
    )
    foreign_asset = ImageAsset(
        user_id=other_workspace.owner_user_id,
        workspace_id=other_workspace.id,
        name="foreign-reference",
        kind="upload",
        storage_key=f"{other_workspace.owner_user_id}/foreign.webp",
        content_type="image/webp",
        width=800,
        height=800,
        file_size=1024,
    )
    db_session.add(foreign_asset)
    await db_session.commit()
    await db_session.refresh(foreign_asset)

    response = await client.post(
        f"/api/mobile/v1/workspaces/{workspace.id}/agent-turns",
        headers={**headers, "Idempotency-Key": "mobile-image-foreign-1"},
        json={
            "input_type": "image",
            "asset_ids": [str(foreign_asset.id)],
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_voice_upload_transcribes_audio_idempotently(
    client,
    db_session,
    tmp_path,
    monkeypatch,
):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-voice-upload@example.com",
        username="mobile-voice-upload",
    )
    monkeypatch.setattr(settings, "AUDIO_STORAGE_DIR", str(tmp_path))
    calls = 0

    async def fake_transcribe(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return SpeechTranscriptionResult(
            transcript="帮我把两个订单发货",
            language="zh",
            provider="aliyun",
            model="qwen3-asr-flash",
        )

    monkeypatch.setattr(
        "app.routers.mobile.transcribe_mobile_audio",
        fake_transcribe,
    )
    request_headers = {
        **headers,
        "Idempotency-Key": "voice-upload-idempotent-1",
    }

    first = await client.post(
        f"/api/mobile/v1/workspaces/{workspace.id}/audio/transcriptions",
        headers=request_headers,
        files={
            "file": (
                "voice.m4a",
                b"\x00\x00\x00\x18ftypmp42fake-audio",
                "audio/mp4",
            )
        },
        data={"duration_ms": "4200"},
    )
    second = await client.post(
        f"/api/mobile/v1/workspaces/{workspace.id}/audio/transcriptions",
        headers=request_headers,
        files={
            "file": (
                "voice.m4a",
                b"\x00\x00\x00\x18ftypmp42fake-audio",
                "audio/mp4",
            )
        },
        data={"duration_ms": "4200"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["asset_id"] == second.json()["asset_id"]
    assert first.json()["transcript"] == "帮我把两个订单发货"
    assert first.json()["language"] == "zh"
    assert first.json()["duration_ms"] == 4200
    assert first.json()["provider"] == "aliyun"
    assert first.json()["model"] == "qwen3-asr-flash"
    assert calls == 1

    asset = await db_session.get(AudioAsset, UUID(first.json()["asset_id"]))
    assert asset is not None
    assert asset.workspace_id == workspace.id
    assert asset.user_id == workspace.owner_user_id
    assert asset.transcript == "帮我把两个订单发货"
    assert (tmp_path / asset.storage_key).is_file()


@pytest.mark.asyncio
async def test_voice_upload_rejects_forged_audio_content(
    client,
    db_session,
    tmp_path,
    monkeypatch,
):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-voice-forged@example.com",
        username="mobile-voice-forged",
    )
    monkeypatch.setattr(settings, "AUDIO_STORAGE_DIR", str(tmp_path))

    response = await client.post(
        f"/api/mobile/v1/workspaces/{workspace.id}/audio/transcriptions",
        headers={**headers, "Idempotency-Key": "voice-forged-1"},
        files={"file": ("voice.m4a", b"not-a-real-audio", "audio/mp4")},
        data={"duration_ms": "1200"},
    )

    assert response.status_code == 400
    assert (await db_session.execute(select(AudioAsset))).scalars().all() == []


@pytest.mark.asyncio
async def test_voice_agent_turn_keeps_raw_and_edited_transcript(
    client,
    db_session,
):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-voice-turn@example.com",
        username="mobile-voice-turn",
    )
    audio = AudioAsset(
        user_id=workspace.owner_user_id,
        workspace_id=workspace.id,
        original_name="voice.m4a",
        storage_key="voice/input.m4a",
        content_type="audio/mp4",
        duration_ms=4200,
        file_size=len(b"fake-m4a-audio"),
        sha256="a" * 64,
        transcript="帮我把这两个订单发货",
        detected_language="zh",
        provider="aliyun",
        model="qwen3-asr-flash",
        status="ready",
        idempotency_key="voice-asset-1",
        expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    db_session.add(audio)
    await db_session.commit()
    await db_session.refresh(audio)

    response = await client.post(
        f"/api/mobile/v1/workspaces/{workspace.id}/agent-turns",
        headers={**headers, "Idempotency-Key": "voice-turn-1"},
        json={
            "input_type": "voice",
            "text": "把这两个订单标记发货",
            "audio_asset_id": str(audio.id),
        },
    )

    assert response.status_code == 202
    turn_id = UUID(response.json()["agent_turn_id"])
    turn = await db_session.get(AgentTurn, turn_id)
    assert turn.input_type == "voice"
    assert turn.text == "把这两个订单标记发货"
    voice_input = (
        await db_session.execute(
            select(AgentTurnInput).where(
                AgentTurnInput.agent_turn_id == turn.id,
                AgentTurnInput.input_type == "voice",
            )
        )
    ).scalar_one()
    assert voice_input.asset_id == audio.id
    assert voice_input.transcript == "帮我把这两个订单发货"
    assert voice_input.text_content == "把这两个订单标记发货"
    task = (
        await db_session.execute(
            select(AgentTask).where(
                AgentTask.idempotency_key == f"mobile:{turn.id}",
            )
        )
    ).scalar_one()
    task_input = json.loads(task.input)
    assert task_input["page_context"]["audio_asset_id"] == str(audio.id)
    assert task_input["page_context"]["audio_language"] == "zh"


@pytest.mark.asyncio
async def test_voice_agent_turn_rejects_foreign_audio(client, db_session):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-voice-owner@example.com",
        username="mobile-voice-owner",
    )
    _other_headers, other_workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-voice-other@example.com",
        username="mobile-voice-other",
    )
    foreign_audio = AudioAsset(
        user_id=other_workspace.owner_user_id,
        workspace_id=other_workspace.id,
        original_name="foreign.m4a",
        storage_key="voice/foreign.m4a",
        content_type="audio/mp4",
        duration_ms=3200,
        file_size=100,
        sha256="b" * 64,
        transcript="帮我回复客户",
        detected_language="zh",
        provider="aliyun",
        model="qwen3-asr-flash",
        status="ready",
        idempotency_key="voice-asset-foreign",
        expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    db_session.add(foreign_audio)
    await db_session.commit()
    await db_session.refresh(foreign_audio)

    response = await client.post(
        f"/api/mobile/v1/workspaces/{workspace.id}/agent-turns",
        headers={**headers, "Idempotency-Key": "voice-turn-foreign-1"},
        json={
            "input_type": "voice",
            "text": "帮我回复客户",
            "audio_asset_id": str(foreign_audio.id),
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_mobile_event_stream_emits_workspace_work_item_event(
    client,
    db_session,
):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-stream@example.com",
        username="mobile-stream",
    )
    item = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=workspace.owner_user_id,
        kind="agent_request",
        source="agent",
        title="检查订单",
        summary="Agent 正在处理。",
        requires_action="none",
        status="running",
    )
    await db_session.commit()

    response = await client.get(
        (
            f"/api/mobile/v1/workspaces/{workspace.id}/stream"
            "?cursor=0&once=true"
        ),
        headers=headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: work_item.updated" in response.text
    assert str(item.id) in response.text


@pytest.mark.asyncio
async def test_mobile_image_upload_is_scoped_to_workspace(
    client,
    db_session,
    tmp_path,
    monkeypatch,
):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-upload@example.com",
        username="mobile-upload",
    )
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    image = Image.new("RGB", (320, 240), (210, 80, 50))
    raw = io.BytesIO()
    image.save(raw, format="JPEG", quality=90)

    response = await client.post(
        f"/api/mobile/v1/workspaces/{workspace.id}/assets/images",
        files={"file": ("product.jpg", raw.getvalue(), "image/jpeg")},
        headers=headers,
    )

    assert response.status_code == 201
    asset_id = uuid.UUID(response.json()["id"])
    asset = (
        await db_session.execute(
            select(ImageAsset).where(ImageAsset.id == asset_id)
        )
    ).scalar_one()
    assert asset.workspace_id == workspace.id
    assert asset.user_id == workspace.owner_user_id


@pytest.mark.asyncio
async def test_work_item_detail_includes_customer_message_and_latest_draft(
    client,
    db_session,
):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-customer-context@example.com",
        username="mobile-customer-context",
    )
    channel = CustomerChannel(
        workspace_id=workspace.id,
        created_by_user_id=workspace.owner_user_id,
        provider="imap_smtp",
        external_account_id="support@example.com",
        display_name="客服邮箱",
        credentials_ciphertext="encrypted",
    )
    db_session.add(channel)
    await db_session.flush()
    thread = CustomerThread(
        workspace_id=workspace.id,
        channel_id=channel.id,
        external_thread_id="customer-thread-1",
        thread_type="direct_message",
        subject="Where is my order?",
        language="en",
        status="waiting_user",
    )
    db_session.add(thread)
    await db_session.flush()
    db_session.add(
        CustomerMessage(
            workspace_id=workspace.id,
            thread_id=thread.id,
            external_message_id="<customer-1@example.com>",
            direction="inbound",
            body_text="Could you tell me when my parcel will arrive?",
            send_status="received",
        )
    )
    draft = ReplyDraft(
        workspace_id=workspace.id,
        thread_id=thread.id,
        version=1,
        language="en",
        body_text="Your parcel is expected to arrive within two days.",
        risk_level="medium",
        status="ready",
    )
    db_session.add(draft)
    item = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=workspace.owner_user_id,
        kind="customer_reply",
        source="integration",
        title="一位买家询问物流",
        summary="回复草稿已准备。",
        requires_action="confirm",
        source_type="customer_thread",
        source_id=str(thread.id),
    )
    await db_session.commit()

    response = await client.get(
        f"/api/mobile/v1/workspaces/{workspace.id}/work-items/{item.id}",
        headers=headers,
    )

    assert response.status_code == 200
    context = response.json()["customer_context"]
    assert context["subject"] == "Where is my order?"
    assert "parcel" in context["customer_message"]
    assert context["draft_id"] == str(draft.id)
    assert "two days" in context["draft_text"]


@pytest.mark.asyncio
async def test_customer_channel_create_encrypts_credentials(client, db_session):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-channel-create@example.com",
        username="mobile-channel-create",
    )
    response = await client.post(
        f"/api/mobile/v1/workspaces/{workspace.id}/customer-channels",
        headers=headers,
        json={
            "provider": "imap_smtp",
            "external_account_id": "support@example.com",
            "display_name": "客服邮箱",
            "credentials": {
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "smtp_username": "support@example.com",
                "smtp_password": "plain-secret",
                "smtp_from": "support@example.com",
                "smtp_security": "starttls",
            },
        },
    )

    assert response.status_code == 201
    assert "plain-secret" not in response.text
    channel = (
        await db_session.execute(
            select(CustomerChannel).where(
                CustomerChannel.workspace_id == workspace.id,
                CustomerChannel.external_account_id == "support@example.com",
            )
        )
    ).scalar_one()
    assert channel.credentials_ciphertext != "plain-secret"
    assert "plain-secret" not in channel.credentials_ciphertext


@pytest.mark.asyncio
async def test_seller_can_edit_latest_reply_draft(client, db_session):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-draft-edit@example.com",
        username="mobile-draft-edit",
    )
    channel = CustomerChannel(
        workspace_id=workspace.id,
        created_by_user_id=workspace.owner_user_id,
        provider="imap_smtp",
        external_account_id="support@example.com",
        display_name="客服邮箱",
        credentials_ciphertext="encrypted",
    )
    db_session.add(channel)
    await db_session.flush()
    thread = CustomerThread(
        workspace_id=workspace.id,
        channel_id=channel.id,
        external_thread_id="edit-thread-1",
        thread_type="direct_message",
        subject="Where is my order?",
        language="en",
    )
    db_session.add(thread)
    await db_session.flush()
    db_session.add(
        CustomerMessage(
            workspace_id=workspace.id,
            thread_id=thread.id,
            external_message_id="<edit-inbound@example.com>",
            direction="inbound",
            body_text="Where is my order?",
            send_status="received",
        )
    )
    old_draft = ReplyDraft(
        workspace_id=workspace.id,
        thread_id=thread.id,
        version=1,
        language="en",
        body_text="Old reply.",
        status="ready",
    )
    db_session.add(old_draft)
    await db_session.commit()

    response = await client.post(
        (
            f"/api/mobile/v1/workspaces/{workspace.id}"
            f"/customer-threads/{thread.id}/reply-drafts"
        ),
        headers=headers,
        json={
            "mode": "edit",
            "body_text": "Updated reply with a delivery date.",
            "language": "en",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["version"] == 2
    assert data["body_text"] == "Updated reply with a delivery date."
    await db_session.refresh(old_draft)
    assert old_draft.status == "stale"


@pytest.mark.asyncio
async def test_mobile_daily_plan_and_closeout_are_available(client, db_session):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-daily-plan@example.com",
        username="mobile-daily-plan",
    )
    await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=workspace.owner_user_id,
        kind="order_exception",
        source="integration",
        title="订单等待发货",
        summary="需要在今天处理。",
        requires_action="confirm",
    )
    await db_session.commit()

    plan = await client.get(
        f"/api/mobile/v1/workspaces/{workspace.id}/daily-plan",
        headers=headers,
        params={"timezone": "Asia/Shanghai"},
    )
    assert plan.status_code == 200
    # 测试跨越 UTC 与工作区本地日期时，新任务可能被正确归入“昨日延续”。
    assert (
        plan.json()["decision_count"] + plan.json()["carryover_count"]
        >= 1
    )
    assert len(plan.json()["items"]) >= 1

    closeout = await client.post(
        f"/api/mobile/v1/workspaces/{workspace.id}/daily-plan/close",
        headers=headers,
        params={"timezone": "Asia/Shanghai"},
    )
    assert closeout.status_code == 200
    assert closeout.json()["status"] == "closed"


@pytest.mark.asyncio
async def test_work_item_detail_includes_media_result(client, db_session):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-media-result@example.com",
        username="mobile-media-result",
    )
    reference = ImageAsset(
        user_id=workspace.owner_user_id,
        workspace_id=workspace.id,
        name="参考图",
        kind="upload",
        storage_key=f"{workspace.owner_user_id}/media-reference.webp",
        content_type="image/webp",
        width=640,
        height=640,
        file_size=1024,
    )
    db_session.add(reference)
    await db_session.flush()
    media_task = ImageGenerationTask(
        user_id=workspace.owner_user_id,
        workspace_id=workspace.id,
        prompt="商品图",
        num_outputs=1,
        credits_cost=8,
        status="completed",
        image_urls=json.dumps(
            ["/api/v1/images/assets/abc/file"],
            ensure_ascii=False,
        ),
        reference_assets_json=json.dumps([str(reference.id)]),
    )
    db_session.add(media_task)
    await db_session.flush()
    item = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=workspace.owner_user_id,
        kind="agent_action",
        source="agent",
        title="商品图片已生成",
        summary="查看生成结果。",
        requires_action="none",
        status="succeeded",
        result={
            "task_id": str(media_task.id),
            "media_type": "image",
            "summary": "图片已生成",
        },
    )
    await db_session.commit()

    response = await client.get(
        f"/api/mobile/v1/workspaces/{workspace.id}/work-items/{item.id}",
        headers=headers,
    )

    assert response.status_code == 200
    media = response.json()["media_result"]
    assert media["media_type"] == "image"
    assert media["images"] == ["/api/v1/images/assets/abc/file"]
    assert media["task_status"] == "completed"
    assert media["prompt"] == "商品图"
    assert media["reference_assets"][0]["id"] == str(reference.id)


@pytest.mark.asyncio
async def test_generated_image_save_to_library_is_idempotent(
    client,
    db_session,
    tmp_path,
    monkeypatch,
):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-media-save@example.com",
        username="mobile-media-save",
    )
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))

    image_buffer = io.BytesIO()
    Image.new("RGB", (32, 32), color=(40, 120, 90)).save(
        image_buffer,
        format="PNG",
    )
    # 预览任务使用受控图片字节，避免测试依赖外部图片服务。
    from app.services import generated_image_assets

    async def fake_download(_url: str) -> bytes:
        return image_buffer.getvalue()

    monkeypatch.setattr(
        generated_image_assets,
        "download_generated_image",
        fake_download,
    )

    media_task = ImageGenerationTask(
        user_id=workspace.owner_user_id,
        workspace_id=workspace.id,
        prompt="给收纳包生成一张旅行场景图",
        num_outputs=1,
        credits_cost=8,
        status="completed",
        image_urls=json.dumps(["https://example.com/generated.png"]),
    )
    db_session.add(media_task)
    await db_session.flush()
    item = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=workspace.owner_user_id,
        kind="agent_action",
        source="agent",
        title="商品图片已生成",
        summary="查看生成结果。",
        requires_action="none",
        status="succeeded",
        result={
            "task_id": str(media_task.id),
            "media_type": "image",
            "summary": "图片已生成",
        },
    )
    await db_session.commit()

    endpoint = (
        f"/api/mobile/v1/workspaces/{workspace.id}"
        f"/work-items/{item.id}/media/save-to-library"
    )
    first = await client.post(endpoint, headers=headers)
    second = await client.post(endpoint, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(first.json()["asset_ids"]) == 1
    assert second.json()["asset_ids"] == first.json()["asset_ids"]
    assets = (
        await db_session.execute(
            select(ImageAsset).where(
                ImageAsset.workspace_id == workspace.id,
                ImageAsset.generation_task_id == media_task.id,
            )
        )
    ).scalars().all()
    assert len(assets) == 1
    assert assets[0].kind == "generated"


@pytest.mark.asyncio
async def test_failed_media_can_regenerate_with_edited_prompt_and_reference(
    client,
    db_session,
):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-media-regenerate@example.com",
        username="mobile-media-regenerate",
    )
    reference = ImageAsset(
        user_id=workspace.owner_user_id,
        workspace_id=workspace.id,
        name="产品参考图",
        kind="upload",
        category="product",
        storage_key=f"{workspace.owner_user_id}/reference.webp",
        content_type="image/webp",
        width=800,
        height=800,
        file_size=2048,
    )
    db_session.add(reference)
    await db_session.flush()
    task = ImageGenerationTask(
        user_id=workspace.owner_user_id,
        workspace_id=workspace.id,
        prompt="原来的商品图描述",
        negative_prompt="模糊",
        num_outputs=1,
        credits_cost=8,
        status="failed",
        error="provider timeout",
        reference_assets_json=json.dumps([]),
    )
    db_session.add(task)
    await db_session.flush()
    item = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=workspace.owner_user_id,
        kind="agent_action",
        source="agent",
        title="商品图片生成失败",
        summary="可以重试。",
        status="waiting_user",
        requires_action="retry",
        result={
            "task_id": str(task.id),
            "media_type": "image",
        },
    )
    old_run = await plan_action_run(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=workspace.owner_user_id,
        work_item_id=item.id,
        action_id="media.generate_image",
        platform="internal",
        target_type="media_task",
        target_id=str(task.id),
        input_data={"prompt": task.prompt, "num_outputs": 1},
        idempotency_key="media-old-run",
    )
    old_run.status = "retryable_failed"
    await db_session.commit()

    response = await client.post(
        (
            f"/api/mobile/v1/workspaces/{workspace.id}"
            f"/work-items/{item.id}/media/regenerate"
        ),
        headers={**headers, "Idempotency-Key": "media-regenerate-1"},
        json={
            "expected_version": item.version,
            "prompt": "改成户外旅行场景，突出轻量收纳",
            "reference_asset_ids": [str(reference.id)],
        },
    )

    assert response.status_code == 202
    runs = (
        await db_session.execute(
            select(ActionRun)
            .where(ActionRun.work_item_id == item.id)
            .order_by(ActionRun.created_at)
        )
    ).scalars().all()
    assert len(runs) == 2
    regenerated = runs[-1]
    input_data = json.loads(regenerated.input_json)
    assert input_data["prompt"] == "改成户外旅行场景，突出轻量收纳"
    assert input_data["reference_asset_ids"] == [str(reference.id)]
    assert regenerated.status in {"queued", "awaiting_confirmation"}


@pytest.mark.asyncio
async def test_work_item_detail_exposes_signed_video_file(
    client,
    db_session,
    tmp_path,
    monkeypatch,
):
    headers, workspace = await _register_and_workspace(
        client,
        db_session,
        email="mobile-video-result@example.com",
        username="mobile-video-result",
    )
    monkeypatch.setattr(settings, "VIDEO_STORAGE_DIR", str(tmp_path))
    video_file = tmp_path / "preview.mp4"
    video_file.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    media_task = VideoGenerationTask(
        user_id=workspace.owner_user_id,
        model="test-video-model",
        resolution="1080p",
        duration=4,
        prompt="商品展示",
        status="succeeded",
        storage_key=video_file.name,
        mime="video/mp4",
    )
    db_session.add(media_task)
    await db_session.flush()
    item = await create_work_item(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=workspace.owner_user_id,
        kind="agent_action",
        source="agent",
        title="商品视频已生成",
        summary="查看生成结果。",
        requires_action="none",
        status="succeeded",
        result={
            "task_id": str(media_task.id),
            "media_type": "video",
            "summary": "视频已生成",
        },
    )
    await db_session.commit()

    detail = await client.get(
        f"/api/mobile/v1/workspaces/{workspace.id}/work-items/{item.id}",
        headers=headers,
    )

    assert detail.status_code == 200
    media = detail.json()["media_result"]
    assert media["media_type"] == "video"
    assert media["task_status"] == "succeeded"
    assert media["video_url"].startswith(
        f"/api/mobile/v1/media/video/{media_task.id}/file?access_token="
    )

    video = await client.get(media["video_url"])
    assert video.status_code == 200
    assert video.headers["content-type"].startswith("video/mp4")
    assert video.content == video_file.read_bytes()
