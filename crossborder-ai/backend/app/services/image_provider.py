"""图片生成 Provider 统一协议与能力边界。"""

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.config import settings
from app.services import provider_config
from app.services.image_quality import estimate_image_cost_micros


@dataclass(frozen=True)
class ImageReferencePayload:
    """参考图二进制内容；任务执行时才从私有素材目录读取。"""

    data: bytes
    mime: str


@dataclass
class ImageProviderRequest:
    prompt: str
    mode: str
    quality_tier: str
    resolution: str
    aspect_ratio: str
    num_outputs: int = 1
    negative_prompt: str = ""
    references: list[ImageReferencePayload] = field(default_factory=list)


@dataclass(frozen=True)
class ImageProviderResult:
    urls: list[str]
    provider: str
    model: str
    actual_cost_micros: int


class ImageProvider(Protocol):
    """所有图片服务商必须遵循的最小异步接口。"""

    name: str

    def is_configured(self) -> bool: ...

    def capabilities(self) -> dict[str, Any]: ...

    def supports(self, mode: str, quality_tier: str) -> bool: ...

    def estimate_cost_micros(
        self,
        mode: str,
        quality_tier: str,
        num_outputs: int,
    ) -> int: ...

    async def generate(self, request: ImageProviderRequest) -> ImageProviderResult: ...


class AliyunImageProvider:
    """通义万相纯文生图适配器；不支持商品参考图。"""

    name = "aliyun"

    def _api_key(self) -> str:
        return provider_config.get(
            "aliyun",
            "api_key",
            settings.ALIYUN_DASHSCOPE_API_KEY or "",
        )

    def _model(self) -> str:
        return provider_config.get(
            "aliyun",
            "model",
            settings.ALIYUN_IMAGE_MODEL,
        )

    def is_configured(self) -> bool:
        return bool(self._api_key())

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "configured": self.is_configured(),
            "modes": ["free_creation", "legacy"],
            "reference_images": False,
            "model": self._model(),
        }

    def supports(self, mode: str, quality_tier: str) -> bool:
        return (
            self.is_configured()
            and mode in {"free_creation", "legacy"}
            and quality_tier in {"fast", "standard", "hd"}
        )

    def estimate_cost_micros(
        self,
        mode: str,
        quality_tier: str,
        num_outputs: int,
    ) -> int:
        return estimate_image_cost_micros(mode, quality_tier, num_outputs)

    async def generate(self, request: ImageProviderRequest) -> ImageProviderResult:
        if not self.supports(request.mode, request.quality_tier):
            raise ValueError("阿里云图片 Provider 不支持当前生成模式")
        from app.services.ai.aliyun_image import AliyunImageService

        urls = await AliyunImageService().generate_image(
            prompt=request.prompt,
            num_outputs=request.num_outputs,
            size=request.resolution.replace("x", "*"),
        )
        return ImageProviderResult(
            urls=list(urls),
            provider=self.name,
            model=self._model(),
            actual_cost_micros=self.estimate_cost_micros(
                request.mode,
                request.quality_tier,
                request.num_outputs,
            ),
        )


class ReplicateImageProvider:
    """Replicate 文生图与参考图商品场景适配器。"""

    name = "replicate"

    def _api_key(self) -> str:
        return provider_config.get(
            "replicate",
            "api_key",
            settings.REPLICATE_API_KEY or "",
        )

    def _text_model(self) -> str:
        return provider_config.get(
            "replicate",
            "model",
            settings.REPLICATE_MODEL,
        )

    def _reference_model(self) -> str:
        return provider_config.get(
            "replicate",
            "reference_model",
            settings.REPLICATE_IMAGE_REFERENCE_MODEL or "",
        )

    def _reference_input_field(self) -> str:
        return provider_config.get(
            "replicate",
            "reference_input_field",
            settings.REPLICATE_IMAGE_REFERENCE_INPUT_FIELD,
        )

    def is_configured(self) -> bool:
        return bool(self._api_key())

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "configured": self.is_configured(),
            "modes": (
                ["free_creation", "legacy", "product_scene"]
                if self._reference_model()
                else ["free_creation", "legacy"]
            ),
            "reference_images": bool(self._reference_model()),
            "model": self._text_model(),
            "reference_model": self._reference_model() or None,
        }

    def supports(self, mode: str, quality_tier: str) -> bool:
        if (
            not self.is_configured()
            or quality_tier not in {"fast", "standard", "hd"}
        ):
            return False
        if mode in {"free_creation", "legacy"}:
            return True
        return mode == "product_scene" and bool(self._reference_model())

    def estimate_cost_micros(
        self,
        mode: str,
        quality_tier: str,
        num_outputs: int,
    ) -> int:
        return estimate_image_cost_micros(mode, quality_tier, num_outputs)

    async def generate(self, request: ImageProviderRequest) -> ImageProviderResult:
        if not self.supports(request.mode, request.quality_tier):
            raise ValueError("Replicate 图片 Provider 不支持当前生成模式")
        from app.services.ai.replicate import ReplicateService

        service = ReplicateService()
        if request.mode == "product_scene":
            if not request.references:
                raise ValueError("商品场景参考图不能为空")
            urls = await service.generate_reference_image(
                prompt=request.prompt,
                references=[
                    (item.data, item.mime)
                    for item in request.references
                ],
                negative_prompt=request.negative_prompt,
                num_outputs=request.num_outputs,
                aspect_ratio=request.aspect_ratio,
                quality_tier=request.quality_tier,
                reference_model=self._reference_model(),
                reference_input_field=self._reference_input_field(),
            )
            model = self._reference_model()
        else:
            urls = await service.generate_image(
                prompt=request.prompt,
                negative_prompt=request.negative_prompt or None,
                num_outputs=request.num_outputs,
                aspect_ratio=request.aspect_ratio,
            )
            model = self._text_model()
        return ImageProviderResult(
            urls=list(urls),
            provider=self.name,
            model=model,
            actual_cost_micros=self.estimate_cost_micros(
                request.mode,
                request.quality_tier,
                request.num_outputs,
            ),
        )


_PROVIDERS: dict[str, ImageProvider] = {
    "aliyun": AliyunImageProvider(),
    "replicate": ReplicateImageProvider(),
}


def get_image_provider(name: str) -> ImageProvider:
    normalized = str(name or "").strip().lower()
    provider = _PROVIDERS.get(normalized)
    if provider is None:
        raise ValueError(f"图片供应商 {normalized or '(empty)'} 未注册")
    return provider


def list_image_providers() -> list[str]:
    return sorted(_PROVIDERS)


def list_image_provider_capabilities(
    *,
    configured_only: bool = False,
) -> list[dict[str, Any]]:
    """返回不含密钥的能力快照。"""
    items = []
    for name in list_image_providers():
        provider = _PROVIDERS[name]
        if configured_only and not provider.is_configured():
            continue
        items.append(provider.capabilities())
    return items
