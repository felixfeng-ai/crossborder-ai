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
        resolution="2048x2048",
        description="适合主图、详情页和高质量素材沉淀",
        credits={"free_creation": 8, "product_scene": 12, "platform_white": 0},
        estimated_cost_micros={"free_creation": 48_000, "product_scene": 120_000},
    ),
}

IMAGE_ASPECT_RATIOS: tuple[str, ...] = ("1:1", "4:5", "3:4", "16:9", "9:16")


def image_generation_credits(
    mode: str,
    quality_tier: str,
    num_outputs: int,
) -> int:
    """按模式、质量档和数量计算积分；旧请求继续沿用每张 3 积分。"""
    count = max(1, min(int(num_outputs or 1), 4))
    if mode == "legacy":
        return count * 3
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
    }
