"""MiniMax TTS 请求与错误契约测试。"""

import json

import httpx
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.marketing_video import MarketingVideoProject
from app.models.user import User
from app.services import provider_config
from app.services.minimax_tts import (
    MiniMaxTTSNotConfigured,
    build_minimax_tts_request,
    synthesize_minimax_tts,
)


def test_tts_capabilities_explain_missing_group_id(monkeypatch):
    from app.services.minimax_tts import get_minimax_tts_capabilities

    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(settings, "MINIMAX_GROUP_ID", "")
    provider_config.clear_cache()

    capabilities = get_minimax_tts_capabilities()

    assert capabilities["enabled"] is False
    assert "GroupId" in capabilities["reason"]


def test_tts_request_includes_text_and_voice_settings():
    payload = build_minimax_tts_request(
        text="Make every commute lighter.",
        model="speech-02-hd",
        voice_id="English_Graceful_Lady",
    )

    assert payload["text"] == "Make every commute lighter."
    assert payload["model"] == "speech-02-hd"
    assert payload["voice_setting"]["voice_id"] == "English_Graceful_Lady"
    assert payload["audio_setting"]["format"] == "mp3"
    assert payload["output_format"] == "hex"


@pytest.mark.asyncio
async def test_synthesize_tts_decodes_hex_audio(monkeypatch):
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(settings, "MINIMAX_GROUP_ID", "group-1")
    provider_config.clear_cache()
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization")
        seen["payload"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "data": {"audio": b"ID3fake-audio".hex(), "status": 2},
                "base_resp": {"status_code": 0, "status_msg": "success"},
            },
        )

    audio, content_type = await synthesize_minimax_tts(
        "Hello shoppers",
        transport=httpx.MockTransport(handler),
    )

    assert audio == b"ID3fake-audio"
    assert content_type == "audio/mpeg"
    assert "GroupId=group-1" in seen["url"]
    assert seen["authorization"] == "Bearer test-key"
    assert seen["payload"]["text"] == "Hello shoppers"


@pytest.mark.asyncio
async def test_synthesize_tts_requires_group_id(monkeypatch):
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(settings, "MINIMAX_GROUP_ID", "")
    provider_config.clear_cache()

    with pytest.raises(MiniMaxTTSNotConfigured, match="GroupId"):
        await synthesize_minimax_tts("Hello")


@pytest.mark.asyncio
async def test_voiceover_endpoint_charges_once_after_success(
    client,
    db_session,
    auth_headers,
    monkeypatch,
):
    user = (
        await db_session.execute(select(User).where(User.email == "test@example.com"))
    ).scalar_one()
    user.credits = 30
    project = MarketingVideoProject(
        user_id=user.id,
        source_asset_id=None,
        title="Terra voice",
        product_name="Terra",
        idea="voiceover",
        platform="tiktok",
        market="US",
        language="en",
        duration=15,
        template_id="presenter_demo",
        model="MiniMax-H3-Lite",
        resolution="480P",
        status="brief_ready",
        brief_json='{"hook":"Meet Terra", "script":"One light layer.", "cta":"Shop now"}',
    )
    db_session.add(project)
    await db_session.flush()

    async def fake_synthesize(text):
        assert "Meet Terra" in text
        return b"ID3audio", "audio/mpeg"

    monkeypatch.setattr(
        "app.routers.marketing_videos.synthesize_minimax_tts",
        fake_synthesize,
    )

    response = await client.post(
        f"/api/v1/marketing-videos/projects/{project.id}/voiceover",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.content == b"ID3audio"
    assert response.headers["x-credits-charged"] == "1"
    await db_session.refresh(user)
    assert user.credits == 29


@pytest.mark.asyncio
async def test_voiceover_missing_group_id_does_not_charge(
    client,
    db_session,
    auth_headers,
    monkeypatch,
):
    user = (
        await db_session.execute(select(User).where(User.email == "test@example.com"))
    ).scalar_one()
    user.credits = 30
    project = MarketingVideoProject(
        user_id=user.id,
        source_asset_id=None,
        title="Terra voice",
        product_name="Terra",
        idea="voiceover",
        platform="tiktok",
        market="US",
        language="en",
        duration=15,
        template_id="presenter_demo",
        model="MiniMax-H3-Lite",
        resolution="480P",
        status="brief_ready",
        brief_json='{"script":"One light layer."}',
    )
    db_session.add(project)
    await db_session.flush()
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(settings, "MINIMAX_GROUP_ID", "")
    provider_config.clear_cache()

    response = await client.post(
        f"/api/v1/marketing-videos/projects/{project.id}/voiceover",
        headers=auth_headers,
    )

    assert response.status_code == 503
    assert "GroupId" in response.json()["detail"]
    await db_session.refresh(user)
    assert user.credits == 30
