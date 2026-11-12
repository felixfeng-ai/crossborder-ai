"""视频供应商统一协议、注册表以及 MiniMax / 即梦适配器。"""

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.services import jimeng_video
from app.services.jimeng_video import (
    cancel_jimeng_video,
    download_jimeng_video,
    get_jimeng_video_capabilities,
    query_jimeng_video,
    submit_jimeng_video,
)
from app.services.minimax_video import (
    MODEL_CONFIGS as MINIMAX_MODEL_CONFIGS,
    cancel_minimax_video,
    download_minimax_video,
    estimate_video_cost_micros as estimate_minimax_cost_micros,
    get_minimax_video_capabilities,
    get_minimax_video_config,
    query_minimax_video,
    submit_minimax_video,
)


@dataclass(frozen=True)
class VideoImagePayload:
    data: bytes
    mime: str


@dataclass
class VideoProviderRequest:
    prompt: str
    model: str
    resolution: str
    duration: int
    ratio: str
    first_frame: VideoImagePayload | None = None
    reference_images: list[VideoImagePayload] = field(default_factory=list)


class VideoProvider(Protocol):
    """供应商必须实现的统一视频任务协议。"""

    name: str

    def capabilities(self) -> dict[str, Any]: ...

    def is_configured(self) -> bool: ...

    def estimate_cost_micros(
        self,
        model: str,
        resolution: str,
        duration: int,
    ) -> int: ...

    def render_duration(self, model: str, target_duration: int) -> int: ...

    async def submit(self, request: VideoProviderRequest) -> str: ...

    async def query(self, provider_task_id: str) -> dict[str, Any]: ...

    async def cancel(self, provider_task_id: str) -> bool: ...

    async def download(self, video_url: str) -> bytes: ...


class MiniMaxVideoProvider:
    """把现有 MiniMax 低层客户端包装成统一 Provider。"""

    name = "minimax"

    def capabilities(self) -> dict[str, Any]:
        return get_minimax_video_capabilities()

    def is_configured(self) -> bool:
        return bool(get_minimax_video_config()["api_key"])

    def estimate_cost_micros(
        self,
        model: str,
        resolution: str,
        duration: int,
    ) -> int:
        return estimate_minimax_cost_micros(model, resolution, duration)

    def render_duration(self, model: str, target_duration: int) -> int:
        config = MINIMAX_MODEL_CONFIGS.get(model)
        if config is None:
            raise ValueError("视频模型不支持")
        target = int(target_duration)
        if target <= 0:
            raise ValueError("镜头时长必须大于 0 秒")
        if target > int(config["max_duration"]):
            raise ValueError(f"镜头时长不能超过 {config['max_duration']} 秒")
        return max(int(config["min_duration"]), target)

    async def submit(self, request: VideoProviderRequest) -> str:
        references = [
            (item.data, item.mime)
            for item in request.reference_images
        ] or None
        return await submit_minimax_video(
            prompt=request.prompt,
            model=request.model,
            resolution=request.resolution,
            duration=request.duration,
            ratio=request.ratio,
            first_frame=request.first_frame.data if request.first_frame else None,
            first_frame_mime=(
                request.first_frame.mime if request.first_frame else None
            ),
            reference_images=references,
        )

    async def query(self, provider_task_id: str) -> dict[str, Any]:
        return await query_minimax_video(provider_task_id)

    async def cancel(self, provider_task_id: str) -> bool:
        return await cancel_minimax_video(provider_task_id)

    async def download(self, video_url: str) -> bytes:
        return await download_minimax_video(video_url)


class JimengVideoProvider:
    """即梦 / Seedance 方舟视频适配器。"""

    name = "jimeng"

    def capabilities(self) -> dict[str, Any]:
        return get_jimeng_video_capabilities()

    def is_configured(self) -> bool:
        return bool(jimeng_video.get_jimeng_video_config()["api_key"])

    def estimate_cost_micros(
        self,
        model: str,
        resolution: str,
        duration: int,
    ) -> int:
        return jimeng_video.estimate_jimeng_cost_micros(
            model,
            resolution,
            duration,
        )

    def render_duration(self, model: str, target_duration: int) -> int:
        config = jimeng_video.MODEL_CONFIGS.get(model)
        if config is None:
            if str(model).startswith("ep-"):
                config = jimeng_video.MODEL_CONFIGS[jimeng_video.DEFAULT_MODEL]
            else:
                raise ValueError("即梦视频模型不支持")
        target = int(target_duration)
        if target <= 0:
            raise ValueError("镜头时长必须大于 0 秒")
        if target > int(config["max_duration"]):
            raise ValueError(f"即梦镜头时长不能超过 {config['max_duration']} 秒")
        return max(int(config["min_duration"]), target)

    async def submit(self, request: VideoProviderRequest) -> str:
        references = [
            (item.data, item.mime)
            for item in request.reference_images
        ] or None
        # Seedance 官方多参考图提示词使用 [图N]，转换后避免模型忽略图片编号。
        prompt = re.sub(r"<Picture (\d+)>", r"[图\1]", request.prompt)
        return await submit_jimeng_video(
            prompt=prompt,
            model=request.model,
            resolution=request.resolution,
            duration=request.duration,
            ratio=request.ratio,
            first_frame=request.first_frame.data if request.first_frame else None,
            first_frame_mime=(
                request.first_frame.mime if request.first_frame else None
            ),
            reference_images=references,
        )

    async def query(self, provider_task_id: str) -> dict[str, Any]:
        return await query_jimeng_video(provider_task_id)

    async def cancel(self, provider_task_id: str) -> bool:
        return await cancel_jimeng_video(provider_task_id)

    async def download(self, video_url: str) -> bytes:
        return await download_jimeng_video(video_url)


_PROVIDERS: dict[str, VideoProvider] = {}


def register_video_provider(provider: VideoProvider) -> None:
    """注册或替换一个视频供应商适配器。"""
    name = str(getattr(provider, "name", "")).strip().lower()
    if not name:
        raise ValueError("视频供应商名称不能为空")
    _PROVIDERS[name] = provider


def get_video_provider(name: str) -> VideoProvider:
    """按名称取得 Provider；未知名称返回业务错误。"""
    normalized = str(name or "").strip().lower()
    provider = _PROVIDERS.get(normalized)
    if provider is None:
        raise ValueError(f"视频供应商 {normalized or '(empty)'} 未注册")
    return provider


def list_video_providers() -> list[str]:
    """返回当前可用的 Provider 名称。"""
    return sorted(_PROVIDERS)


def list_provider_capabilities(
    *,
    configured_only: bool = False,
) -> list[dict[str, Any]]:
    """返回各 Provider 的安全能力快照，供路由和前端展示。"""
    capabilities = []
    for name in list_video_providers():
        provider = _PROVIDERS[name]
        if configured_only and not provider.is_configured():
            continue
        item = dict(provider.capabilities())
        item["provider"] = name
        item["configured"] = provider.is_configured()
        capabilities.append(item)
    return capabilities


def get_video_capabilities_summary() -> dict[str, Any]:
    """组装不暴露密钥的跨 Provider 能力摘要。"""
    providers = sorted(
        list_provider_capabilities(configured_only=True),
        key=lambda item: (
            0 if item["provider"] == "minimax" else 1,
            str(item["provider"]),
        ),
    )
    minimax = get_minimax_video_capabilities()
    primary = providers[0] if providers else {
        **minimax,
        "provider": "minimax",
        "configured": False,
    }
    models = [
        {**model, "provider": provider["provider"]}
        for provider in providers
        for model in provider.get("models", [])
    ] or minimax["models"]
    return {
        "enabled": bool(providers),
        "provider": primary["provider"],
        "default_model": primary["default_model"],
        "default_resolution": primary["default_resolution"],
        "models": models,
        "templates": minimax["templates"],
        "providers": providers,
    }


register_video_provider(MiniMaxVideoProvider())
register_video_provider(JimengVideoProvider())
