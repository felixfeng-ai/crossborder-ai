"""选品报告字段归一化，隔离 LLM 字段漂移与前端契约。"""

from typing import Any


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def _number(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip().replace(",", "").replace("¥", "").replace("$", "")
    is_percent = text.endswith("%")
    text = text.rstrip("%").strip()
    try:
        number = float(text)
    except ValueError:
        return None
    if number.is_integer():
        number = int(number)
    return number


def _text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not isinstance(value, str) or not value.strip():
        return []
    normalized = value.replace("，", "、").replace(",", "、").replace("；", "、")
    return [item.strip() for item in normalized.split("、") if item.strip()]


def normalize_selection_product(product: Any) -> dict[str, Any] | None:
    """把中英文商品字段别名统一成 ProductCandidate 契约。"""
    if not isinstance(product, dict):
        return None
    name = _first(product, "name", "title", "product_name", "商品名", "名称")
    if not isinstance(name, str) or not name.strip():
        return None

    item = dict(product)
    item.update(
        {
            "name": name.strip(),
            "suggested_price_usd": _number(
                _first(
                    product,
                    "suggested_price_usd",
                    "price_usd",
                    "avg_price_usd",
                    "price",
                    "价格美元",
                    "建议售价",
                )
            ),
            "cost_cny": _number(
                _first(product, "cost_cny", "采购价", "成本", "成本人民币")
            ),
            "net_profit_usd": _number(
                _first(product, "net_profit_usd", "单件净利", "净利")
            ),
            "net_margin": _number(
                _first(product, "net_margin", "净利率", "利润率")
            ),
            "competition": _number(
                _first(product, "competition", "competition_level", "竞争度")
            ),
            "risk_tips": _text_list(
                _first(product, "risk_tips", "risks", "风险提示", "主要痛点")
            ),
        }
    )
    return item


def normalize_selection_report(
    structured: dict[str, Any],
    *,
    include_products: bool,
) -> dict[str, Any]:
    """归一化完整报告；品类分析模式禁止返回候选商品。"""
    report = dict(structured)
    market = structured.get("market")
    if isinstance(market, dict):
        normalized_market = dict(market)
        normalized_market["user_pains"] = _text_list(market.get("user_pains"))
        report["market"] = normalized_market

    if include_products:
        raw_products = structured.get("products")
        products = (
            [
                item
                for raw in raw_products
                if (item := normalize_selection_product(raw)) is not None
            ]
            if isinstance(raw_products, list)
            else []
        )
        report["products"] = products
    else:
        report["products"] = []

    recommendation = structured.get("recommendation")
    if isinstance(recommendation, dict):
        normalized_recommendation = dict(recommendation)
        normalized_recommendation["top_pick"] = (
            _first(recommendation, "top_pick", "首选商品", "推荐商品")
            or normalized_recommendation.get("top_pick")
        )
        normalized_recommendation["reasons"] = _text_list(
            recommendation.get("reasons")
        )
        normalized_recommendation["risks"] = _text_list(
            recommendation.get("risks")
        )
        report["recommendation"] = normalized_recommendation
    return report
