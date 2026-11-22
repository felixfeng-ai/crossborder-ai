"""语音转写服务。

移动端上传的短语音直接交给阿里云百炼 Qwen ASR。服务只返回转写文本，
不把供应商原始响应、密钥或音频内容写进日志。
"""

import base64
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.services import provider_config
from app.services.language_service import detect_language


class SpeechTranscriptionError(RuntimeError):
    """可安全展示给卖家的语音转写失败。"""


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
        except httpx.HTTPError as exc:
            raise SpeechTranscriptionError(
                "语音识别服务暂时不可用，请稍后重试"
            ) from exc
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
    """用运行时配置创建转写器，便于管理端轮换凭据和模型。"""

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
