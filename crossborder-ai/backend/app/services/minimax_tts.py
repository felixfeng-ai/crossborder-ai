"""MiniMax T2A 语音合成服务。"""

from typing import Any
from urllib.parse import quote

import httpx

from app.services import provider_config


class MiniMaxTTSNotConfigured(RuntimeError):
    """语音服务缺少必要配置。"""


class MiniMaxTTSError(RuntimeError):
    """语音供应商请求或响应失败。"""


def get_minimax_tts_capabilities() -> dict[str, Any]:
    """返回不含密钥的语音能力状态。"""
    api_key = provider_config.get("minimax", "api_key")
    group_id = provider_config.get("minimax", "group_id")
    model = provider_config.get("minimax", "tts_model", "speech-02-hd")
    voice_id = provider_config.get(
        "minimax",
        "voice_id",
        "English_Graceful_Lady",
    )
    if not api_key:
        return {
            "enabled": False,
            "provider": "minimax",
            "reason": "语音服务未配置 API Key",
            "model": model,
            "voice_id": voice_id,
        }
    if not group_id:
        return {
            "enabled": False,
            "provider": "minimax",
            "reason": "语音服务未配置 GroupId",
            "model": model,
            "voice_id": voice_id,
        }
    return {
        "enabled": True,
        "provider": "minimax",
        "reason": "",
        "model": model,
        "voice_id": voice_id,
    }


def build_minimax_tts_request(
    text: str,
    *,
    model: str,
    voice_id: str,
) -> dict[str, Any]:
    """构造 MiniMax T2A v2 请求，不包含任何凭据。"""
    clean = " ".join(str(text or "").split()).strip()
    if not clean:
        raise ValueError("配音文本不能为空")
    return {
        "model": model,
        "text": clean[:5_000],
        "stream": False,
        "voice_setting": {
            "voice_id": voice_id,
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32_000,
            "bitrate": 128_000,
            "format": "mp3",
            "channel": 1,
        },
        "output_format": "hex",
    }


async def synthesize_minimax_tts(
    text: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[bytes, str]:
    """调用 MiniMax TTS 并返回音频字节；失败时不消耗业务积分。"""
    capabilities = get_minimax_tts_capabilities()
    if not capabilities["enabled"]:
        raise MiniMaxTTSNotConfigured(capabilities["reason"])

    api_key = provider_config.get("minimax", "api_key")
    group_id = provider_config.get("minimax", "group_id")
    base_url = provider_config.get(
        "minimax",
        "tts_base_url",
        "https://api.minimaxi.com",
    ).rstrip("/")
    payload = build_minimax_tts_request(
        text,
        model=capabilities["model"],
        voice_id=capabilities["voice_id"],
    )
    url = f"{base_url}/v1/t2a_v2?GroupId={quote(group_id, safe='')}"
    try:
        async with httpx.AsyncClient(
            timeout=90.0,
            transport=transport,
        ) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise MiniMaxTTSError("MiniMax 语音请求失败") from exc

    base_resp = body.get("base_resp") if isinstance(body, dict) else {}
    status_code = int((base_resp or {}).get("status_code", -1))
    if status_code != 0:
        raise MiniMaxTTSError(
            str((base_resp or {}).get("status_msg") or "MiniMax 语音生成失败")
        )

    audio_hex = ((body.get("data") or {}).get("audio") or "").strip()
    if not audio_hex:
        raise MiniMaxTTSError("MiniMax 未返回可播放音频")
    try:
        audio = bytes.fromhex(audio_hex)
    except ValueError as exc:
        raise MiniMaxTTSError("MiniMax 返回的音频格式无效") from exc
    if not audio:
        raise MiniMaxTTSError("MiniMax 返回的音频为空")
    return audio, "audio/mpeg"
