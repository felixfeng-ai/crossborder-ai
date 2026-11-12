"""视频供应商统一协议、注册表和 MiniMax 适配器。"""

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.services.minimax_video import (
    cancel_minimax_video,
    download_minimax_video,
    get_minimax_video_capabilities,
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

    async def submit(self, request: VideoProviderRequest) -> str: ...

    async def query(self, provider_task_id: str) -> dict[str, Any]: ...

    async def cancel(self, provider_task_id: str) -> bool: ...

    async def download(self, video_url: str) -> bytes: ...


class MiniMaxVideoProvider:
    """把现有 MiniMax 低层客户端包装成统一 Provider。"""

    name = "minimax"

    def capabilities(self) -> dict[str, Any]:
        return get_minimax_video_capabilities()

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


register_video_provider(MiniMaxVideoProvider())
