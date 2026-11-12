"""即梦 / Seedance 火山方舟视频 Provider。"""

import base64
import math
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.services import provider_config


SEEDANCE_1_5_PRO = "doubao-seedance-1-5-pro-251215"
SEEDANCE_2_MINI = "doubao-seedance-2-0-mini-260615"
SEEDANCE_2_FAST = "doubao-seedance-2-0-fast-260128"
SEEDANCE_2_STANDARD = "doubao-seedance-2-0-260128"
SEEDANCE_2_5 = "doubao-seedance-2-5-260628"
DEFAULT_MODEL = SEEDANCE_2_STANDARD

MODEL_CONFIGS: dict[str, dict[str, Any]] = {
    SEEDANCE_1_5_PRO: {
        "label": "Seedance 1.5 Pro",
        "min_duration": 4,
        "max_duration": 12,
        "max_reference_images": 4,
        "supports_audio": True,
        "prices_per_second": {
            "480P": 0.40,
            "720P": 0.86,
            "1080P": 1.94,
        },
        "credits_per_second": {
            "480P": 12.0,
            "720P": 18.0,
            "1080P": 28.0,
        },
    },
    SEEDANCE_2_MINI: {
        "label": "Seedance 2.0 Mini",
        "min_duration": 4,
        "max_duration": 15,
        "max_reference_images": 9,
        "supports_audio": True,
        "prices_per_second": {
            "480P": 0.2311,
            "720P": 0.4970,
        },
        "credits_per_second": {
            "480P": 5.0,
            "720P": 9.0,
        },
    },
    SEEDANCE_2_FAST: {
        "label": "Seedance 2.0 Fast",
        "min_duration": 4,
        "max_duration": 15,
        "max_reference_images": 9,
        "supports_audio": True,
        "prices_per_second": {
            "480P": 0.3717,
            "720P": 0.7992,
        },
        "credits_per_second": {
            "480P": 7.0,
            "720P": 15.0,
        },
    },
    SEEDANCE_2_STANDARD: {
        "label": "Seedance 2.0 Standard",
        "min_duration": 4,
        "max_duration": 15,
        "max_reference_images": 9,
        "supports_audio": True,
        "prices_per_second": {
            "480P": 0.4621,
            "720P": 0.9936,
            "1080P": 2.2361,
        },
        "credits_per_second": {
            "480P": 9.0,
            "720P": 19.0,
            "1080P": 44.0,
        },
    },
    SEEDANCE_2_5: {
        "label": "Seedance 2.5 Pro",
        "min_duration": 4,
        "max_duration": 30,
        "max_reference_images": 30,
        "supports_audio": True,
        "prices_per_second": {
            "480P": 0.6725,
            "720P": 1.5120,
            "1080P": 3.7422,
        },
        "credits_per_second": {
            "480P": 14.0,
            "720P": 31.0,
            "1080P": 68.0,
        },
    },
}


@dataclass
class JimengVideoRequest:
    url: str
    headers: dict[str, str]
    body: dict[str, Any]


def get_jimeng_video_config() -> dict[str, str]:
    """读取即梦运行时配置，支持环境变量和后台加密配置。"""
    return {
        "api_key": provider_config.get(
            "jimeng",
            "api_key",
            settings.JIMENG_API_KEY or "",
        ),
        "base_url": provider_config.get(
            "jimeng",
            "base_url",
            settings.JIMENG_VIDEO_BASE_URL,
        ).rstrip("/"),
        "model": provider_config.get(
            "jimeng",
            "model",
            settings.JIMENG_VIDEO_MODEL,
        ),
        "resolution": provider_config.get(
            "jimeng",
            "resolution",
            settings.JIMENG_VIDEO_RESOLUTION,
        ),
    }


def _model_config(model: str) -> dict[str, Any]:
    """返回模型能力；自定义接入点按默认 2.0 Standard 处理。"""
    config = MODEL_CONFIGS.get(model)
    if config is not None:
        return config
    if str(model).startswith("ep-"):
        return MODEL_CONFIGS[DEFAULT_MODEL]
    raise ValueError("即梦视频模型不支持")


def _normalize_resolution(resolution: str) -> str:
    value = str(resolution or "").strip().upper()
    if value not in {"480P", "720P", "1080P"}:
        raise ValueError("即梦仅支持 480P、720P 或 1080P")
    return value


def get_jimeng_video_capabilities(api_key: str | None = None) -> dict[str, Any]:
    """返回即梦模型能力和平台积分基准。"""
    config = get_jimeng_video_config()
    models = []
    for model_id, model in MODEL_CONFIGS.items():
        models.append(
            {
                "id": model_id,
                "label": model["label"],
                "min_duration": model["min_duration"],
                "max_duration": model["max_duration"],
                "max_reference_images": model["max_reference_images"],
                "supports_audio": model["supports_audio"],
                "resolutions": list(model["prices_per_second"]),
                "prices_per_second": model["prices_per_second"],
                "credits_per_second": model["credits_per_second"],
            }
        )
    return {
        "enabled": bool(api_key if api_key is not None else config["api_key"]),
        "provider": "jimeng",
        "default_model": config["model"],
        "default_resolution": _normalize_resolution(config["resolution"]),
        "models": models,
    }


def build_jimeng_video_request(
    *,
    api_key: str,
    prompt: str,
    model: str,
    resolution: str,
    duration: int,
    ratio: str,
    first_frame: bytes | None = None,
    first_frame_mime: str | None = None,
    reference_images: list[tuple[bytes, str]] | None = None,
    base_url: str | None = None,
) -> JimengVideoRequest:
    """构造 Seedance 官方内容生成任务请求。"""
    prompt = str(prompt or "").strip()
    if not prompt:
        raise ValueError("缺少视频提示词")
    if len(prompt) > 7000:
        raise ValueError("视频提示词不能超过 7000 字符")

    model_config = _model_config(model)
    duration = int(duration)
    if duration < model_config["min_duration"] or duration > model_config["max_duration"]:
        raise ValueError(
            f"即梦视频时长必须在 {model_config['min_duration']}-"
            f"{model_config['max_duration']} 秒"
        )
    normalized_resolution = _normalize_resolution(resolution)
    if normalized_resolution not in model_config["prices_per_second"]:
        raise ValueError(f"即梦模型不支持 {normalized_resolution}")
    if not str(ratio or "").strip():
        raise ValueError("即梦视频缺少画幅")

    references = reference_images or []
    if references and first_frame:
        raise ValueError("首帧与多参考图不能同时提交")
    if not first_frame and not references:
        raise ValueError("视频请求缺少商品图片")
    max_references = int(model_config["max_reference_images"])
    if len(references) > max_references:
        raise ValueError(f"当前即梦模型最多支持 {max_references} 张参考图")

    def image_data_uri(data: bytes, mime: str) -> str:
        if mime not in {"image/png", "image/jpeg", "image/webp"}:
            raise ValueError("图片格式不支持")
        if not data or len(data) > 30 * 1024 * 1024:
            raise ValueError("图片不能为空且不能超过 30MB")
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    if references:
        content.extend(
            {
                "type": "image_url",
                "image_url": {"url": image_data_uri(data, mime)},
                "role": "reference_image",
            }
            for data, mime in references
        )
    else:
        assert first_frame is not None
        assert first_frame_mime is not None
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": image_data_uri(first_frame, first_frame_mime)
                },
                "role": "first_frame",
            }
        )

    base = (base_url or settings.JIMENG_VIDEO_BASE_URL).rstrip("/")
    return JimengVideoRequest(
        url=f"{base}/contents/generations/tasks",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        body={
            "model": model,
            "content": content,
            "resolution": normalized_resolution.lower(),
            "duration": duration,
            "ratio": str(ratio).strip(),
            "watermark": False,
            "generate_audio": False,
        },
    )


def parse_jimeng_submission(payload: dict[str, Any]) -> str:
    task_id = str(payload.get("id") or "").strip()
    if not task_id:
        raise ValueError("即梦视频服务没有返回任务 ID")
    return task_id


def parse_jimeng_task(payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status") or "").strip().lower()
    if status in {"queued", "running"}:
        return {"status": status}
    if status in {"cancelled", "canceled"}:
        return {"status": "canceled"}
    if status == "succeeded":
        content = payload.get("content") if isinstance(payload.get("content"), dict) else {}
        video_url = str(content.get("video_url") or "").strip()
        if not video_url:
            raise ValueError("即梦视频服务没有返回成片地址")
        return {
            "status": "succeeded",
            "video_url": video_url,
            "duration": payload.get("duration"),
        }
    if status in {"failed", "expired"}:
        error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        message = str(error.get("message") or "即梦视频生成失败")
        code = str(error.get("code") or "").strip()
        return {
            "status": "failed",
            "error": f"{message}（{code}）" if code else message,
            "error_code": code or None,
        }
    raise ValueError("即梦视频任务状态无法识别")


def estimate_jimeng_cost_micros(model: str, resolution: str, duration: int) -> int:
    config = _model_config(model)
    normalized = _normalize_resolution(resolution)
    price = float(config["prices_per_second"][normalized])
    return round(price * int(duration) * 1_000_000)


def estimate_jimeng_credits(model: str, resolution: str, duration: int) -> int:
    config = _model_config(model)
    normalized = _normalize_resolution(resolution)
    rate = float(config["credits_per_second"][normalized])
    return max(1, math.ceil(rate * int(duration)))


def _provider_error(status_code: int, message: str = "") -> ValueError:
    if status_code in {401, 403}:
        return ValueError("即梦视频服务密钥无效，请联系管理员")
    if status_code == 402:
        return ValueError("即梦视频服务余额不足，请联系管理员")
    if status_code == 400:
        return ValueError("即梦视频请求参数有误，请调整素材或参数")
    if status_code == 422:
        return ValueError("即梦视频内容未通过供应商审核，请调整素材或提示词")
    if status_code == 429:
        return ValueError("即梦视频生成请求过于频繁，请稍后再试")
    if status_code >= 500:
        return ValueError("即梦视频服务请求失败，请稍后重试")
    return ValueError(message or "即梦视频服务请求失败")


def _response_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200]
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or "")
    return str(payload.get("message") or "") if isinstance(payload, dict) else ""


async def submit_jimeng_video(
    *,
    prompt: str,
    model: str,
    resolution: str,
    duration: int,
    ratio: str,
    first_frame: bytes | None = None,
    first_frame_mime: str | None = None,
    reference_images: list[tuple[bytes, str]] | None = None,
) -> str:
    """提交 Seedance 任务并返回方舟任务 ID。"""
    config = get_jimeng_video_config()
    if not config["api_key"]:
        raise ValueError("即梦视频服务未配置，请联系管理员")
    request = build_jimeng_video_request(
        api_key=config["api_key"],
        prompt=prompt,
        model=model,
        resolution=resolution,
        duration=duration,
        ratio=ratio,
        first_frame=first_frame,
        first_frame_mime=first_frame_mime,
        reference_images=reference_images,
        base_url=config["base_url"],
    )
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            request.url,
            headers=request.headers,
            json=request.body,
        )
    if response.status_code >= 400:
        raise _provider_error(
            response.status_code,
            _response_error_message(response),
        )
    return parse_jimeng_submission(response.json())


async def query_jimeng_video(provider_task_id: str) -> dict[str, Any]:
    """查询 Seedance 异步任务并归一状态。"""
    config = get_jimeng_video_config()
    if not config["api_key"]:
        raise ValueError("即梦视频服务未配置，请联系管理员")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{config['base_url']}/contents/generations/tasks/"
            f"{quote(provider_task_id, safe='')}",
            headers={"Authorization": f"Bearer {config['api_key']}"},
        )
    if response.status_code >= 400:
        raise _provider_error(
            response.status_code,
            _response_error_message(response),
        )
    return parse_jimeng_task(response.json())


async def cancel_jimeng_video(provider_task_id: str) -> bool:
    """取消方舟任务；已结束或不存在的任务返回 False。"""
    config = get_jimeng_video_config()
    if not config["api_key"]:
        return False
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.delete(
            f"{config['base_url']}/contents/generations/tasks/"
            f"{quote(provider_task_id, safe='')}",
            headers={"Authorization": f"Bearer {config['api_key']}"},
        )
    if response.status_code in {400, 404, 409}:
        return False
    if response.status_code >= 500:
        raise ValueError("取消即梦视频任务失败，请稍后重试")
    response.raise_for_status()
    return True


async def download_jimeng_video(video_url: str) -> bytes:
    """下载签名成片并校验 MP4 文件头。"""
    async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
        response = await client.get(video_url)
    if response.status_code >= 400:
        raise ValueError("即梦视频下载失败，稍后会自动重试")
    data = response.content
    if len(data) > 200 * 1024 * 1024:
        raise ValueError("视频超过 200MB，已拒绝保存")
    if len(data) < 12 or data[4:8] != b"ftyp":
        raise ValueError("即梦供应商返回的内容不是有效 MP4")
    return data
