"""确定性利润计算必须拒绝缺失成本并输出可审计明细。"""

import pytest

from app.services.profit_calculation import (
    ProfitCalculationError,
    calculate_profit,
    calculate_profit_scenarios,
)


def test_calculate_profit_returns_auditable_breakdown():
    result = calculate_profit(
        selling_price_usd=30,
        exchange_rate_cny_per_usd=7.2,
        product_cost_cny=30,
        shipping_cost_cny=20,
        platform_fee_rate=0.15,
        fulfillment_fee_usd=5,
        other_cost_cny=0,
    )

    assert result["revenue_cny"] == 216
    assert result["costs"]["platform_fee_cny"] == 32.4
    assert result["costs"]["fulfillment_fee_cny"] == 36
    assert result["costs"]["total_cny"] == 118.4
    assert result["net_profit_cny"] == 97.6
    assert result["net_margin_pct"] == 45.19
    assert result["break_even_selling_price_usd"] == 14.05
    assert result["formula_version"] == "profit-v1"


def test_calculate_profit_rejects_missing_product_cost():
    with pytest.raises(ProfitCalculationError, match="采购价"):
        calculate_profit(
            selling_price_usd=30,
            exchange_rate_cny_per_usd=7.2,
            product_cost_cny=None,
            shipping_cost_cny=20,
            platform_fee_rate=0.15,
            fulfillment_fee_usd=5,
        )


def test_profit_scenarios_use_observed_price_range():
    result = calculate_profit_scenarios(
        selling_prices_usd={"conservative": 24.99, "base": 29.99, "aggressive": 34.99},
        exchange_rate_cny_per_usd=7.2,
        product_cost_cny=35,
        shipping_cost_cny=18,
        platform_fee_rate=0.15,
        fulfillment_fee_usd=4.5,
    )

    assert set(result) == {"conservative", "base", "aggressive"}
    assert result["conservative"]["selling_price_usd"] == 24.99
    assert result["aggressive"]["net_profit_cny"] > result["conservative"]["net_profit_cny"]
