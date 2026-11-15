"""图片生成 Provider 统一协议与能力边界。"""

import io
from dataclasses import dataclass, field
from typing import Any, Protocol

from PIL import Image, ImageOps

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
    scale: int = 1
    references: list[ImageReferencePayload] = field(default_factory=list)


@dataclass(frozen=True)
class ImageProviderResult:
    urls: list[str]
    provider: str
    model: str
    actual_cost_micros: int
    local_outputs: list[bytes] | None = None


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

    def _edit_model(self, mode: str) -> str:
        field_name, fallback = {
            "inpaint": ("inpaint_model", settings.REPLICATE_IMAGE_INPAINT_MODEL),
            "outpaint": ("outpaint_model", settings.REPLICATE_IMAGE_OUTPAINT_MODEL),
            "remove_object": ("remove_model", settings.REPLICATE_IMAGE_REMOVE_MODEL),
        }.get(mode, ("", ""))
        if not field_name:
            return ""
        return provider_config.get("replicate", field_name, fallback or "")

    def is_configured(self) -> bool:
        return bool(self._api_key())

    def capabilities(self) -> dict[str, Any]:
        modes = ["free_creation", "legacy"]
        if self._reference_model():
            modes.append("product_scene")
        modes.extend(
            mode
            for mode in ("inpaint", "outpaint", "remove_object")
            if self._edit_model(mode)
        )
        return {
            "provider": self.name,
            "configured": self.is_configured(),
            "modes": modes,
            "reference_images": bool(self._reference_model()),
            "model": self._text_model(),
            "reference_model": self._reference_model() or None,
            "edit_models": {
                mode: self._edit_model(mode) or None
                for mode in ("inpaint", "outpaint", "remove_object")
            },
        }

    def supports(self, mode: str, quality_tier: str) -> bool:
        if not self.is_configured():
            return False
        if mode in {"inpaint", "outpaint", "remove_object"}:
            return bool(self._edit_model(mode))
        if quality_tier not in {"fast", "standard", "hd"}:
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
        if request.mode in {"inpaint", "outpaint", "remove_object"}:
            if not request.references:
                raise ValueError("编辑源图不能为空")
            model = self._edit_model(request.mode)
            mask = request.references[1] if len(request.references) > 1 else None
            urls = await service.generate_edit_image(
                model=model,
                mode=request.mode,
                prompt=request.prompt,
                source=(
                    request.references[0].data,
                    request.references[0].mime,
                ),
                mask=(mask.data, mask.mime) if mask is not None else None,
                aspect_ratio=request.aspect_ratio,
            )
        elif request.mode == "product_scene":
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


class LocalImageProvider:
    """无需外部服务的本地图片处理 Provider。"""

    name = "local"

    def is_configured(self) -> bool:
        return True

    def capabilities(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "configured": True,
            "modes": ["upscale"],
            "reference_images": True,
        }

    def supports(self, mode: str, quality_tier: str) -> bool:
        return mode == "upscale"

    def estimate_cost_micros(
        self,
        mode: str,
        quality_tier: str,
        num_outputs: int,
    ) -> int:
        return 0

    async def generate(self, request: ImageProviderRequest) -> ImageProviderResult:
        if not self.supports(request.mode, request.quality_tier):
            raise ValueError("本地图片 Provider 不支持当前编辑方式")
        if not request.references:
            raise ValueError("待放大图片不能为空")
        scale = max(2, min(int(request.scale or 2), 4))
        with Image.open(io.BytesIO(request.references[0].data)) as source:
            rgba = ImageOps.exif_transpose(source).convert("RGBA")
        target_width = rgba.width * scale
        target_height = rgba.height * scale
        if target_width > 6000 or target_height > 6000:
            raise ValueError("放大后尺寸过大，请降低倍率")
        output = rgba.resize(
            (target_width, target_height),
            Image.Resampling.LANCZOS,
        )
        buffer = io.BytesIO()
        # 大图无损 PNG 很容易超过素材入口限制；先编码高质 WebP，
        # 后续统一素材流程仍会再次规范化为无元数据 WebP。
        output.save(buffer, format="WEBP", quality=95, method=3)
        return ImageProviderResult(
            urls=[],
            provider=self.name,
            model="pillow-lanczos",
            actual_cost_micros=0,
            local_outputs=[buffer.getvalue()],
        )


_PROVIDERS: dict[str, ImageProvider] = {
    "aliyun": AliyunImageProvider(),
    "replicate": ReplicateImageProvider(),
    "local": LocalImageProvider(),
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
