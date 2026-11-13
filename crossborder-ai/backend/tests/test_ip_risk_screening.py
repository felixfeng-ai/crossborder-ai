"""IP 风险初筛规则、报告和降级测试。"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.marketing_campaign import MarketingCampaign
from app.models.listing_draft import ListingDraft
from app.models.image_asset import ImageAsset
from app.models.persona import Persona
from app.models.product import Product
from app.models.user import User
from app.services.ai.deepseek import DeepSeekService
from app.services.ip_risk import (
    ensure_ip_report_for_publish,
    ip_publish_block_reason,
    screen_product_text,
    screen_ip_text,
)
from app.services.ip_vision import visual_items_to_risks


BRAND_CONFIG = {
    "version": "test-brand-v1",
    "brands": [
        {
            "brand_key": "nike",
            "display_name": "Nike",
            "aliases": ["Nike"],
            "match_mode": "word",
            "platforms": ["amazon", "shopify", "tiktok"],
            "severity": "high",
            "requires_authorization": True,
        }
    ],
}
CERT_CONFIG = {
    "version": "test-cert-v1",
    "claims": [
        {
            "code": "FDA",
            "patterns": ["FDA approved", "FDA registered"],
            "severity_without_evidence": "high",
            "evidence_type": "certification",
        },
        {
            "code": "CE",
            "patterns": ["CE certified", "CE approved"],
            "severity_without_evidence": "medium",
            "evidence_type": "certification",
        },
    ],
}
CATEGORY_CONFIG = {
    "version": "test-category-v1",
    "categories": {
        "toys": {
            "authorization_hint": "玩具类商品需要确认儿童认证和 IP 授权链。",
            "severity": "medium",
            "image_check_required": True,
        }
    },
}


def test_ip_screen_detects_brand_and_missing_certification_evidence():
    result = screen_ip_text(
        {
            "title": "Nike-style running shoes",
            "description": "FDA approved running shoes and official Nike partner.",
        },
        declarations=[],
        platform="amazon",
        category_code="toys",
        brand_config=BRAND_CONFIG,
        certification_config=CERT_CONFIG,
        category_config=CATEGORY_CONFIG,
    )

    codes = [item["code"] for item in result["risks"]]
    assert result["overall_risk"] == "high"
    assert codes.count("TRADEMARK_TERM") == 2
    assert "CERTIFICATION_CLAIM_WITHOUT_EVIDENCE" in codes
    assert "AUTHORIZATION_CLAIM_UNVERIFIED" in codes
    assert "CATEGORY_AUTHORIZATION_REVIEW" in codes
    nike = next(item for item in result["risks"] if item["code"] == "TRADEMARK_TERM")
    assert nike["evidence"]["field"] == "title"
    assert nike["evidence"]["text"] == "Nike"
    assert nike["evidence"]["start"] == 0


def test_ip_screen_is_deterministic():
    fields = {
        "title": "Nike shoes",
        "description": "CE certified and FDA approved.",
    }
    kwargs = dict(
        declarations=[],
        platform="amazon",
        category_code="toys",
        brand_config=BRAND_CONFIG,
        certification_config=CERT_CONFIG,
        category_config=CATEGORY_CONFIG,
    )

    first = screen_ip_text(fields, **kwargs)
    second = screen_ip_text(fields, **kwargs)

    assert first == second


def test_authorized_brand_is_downgraded_but_still_explainable():
    result = screen_ip_text(
        {"title": "Nike shoes"},
        declarations=[
            {
                "claim_type": "brand_authorization",
                "claim_value": "Nike",
                "evidence_status": "manually_verified",
                "expires_at": None,
            }
        ],
        platform="amazon",
        category_code=None,
        brand_config=BRAND_CONFIG,
        certification_config=CERT_CONFIG,
        category_config=CATEGORY_CONFIG,
    )

    risk = next(
        item for item in result["risks"] if item["code"] == "TRADEMARK_TERM"
    )
    assert risk["severity"] == "info"
    assert "人工" in risk["suggestion"]


def test_expired_brand_evidence_does_not_downgrade_risk():
    result = screen_ip_text(
        {"title": "Nike shoes"},
        declarations=[
            {
                "claim_type": "brand_authorization",
                "claim_value": "Nike",
                "evidence_status": "provided",
                "expires_at": (
                    datetime.now(timezone.utc) - timedelta(days=1)
                ).isoformat(),
            }
        ],
        platform="amazon",
        category_code=None,
        brand_config=BRAND_CONFIG,
        certification_config=CERT_CONFIG,
        category_config=CATEGORY_CONFIG,
    )

    risk = next(
        item for item in result["risks"] if item["code"] == "TRADEMARK_TERM"
    )
    assert risk["severity"] == "high"


@pytest.mark.asyncio
async def test_persona_category_requires_visual_check_before_publish(db_session):
    user = User(
        email=f"ip-category-{uuid.uuid4().hex[:8]}@test.com",
        username="ip-category",
        password_hash="x",
        plan="professional",
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        Persona(
            user_id=user.id,
            product_category="toys",
        )
    )
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
        title="Plush collectible toy",
    )
    db_session.add(product)
    await db_session.commit()

    report = await screen_product_text(
        db_session,
        user=user,
        product=product,
        listing=None,
        platform="amazon",
        scope="text",
    )

    assert report["status"] == "partial"
    assert report["coverage"]["image_required"] is True
    assert report["coverage"]["image"] == "not_checked"
    assert ip_publish_block_reason(report) == "check_incomplete"

    persona = (
        await db_session.execute(
            select(Persona).where(Persona.user_id == user.id)
        )
    ).scalar_one()
    persona.product_category = "cosmetics"
    await db_session.commit()
    optional_report = await screen_product_text(
        db_session,
        user=user,
        product=product,
        listing=None,
        platform="amazon",
        scope="text",
    )
    assert optional_report["status"] == "completed"
    assert optional_report["coverage"]["image_required"] is False
    assert ip_publish_block_reason(optional_report) is None


def test_visual_result_keeps_bbox_without_legal_conclusion():
    risks = visual_items_to_risks(
        [
            {
                "type": "logo",
                "label": "Nike",
                "confidence": 0.92,
                "bbox": [100, 200, 300, 400],
                "reason": "可见疑似品牌 Logo",
            }
        ],
        asset_id="asset-1",
    )

    assert risks[0]["code"] == "IMAGE_TRADEMARK_SUSPECTED"
    assert risks[0]["evidence"]["bbox"] == [100.0, 200.0, 300.0, 400.0]
    assert "侵权" not in risks[0]["suggestion"]


@pytest.mark.asyncio
async def test_ip_screen_api_persists_report_and_skips_missing_vision(
    client,
    auth_headers,
    db_session,
):
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    db_session.add(user)
    await db_session.flush()
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
        title="IP API 测试商品",
        brand_name="DONMIS",
    )
    db_session.add(product)
    await db_session.flush()
    campaign = MarketingCampaign(
        user_id=user.id,
        product_id=product.id,
        title="IP API 活动",
        objective="conversion",
        platform="amazon",
        market="US",
        language="en",
        budget_credits=100,
        brief_json="{}",
    )
    db_session.add(campaign)
    await db_session.commit()

    response = await client.post(
        "/api/v1/ip-risk/screen",
        json={
            "product_id": str(product.id),
            "scope": "both",
            "trigger": "manual",
            "text_fields": {
                "title": "Nike-style shoes",
                "description": "FDA approved and official Nike partner.",
            },
        },
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["overall_risk"] == "high"
    assert payload["status"] == "partial"
    assert payload["coverage"] == {
        "text": "checked",
        "image": "not_checked",
        "image_required": True,
    }

    report = await client.get(
        f"/api/v1/ip-risk/reports/{payload['report_id']}",
        headers=auth_headers,
    )
    assert report.status_code == 200
    assert report.json()["risks"]

    other = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"ip-other-{uuid.uuid4().hex[:8]}@example.com",
            "username": "ip-other",
            "password": "testpass123",
        },
    )
    foreign = await client.get(
        f"/api/v1/ip-risk/reports/{payload['report_id']}",
        headers={"Authorization": f"Bearer {other.json()['access_token']}"},
    )
    assert foreign.status_code == 404


@pytest.mark.asyncio
async def test_listing_generation_runs_ip_screening(
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
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
        title="Listing IP 生成测试",
    )
    db_session.add(product)
    await db_session.commit()

    async def fake_generate(self, system_prompt, user_prompt, **kwargs):
        return "Nike-style shoes. FDA approved. Official Nike partner."

    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)
    response = await client.post(
        "/api/v1/content/generate",
        json={
            "product_id": str(product.id),
            "platform": "amazon",
            "language": "en",
            "tone": "professional",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ip_risk"]["overall_risk"] == "high"
    assert payload["ip_risk"]["report_id"]


@pytest.mark.asyncio
async def test_publish_gate_helper_detects_high_risk(db_session):
    user = User(
        email=f"ip-gate-{uuid.uuid4().hex[:8]}@test.com",
        username="ip-gate",
        password_hash="x",
        plan="professional",
    )
    db_session.add(user)
    await db_session.flush()
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
        title="发布 Gate 商品",
    )
    db_session.add(product)
    await db_session.flush()
    listing = ListingDraft(
        user_id=user.id,
        product_id=product.id,
        platform="shopify",
        language="en",
        tone="professional",
        status="ready",
        title="Nike shoes",
        description="FDA approved official Nike partner.",
        bullet_points="[]",
        version=1,
        content_hash="x",
        compliance_status="pass",
    )
    db_session.add(listing)
    await db_session.commit()

    report = await ensure_ip_report_for_publish(
        db_session,
        user=user,
        product=product,
        listing=listing,
        platform="shopify",
    )

    assert report["overall_risk"] == "high"
    assert report["risks"]


@pytest.mark.asyncio
async def test_ip_declarations_downgrade_risks(
    client,
    auth_headers,
    db_session,
):
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
        title="授权声明测试商品",
    )
    db_session.add(product)
    await db_session.commit()

    future_expiry = datetime.now(timezone.utc) + timedelta(days=90)
    for claim_type, claim_value in [
        ("brand_authorization", "Nike"),
        ("certification", "FDA"),
    ]:
        response = await client.post(
            "/api/v1/ip-risk/declarations",
            json={
                "product_id": str(product.id),
                "claim_type": claim_type,
                "claim_value": claim_value,
                "evidence_url": "https://example.com/evidence.pdf",
                "evidence_status": "manually_verified",
                "expires_at": future_expiry.isoformat(),
            },
            headers=auth_headers,
        )
        assert response.status_code == 201, response.text

    screened = await client.post(
        "/api/v1/ip-risk/screen",
        json={
            "product_id": str(product.id),
            "scope": "text",
            "text_fields": {
                "title": "Nike shoes",
                "description": "FDA approved official Nike partner.",
            },
        },
        headers=auth_headers,
    )
    assert screened.status_code == 201, screened.text
    assert screened.json()["overall_risk"] == "low"
    assert all(
        item["severity"] == "info"
        for item in screened.json()["risks"]
    )

    listed = await client.get(
        f"/api/v1/ip-risk/declarations?product_id={product.id}",
        headers=auth_headers,
    )
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 2
    assert all(item["expires_at"] for item in listed.json()["items"])
    declaration_id = listed.json()["items"][0]["id"]
    deleted = await client.delete(
        f"/api/v1/ip-risk/declarations/{declaration_id}",
        headers=auth_headers,
    )
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_visual_ip_screen_returns_bbox_when_model_configured(
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
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
        title="视觉 IP 测试商品",
    )
    asset = ImageAsset(
        user_id=user.id,
        name="visual-ip.png",
        kind="upload",
        storage_key=f"{user.id}/visual-ip.png",
        content_type="image/png",
        width=800,
        height=800,
        file_size=100,
    )
    db_session.add_all([product, asset])
    await db_session.commit()

    monkeypatch.setattr(
        "app.services.ip_vision.get_vision_config",
        lambda: ("test-key", "qwen3-vl-plus", "https://example.com"),
    )

    async def fake_analyze(image_asset):
        assert image_asset.id == asset.id
        return [
            {
                "type": "logo",
                "label": "Nike",
                "confidence": 0.9,
                "bbox": [100, 100, 300, 300],
            }
        ]

    monkeypatch.setattr(
        "app.services.ip_vision.analyze_image_asset",
        fake_analyze,
    )
    response = await client.post(
        "/api/v1/ip-risk/screen",
        json={
            "product_id": str(product.id),
            "image_asset_ids": [str(asset.id)],
            "scope": "both",
            "text_fields": {"title": "Plain product"},
        },
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["coverage"]["image"] == "checked"
    image_risk = next(
        item
        for item in payload["risks"]
        if item["code"] == "IMAGE_TRADEMARK_SUSPECTED"
    )
    assert image_risk["evidence"]["bbox"] == [100.0, 100.0, 300.0, 300.0]


@pytest.mark.asyncio
async def test_image_scope_without_vision_config_is_partial(
    db_session,
    monkeypatch,
):
    user = User(
        email=f"ip-vision-off-{uuid.uuid4().hex[:8]}@test.com",
        username="ip-vision-off",
        password_hash="x",
        plan="professional",
    )
    db_session.add(user)
    await db_session.flush()
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
        title="无视觉模型",
    )
    asset = ImageAsset(
        user_id=user.id,
        name="no-vision.png",
        kind="upload",
        storage_key=f"{user.id}/no-vision.png",
        content_type="image/png",
        width=100,
        height=100,
        file_size=10,
    )
    db_session.add_all([product, asset])
    await db_session.commit()
    monkeypatch.setattr(
        "app.services.ip_vision.get_vision_config",
        lambda: None,
    )

    from app.services.ip_risk import screen_product_text

    report = await screen_product_text(
        db_session,
        user=user,
        product=product,
        listing=None,
        platform="amazon",
        scope="image",
        image_assets=[asset],
    )

    assert report["status"] == "partial"
    assert report["overall_risk"] == "unknown"
    assert report["coverage"] == {
        "text": "not_checked",
        "image": "not_checked",
        "image_required": True,
    }
    assert any(
        item["code"] == "VISUAL_CHECK_NOT_CONFIGURED"
        for item in report["risks"]
    )


def test_ip_publish_gate_blocks_high_risk_and_incomplete_checks():
    assert ip_publish_block_reason(
        {
            "status": "completed",
            "overall_risk": "high",
            "coverage": {"text": "checked", "image": "checked"},
        }
    ) == "high_risk"
    assert ip_publish_block_reason(
        {
            "status": "partial",
            "overall_risk": "unknown",
            "coverage": {"text": "checked", "image": "not_checked"},
        }
    ) == "check_incomplete"
    assert ip_publish_block_reason(
        {
            "status": "failed",
            "overall_risk": "low",
            "coverage": {"text": "checked", "image": "failed"},
        }
    ) == "check_incomplete"
    assert ip_publish_block_reason(
        {
            "status": "completed",
            "overall_risk": "low",
            "coverage": {"text": "not_checked", "image": "checked"},
        }
    ) == "check_incomplete"
    assert ip_publish_block_reason(
        {
            "status": "completed",
            "overall_risk": "low",
            "coverage": {"text": "checked", "image": "failed"},
        }
    ) == "check_incomplete"
    assert ip_publish_block_reason(
        {
            "status": "completed",
            "overall_risk": "low",
            "coverage": {"text": "checked", "image": "not_checked"},
        }
    ) is None
    assert ip_publish_block_reason(
        {
            "status": "completed",
            "overall_risk": "low",
            "coverage": {"text": "checked", "image": "checked"},
        }
    ) is None
