"""图片生成模式、质量档与服务商成本估算。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ImageQualitySpec:
    """单个质量档的尺寸与商城积分成本。"""

    id: str
    label: str
    resolution: str
    description: str
    credits: dict[str, int]
    estimated_cost_micros: dict[str, int]


IMAGE_MODES: tuple[dict[str, str], ...] = (
    {
        "id": "product_scene",
        "label": "商品场景",
        "description": "参考商品图保持主体一致，生成投放场景图",
    },
    {
        "id": "free_creation",
        "label": "自由创作",
        "description": "不默认注入品牌人设的广告视觉创作",
    },
    {
        "id": "platform_white",
        "label": "平台白底",
        "description": "按平台尺寸生成本地白底商品图",
    },
)

IMAGE_QUALITY_TIERS: dict[str, ImageQualitySpec] = {
    "fast": ImageQualitySpec(
        id="fast",
        label="快速",
        resolution="1024x1024",
        description="适合构图探索和批量测试",
        credits={"free_creation": 3, "product_scene": 8, "platform_white": 0},
        # 成本仅用于内部记录与毛利分析，不作为对外报价。
        estimated_cost_micros={"free_creation": 12_000, "product_scene": 40_000},
    ),
    "standard": ImageQualitySpec(
        id="standard",
        label="标准",
        resolution="1280x1280",
        description="质量与速度平衡，适合日常上新",
        credits={"free_creation": 5, "product_scene": 10, "platform_white": 0},
        estimated_cost_micros={"free_creation": 24_000, "product_scene": 72_000},
    ),
    "hd": ImageQualitySpec(
        id="hd",
        label="高清",
        # 通义万相单边上限为 1440，高清档使用当前可稳定生成的最高尺寸。
        resolution="1440x1440",
        description="适合主图、详情页和高质量素材沉淀",
        credits={"free_creation": 8, "product_scene": 12, "platform_white": 0},
        estimated_cost_micros={"free_creation": 48_000, "product_scene": 120_000},
    ),
}

IMAGE_ASPECT_RATIOS: tuple[str, ...] = ("1:1", "4:5", "3:4", "16:9", "9:16")

IMAGE_EDIT_CREDITS: dict[str, int] = {
    "inpaint": 6,
    "outpaint": 6,
    "remove_object": 5,
    "upscale": 2,
}


def resolve_image_resolution(quality_tier: str, aspect_ratio: str) -> str:
    """按质量档和画幅计算最终画布，避免 Provider 收到超出上限的尺寸。"""
    spec = IMAGE_QUALITY_TIERS.get(quality_tier)
    if spec is None:
        raise ValueError("未知的图片质量档位")

    ratio = aspect_ratio if aspect_ratio in IMAGE_ASPECT_RATIOS else "1:1"
    ratio_width, ratio_height = (int(part) for part in ratio.split(":", 1))
    max_width, max_height = (
        int(part) for part in spec.resolution.split("x", 1)
    )

    # 以质量档给出的长边为上限，短边按画幅等比计算并取偶数。
    if ratio_width >= ratio_height:
        width = max_width
        height = round(max_width * ratio_height / ratio_width / 2) * 2
    else:
        height = max_height
        width = round(max_height * ratio_width / ratio_height / 2) * 2
    return f"{max(2, width)}x{max(2, height)}"


def image_generation_credits(
    mode: str,
    quality_tier: str,
    num_outputs: int,
) -> int:
    """按模式、质量档和数量计算积分；旧请求继续沿用每张 3 积分。"""
    count = max(1, min(int(num_outputs or 1), 4))
    if mode == "legacy":
        return count * 3
    if mode in IMAGE_EDIT_CREDITS:
        return count * IMAGE_EDIT_CREDITS[mode]
    spec = IMAGE_QUALITY_TIERS.get(quality_tier)
    if spec is None:
        raise ValueError("未知的图片质量档位")
    unit_credits = spec.credits.get(mode)
    if unit_credits is None:
        raise ValueError("未知的图片生成模式")
    return unit_credits * count


def estimate_image_cost_micros(
    mode: str,
    quality_tier: str,
    num_outputs: int,
) -> int:
    """估算服务商成本；白底本地处理不产生模型调用成本。"""
    if mode == "platform_white":
        return 0
    if mode == "upscale":
        return 0
    if mode in {"inpaint", "outpaint"}:
        return 80_000 * max(1, min(int(num_outputs or 1), 4))
    if mode == "remove_object":
        return 60_000 * max(1, min(int(num_outputs or 1), 4))
    spec = IMAGE_QUALITY_TIERS.get(quality_tier)
    if spec is None:
        return 0
    return spec.estimated_cost_micros.get(mode, 0) * max(
        1,
        min(int(num_outputs or 1), 4),
    )


def public_image_capabilities() -> dict:
    """返回前端可见的图片生成能力矩阵。"""
    return {
        "modes": list(IMAGE_MODES),
        "quality_tiers": [
            {
                "id": spec.id,
                "label": spec.label,
                "resolution": spec.resolution,
                "description": spec.description,
                "credits": spec.credits,
            }
            for spec in IMAGE_QUALITY_TIERS.values()
        ],
        "aspect_ratios": list(IMAGE_ASPECT_RATIOS),
        "reference_image_limit": {"min": 1, "max": 4},
        "edit_operations": [
            {
                "id": operation,
                "credits": credits,
            }
            for operation, credits in IMAGE_EDIT_CREDITS.items()
        ],
    }
