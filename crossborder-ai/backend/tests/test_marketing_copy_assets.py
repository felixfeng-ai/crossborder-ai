"""营销文案资产化、平台版本和 A/B 变体。"""

import json
import re
import uuid

import pytest
from sqlalchemy import select

from app.models.marketing_campaign import MarketingCampaign
from app.models.product import Product
from app.models.user import User
from app.services.marketing_copy_service import generate_marketing_copy_batch


async def _create_context(db_session):
    user = User(
        email=f"marketing-copy-{uuid.uuid4().hex[:8]}@example.com",
        username="marketing-copy",
        password_hash="x",
        plan="professional",
        credits=200,
    )
    db_session.add(user)
    await db_session.flush()
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
        title="DONMIS 冬日香薰礼盒",
        description="包含多种干花香薰片，适合节日送礼。",
        price=59.9,
        brand_name="DONMIS",
    )
    db_session.add(product)
    await db_session.flush()
    campaign = MarketingCampaign(
        user_id=user.id,
        product_id=product.id,
        title="冬日香薰礼盒转化活动",
        objective="conversion",
        platform="tiktok",
        market="US",
        language="en",
        budget_credits=500,
        brief_json='{"offer":"节日礼赠","audience":"美国节日送礼用户"}',
    )
    db_session.add(campaign)
    await db_session.flush()
    return user, product, campaign


class _FakeCopyLLM:
    async def generate(self, system_prompt, user_prompt, **kwargs):
        items = []
        for platform in ("tiktok", "amazon", "shopify"):
            for variant in ("A", "B"):
                items.append({
                    "platform": platform,
                    "variant_key": variant,
                    "headline": f"{platform} {variant} holiday gift",
                    "body": f"Body for {platform} variant {variant}",
                    "cta": "Shop the holiday gift",
                    "hashtags": ["#HolidayGift", "#HomeFragrance"],
                    "keywords": ["holiday gift", "fragrance gift"],
                })
        return json.dumps({"items": items}, ensure_ascii=False)


@pytest.mark.asyncio
async def test_generate_copy_creates_three_platforms_and_ab_variants(db_session):
    user, _, campaign = await _create_context(db_session)

    assets = await generate_marketing_copy_batch(
        db_session,
        user,
        campaign_id=campaign.id,
        platforms=["tiktok", "amazon", "shopify"],
        language="en",
        instructions="强调节日送礼",
        llm=_FakeCopyLLM(),
    )

    assert len(assets) == 6
    assert len({asset.batch_id for asset in assets}) == 1
    assert {asset.platform for asset in assets} == {
        "tiktok",
        "amazon",
        "shopify",
    }
    assert {(asset.platform, asset.variant_key) for asset in assets} == {
        (platform, variant)
        for platform in ("tiktok", "amazon", "shopify")
        for variant in ("A", "B")
    }
    assert all(asset.campaign_id == campaign.id for asset in assets)
    assert all(asset.user_id == user.id for asset in assets)
    assert all(asset.compliance_status == "pass" for asset in assets)


@pytest.mark.asyncio
async def test_invalid_llm_output_uses_factual_fallback(db_session):
    user, product, campaign = await _create_context(db_session)

    class _BrokenLLM:
        async def generate(self, system_prompt, user_prompt, **kwargs):
            return "not-json"

    assets = await generate_marketing_copy_batch(
        db_session,
        user,
        campaign_id=campaign.id,
        platforms=["tiktok", "shopify"],
        language="en",
        instructions="",
        llm=_BrokenLLM(),
    )

    assert len(assets) == 4
    assert all("DONMIS" in asset.body for asset in assets)
    assert "59.9" not in " ".join(asset.body for asset in assets)
    assert not re.search(r"[\u4e00-\u9fff]", " ".join(asset.body for asset in assets))


@pytest.mark.asyncio
async def test_copy_api_lists_and_isolates_campaign_assets(
    client,
    auth_headers,
    db_session,
    monkeypatch,
):
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    user.plan = "professional"
    await db_session.flush()
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
        title="可生成文案的商品",
        description="商品事实描述",
    )
    db_session.add(product)
    await db_session.flush()
    campaign = MarketingCampaign(
        user_id=user.id,
        product_id=product.id,
        title="文案 API 活动",
        objective="conversion",
        platform="tiktok",
        market="US",
        language="en",
        budget_credits=100,
        brief_json="{}",
    )
    db_session.add(campaign)
    await db_session.flush()

    async def fake_generate(self, system_prompt, user_prompt, **kwargs):
        return await _FakeCopyLLM().generate(system_prompt, user_prompt, **kwargs)

    monkeypatch.setattr(
        "app.services.ai.deepseek.DeepSeekService.generate",
        fake_generate,
    )

    created = await client.post(
        f"/api/v1/marketing-campaigns/{campaign.id}/copy/generate",
        json={
            "platforms": ["tiktok", "amazon", "shopify"],
            "language": "en",
            "instructions": "A/B 测试不同购买动机",
        },
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["count"] == 6

    listed = await client.get(
        f"/api/v1/marketing-campaigns/{campaign.id}/copy",
        headers=auth_headers,
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 6
    copy_id = listed.json()["items"][0]["id"]
    updated = await client.patch(
        f"/api/v1/marketing-campaigns/{campaign.id}/copy/{copy_id}",
        json={
            "headline": "Updated factual headline",
            "body": "Updated factual body.",
            "cta": "Learn more",
        },
        headers=auth_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2
    assert updated.json()["headline"] == "Updated factual headline"

    other = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"copy-other-{uuid.uuid4().hex[:8]}@example.com",
            "username": "copy-other",
            "password": "testpass123",
        },
    )
    other_headers = {
        "Authorization": f"Bearer {other.json()['access_token']}",
    }
    foreign = await client.get(
        f"/api/v1/marketing-campaigns/{campaign.id}/copy",
        headers=other_headers,
    )
    assert foreign.status_code == 404
