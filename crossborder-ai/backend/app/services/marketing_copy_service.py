"""多平台营销文案生成、合规检查和活动资产落库。"""

import json
import logging
import re
import uuid
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.marketing_campaign import MarketingCampaign
from app.models.marketing_copy import MarketingCopyAsset
from app.models.product import Product
from app.models.user import User
from app.services import provider_config
from app.services.ai.compliance import check_text, merge_banned_words
from app.services.ai.deepseek import DeepSeekService
from app.services.ai.persona_kit import (
    build_persona_kit,
    fetch_persona,
    format_persona_block,
)


logger = logging.getLogger("veyaship")

MARKETING_COPY_PLATFORMS = ("tiktok", "amazon", "shopify")
MARKETING_COPY_VARIANTS = ("A", "B")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")

PLATFORM_COPY_RULES = {
    "tiktok": (
        "Short-form video copy. Lead with a strong hook, keep sentences spoken and "
        "concise, use 3-5 relevant hashtags, and end with a clear action."
    ),
    "amazon": (
        "Amazon listing copy. Use a specific benefit-led headline, factual body, "
        "search-relevant keywords, and a restrained retail CTA. Do not invent specs."
    ),
    "shopify": (
        "Shopify product-page copy. Blend brand story with concrete product benefits, "
        "keep the CTA direct, and include reusable SEO keywords."
    ),
}


def _parse_json_object(raw: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group())
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _string_list(value: Any, limit: int = 10) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:limit]


def _campaign_brief(campaign: MarketingCampaign) -> dict[str, Any]:
    try:
        parsed = json.loads(campaign.brief_json or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _fallback_copy(
    *,
    platform: str,
    variant_key: str,
    campaign: MarketingCampaign,
    product: Product,
    language: str,
) -> dict[str, Any]:
    """模型不可用时，只使用已确认的商品和活动事实生成可编辑初稿。"""
    title = product.title or "Product"
    description = (product.description or "").strip()
    brand = (product.brand_name or "").strip()
    brief = _campaign_brief(campaign)
    audience = str(brief.get("audience") or "").strip()
    offer = str(brief.get("offer") or "").strip()
    english_target = language.lower() == "en"
    display_title = (
        brand or "This product"
        if english_target and CJK_RE.search(title)
        else title
    )
    factual_detail = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", description)).strip()
    if english_target and CJK_RE.search(factual_detail):
        factual_detail = ""
    factual_detail = factual_detail[:280]

    angle = (
        ("直接利益" if variant_key == "A" else "情绪场景")
        if language.lower() == "zh"
        else ("benefit-led" if variant_key == "A" else "emotion-led")
    )
    if platform == "tiktok":
        headline = (
            f"{display_title}: make the everyday moment feel special"
            if variant_key == "A"
            else f"The gift that turns a simple moment into a memory"
        )
        cta = "Tap to discover the collection"
        hashtags = ["#GiftIdeas", "#ProductFinds", "#Lifestyle"]
    elif platform == "amazon":
        headline = (
            f"{display_title} - designed for everyday use"
            if variant_key == "A"
            else f"{display_title} - a thoughtful choice for gifting"
        )
        cta = "Add to cart"
        hashtags = []
    else:
        headline = (
            f"{display_title}, made for considered everyday moments"
            if variant_key == "A"
            else f"Give a moment that feels personal: {display_title}"
        )
        cta = "Explore the product"
        hashtags = ["#ShopSmall", "#EverydayMoments"]

    identity = f" Brand: {brand}." if brand else ""
    audience_line = (
        f" For {audience}."
        if audience and (not english_target or not CJK_RE.search(audience))
        else ""
    )
    offer_line = (
        f" Current campaign note: {offer}."
        if offer and (not english_target or not CJK_RE.search(offer))
        else ""
    )
    body = (
        f"{display_title} brings a practical yet thoughtful option for the target market."
        f"{identity}{audience_line}{offer_line}"
        f" Confirmed product detail: {factual_detail or 'See the current product page for details.'}"
        f" This {angle} version keeps every claim grounded in the supplied product facts."
    )
    keywords = [
        token
        for token in re.findall(r"[A-Za-z0-9\u4e00-\u9fff]{2,}", title)
        if token.lower() not in {"the", "and", "for", "with"}
        and (not english_target or not CJK_RE.search(token))
    ][:8]
    return {
        "platform": platform,
        "variant_key": variant_key,
        "headline": headline[:500],
        "body": body[:4000],
        "cta": cta[:500],
        "hashtags": hashtags,
        "keywords": keywords,
        "angle": angle,
    }


def _fallback_items(
    platforms: list[str],
    campaign: MarketingCampaign,
    product: Product,
    language: str,
) -> list[dict[str, Any]]:
    return [
        _fallback_copy(
            platform=platform,
            variant_key=variant,
            campaign=campaign,
            product=product,
            language=language,
        )
        for platform in platforms
        for variant in MARKETING_COPY_VARIANTS
    ]


async def _generate_items_with_llm(
    *,
    llm: DeepSeekService,
    campaign: MarketingCampaign,
    product: Product,
    platforms: list[str],
    language: str,
    instructions: str,
) -> list[dict[str, Any]]:
    brief = _campaign_brief(campaign)
    persona_block = ""
    system_prompt = (
        "You are a senior cross-border e-commerce marketing copy director. "
        "Create two genuinely different A/B variants for every requested platform. "
        "Use only supplied product and campaign facts. Never invent price, discount, "
        "certifications, ingredients, dimensions, reviews, or performance claims. "
        "Return ONLY valid JSON in this shape: "
        '{"items":[{"platform":"tiktok","variant_key":"A","headline":"...",'
        '"body":"...","cta":"...","hashtags":["#..."],"keywords":["..."],'
        '"angle":"benefit or emotion"}]}.'
    )

    platform_rules = "\n".join(
        f"- {platform}: {PLATFORM_COPY_RULES[platform]}"
        for platform in platforms
    )
    user_prompt = (
        f"Product title: {product.title}\n"
        f"Brand: {product.brand_name or 'Not provided'}\n"
        f"Product description: {product.description or 'Not provided'}\n"
        f"Objective: {campaign.objective}\n"
        f"Market: {campaign.market}\n"
        f"Language: {language}\n"
        f"Campaign brief: {json.dumps(brief, ensure_ascii=False)}\n"
        f"Additional instruction: {instructions or 'None'}\n"
        f"Platforms and rules:\n{platform_rules}\n"
        "Variant A should use a direct benefit-led angle. Variant B should use a "
        "different emotional or story-led angle while preserving the same facts."
    )
    raw = await llm.generate(
        system_prompt,
        user_prompt,
        max_tokens=3500,
        persona_block=persona_block or None,
    )
    payload = _parse_json_object(raw)
    parsed_items = payload.get("items")
    return parsed_items if isinstance(parsed_items, list) else []


def _normalize_generated_items(
    *,
    parsed_items: list[dict[str, Any]],
    fallback_items: list[dict[str, Any]],
    platforms: list[str],
) -> list[dict[str, Any]]:
    parsed_by_key = {
        (str(item.get("platform", "")).lower(), str(item.get("variant_key", "")).upper()): item
        for item in parsed_items
        if isinstance(item, dict)
    }
    normalized: list[dict[str, Any]] = []
    for fallback in fallback_items:
        platform = fallback["platform"]
        variant = fallback["variant_key"]
        candidate = parsed_by_key.get((platform, variant), {})
        headline = str(candidate.get("headline") or fallback["headline"]).strip()
        body = str(candidate.get("body") or fallback["body"]).strip()
        cta = str(candidate.get("cta") or fallback["cta"]).strip()
        normalized.append({
            "platform": platform,
            "variant_key": variant,
            "headline": headline[:500],
            "body": body[:4000],
            "cta": cta[:500],
            "hashtags": _string_list(candidate.get("hashtags")) or fallback["hashtags"],
            "keywords": _string_list(candidate.get("keywords")) or fallback["keywords"],
            "angle": str(candidate.get("angle") or fallback["angle"])[:100],
        })
    return normalized


def _copy_compliance(
    item: dict[str, Any],
    banned_words: Optional[list[str]] = None,
) -> list[str]:
    violations: list[str] = []
    word_list = merge_banned_words(banned_words or [])
    texts = [
        item["headline"],
        item["body"],
        item["cta"],
        *item["hashtags"],
        *item["keywords"],
    ]
    for text in texts:
        for word in check_text(text, word_list):
            if word not in violations:
                violations.append(word)
    return violations


def evaluate_marketing_copy_compliance(
    *,
    headline: str,
    body: str,
    cta: str,
    hashtags: list[str],
    keywords: list[str],
    banned_words: Optional[list[str]] = None,
) -> list[str]:
    """供 API 编辑和 Agent 生成共用的确定性合规检查。"""
    return _copy_compliance(
        {
            "headline": headline,
            "body": body,
            "cta": cta,
            "hashtags": hashtags,
            "keywords": keywords,
        },
        banned_words,
    )


async def generate_marketing_copy_batch(
    db: AsyncSession,
    user: User,
    *,
    campaign_id: UUID,
    platforms: list[str],
    language: str,
    instructions: str = "",
    source: str = "agent",
    llm: Optional[DeepSeekService] = None,
) -> list[MarketingCopyAsset]:
    """生成并保存批次内所有平台 A/B 文案。"""
    requested = list(dict.fromkeys(
        str(platform).strip().lower()
        for platform in platforms
        if str(platform).strip().lower() in MARKETING_COPY_PLATFORMS
    ))
    if not requested:
        raise ValueError("至少选择一个支持的文案平台")

    campaign = (
        await db.execute(
            select(MarketingCampaign).where(
                MarketingCampaign.id == campaign_id,
                MarketingCampaign.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if campaign is None:
        raise ValueError("营销活动不存在")
    product = (
        await db.get(Product, campaign.product_id)
        if campaign.product_id
        else None
    )
    if product is None or not (product.title or "").strip():
        raise ValueError("活动缺少可用的绑定商品")

    fallback_items = _fallback_items(requested, campaign, product, language)
    text_llm = llm or DeepSeekService()
    configured_key = provider_config.get(
        "deepseek",
        "api_key",
        settings.DEEPSEEK_API_KEY or "",
    )
    if llm is not None or configured_key:
        try:
            parsed_items = await _generate_items_with_llm(
                llm=text_llm,
                campaign=campaign,
                product=product,
                platforms=requested,
                language=language,
                instructions=instructions,
            )
        except Exception as exc:
            logger.warning("营销文案模型生成失败，使用事实降级文案: %s", exc)
            parsed_items = []
    else:
        # 未配置模型 Key 时直接使用事实降级，避免无效网络重试阻塞页面。
        parsed_items = []
    items = _normalize_generated_items(
        parsed_items=parsed_items,
        fallback_items=fallback_items,
        platforms=requested,
    )

    persona = await fetch_persona(db, user.id)
    persona_kit = build_persona_kit(persona) if persona else {}
    banned_words = persona_kit.get("banned_words") or []
    batch_id = uuid.uuid4()
    model_used = provider_config.get("deepseek", "model", settings.DEEPSEEK_MODEL)
    brief = _campaign_brief(campaign)
    assets: list[MarketingCopyAsset] = []
    for item in items:
        violations = _copy_compliance(item, banned_words)
        compliance_status = "block" if violations else "pass"
        asset = MarketingCopyAsset(
            batch_id=batch_id,
            user_id=user.id,
            campaign_id=campaign.id,
            platform=item["platform"],
            variant_key=item["variant_key"],
            language=language,
            headline=item["headline"],
            body=item["body"],
            cta=item["cta"],
            hashtags_json=json.dumps(item["hashtags"], ensure_ascii=False),
            keywords_json=json.dumps(item["keywords"], ensure_ascii=False),
            metadata_json=json.dumps(
                {
                    "objective": campaign.objective,
                    "market": campaign.market,
                    "audience": brief.get("audience"),
                    "offer": brief.get("offer"),
                    "instructions": instructions,
                    "angle": item["angle"],
                },
                ensure_ascii=False,
            ),
            status="blocked" if violations else "ready",
            compliance_status=compliance_status,
            violations_json=json.dumps(violations, ensure_ascii=False),
            source=source,
            model_used=model_used,
        )
        db.add(asset)
        assets.append(asset)
    await db.flush()
    for asset in assets:
        await db.refresh(asset)
    return sorted(
        assets,
        key=lambda asset: (
            MARKETING_COPY_PLATFORMS.index(asset.platform),
            asset.variant_key,
        ),
    )
