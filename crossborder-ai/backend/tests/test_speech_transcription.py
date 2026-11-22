"""语音转写服务测试。"""

import base64
import json

import httpx
import pytest

from app.services.speech_transcription import (
    AliyunSpeechTranscriber,
    SpeechTranscriptionError,
    SpeechTranscriptionResult,
    transcribe_mobile_audio,
)
from app.services import provider_config, speech_transcription


@pytest.mark.asyncio
async def test_aliyun_transcriber_sends_audio_and_returns_text():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "帮我把两个订单发货",
                        }
                    }
                ]
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        transcriber = AliyunSpeechTranscriber(
            api_key="test-key",
            base_url="https://dashscope.example/v1",
            model="qwen3-asr-flash",
            client=client,
        )
        result = await transcriber.transcribe(
            audio=b"fake-m4a-audio",
            content_type="audio/mp4",
            filename="voice.m4a",
        )

    assert captured["url"] == "https://dashscope.example/v1/chat/completions"
    assert captured["authorization"] == "Bearer test-key"
    assert captured["payload"]["model"] == "qwen3-asr-flash"
    audio_data = captured["payload"]["messages"][0]["content"][0]["input_audio"][
        "data"
    ]
    assert audio_data.startswith("data:audio/mp4;base64,")
    assert audio_data.split(",", 1)[1] == base64.b64encode(
        b"fake-m4a-audio"
    ).decode()
    assert captured["payload"]["asr_options"]["enable_lid"] is True
    assert result.transcript == "帮我把两个订单发货"
    assert result.language == "zh"


@pytest.mark.asyncio
async def test_aliyun_transcriber_rejects_empty_provider_result():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": ""}}]},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        transcriber = AliyunSpeechTranscriber(
            api_key="test-key",
            base_url="https://dashscope.example/v1",
            model="qwen3-asr-flash",
            client=client,
        )
        with pytest.raises(SpeechTranscriptionError, match="没有识别到"):
            await transcriber.transcribe(
                audio=b"silent",
                content_type="audio/mp4",
                filename="voice.m4a",
            )


@pytest.mark.asyncio
async def test_mobile_transcriber_does_not_mask_environment_key(monkeypatch):
    """调用层不能把空默认值传给运行时配置，否则会遮蔽环境 Key。"""

    calls: list[tuple] = []

    def fake_get(*args):
        calls.append(args)
        return "env-dashscope-key"

    class FakeTranscriber:
        def __init__(self, **kwargs):
            assert kwargs["api_key"] == "env-dashscope-key"

        async def transcribe(self, **kwargs):
            assert kwargs["audio"] == b"audio"
            return SpeechTranscriptionResult(
                transcript="帮我查订单",
                language="zh",
                provider="aliyun",
                model="qwen3-asr-flash",
            )

    monkeypatch.setattr(provider_config, "get", fake_get)
    monkeypatch.setattr(
        speech_transcription,
        "AliyunSpeechTranscriber",
        FakeTranscriber,
    )

    result = await transcribe_mobile_audio(
        audio=b"audio",
        content_type="audio/wav",
        filename="voice.wav",
    )

    assert result.transcript == "帮我查订单"
    assert calls[0] == ("aliyun", "api_key")
