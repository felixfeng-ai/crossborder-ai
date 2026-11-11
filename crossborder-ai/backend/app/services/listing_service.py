"""Listing 主链路生成、持久化与校验服务。

统一负责 AI 生成落库、人工编辑版本递增、合规报告绑定和发布前状态读取。
Web、Agent 与批量任务都必须通过这里操作 Listing，避免出现多套状态语义。
"""

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.listing_draft import ListingComplianceReport, ListingDraft
from app.models.product import Product
from app.models.user import User
from app.services import provider_config
from app.services.ai.compliance import check_text, merge_banned_words, suggest_replacements
from app.services.ai.deepseek import DeepSeekService
from app.services.ai.persona_kit import (
    build_persona_kit,
    fetch_persona,
    format_persona_block,
)


@dataclass
class GeneratedListingResult:
    """统一承载网页与 Agent 共用的一次 Listing 生成结果。"""

    draft: ListingDraft
    title: str
    description: str
    bullet_points: list[str]
    seo_title: str
    seo_description: str
    violations: list[str]
    suggestions: list[dict]
    blocked: bool
    model_used: str


def _content_hash(
    title: str,
    description: str,
    bullet_points: Iterable[str],
    seo_title: str,
    seo_description: str,
) -> str:
    """计算正文哈希，用于识别内容是否与当前数据一致。"""
    payload = json.dumps(
        {
            "title": title,
            "description": description,
            "bullet_points": list(bullet_points),
            "seo_title": seo_title,
            "seo_description": seo_description,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def persist_generated_listing(
    db: AsyncSession,
    *,
    user: User,
    product: Product,
    platform: str,
    language: str,
    tone: str,
    title: str,
    description: str,
    bullet_points: list[str],
    seo_title: str,
    seo_description: str,
    violations: list[str],
    blocked: bool,
    ai_model_used: str,
    image_task_id: str = "",
) -> ListingDraft:
    """保存 AI 生成结果，并写入与当前版本绑定的合规报告。"""
    compliance_status = "block" if blocked else "pass"
    status = "blocked" if blocked else "ready"
    draft = ListingDraft(
        user_id=user.id,
        product_id=product.id,
        platform=platform,
        language=language,
        tone=tone,
        status=status,
        title=title,
        description=description,
        bullet_points=json.dumps(bullet_points, ensure_ascii=False),
        seo_title=seo_title,
        seo_description=seo_description,
        version=1,
        content_hash=_content_hash(
            title, description, bullet_points, seo_title, seo_description
        ),
        compliance_status=compliance_status,
        compliance_violations=json.dumps(violations, ensure_ascii=False),
        ai_model_used=ai_model_used,
        image_task_id=image_task_id or None,
    )
    db.add(draft)
    await db.flush()

    # 报告必须绑定刚生成的版本号；后续人工编辑后旧报告自动失效。
    report = ListingComplianceReport(
        listing_id=draft.id,
        listing_version=draft.version,
        status=compliance_status,
        violations=json.dumps(violations, ensure_ascii=False),
        source="generation",
    )
    db.add(report)
    await db.flush()
    return draft


def _parse_string_list(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def build_product_fact_block(product: Product, extra_context: str = "") -> str:
    """构建 Listing Prompt 的完整商品事实块。

    标题只能描述商品名称，不能替代描述、店铺、销量和价格等事实。
    所有 Listing 生成入口必须复用该函数，避免 Agent 与网页生成质量分叉。
    """
    lines: list[str] = []
    if product.description:
        lines.append(f"Description: {product.description[:1500]}")
    if product.price is not None:
        lines.append(f"Supply reference price: {product.price}")
    if product.shop_name:
        lines.append(f"Shop: {product.shop_name}")
    if product.sales_count is not None:
        lines.append(f"Sales: {product.sales_count}")
    if product.main_image_url:
        lines.append("Primary product image: available for downstream asset workflow")
    if extra_context.strip():
        lines.append(f"Verified customer voice:\n{extra_context.strip()}")
    return "\n".join(lines) or "No additional product facts provided."


async def generate_listing_title(
    llm: DeepSeekService,
    product: Product,
    *,
    platform: str,
    language: str,
    tone: str,
    persona_block: str = "",
    voc_context: str = "",
) -> str:
    """生成平台标题，DeepSeek 限流时最多重试三次。"""
    language_instruction = (
        "用中文写标题。"
        if language == "zh"
        else f"Write the title in {language.upper()}."
    )
    prompt = (
        f"Generate an optimized {platform} product title "
        f"(max 200 chars, {tone} tone). {language_instruction}\n"
        f"Product: {product.title}\n"
        f"{build_product_fact_block(product, voc_context)}"
    )
    for _ in range(3):
        result = await llm.generate(
            system_prompt=f"You are a professional {platform} listing copywriter.",
            user_prompt=prompt,
            max_tokens=300,
            persona_block=persona_block,
        )
        if result and result.strip():
            return result.strip()
        await asyncio.sleep(1)
    return ""


async def generate_listing_description(
    llm: DeepSeekService,
    product: Product,
    *,
    platform: str,
    language: str,
    tone: str,
    persona_block: str = "",
    voc_context: str = "",
) -> str:
    """生成包含完整商品事实的描述。"""
    return await llm.generate_product_description(
        product_title=product.title or "",
        product_features=build_product_fact_block(product, voc_context),
        platform=platform,
        tone=tone,
        target_language=language if language != "en" else None,
        persona_block=persona_block,
    )


async def generate_listing_bullets(
    llm: DeepSeekService,
    product: Product,
    *,
    platform: str,
    persona_block: str = "",
    voc_context: str = "",
) -> list[str]:
    """生成包含描述、店铺、销量与价格事实的五点卖点。"""
    return await llm.generate_bullet_points(
        product_title=product.title or "",
        features=build_product_fact_block(product, voc_context),
        platform=platform,
        persona_block=persona_block,
    )


async def generate_and_persist_listing(
    db: AsyncSession,
    *,
    user: User,
    product: Product,
    platform: str,
    language: str,
    tone: str = "professional",
    llm: Optional[DeepSeekService] = None,
) -> GeneratedListingResult:
    """生成完整 Listing、执行合规检查并落库。

    这是网页、Agent 与后续批量任务共用的唯一生成入口。调用方只负责权限、
    商品归属和积分扣减，内容事实、品牌注入、SEO 与版本化合规全部在此完成。
    """
    if not product.title:
        raise ValueError("商品缺少标题，请先补充商品信息")

    text_generator = llm or DeepSeekService()
    persona = await fetch_persona(db, user.id)
    persona_kit = build_persona_kit(persona) if persona else None
    persona_block = format_persona_block(persona_kit) if persona_kit else ""
    brand_banned_words = (persona_kit or {}).get("banned_words") or []
    from app.services.voc_service import latest_voc_for_product, voc_listing_context

    latest_voc = await latest_voc_for_product(db, user.id, product.id)
    voc_context = voc_listing_context(latest_voc)

    title_task = generate_listing_title(
        text_generator,
        product,
        platform=platform,
        language=language,
        tone=tone,
        persona_block=persona_block,
        voc_context=voc_context,
    )
    description_task = generate_listing_description(
        text_generator,
        product,
        platform=platform,
        language=language,
        tone=tone,
        persona_block=persona_block,
        voc_context=voc_context,
    )
    bullets_task = generate_listing_bullets(
        text_generator,
        product,
        platform=platform,
        persona_block=persona_block,
        voc_context=voc_context,
    )
    title, description, bullet_points = await asyncio.gather(
        title_task,
        description_task,
        bullets_task,
    )
    seo = await text_generator.optimize_seo(
        title=title,
        description=description,
        platform=platform,
        persona_block=persona_block,
    )
    seo_title = str(seo.get("seo_title") or "")
    seo_description = str(seo.get("seo_description") or "")

    violations: list[str] = []
    word_list = merge_banned_words(brand_banned_words)
    for text in (title, description, *bullet_points, seo_title, seo_description):
        for word in check_text(text or "", word_list):
            if word not in violations:
                violations.append(word)
    blocked = bool(violations)
    suggestions = suggest_replacements(violations) if blocked else []
    model_used = provider_config.get(
        "deepseek",
        "model",
        settings.DEEPSEEK_MODEL,
    )
    draft = await persist_generated_listing(
        db,
        user=user,
        product=product,
        platform=platform,
        language=language,
        tone=tone,
        title=title,
        description=description,
        bullet_points=bullet_points,
        seo_title=seo_title,
        seo_description=seo_description,
        violations=violations,
        blocked=blocked,
        ai_model_used=model_used,
    )
    return GeneratedListingResult(
        draft=draft,
        title=title,
        description=description,
        bullet_points=bullet_points,
        seo_title=seo_title,
        seo_description=seo_description,
        violations=violations,
        suggestions=suggestions,
        blocked=blocked,
        model_used=model_used,
    )


def serialize_listing(draft: ListingDraft) -> dict:
    """把数据库模型转换成稳定的 API 响应结构。"""
    return {
        "id": str(draft.id),
        "product_id": str(draft.product_id),
        "platform": draft.platform,
        "language": draft.language,
        "tone": draft.tone,
        "status": draft.status,
        "title": draft.title,
        "description": draft.description or "",
        "bullet_points": _parse_string_list(draft.bullet_points),
        "seo_title": draft.seo_title or "",
        "seo_description": draft.seo_description or "",
        "version": draft.version,
        "compliance_status": draft.compliance_status,
        "violations": _parse_string_list(draft.compliance_violations),
        "ai_model_used": draft.ai_model_used or "",
        "created_at": str(draft.created_at),
        "updated_at": str(draft.updated_at),
    }


def update_listing_content(
    listing: ListingDraft,
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    bullet_points: Optional[list[str]] = None,
    seo_title: Optional[str] = None,
    seo_description: Optional[str] = None,
) -> ListingDraft:
    """应用人工编辑，并使旧版本合规结果失效。"""
    if title is not None:
        listing.title = title.strip()
    if description is not None:
        listing.description = description
    if bullet_points is not None:
        listing.bullet_points = json.dumps(bullet_points, ensure_ascii=False)
    if seo_title is not None:
        listing.seo_title = seo_title
    if seo_description is not None:
        listing.seo_description = seo_description

    # 任何正文变化都必须递增版本，状态回到 draft，等待重新合规。
    bullets = _parse_string_list(listing.bullet_points)
    listing.version += 1
    listing.status = "draft"
    listing.compliance_status = "unknown"
    listing.compliance_violations = "[]"
    listing.content_hash = _content_hash(
        listing.title,
        listing.description or "",
        bullets,
        listing.seo_title or "",
        listing.seo_description or "",
    )
    return listing


async def run_listing_compliance(
    db: AsyncSession,
    listing: ListingDraft,
    user_banned_words: Optional[list[str]] = None,
) -> ListingDraft:
    """对当前 Listing 版本执行确定性合规检查并生成报告。"""
    from app.services.ai.compliance import check_text, merge_banned_words

    violations: list[str] = []
    word_list = merge_banned_words(user_banned_words or [])
    texts = [
        listing.title,
        listing.description or "",
        *(_parse_string_list(listing.bullet_points)),
        listing.seo_title or "",
        listing.seo_description or "",
    ]
    for text in texts:
        for word in check_text(text, word_list):
            if word not in violations:
                violations.append(word)

    # 只保存为 pass/block 两态；发布接口要求最新版本报告必须为 pass。
    passed = not violations
    listing.status = "ready" if passed else "blocked"
    listing.compliance_status = "pass" if passed else "block"
    listing.compliance_violations = json.dumps(violations, ensure_ascii=False)
    db.add(
        ListingComplianceReport(
            listing_id=listing.id,
            listing_version=listing.version,
            status=listing.compliance_status,
            violations=listing.compliance_violations,
            source="manual_recheck",
        )
    )
    await db.flush()
    return listing


async def get_owned_listing(
    db: AsyncSession, listing_id: str | UUID, user_id: UUID
) -> Optional[ListingDraft]:
    try:
        lid = listing_id if isinstance(listing_id, UUID) else UUID(str(listing_id))
    except (ValueError, TypeError):
        return None
    result = await db.execute(
        select(ListingDraft).where(
            ListingDraft.id == lid,
            ListingDraft.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_current_compliance_report(
    db: AsyncSession, listing: ListingDraft
) -> Optional[ListingComplianceReport]:
    result = await db.execute(
        select(ListingComplianceReport)
        .where(
            ListingComplianceReport.listing_id == listing.id,
            ListingComplianceReport.listing_version == listing.version,
        )
        .order_by(desc(ListingComplianceReport.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()
