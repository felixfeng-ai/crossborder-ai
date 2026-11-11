"""商品图片校验、规范化与平台白底适配。"""

import io
import os
import threading
from pathlib import Path
from typing import Any
from typing import Callable

from PIL import Image, ImageFile, ImageOps, UnidentifiedImageError


# 防止压缩炸弹：商品图限制在 8000 像素边和 3600 万像素以内。
Image.MAX_IMAGE_PIXELS = 36_000_000
ImageFile.LOAD_TRUNCATED_IMAGES = False

# U2NetP 模型跟随项目部署，避免生产机在请求处理中临时下载模型。
_REMBG_HOME = Path(__file__).resolve().parents[2] / "storage" / "rembg"
os.environ.setdefault("U2NET_HOME", str(_REMBG_HOME))
_REMBG_SESSION = None
_REMBG_SESSION_LOCK = threading.Lock()

IMAGE_PLATFORM_PRESETS: tuple[dict[str, Any], ...] = (
    {
        "id": "amazon-main",
        "platform": "Amazon",
        "label": "主图",
        "width": 2000,
        "height": 2000,
        "note": "白底方形主图",
    },
    {
        "id": "shopify-product",
        "platform": "Shopify",
        "label": "商品主图",
        "width": 2048,
        "height": 2048,
        "note": "高分辨率方形素材",
    },
    {
        "id": "temu-main",
        "platform": "Temu",
        "label": "主图",
        "width": 1200,
        "height": 1200,
        "note": "轻量方形主图",
    },
    {
        "id": "shein-main",
        "platform": "SHEIN",
        "label": "商品主图",
        "width": 1349,
        "height": 1785,
        "note": "3:4 商品图",
    },
    {
        "id": "tiktok-main",
        "platform": "TikTok Shop",
        "label": "商品主图",
        "width": 1080,
        "height": 1080,
        "note": "内容电商方形图",
    },
    {
        "id": "aliexpress-main",
        "platform": "AliExpress",
        "label": "主图",
        "width": 1000,
        "height": 1000,
        "note": "基础方形主图",
    },
    {
        "id": "walmart-main",
        "platform": "Walmart",
        "label": "主图",
        "width": 2000,
        "height": 2000,
        "note": "白底高分辨率主图",
    },
)


def list_platform_presets() -> list[dict[str, Any]]:
    return [dict(item) for item in IMAGE_PLATFORM_PRESETS]


def get_platform_preset(preset_id: str) -> dict[str, Any]:
    for preset in IMAGE_PLATFORM_PRESETS:
        if preset["id"] == preset_id:
            return dict(preset)
    raise ValueError("未知的平台尺寸预设")


def _remove_background_with_u2net(source: bytes) -> bytes:
    """使用本地 U2NetP 模型输出带透明通道的商品主体。"""

    global _REMBG_SESSION
    try:
        from rembg import new_session, remove

        if _REMBG_SESSION is None:
            with _REMBG_SESSION_LOCK:
                if _REMBG_SESSION is None:
                    _REMBG_SESSION = new_session("u2netp")
        return remove(
            source,
            session=_REMBG_SESSION,
            alpha_matting=False,
            post_process_mask=True,
        )
    except Exception as exc:
        raise ValueError("商品主体抠图失败，请稍后重试") from exc


def normalize_uploaded_image(data: bytes, max_bytes: int) -> tuple[bytes, int, int]:
    """校验上传图片并转成无元数据的 WebP。"""
    if not data or len(data) > max_bytes:
        raise ValueError("图片不能为空且不能超过上传大小限制")

    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image)
            width, height = image.size
            if width < 1 or height < 1 or width > 8000 or height > 8000:
                raise ValueError("图片尺寸超出支持范围")
            if width * height > 36_000_000:
                raise ValueError("图片像素过大，请压缩后重新上传")

            rgba = image.convert("RGBA")
            output = io.BytesIO()
            rgba.save(output, format="WEBP", quality=94, method=6)
            return output.getvalue(), width, height
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("无法识别图片，请上传 JPEG、PNG 或 WebP 文件") from exc


def create_white_background_image(
    source: bytes,
    width: int,
    height: int,
    *,
    margin_ratio: float = 0.04,
    background_remover: Callable[[bytes], bytes] | None = None,
) -> bytes:
    """先移除原背景，再等比缩放主体并合成到纯白画布。"""
    if width < 100 or height < 100 or width > 4000 or height > 4000:
        raise ValueError("输出尺寸必须在 100-4000 像素之间")

    try:
        with Image.open(io.BytesIO(source)) as source_image:
            source_rgba = ImageOps.exif_transpose(source_image).convert("RGBA")
        source_alpha = source_rgba.getchannel("A")
        if background_remover is None and source_alpha.getextrema()[0] < 255:
            image = source_rgba
        else:
            remover = background_remover or _remove_background_with_u2net
            cutout = remover(source)
            with Image.open(io.BytesIO(cutout)) as input_image:
                image = ImageOps.exif_transpose(input_image).convert("RGBA")
    except ValueError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("背景移除结果异常，请重新上传原图") from exc

    alpha = image.getchannel("A")
    content_bbox = alpha.getbbox()
    if content_bbox is None:
        raise ValueError("未识别到商品主体，请更换更清晰的商品图")
    image = image.crop(content_bbox)

    margin_x = max(1, int(width * margin_ratio))
    margin_y = max(1, int(height * margin_ratio))
    inner_width = max(1, width - margin_x * 2)
    inner_height = max(1, height - margin_y * 2)
    fitted = ImageOps.contain(
        image,
        (inner_width, inner_height),
        method=Image.Resampling.LANCZOS,
    )

    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    x = (width - fitted.width) // 2
    y = (height - fitted.height) // 2
    canvas.alpha_composite(fitted, (x, y))

    output = io.BytesIO()
    canvas.save(
        output,
        format="PNG",
        optimize=True,
    )
    return output.getvalue()
