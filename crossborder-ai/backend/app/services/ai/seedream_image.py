"""火山方舟 Seedream 图片生成直连服务。"""

import base64
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.services import provider_config


@dataclass(frozen=True)
class SeedreamImageRequest:
    url: str
    headers: dict[str, str]
    body: dict[str, Any]


def get_seedream_image_config() -> dict[str, str]:
    """读取 Seedream 配置；未单独配置 Key 时复用即梦 Ark Key。"""
    return {
        "api_key": provider_config.get("seedream", "api_key", ""),
        "base_url": provider_config.get("seedream", "base_url", "").rstrip("/"),
        "model": provider_config.get(
            "seedream",
            "model",
            settings.SEEDREAM_IMAGE_MODEL,
        ),
    }


def _quality_size(quality_tier: str) -> str:
    """Seedream 4.0 支持 1K、2K、4K 三档原生输出。"""
    return {
        "fast": "1K",
        "standard": "2K",
        "hd": "4K",
    }.get(quality_tier, "2K")


def _image_data_uri(data: bytes, mime: str) -> str:
    if mime not in {"image/png", "image/jpeg", "image/webp", "image/bmp"}:
        raise ValueError("Seedream 参考图格式不支持")
    if not data:
        raise ValueError("Seedream 参考图不能为空")
    if len(data) > 10 * 1024 * 1024:
        raise ValueError("Seedream 单张参考图不能超过 10MB")
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def build_seedream_image_request(
    *,
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
    reference_images: list[tuple[bytes, str]],
    quality_tier: str,
) -> SeedreamImageRequest:
    """构造方舟图片请求；自由创作不传 image，商品场景传参考图数组。"""
    normalized_prompt = str(prompt or "").strip()
    if not normalized_prompt:
        raise ValueError("Seedream 提示词不能为空")
    if len(reference_images) > 14:
        raise ValueError("Seedream 最多支持 14 张参考图")

    body: dict[str, Any] = {
        "model": model,
        "prompt": normalized_prompt,
        "size": _quality_size(quality_tier),
        "sequential_image_generation": "disabled",
        "response_format": "url",
        "watermark": False,
    }
    if reference_images:
        body["image"] = [
            _image_data_uri(data, mime)
            for data, mime in reference_images
        ]
    return SeedreamImageRequest(
        url=f"{base_url.rstrip('/')}/images/generations",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        body=body,
    )


def parse_seedream_image_response(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("Seedream 没有返回图片结果")
    urls = [
        str(item.get("url") or "").strip()
        for item in data
        if isinstance(item, dict) and str(item.get("url") or "").strip()
    ]
    if not urls:
        raise ValueError("Seedream 没有返回图片地址")
    return urls


def _seedream_error(status_code: int, message: str = "") -> ValueError:
    if status_code in {401, 403}:
        return ValueError("Seedream 服务密钥无效或没有模型权限，请联系管理员")
    if status_code == 402:
        return ValueError("Seedream 服务余额不足，请联系管理员")
    if status_code == 400:
        return ValueError("Seedream 请求参数有误，请检查参考图或尺寸")
    if status_code == 422:
        return ValueError("Seedream 内容未通过供应商审核，请调整素材或提示词")
    if status_code == 429:
        return ValueError("Seedream 请求过于频繁，请稍后重试")
    if status_code >= 500:
        return ValueError("Seedream 服务暂不可用，请稍后重试")
    return ValueError(message or "Seedream 图片生成失败")


def _response_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:200]
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or "")
    return str(payload.get("message") or "")


async def generate_seedream_images(
    *,
    prompt: str,
    reference_images: list[tuple[bytes, str]],
    quality_tier: str,
    num_outputs: int,
) -> tuple[list[str], str]:
    """按输出张数逐个调用方舟接口，保证返回数量与任务一致。"""
    config = get_seedream_image_config()
    if not config["api_key"]:
        raise ValueError("Seedream 服务未配置，请联系管理员配置方舟 API Key")

    request = build_seedream_image_request(
        api_key=config["api_key"],
        base_url=config["base_url"],
        model=config["model"],
        prompt=prompt,
        reference_images=reference_images,
        quality_tier=quality_tier,
    )
    urls: list[str] = []
    async with httpx.AsyncClient(timeout=180) as client:
        for _ in range(max(1, min(int(num_outputs or 1), 4))):
            response = await client.post(
                request.url,
                headers=request.headers,
                json=request.body,
            )
            if response.status_code >= 400:
                raise _seedream_error(
                    response.status_code,
                    _response_error_message(response),
                )
            urls.extend(parse_seedream_image_response(response.json()))
    return urls, config["model"]
