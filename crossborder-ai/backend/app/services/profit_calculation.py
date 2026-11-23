"""确定性跨境利润计算。

模型不能在这里填写成本或利润数字。所有输入必须来自卖家、平台事实或市场样本，
缺失值直接拒绝，避免把未知采购价或运费当成 0。
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


class ProfitCalculationError(ValueError):
    """利润输入不完整或数值非法。"""


def _decimal(value: Any, field: str, *, allow_zero: bool = True) -> Decimal:
    """把输入转换为 Decimal；拒绝空值、布尔值、NaN 和无穷大。"""
    if value is None or value == "" or isinstance(value, bool):
        raise ProfitCalculationError(f"{field}不能为空")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ProfitCalculationError(f"{field}不是有效数字") from exc
    if not number.is_finite():
        raise ProfitCalculationError(f"{field}不是有效数字")
    if number < 0 or (not allow_zero and number == 0):
        comparator = "大于 0" if not allow_zero else "不能小于 0"
        raise ProfitCalculationError(f"{field}{comparator}")
    return number


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _percent(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def calculate_profit(
    *,
    selling_price_usd: Any,
    exchange_rate_cny_per_usd: Any,
    product_cost_cny: Any,
    shipping_cost_cny: Any,
    platform_fee_rate: Any,
    fulfillment_fee_usd: Any = 0,
    other_cost_cny: Any = 0,
) -> dict[str, Any]:
    """按固定公式计算单件利润和盈亏平衡价。"""
    selling_price = _decimal(
        selling_price_usd,
        "售价",
        allow_zero=False,
    )
    exchange_rate = _decimal(
        exchange_rate_cny_per_usd,
        "汇率",
        allow_zero=False,
    )
    product_cost = _decimal(
        product_cost_cny,
        "采购价",
        allow_zero=False,
    )
    shipping_cost = _decimal(shipping_cost_cny, "头程/包装运费")
    fee_rate = _decimal(platform_fee_rate, "平台佣金率")
    fulfillment_fee = _decimal(fulfillment_fee_usd, "尾程配送费")
    other_cost = _decimal(other_cost_cny, "其他成本")

    if fee_rate >= 1:
        raise ProfitCalculationError("平台佣金率必须小于 100%")

    revenue_cny = selling_price * exchange_rate
    platform_fee_cny = revenue_cny * fee_rate
    fulfillment_fee_cny = fulfillment_fee * exchange_rate
    total_cost_cny = (
        product_cost
        + shipping_cost
        + platform_fee_cny
        + fulfillment_fee_cny
        + other_cost
    )
    net_profit_cny = revenue_cny - total_cost_cny
    net_margin_pct = (
        net_profit_cny / revenue_cny * Decimal("100")
        if revenue_cny > 0
        else Decimal("0")
    )

    # 盈亏平衡：售价 × 汇率 × (1 - 佣金率) = 其余固定成本。
    fixed_cost_cny = (
        product_cost + shipping_cost + fulfillment_fee_cny + other_cost
    )
    break_even = fixed_cost_cny / (exchange_rate * (Decimal("1") - fee_rate))
    net_profit_usd = net_profit_cny / exchange_rate

    return {
        "formula_version": "profit-v1",
        "selling_price_usd": _money(selling_price),
        "exchange_rate_cny_per_usd": _money(exchange_rate),
        "revenue_cny": _money(revenue_cny),
        "costs": {
            "product_cost_cny": _money(product_cost),
            "shipping_cost_cny": _money(shipping_cost),
            "platform_fee_rate": _money(fee_rate),
            "platform_fee_cny": _money(platform_fee_cny),
            "fulfillment_fee_usd": _money(fulfillment_fee),
            "fulfillment_fee_cny": _money(fulfillment_fee_cny),
            "other_cost_cny": _money(other_cost),
            "total_cny": _money(total_cost_cny),
        },
        "net_profit_cny": _money(net_profit_cny),
        "net_profit_usd": _money(net_profit_usd),
        "net_margin_pct": _percent(net_margin_pct),
        "break_even_selling_price_usd": _money(break_even),
        "profitable": net_profit_cny > 0,
    }


def calculate_profit_scenarios(
    *,
    selling_prices_usd: dict[str, Any],
    exchange_rate_cny_per_usd: Any,
    product_cost_cny: Any,
    shipping_cost_cny: Any,
    platform_fee_rate: Any,
    fulfillment_fee_usd: Any = 0,
    other_cost_cny: Any = 0,
) -> dict[str, dict[str, Any]]:
    """按真实观测价格或卖家给定价格计算保守、基准和进取情景。"""
    if set(selling_prices_usd) != {"conservative", "base", "aggressive"}:
        raise ProfitCalculationError(
            "利润情景必须包含 conservative、base 和 aggressive"
        )
    return {
        name: calculate_profit(
            selling_price_usd=price,
            exchange_rate_cny_per_usd=exchange_rate_cny_per_usd,
            product_cost_cny=product_cost_cny,
            shipping_cost_cny=shipping_cost_cny,
            platform_fee_rate=platform_fee_rate,
            fulfillment_fee_usd=fulfillment_fee_usd,
            other_cost_cny=other_cost_cny,
        )
        for name, price in selling_prices_usd.items()
    }
