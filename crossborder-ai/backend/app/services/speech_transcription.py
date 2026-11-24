"""语音转写服务。

移动端短语音优先交给豆包录音文件极速版识别，权限或服务异常时降级到
阿里云 Qwen ASR。服务只返回转写文本，不把供应商原始响应、密钥或音频内容
写进日志。
"""

import asyncio
import base64
import json
import shutil
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.services import provider_config
from app.services.language_service import detect_language


# 静态热词只覆盖高频平台和业务字段；店铺名、商品名等动态上下文后续按请求注入。
DOUBAO_HOTWORDS = (
    "Shopify",
    "Temu",
    "TikTok Shop",
    "Amazon",
    "1688",
    "SKU",
    "ASIN",
    "FBA",
    "FBM",
    "listing",
    "妥投",
    "履约",
)


class SpeechTranscriptionError(RuntimeError):
    """可安全展示给卖家的语音转写失败。

    ``allow_fallback`` 只标记供应商级短暂故障；损坏音频、静音和参数错误必须
    保持为 ``False``，避免把同一段无效录音重复发送给另一家供应商。
    """

    def __init__(self, message: str, *, allow_fallback: bool = False):
        super().__init__(message)
        self.allow_fallback = allow_fallback


@dataclass(frozen=True)
class SpeechTranscriptionResult:
    transcript: str
    language: str
    provider: str
    model: str


class AliyunSpeechTranscriber:
    """通过 OpenAI 兼容接口调用 Qwen3 ASR。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = (
            timeout_seconds or settings.ALIYUN_ASR_TIMEOUT_SECONDS
        )
        self.client = client

    async def transcribe(
        self,
        *,
        audio: bytes,
        content_type: str,
        filename: str,
    ) -> SpeechTranscriptionResult:
        if not self.api_key:
            raise SpeechTranscriptionError("语音转写服务尚未配置")
        if not audio:
            raise SpeechTranscriptionError("没有收到有效语音")

        mime = (
            content_type
            if content_type.startswith("audio/")
            else "application/octet-stream"
        )
        encoded = base64.b64encode(audio).decode("ascii")
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": f"data:{mime};base64,{encoded}",
                            },
                        }
                    ],
                }
            ],
            "stream": False,
            "asr_options": {"enable_lid": True},
        }
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(
            timeout=self.timeout_seconds,
        )
        try:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.HTTPError:
            raise SpeechTranscriptionError(
                "语音识别服务暂时不可用，请稍后重试"
            ) from None
        finally:
            if owns_client:
                await client.aclose()

        if response.status_code >= 400:
            raise SpeechTranscriptionError("语音识别失败，请重新录制")
        try:
            body = response.json()
        except ValueError as exc:
            raise SpeechTranscriptionError("语音识别结果格式异常") from exc
        transcript = _extract_transcript(body).strip()
        if not transcript:
            raise SpeechTranscriptionError("没有识别到清晰的语音内容")
        return SpeechTranscriptionResult(
            transcript=transcript,
            language=detect_language(transcript),
            provider="aliyun",
            model=self.model,
        )


class DoubaoSpeechTranscriber:
    """通过录音文件极速版接口调用豆包大模型 ASR。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        resource_id: str,
        timeout_seconds: float | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.resource_id = resource_id.strip()
        self.timeout_seconds = (
            timeout_seconds or settings.DOUBAO_ASR_TIMEOUT_SECONDS
        )
        self.client = client

    async def transcribe(
        self,
        *,
        audio: bytes,
        content_type: str,
        filename: str,
    ) -> SpeechTranscriptionResult:
        if not self.api_key:
            raise SpeechTranscriptionError(
                "语音转写服务尚未配置",
                allow_fallback=True,
            )
        if not self.resource_id:
            raise SpeechTranscriptionError(
                "豆包语音识别资源尚未配置",
                allow_fallback=True,
            )
        if not audio:
            raise SpeechTranscriptionError("没有收到有效语音")

        normalized_audio, audio_format = await _prepare_doubao_audio(
            audio,
            content_type,
        )
        encoded = base64.b64encode(normalized_audio).decode("ascii")
        context = json.dumps(
            {
                "hotwords": [
                    {"word": word} for word in DOUBAO_HOTWORDS
                ]
            },
            ensure_ascii=False,
        )
        payload = {
            "user": {"uid": "veya-mobile"},
            "audio": {
                "format": audio_format,
                "data": encoded,
            },
            "request": {
                "model_name": "bigmodel",
                "corpus": {"context": context},
            },
        }
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(
            timeout=self.timeout_seconds,
        )
        try:
            response = await client.post(
                f"{self.base_url}/auc/bigmodel/recognize/flash",
                headers={
                    "X-Api-Key": self.api_key,
                    "X-Api-Resource-Id": self.resource_id,
                    "X-Api-Request-Id": str(uuid.uuid4()),
                    "X-Api-Sequence": "-1",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.TimeoutException:
            raise SpeechTranscriptionError(
                "豆包语音识别超时",
                allow_fallback=True,
            ) from None
        except httpx.HTTPError:
            raise SpeechTranscriptionError(
                "豆包语音识别暂时不可用",
                allow_fallback=True,
            ) from None
        finally:
            if owns_client:
                await client.aclose()

        _raise_for_doubao_response_error(response)
        try:
            body = response.json()
        except ValueError as exc:
            raise SpeechTranscriptionError(
                "豆包语音识别结果格式异常",
                allow_fallback=True,
            ) from exc
        transcript = _extract_doubao_transcript(body).strip()
        if not transcript:
            raise SpeechTranscriptionError("没有识别到清晰的语音内容")
        return SpeechTranscriptionResult(
            transcript=transcript,
            language=detect_language(transcript),
            provider="doubao_asr",
            model=self.resource_id,
        )


async def _prepare_doubao_audio(
    audio: bytes,
    content_type: str,
) -> tuple[bytes, str]:
    """把极速版不支持的移动端录音格式转为 16k 单声道 WAV。"""

    mime = (content_type or "").split(";", 1)[0].lower().strip()
    if mime in {"audio/wav", "audio/x-wav"}:
        return audio, "wav"
    if mime == "audio/mpeg":
        return audio, "mp3"
    converted = await _transcode_audio_to_wav(audio, mime)
    if (
        len(converted) < 12
        or converted[:4] != b"RIFF"
        or converted[8:12] != b"WAVE"
    ):
        raise SpeechTranscriptionError("无法读取录音内容")
    return converted, "wav"


def _ffmpeg_executable() -> str:
    """优先使用系统 FFmpeg，缺失时使用项目内置的静态版本。"""

    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        raise SpeechTranscriptionError(
            "服务器缺少音频转换组件",
            allow_fallback=True,
        ) from None


async def _transcode_audio_to_wav(audio: bytes, content_type: str) -> bytes:
    """流式调用 FFmpeg，不落临时文件，避免残留用户原始录音。"""

    try:
        process = await asyncio.create_subprocess_exec(
            _ffmpeg_executable(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            "pipe:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "wav",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise SpeechTranscriptionError(
            "音频转换组件暂时不可用",
            allow_fallback=True,
        ) from exc
    try:
        stdout, _stderr = await asyncio.wait_for(
            process.communicate(input=audio),
            timeout=settings.DOUBAO_ASR_TRANSCODE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.wait()
        raise SpeechTranscriptionError("音频转换超时，请重新录制") from exc
    if process.returncode != 0 or not stdout:
        # FFmpeg 无法解码通常意味着文件损坏或伪装了 MIME，不做供应商重试。
        raise SpeechTranscriptionError("录音格式无效，请重新录制")
    return stdout


def _raise_for_doubao_response_error(response: httpx.Response) -> None:
    """把豆包状态码转换成可分级的安全错误，不保留原始响应正文。"""

    if response.status_code >= 400:
        allow_fallback = (
            response.status_code in {401, 403, 408, 425, 429}
            or response.status_code >= 500
        )
        raise SpeechTranscriptionError(
            "豆包语音识别暂时不可用",
            allow_fallback=allow_fallback,
        )

    status_code = (response.headers.get("x-api-status-code") or "").strip()
    if not status_code or status_code == "20000000":
        return
    if status_code in {"20000003", "45000002"}:
        raise SpeechTranscriptionError("没有检测到清晰的人声")
    if status_code in {"45000001", "45000151"}:
        raise SpeechTranscriptionError("录音格式或识别参数无效")
    if status_code.startswith("550") or status_code.startswith("500"):
        raise SpeechTranscriptionError(
            "豆包语音识别暂时不可用",
            allow_fallback=True,
        )
    # 未知业务错误以可恢复处理，确保语音入口不会因单个供应商变更而中断。
    raise SpeechTranscriptionError(
        "豆包语音识别暂时不可用",
        allow_fallback=True,
    )


def _extract_doubao_transcript(body: dict[str, Any]) -> str:
    """兼容极速版的整段文本和分句结果。"""

    result = body.get("result")
    if not isinstance(result, dict):
        return ""
    text = result.get("text")
    if isinstance(text, str):
        return text
    utterances = result.get("utterances")
    if not isinstance(utterances, list):
        return ""
    parts = [
        item["text"]
        for item in utterances
        if isinstance(item, dict) and isinstance(item.get("text"), str)
    ]
    return "".join(parts)


def _extract_transcript(body: dict[str, Any]) -> str:
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        message = (choices[0] or {}).get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            text = content.get("text") or content.get("transcript")
            if isinstance(text, str):
                return text
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text") or item.get("transcript")
                    if isinstance(text, str):
                        parts.append(text)
            if parts:
                return "".join(parts)
        message_text = message.get("transcript")
        if isinstance(message_text, str):
            return message_text
    output = body.get("output")
    if isinstance(output, dict):
        output_text = output.get("text") or output.get("transcript")
        if isinstance(output_text, str):
            return output_text
    return ""


async def transcribe_mobile_audio(
    *,
    audio: bytes,
    content_type: str,
    filename: str,
) -> SpeechTranscriptionResult:
    """用运行时配置优先转写，并在供应商级故障时安全降级。"""

    doubao_api_key = provider_config.get("doubao_asr", "api_key")
    if doubao_api_key.strip():
        doubao = DoubaoSpeechTranscriber(
            api_key=doubao_api_key,
            base_url=provider_config.get(
                "doubao_asr",
                "base_url",
                settings.DOUBAO_ASR_BASE_URL,
            ),
            resource_id=provider_config.get(
                "doubao_asr",
                "resource_id",
                settings.DOUBAO_ASR_RESOURCE_ID,
            ),
        )
        try:
            return await doubao.transcribe(
                audio=audio,
                content_type=content_type,
                filename=filename,
            )
        except SpeechTranscriptionError as exc:
            if not exc.allow_fallback:
                raise

    transcriber = AliyunSpeechTranscriber(
        api_key=provider_config.get("aliyun", "api_key"),
        base_url=provider_config.get(
            "aliyun",
            "asr_base_url",
            settings.ALIYUN_ASR_BASE_URL,
        ),
        model=provider_config.get(
            "aliyun",
            "asr_model",
            settings.ALIYUN_ASR_MODEL,
        ),
    )
    return await transcriber.transcribe(
        audio=audio,
        content_type=content_type,
        filename=filename,
    )
