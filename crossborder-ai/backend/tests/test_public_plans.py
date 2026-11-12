"""公开套餐接口与首页内容一致性测试。"""

import pytest


@pytest.mark.asyncio
async def test_public_plans_expose_current_capabilities(client):
    response = await client.get("/api/v1/billing/plans")

    assert response.status_code == 200
    plans = {item["id"]: item for item in response.json()["plans"]}
    assert plans["free"]["price"] == 0
    assert plans["standard"]["price"] == 99
    assert plans["professional"]["price"] == 249
    assert plans["standard"]["first_month_price"] == 79
    assert plans["professional"]["first_month_price"] == 199
    assert plans["professional"]["first_month_bonus_credits"] == 100
    assert plans["professional"]["recommended"] is True
    assert any("30 AI 积分" in item for item in plans["free"]["features"])
    assert any("800 AI 积分" in item for item in plans["standard"]["features"])
    assert any("3,000 AI 积分" in item for item in plans["professional"]["features"])
    assert any("VOC" in item for item in plans["free"]["features"])
    assert any("自动巡检" in item for item in plans["standard"]["features"])
    assert any("字幕" in item for item in plans["professional"]["features"])


@pytest.mark.asyncio
async def test_public_credit_packs_match_current_pricing(client):
    response = await client.get("/api/v1/billing/credit-packs")

    assert response.status_code == 200
    packs = {item["id"]: item for item in response.json()["packs"]}
    assert {key: value["credits"] for key, value in packs.items()} == {
        "pack_200": 200,
        "pack_500": 500,
        "pack_1200": 1200,
        "pack_trial_50": 50,
    }
    assert {key: value["price"] for key, value in packs.items()} == {
        "pack_200": 19,
        "pack_500": 45,
        "pack_1200": 99,
        "pack_trial_50": 9.9,
    }
