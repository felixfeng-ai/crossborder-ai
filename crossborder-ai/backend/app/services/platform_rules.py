"""跨境电商 Listing 平台字段规则。"""

from typing import Any


PLATFORM_RULES: dict[str, dict[str, Any]] = {
    "amazon": {
        "label": "Amazon",
        "title_max": 200,
        "description_max": 2000,
        "min_bullets": 5,
        "seo_required": True,
    },
    "shopify": {
        "label": "Shopify",
        "title_max": 255,
        "description_max": 100000,
        "min_bullets": 1,
        "seo_required": True,
    },
    "ebay": {
        "label": "eBay",
        "title_max": 80,
        "description_max": 500000,
        "min_bullets": 1,
        "seo_required": False,
    },
    "temu": {
        "label": "Temu",
        "title_max": 250,
        "description_max": 5000,
        "min_bullets": 3,
        "seo_required": False,
    },
    "shein": {
        "label": "SHEIN",
        "title_max": 200,
        "description_max": 5000,
        "min_bullets": 3,
        "seo_required": False,
    },
    "tiktok": {
        "label": "TikTok Shop",
        "title_max": 255,
        "description_max": 5000,
        "min_bullets": 3,
        "seo_required": False,
    },
    "aliexpress": {
        "label": "AliExpress",
        "title_max": 255,
        "description_max": 5000,
        "min_bullets": 3,
        "seo_required": False,
    },
    "walmart": {
        "label": "Walmart",
        "title_max": 200,
        "description_max": 4000,
        "min_bullets": 3,
        "seo_required": False,
    },
}


def get_platform_rule(platform: str) -> dict[str, Any]:
    return dict(PLATFORM_RULES.get((platform or "").lower(), PLATFORM_RULES["shopify"]))


def validate_listing_for_platform(platform: str, content: dict[str, Any]) -> dict[str, Any]:
    """返回发布前字段就绪检查，error 阻断，warning 仅提示。"""
    rule = get_platform_rule(platform)
    title = str(content.get("title") or "").strip()
    description = str(content.get("description") or "").strip()
    bullets = content.get("bullet_points") or []
    seo_title = str(content.get("seo_title") or "").strip()
    seo_description = str(content.get("seo_description") or "").strip()

    checks: list[dict[str, str]] = []

    if not title:
        checks.append({"id": "title", "status": "error", "message": "标题不能为空"})
    elif len(title) > rule["title_max"]:
        checks.append(
            {
                "id": "title",
                "status": "error",
                "message": f"标题超过 {rule['title_max']} 字符",
            }
        )
    else:
        checks.append({"id": "title", "status": "pass", "message": "标题长度符合平台限制"})

    if not description:
        checks.append({"id": "description", "status": "error", "message": "商品描述不能为空"})
    elif len(description) > rule["description_max"]:
        checks.append(
            {
                "id": "description",
                "status": "error",
                "message": f"描述超过 {rule['description_max']} 字符",
            }
        )
    else:
        checks.append({"id": "description", "status": "pass", "message": "描述长度符合平台限制"})

    if len(bullets) < rule["min_bullets"]:
        checks.append(
            {
                "id": "bullets",
                "status": "warning",
                "message": f"建议至少 {rule['min_bullets']} 条卖点，当前 {len(bullets)} 条",
            }
        )
    else:
        checks.append({"id": "bullets", "status": "pass", "message": "卖点数量符合建议"})

    if rule["seo_required"] and (not seo_title or not seo_description):
        checks.append({"id": "seo", "status": "warning", "message": "SEO 标题或描述不完整"})
    else:
        checks.append({"id": "seo", "status": "pass", "message": "SEO 字段已填写"})

    errors = sum(1 for check in checks if check["status"] == "error")
    warnings = sum(1 for check in checks if check["status"] == "warning")
    score = max(0, 100 - errors * 35 - warnings * 10)
    return {
        "platform": (platform or "").lower(),
        "label": rule["label"],
        "ok": errors == 0,
        "score": score,
        "checks": checks,
    }


def list_platform_rules() -> list[dict[str, Any]]:
    return [
        {"id": platform, **rule}
        for platform, rule in PLATFORM_RULES.items()
    ]
