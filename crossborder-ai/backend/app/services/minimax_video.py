"""MiniMax H3 视频生成 Provider。"""

import base64
import hashlib
import math
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.services import provider_config


MODEL_CONFIGS: dict[str, dict[str, Any]] = {
    "MiniMax-H3": {
        "min_duration": 4,
        "max_duration": 15,
        "prices_per_second": {"768P": 0.5, "2K": 0.8},
        "credits_per_second": {"768P": 10.0, "2K": 15.0},
    },
    "MiniMax-H3-Highspeed": {
        "min_duration": 4,
        "max_duration": 15,
        "prices_per_second": {"480P": 0.26, "768P": 0.4},
        "credits_per_second": {"480P": 5.0, "768P": 7.5},
    },
    "MiniMax-H3-Lite": {
        "min_duration": 4,
        "max_duration": 15,
        "prices_per_second": {"480P": 0.16, "768P": 0.26},
        "credits_per_second": {"480P": 3.0, "768P": 4.5},
    },
    "MiniMax-H3-Max": {
        "min_duration": 5,
        "max_duration": 15,
        "prices_per_second": {"480P": 0.33, "768P": 0.5},
        "credits_per_second": {"480P": 8.0, "768P": 12.5},
    },
}
MAX_MULTI_IMAGE_PAYLOAD_BYTES = 60 * 1024 * 1024

VIDEO_TEMPLATES = (
    {
        "id": "clean_product",
        "name": "纯净商品动态",
        "description": "镜头缓慢推进，突出商品外观、材质和光影。",
        "prompt_suffix": "Premium product hero shot, slow camera push-in, clean background, realistic light and material.",
    },
    {
        "id": "feature_focus",
        "name": "卖点聚焦",
        "description": "轻微环绕和局部视差，为字幕与卖点留出画面空间。",
        "prompt_suffix": "Short-form ecommerce product shot, gentle orbit and parallax, clear negative space for captions.",
    },
    {
        "id": "campaign_cta",
        "name": "促销广告",
        "description": "节奏更明快，适合价格、折扣和 CTA 叠加。",
        "prompt_suffix": "Promotional product commercial, confident camera movement, dynamic lighting, space for price and CTA.",
    },
)

PRODUCT_LOCK_PROMPT = """
PRODUCT CONSISTENCY LOCK:
- Keep the product shape, geometry, proportions, color, material, structure, logo, package text and labels exactly unchanged.
- Do not add, remove or redesign any product part.
- Only animate camera movement, lighting, background, reflections and subtle environmental motion.
- No morphing, melting, reassembly, extra accessories or invented product features.
""".strip()


@dataclass
class MiniMaxVideoRequest:
    url: str
    headers: dict[str, str]
    body: dict[str, Any]


def get_minimax_video_config() -> dict[str, str]:
    api_key = provider_config.get(
        "minimax",
        "api_key",
        settings.MINIMAX_API_KEY or "",
    )
    return {
        "api_key": api_key,
        "base_url": provider_config.get(
            "minimax",
            "base_url",
            settings.MINIMAX_VIDEO_BASE_URL,
        ).rstrip("/"),
        "model": provider_config.get(
            "minimax",
            "model",
            settings.MINIMAX_VIDEO_MODEL,
        ),
        "resolution": provider_config.get(
            "minimax",
            "resolution",
            settings.MINIMAX_VIDEO_RESOLUTION,
        ),
    }


def get_minimax_video_capabilities(api_key: str | None = None) -> dict[str, Any]:
    config = get_minimax_video_config()
    models = []
    for model_id, model in MODEL_CONFIGS.items():
        prices = model["prices_per_second"]
        credit_rates = model["credits_per_second"]
        models.append(
            {
                "id": model_id,
                "min_duration": model["min_duration"],
                "max_duration": model["max_duration"],
                "resolutions": list(prices.keys()),
                "prices_per_second": prices,
                "credits_per_second": credit_rates,
            }
        )
    return {
        "enabled": bool(api_key if api_key is not None else config["api_key"]),
        "provider": "minimax",
        "default_model": config["model"],
        "default_resolution": config["resolution"],
        "models": models,
        "templates": list(VIDEO_TEMPLATES),
    }


def _validate_selection(model: str, resolution: str, duration: int) -> tuple[dict[str, Any], float]:
    model_config = MODEL_CONFIGS.get(model)
    if not model_config:
        raise ValueError("视频模型不支持")
    duration = int(duration)
    if duration < model_config["min_duration"] or duration > model_config["max_duration"]:
        raise ValueError(
            f"视频时长必须在 {model_config['min_duration']}-{model_config['max_duration']} 秒"
        )
    price = model_config["prices_per_second"].get(resolution)
    if price is None:
        raise ValueError(f"{model} 不支持 {resolution}")
    return model_config, float(price)


def estimate_video_cost_micros(model: str, resolution: str, duration: int) -> int:
    _, price = _validate_selection(model, resolution, duration)
    return round(price * int(duration) * 1_000_000)


def estimate_video_credits(model: str, resolution: str, duration: int) -> int:
    model_config, _ = _validate_selection(model, resolution, duration)
    rate = model_config["credits_per_second"].get(resolution)
    if rate is None:
        raise ValueError(f"{model} 不支持 {resolution}")
    return max(1, math.ceil(float(rate) * int(duration)))


def build_minimax_video_request(
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
) -> MiniMaxVideoRequest:
    """构造 H3 视频请求，首帧与多参考图使用互斥的官方角色。"""
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("缺少视频提示词")
    if len(prompt) > 7000:
        raise ValueError("视频提示词不能超过 7000 字符")
    _validate_selection(model, resolution, duration)
    references = reference_images or []
    if references and first_frame:
        raise ValueError("首帧与多参考图不能同时提交")
    if len(references) > 9:
        raise ValueError("商品参考图最多支持 9 张")
    if not first_frame and not references:
        raise ValueError("视频请求缺少商品图片")

    def image_data_uri(data: bytes, mime: str) -> str:
        if mime not in {"image/png", "image/jpeg", "image/webp"}:
            raise ValueError("图片格式不支持")
        if not data or len(data) > 30 * 1024 * 1024:
            raise ValueError("图片不能为空且不能超过 30MB")
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"

    if references:
        if ratio == "adaptive" and model == "MiniMax-H3-Lite":
            raise ValueError("H3 Lite 多参考图模式必须指定明确画幅")
        image_urls = [
            image_data_uri(data, mime)
            for data, mime in references
        ]
        # Base64 会膨胀约 33%，提前限制总载荷，避免供应商直接返回 64MB 超限。
        if sum(len(url) for url in image_urls) > MAX_MULTI_IMAGE_PAYLOAD_BYTES:
            raise ValueError("商品参考图总大小过大，请压缩后重试")
        image_content = [
            {
                "type": "image_url",
                "image_url": {"url": image_url},
                "role": "reference_image",
            }
            for image_url in image_urls
        ]
        effective_ratio = ratio
    else:
        assert first_frame is not None
        assert first_frame_mime is not None
        image_content = [
            {
                "type": "image_url",
                "image_url": {
                    "url": image_data_uri(first_frame, first_frame_mime)
                },
                "role": "first_frame",
            }
        ]
        effective_ratio = "adaptive"

    base = (base_url or settings.MINIMAX_VIDEO_BASE_URL).rstrip("/")
    return MiniMaxVideoRequest(
        url=f"{base}/v2/video_generation",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        body={
            "model": model,
            "content": [
                {"type": "text", "text": prompt},
                *image_content,
            ],
            "resolution": resolution,
            "duration": int(duration),
            "ratio": effective_ratio,
            "aigc_watermark": False,
        },
    )


def parse_minimax_submission(payload: dict[str, Any]) -> str:
    task_id = str(payload.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("视频服务没有返回任务 ID")
    return task_id


def parse_minimax_task(payload: dict[str, Any]) -> dict[str, Any]:
    task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    status = str(task.get("status") or "")
    if status in {"queued", "running"}:
        return {"status": status}
    if status in {"canceled", "cancelled"}:
        return {"status": "canceled"}
    if status == "succeeded":
        content = task.get("content") if isinstance(task.get("content"), dict) else {}
        video_url = str(content.get("url") or "").strip()
        if not video_url:
            raise ValueError("视频服务没有返回成片地址")
        return {
            "status": "succeeded",
            "video_url": video_url,
            "duration": task.get("duration"),
            "resolution": task.get("resolution"),
            "ratio": task.get("ratio"),
            "usage": task.get("usage") or {},
        }
    if status == "failed":
        error = task.get("error") if isinstance(task.get("error"), dict) else {}
        return {
            "status": "failed",
            "error": str(error.get("message") or "视频生成失败"),
            "error_code": error.get("code"),
        }
    raise ValueError("视频任务状态无法识别")


def _provider_error(status_code: int, message: str) -> ValueError:
    if status_code in {401, 403}:
        return ValueError("平台视频服务密钥无效，请联系管理员")
    if status_code == 402:
        return ValueError("平台视频服务余额不足，请联系管理员")
    if status_code == 400:
        return ValueError("视频请求参数有误，请调整素材或参数")
    if status_code == 422:
        return ValueError("视频内容未通过供应商审核，请调整素材或提示词")
    if status_code == 429:
        return ValueError("视频生成请求过于频繁，请稍后再试")
    if status_code >= 500:
        return ValueError("平台视频服务请求失败，请稍后重试")
    return ValueError(message or "平台视频服务请求失败")


async def submit_minimax_video(
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
    config = get_minimax_video_config()
    if not config["api_key"]:
        raise ValueError("平台视频服务未配置，请联系管理员")
    request = build_minimax_video_request(
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
        response = await client.post(request.url, headers=request.headers, json=request.body)
    if response.status_code >= 400:
        try:
            message = response.json().get("error", {}).get("message", "")
        except ValueError:
            message = response.text[:200]
        raise _provider_error(response.status_code, message)
    return parse_minimax_submission(response.json())


async def query_minimax_video(provider_task_id: str) -> dict[str, Any]:
    config = get_minimax_video_config()
    if not config["api_key"]:
        raise ValueError("平台视频服务未配置，请联系管理员")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{config['base_url']}/v2/query/video_generation/{quote(provider_task_id, safe='')}",
            headers={"Authorization": f"Bearer {config['api_key']}"},
        )
    if response.status_code >= 400:
        raise _provider_error(response.status_code, response.text[:200])
    return parse_minimax_task(response.json())


async def cancel_minimax_video(provider_task_id: str) -> bool:
    config = get_minimax_video_config()
    if not config["api_key"]:
        return False
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.delete(
            f"{config['base_url']}/v2/video_generation/{quote(provider_task_id, safe='')}",
            headers={"Authorization": f"Bearer {config['api_key']}"},
        )
    if response.status_code in {400, 404}:
        return False
    if response.status_code >= 500:
        raise ValueError("取消视频任务失败，请稍后重试")
    response.raise_for_status()
    return True


async def download_minimax_video(video_url: str) -> bytes:
    async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
        response = await client.get(video_url)
    if response.status_code >= 400:
        raise ValueError("视频下载失败，稍后会自动重试")
    data = response.content
    if len(data) > 200 * 1024 * 1024:
        raise ValueError("视频超过 200MB，已拒绝保存")
    if len(data) < 12 or data[4:8] != b"ftyp":
        raise ValueError("供应商返回的内容不是有效 MP4")
    return data


def video_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

