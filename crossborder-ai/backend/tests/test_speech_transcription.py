"""语音转写服务测试。"""

import asyncio
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


WAV_AUDIO = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32


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

    def fake_get(provider: str, field: str, default: str | None = None):
        args = (provider, field)
        calls.append(args)
        if provider == "doubao_asr":
            return ""
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
    assert calls[0] == ("doubao_asr", "api_key")
    assert ("aliyun", "api_key") in calls


@pytest.mark.asyncio
async def test_doubao_transcriber_sends_api_key_audio_and_hotwords():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"x-api-status-code": "20000000"},
            json={
                "audio_info": {"duration": 1800},
                "result": {"text": "帮我把 Shopify 订单发货"},
            },
        )

    transcriber_cls = getattr(
        speech_transcription,
        "DoubaoSpeechTranscriber",
        None,
    )
    assert transcriber_cls is not None

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        transcriber = transcriber_cls(
            api_key="ark-asr-key",
            base_url="https://openspeech.example/api/v3",
            resource_id="volc.bigasr.auc_turbo",
            client=client,
        )
        result = await transcriber.transcribe(
            audio=WAV_AUDIO,
            content_type="audio/wav",
            filename="voice.wav",
        )

    assert (
        captured["url"]
        == "https://openspeech.example/api/v3/auc/bigmodel/recognize/flash"
    )
    assert captured["headers"]["x-api-key"] == "ark-asr-key"
    assert (
        captured["headers"]["x-api-resource-id"]
        == "volc.bigasr.auc_turbo"
    )
    assert captured["headers"]["x-api-sequence"] == "-1"
    assert captured["payload"]["audio"]["format"] == "wav"
    assert captured["payload"]["audio"]["data"] == base64.b64encode(
        WAV_AUDIO
    ).decode()
    context = json.loads(
        captured["payload"]["request"]["corpus"]["context"]
    )
    hotwords = {item["word"] for item in context["hotwords"]}
    assert {"Shopify", "Temu", "TikTok Shop", "SKU", "ASIN"} <= hotwords
    assert result.transcript == "帮我把 Shopify 订单发货"
    assert result.provider == "doubao_asr"
    assert result.model == "volc.bigasr.auc_turbo"


@pytest.mark.asyncio
async def test_doubao_transcriber_transcodes_m4a_before_upload(monkeypatch):
    captured: dict = {}
    converted = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32

    async def fake_transcode(audio: bytes, content_type: str) -> bytes:
        captured["source"] = audio
        captured["content_type"] = content_type
        return converted

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"x-api-status-code": "20000000"},
            json={"result": {"text": "查看今天的订单"}},
        )

    monkeypatch.setattr(
        speech_transcription,
        "_transcode_audio_to_wav",
        fake_transcode,
        raising=False,
    )
    transcriber_cls = getattr(
        speech_transcription,
        "DoubaoSpeechTranscriber",
        None,
    )
    assert transcriber_cls is not None

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        transcriber = transcriber_cls(
            api_key="ark-asr-key",
            base_url="https://openspeech.example/api/v3",
            resource_id="volc.bigasr.auc_turbo",
            client=client,
        )
        await transcriber.transcribe(
            audio=b"m4a-source",
            content_type="audio/mp4",
            filename="voice.m4a",
        )

    assert captured["source"] == b"m4a-source"
    assert captured["content_type"] == "audio/mp4"
    assert captured["payload"]["audio"]["format"] == "wav"
    assert captured["payload"]["audio"]["data"] == base64.b64encode(
        converted
    ).decode()


@pytest.mark.asyncio
async def test_doubao_permission_error_is_eligible_for_qwen_fallback():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={
                "x-api-status-code": "45000001",
                "x-api-message": "resource not granted",
            },
            json={"error": "permission denied"},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        transcriber = speech_transcription.DoubaoSpeechTranscriber(
            api_key="ark-asr-key",
            base_url="https://openspeech.example/api/v3",
            resource_id="volc.bigasr.auc_turbo",
            client=client,
        )
        with pytest.raises(SpeechTranscriptionError) as error:
            await transcriber.transcribe(
                audio=WAV_AUDIO,
                content_type="audio/wav",
                filename="voice.wav",
            )

    assert error.value.allow_fallback is True
    assert "ark-asr-key" not in str(error.value)


@pytest.mark.asyncio
async def test_doubao_silence_is_not_retried_by_another_provider():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"x-api-status-code": "20000000"},
            json={"result": {"text": ""}},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        transcriber = speech_transcription.DoubaoSpeechTranscriber(
            api_key="ark-asr-key",
            base_url="https://openspeech.example/api/v3",
            resource_id="volc.bigasr.auc_turbo",
            client=client,
        )
        with pytest.raises(
            SpeechTranscriptionError,
            match="没有识别到",
        ) as error:
            await transcriber.transcribe(
                audio=WAV_AUDIO,
                content_type="audio/wav",
                filename="voice.wav",
            )

    assert error.value.allow_fallback is False


@pytest.mark.asyncio
async def test_mobile_transcriber_falls_back_to_qwen_after_doubao_failure(
    monkeypatch,
):
    calls: list[str] = []

    def fake_get(provider: str, field: str, default: str | None = None):
        values = {
            ("doubao_asr", "api_key"): "ark-asr-key",
            ("doubao_asr", "base_url"): "https://openspeech.example/api/v3",
            ("doubao_asr", "resource_id"): "volc.bigasr.auc_turbo",
            ("aliyun", "api_key"): "dashscope-key",
            ("aliyun", "asr_base_url"): "https://dashscope.example/v1",
            ("aliyun", "asr_model"): "qwen3-asr-flash",
        }
        return values.get((provider, field), default or "")

    class FakeDoubaoTranscriber:
        def __init__(self, **_kwargs):
            pass

        async def transcribe(self, **_kwargs):
            calls.append("doubao_asr")
            raise SpeechTranscriptionError(
                "豆包语音资源未开通",
                allow_fallback=True,
            )

    class FakeAliyunTranscriber:
        def __init__(self, **_kwargs):
            pass

        async def transcribe(self, **_kwargs):
            calls.append("aliyun")
            return SpeechTranscriptionResult(
                transcript="帮我查订单",
                language="zh",
                provider="aliyun",
                model="qwen3-asr-flash",
            )

    monkeypatch.setattr(provider_config, "get", fake_get)
    monkeypatch.setattr(
        speech_transcription,
        "DoubaoSpeechTranscriber",
        FakeDoubaoTranscriber,
        raising=False,
    )
    monkeypatch.setattr(
        speech_transcription,
        "AliyunSpeechTranscriber",
        FakeAliyunTranscriber,
    )

    result = await transcribe_mobile_audio(
        audio=b"audio",
        content_type="audio/wav",
        filename="voice.wav",
    )

    assert calls == ["doubao_asr", "aliyun"]
    assert result.provider == "aliyun"


@pytest.mark.asyncio
async def test_mobile_transcriber_does_not_fallback_for_invalid_audio(
    monkeypatch,
):
    calls: list[str] = []

    def fake_get(provider: str, field: str, default: str | None = None):
        values = {
            ("doubao_asr", "api_key"): "ark-asr-key",
            ("doubao_asr", "base_url"): "https://openspeech.example/api/v3",
            ("doubao_asr", "resource_id"): "volc.bigasr.auc_turbo",
        }
        return values.get((provider, field), default or "")

    class FakeDoubaoTranscriber:
        def __init__(self, **_kwargs):
            pass

        async def transcribe(self, **_kwargs):
            calls.append("doubao_asr")
            raise SpeechTranscriptionError(
                "音频格式无效",
                allow_fallback=False,
            )

    class FakeAliyunTranscriber:
        def __init__(self, **_kwargs):
            calls.append("aliyun")

        async def transcribe(self, **_kwargs):
            raise AssertionError("输入错误不应触发二次转写")

    monkeypatch.setattr(provider_config, "get", fake_get)
    monkeypatch.setattr(
        speech_transcription,
        "DoubaoSpeechTranscriber",
        FakeDoubaoTranscriber,
        raising=False,
    )
    monkeypatch.setattr(
        speech_transcription,
        "AliyunSpeechTranscriber",
        FakeAliyunTranscriber,
    )

    with pytest.raises(SpeechTranscriptionError, match="音频格式无效"):
        await transcribe_mobile_audio(
            audio=b"invalid",
            content_type="audio/wav",
            filename="voice.wav",
        )

    assert calls == ["doubao_asr"]


@pytest.mark.asyncio
async def test_aliyun_transcriber_rejects_missing_key_and_audio():
    with pytest.raises(SpeechTranscriptionError, match="尚未配置"):
        await AliyunSpeechTranscriber(
            api_key="",
            base_url="https://dashscope.example/v1",
            model="qwen3-asr-flash",
        ).transcribe(
            audio=b"audio",
            content_type="audio/wav",
            filename="voice.wav",
        )

    with pytest.raises(SpeechTranscriptionError, match="没有收到"):
        await AliyunSpeechTranscriber(
            api_key="test-key",
            base_url="https://dashscope.example/v1",
            model="qwen3-asr-flash",
        ).transcribe(
            audio=b"",
            content_type="audio/wav",
            filename="voice.wav",
        )


@pytest.mark.asyncio
async def test_aliyun_transcriber_maps_provider_failures_to_safe_errors():
    async def call_with_handler(handler):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
        ) as client:
            transcriber = AliyunSpeechTranscriber(
                api_key="test-key",
                base_url="https://dashscope.example/v1",
                model="qwen3-asr-flash",
                client=client,
            )
            return await transcriber.transcribe(
                audio=b"audio",
                content_type="audio/wav",
                filename="voice.wav",
            )

    with pytest.raises(SpeechTranscriptionError, match="识别失败"):
        await call_with_handler(
            lambda _request: httpx.Response(500, json={"error": "upstream"})
        )

    with pytest.raises(SpeechTranscriptionError, match="格式异常"):
        await call_with_handler(
            lambda _request: httpx.Response(200, content=b"not-json")
        )

    def network_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(SpeechTranscriptionError, match="暂时不可用"):
        await call_with_handler(network_error)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"choices": [{"message": {"content": {"text": "文本一"}}}]}, "文本一"),
        (
            {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"text": "文本"},
                                {"transcript": "二"},
                            ]
                        }
                    }
                ]
            },
            "文本二",
        ),
        ({"choices": [{"message": {"transcript": "文本三"}}]}, "文本三"),
        ({"output": {"transcript": "文本四"}}, "文本四"),
    ],
)
def test_aliyun_extracts_supported_result_shapes(body, expected):
    assert speech_transcription._extract_transcript(body) == expected


@pytest.mark.asyncio
async def test_doubao_transcriber_validates_required_inputs():
    with pytest.raises(SpeechTranscriptionError, match="尚未配置") as missing_key:
        await speech_transcription.DoubaoSpeechTranscriber(
            api_key="",
            base_url="https://openspeech.example/api/v3",
            resource_id="volc.bigasr.auc_turbo",
        ).transcribe(
            audio=WAV_AUDIO,
            content_type="audio/wav",
            filename="voice.wav",
        )
    assert missing_key.value.allow_fallback is True

    with pytest.raises(SpeechTranscriptionError, match="资源尚未配置") as missing_resource:
        await speech_transcription.DoubaoSpeechTranscriber(
            api_key="key",
            base_url="https://openspeech.example/api/v3",
            resource_id="",
        ).transcribe(
            audio=WAV_AUDIO,
            content_type="audio/wav",
            filename="voice.wav",
        )
    assert missing_resource.value.allow_fallback is True

    with pytest.raises(SpeechTranscriptionError, match="没有收到"):
        await speech_transcription.DoubaoSpeechTranscriber(
            api_key="key",
            base_url="https://openspeech.example/api/v3",
            resource_id="volc.bigasr.auc_turbo",
        ).transcribe(
            audio=b"",
            content_type="audio/wav",
            filename="voice.wav",
        )


@pytest.mark.asyncio
async def test_doubao_mp3_is_uploaded_without_transcoding(monkeypatch):
    captured: dict = {}

    async def unexpected_transcode(*_args, **_kwargs):
        raise AssertionError("MP3 不应再次转码")

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"x-api-status-code": "20000000"},
            json={"result": {"text": "查看商品"}},
        )

    monkeypatch.setattr(
        speech_transcription,
        "_transcode_audio_to_wav",
        unexpected_transcode,
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        await speech_transcription.DoubaoSpeechTranscriber(
            api_key="key",
            base_url="https://openspeech.example/api/v3",
            resource_id="volc.bigasr.auc_turbo",
            client=client,
        ).transcribe(
            audio=b"ID3-mp3",
            content_type="audio/mpeg",
            filename="voice.mp3",
        )

    assert captured["payload"]["audio"]["format"] == "mp3"
    assert captured["payload"]["audio"]["data"] == base64.b64encode(
        b"ID3-mp3"
    ).decode()


@pytest.mark.asyncio
async def test_doubao_network_failures_are_eligible_for_fallback():
    async def call_with_handler(handler):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
        ) as client:
            transcriber = speech_transcription.DoubaoSpeechTranscriber(
                api_key="key",
                base_url="https://openspeech.example/api/v3",
                resource_id="volc.bigasr.auc_turbo",
                client=client,
            )
            return await transcriber.transcribe(
                audio=WAV_AUDIO,
                content_type="audio/wav",
                filename="voice.wav",
            )

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(SpeechTranscriptionError, match="超时") as timed_out:
        await call_with_handler(timeout)
    assert timed_out.value.allow_fallback is True

    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(SpeechTranscriptionError, match="暂时不可用") as network:
        await call_with_handler(offline)
    assert network.value.allow_fallback is True

    with pytest.raises(SpeechTranscriptionError, match="格式异常") as malformed:
        await call_with_handler(
            lambda _request: httpx.Response(200, content=b"not-json")
        )
    assert malformed.value.allow_fallback is True


@pytest.mark.parametrize(
    ("status_code", "provider_code", "message", "fallback"),
    [
        (400, "", "暂时不可用", False),
        (429, "", "暂时不可用", True),
        (200, "20000003", "没有检测到", False),
        (200, "45000001", "参数无效", False),
        (200, "55000031", "暂时不可用", True),
        (200, "59999999", "暂时不可用", True),
        (200, "88888888", "暂时不可用", True),
    ],
)
def test_doubao_status_mapping(status_code, provider_code, message, fallback):
    response = httpx.Response(
        status_code,
        headers={"x-api-status-code": provider_code},
    )
    with pytest.raises(SpeechTranscriptionError, match=message) as error:
        speech_transcription._raise_for_doubao_response_error(response)
    assert error.value.allow_fallback is fallback


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({}, ""),
        ({"result": "invalid"}, ""),
        ({"result": {"text": "整段结果"}}, "整段结果"),
        (
            {
                "result": {
                    "utterances": [
                        {"text": "分句"},
                        {"text": "结果"},
                        {"ignored": True},
                    ]
                }
            },
            "分句结果",
        ),
    ],
)
def test_doubao_extracts_supported_result_shapes(body, expected):
    assert speech_transcription._extract_doubao_transcript(body) == expected


@pytest.mark.asyncio
async def test_doubao_rejects_invalid_transcoded_wave(monkeypatch):
    async def invalid_transcode(*_args, **_kwargs):
        return b"not-a-wave"

    monkeypatch.setattr(
        speech_transcription,
        "_transcode_audio_to_wav",
        invalid_transcode,
    )

    with pytest.raises(SpeechTranscriptionError, match="无法读取"):
        await speech_transcription._prepare_doubao_audio(
            b"m4a",
            "audio/mp4",
        )


def test_ffmpeg_executable_prefers_system_binary(monkeypatch):
    monkeypatch.setattr(
        speech_transcription.shutil,
        "which",
        lambda _name: "C:/tools/ffmpeg.exe",
    )

    assert (
        speech_transcription._ffmpeg_executable()
        == "C:/tools/ffmpeg.exe"
    )


@pytest.mark.asyncio
async def test_transcoder_rejects_unreadable_audio(monkeypatch):
    class FailedProcess:
        returncode = 1

        async def communicate(self, input=None):
            return b"", b"decode failed"

    async def fake_subprocess(*_args, **_kwargs):
        return FailedProcess()

    monkeypatch.setattr(
        speech_transcription,
        "_ffmpeg_executable",
        lambda: "ffmpeg",
    )
    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        fake_subprocess,
    )

    with pytest.raises(SpeechTranscriptionError, match="录音格式无效"):
        await speech_transcription._transcode_audio_to_wav(
            b"broken",
            "audio/mp4",
        )


@pytest.mark.asyncio
async def test_transcoder_maps_timeout_to_safe_error(monkeypatch):
    class HangingProcess:
        killed = False

        async def communicate(self, input=None):
            return b"", b""

        def kill(self):
            self.killed = True

        async def wait(self):
            return 0

    process = HangingProcess()

    async def fake_subprocess(*_args, **_kwargs):
        return process

    async def fake_wait_for(awaitable, **_kwargs):
        awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(
        speech_transcription,
        "_ffmpeg_executable",
        lambda: "ffmpeg",
    )
    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        fake_subprocess,
    )
    monkeypatch.setattr(asyncio, "wait_for", fake_wait_for)

    with pytest.raises(SpeechTranscriptionError, match="转换超时"):
        await speech_transcription._transcode_audio_to_wav(
            b"slow",
            "audio/mp4",
        )
    assert process.killed is True
