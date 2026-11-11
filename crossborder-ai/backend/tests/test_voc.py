"""VOC 评论导入、分析和 Listing 反哺测试。"""

import json
import uuid

import pytest
from sqlalchemy import select

from app.models.product import Product
from app.models.user import User
from app.models.voc import VocAnalysis
from app.services.ai.deepseek import DeepSeekService
from app.services.voc_service import _fallback_analysis, parse_review_input
from app.services.listing_service import generate_and_persist_listing


def test_parse_review_input_supports_csv_and_plain_text():
    csv = """review,rating
"Battery lasts all day",5
"Too heavy for travel",2
"Sound quality is excellent",4
"""
    reviews = parse_review_input(csv)

    assert len(reviews) == 3
    assert "Battery lasts all day" in reviews[0]
    assert "Too heavy for travel" in reviews[1]
    assert reviews[2].startswith("Sound quality")


def test_fallback_analysis_does_not_treat_negative_clause_as_selling_point():
    analysis = _fallback_analysis(
        [
            "Battery lasts all day but the headband feels tight",
            "Too heavy for long commutes",
        ]
    )

    assert "Battery lasts all day" in analysis["selling_points"]
    assert all("Too heavy" not in item for item in analysis["selling_points"])
    assert any("Too heavy" in item for item in analysis["pain_points"])


@pytest.mark.asyncio
async def test_voc_analysis_persists_aggregate_and_charges_credit(
    client,
    db_session,
    auth_headers,
    monkeypatch,
):
    user = (
        await db_session.execute(select(User).where(User.email == "test@example.com"))
    ).scalar_one()
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
        title="Travel headphones",
        price=18,
    )
    db_session.add(product)
    await db_session.flush()
    user.credits = 30

    async def fake_generate(self, system_prompt, user_prompt, **kwargs):
        assert "Travel headphones" in user_prompt
        return json.dumps(
            {
                "summary": "Users like battery life but complain about weight.",
                "pain_points": ["heavy for travel", "tight headband"],
                "selling_points": ["all-day battery", "clear sound"],
                "objections": ["weight"],
                "keywords": ["battery", "heavy", "sound"],
                "sentiment": {
                    "positive": 0.6,
                    "neutral": 0.2,
                    "negative": 0.2,
                },
                "recommendations": ["Emphasize lightweight comfort and battery life"],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)
    response = await client.post(
        "/api/v1/voc/analyze",
        json={
            "product_id": str(product.id),
            "platform": "amazon",
            "language": "en",
            "reviews": "Battery is excellent\nToo heavy\nSound is clear",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["review_count"] == 3
    assert body["pain_points"] == ["heavy for travel", "tight headband"]
    analysis = (
        await db_session.execute(
            select(VocAnalysis).where(VocAnalysis.id == uuid.UUID(body["id"]))
        )
    ).scalar_one()
    assert analysis.product_id == product.id
    assert "Battery is excellent" not in analysis.pain_points_json
    await db_session.refresh(user)
    assert user.credits == 29


@pytest.mark.asyncio
async def test_voc_rejects_foreign_product(client, db_session, auth_headers):
    other = User(
        email=f"voc-other-{uuid.uuid4().hex[:8]}@example.com",
        username="voc-other",
        password_hash="x",
    )
    db_session.add(other)
    await db_session.flush()
    product = Product(
        user_id=other.id,
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
        title="Foreign",
    )
    db_session.add(product)
    await db_session.flush()

    response = await client.post(
        "/api/v1/voc/analyze",
        json={
            "product_id": str(product.id),
            "reviews": "Good\nBad\nOkay",
        },
        headers=auth_headers,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_listing_generation_uses_latest_voc_context(db_session, monkeypatch):
    user = User(
        email=f"voc-listing-{uuid.uuid4().hex[:8]}@example.com",
        username="voc-listing",
        password_hash="x",
        credits=30,
    )
    db_session.add(user)
    await db_session.flush()
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
        title="Travel headphones",
        price=18,
    )
    db_session.add(product)
    await db_session.flush()
    db_session.add(
        VocAnalysis(
            user_id=user.id,
            product_id=product.id,
            platform="amazon",
            language="en",
            review_count=10,
            summary="Buyers want lighter headphones.",
            pain_points_json='["heavy for travel"]',
            selling_points_json='["all-day battery"]',
            objections_json='["weight"]',
            keywords_json='["lightweight"]',
            sentiment_json="{}",
            recommendations_json="[]",
            model_used="test",
        )
    )
    await db_session.flush()
    captured: list[str] = []

    class FakeLLM:
        async def generate(self, system_prompt, user_prompt, **kwargs):
            captured.append(user_prompt)
            return "Travel Headphones with All-Day Battery"

        async def generate_product_description(self, **kwargs):
            captured.append(kwargs["product_features"])
            return "Description"

        async def generate_bullet_points(self, **kwargs):
            captured.append(kwargs["features"])
            return ["All-day battery", "Lightweight design", "Clear sound"]

        async def optimize_seo(self, **kwargs):
            return {"seo_title": "Travel Headphones", "seo_description": "Lightweight"}

    await generate_and_persist_listing(
        db_session,
        user=user,
        product=product,
        platform="amazon",
        language="en",
        llm=FakeLLM(),
    )

    assert any("heavy for travel" in text for text in captured)
    assert any("all-day battery" in text for text in captured)
