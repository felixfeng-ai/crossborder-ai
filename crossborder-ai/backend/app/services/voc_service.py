"""VOC 评论解析、AI 聚合与 Listing 上下文。"""

import csv
import io
import json
import re
from collections import Counter
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.voc import VocAnalysis
from app.services import provider_config
from app.core.config import settings
from app.services.ai.deepseek import DeepSeekService


MAX_REVIEWS = 100
MAX_REVIEW_LENGTH = 2000

_STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "was", "are", "but", "not",
    "very", "you", "have", "has", "too", "all", "from", "they", "its", "it's",
    "product", "good", "bad", "okay", "really", "just", "use", "used", "about",
}


def _clean_review(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip().strip('"')
    return value[:MAX_REVIEW_LENGTH]


def parse_review_input(raw: str) -> list[str]:
    """支持纯文本逐行评论和常见 CSV，最多处理 100 条。"""
    text = (raw or "").strip()
    if not text:
        return []
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    parsed_rows = list(csv.reader(io.StringIO(text)))
    multi_column = sum(1 for row in parsed_rows if len(row) > 1)
    if multi_column >= max(1, len(parsed_rows) // 2):
        rows = parsed_rows
        first = [cell.strip().lower() for cell in rows[0]]
        if any(
            marker in " ".join(first)
            for marker in ("review", "comment", "评论", "content", "rating")
        ):
            rows = rows[1:]
        reviews = [
            _clean_review(" ".join(cell for cell in row if cell.strip()))
            for row in rows
        ]
    else:
        reviews = [_clean_review(line) for line in lines]
    return [review for review in reviews if review][:MAX_REVIEWS]


def _fallback_analysis(reviews: list[str]) -> dict[str, Any]:
    words = []
    for review in reviews:
        words.extend(
            word.lower()
            for word in re.findall(r"[A-Za-z\u4e00-\u9fff]{3,}", review)
            if word.lower() not in _STOPWORDS
        )
    keywords = [word for word, _ in Counter(words).most_common(12)]
    negative_markers = ("heavy", "tight", "bad", "poor", "break", "noisy", "重", "差", "紧")
    positive_markers = (
        "great", "love", "clear", "long", "last", "excellent",
        "好", "清晰", "耐用",
    )
    pain_points: list[str] = []
    selling_points: list[str] = []
    for review in reviews:
        # 转折句必须拆开判断，避免“heavy but long battery”同时污染卖点和痛点。
        clauses = [
            clause.strip()
            for clause in re.split(
                r"\b(?:but|however|although|though)\b|但是|不过|但",
                review,
                flags=re.IGNORECASE,
            )
            if clause.strip()
        ]
        for clause in clauses:
            normalized = clause.lower()
            is_negative = any(marker in normalized for marker in negative_markers)
            is_positive = any(marker in normalized for marker in positive_markers)
            if is_negative and clause[:120] not in pain_points:
                pain_points.append(clause[:120])
            elif is_positive and clause[:120] not in selling_points:
                selling_points.append(clause[:120])
    pain_points = pain_points[:5]
    selling_points = selling_points[:5]
    return {
        "summary": f"已分析 {len(reviews)} 条评论；建议结合高频词和正负面反馈继续人工复核。",
        "pain_points": pain_points,
        "selling_points": selling_points,
        "objections": pain_points[:3],
        "keywords": keywords,
        "sentiment": {"positive": 0.0, "neutral": 1.0, "negative": 0.0},
        "recommendations": ["优先把真实痛点转化为 Listing 卖点和图片说明"],
    }


def _normalize_analysis(payload: dict[str, Any], reviews: list[str]) -> dict[str, Any]:
    fallback = _fallback_analysis(reviews)

    def string_list(key: str, limit: int = 20) -> list[str]:
        value = payload.get(key)
        if not isinstance(value, list):
            return fallback[key]
        return [str(item).strip()[:500] for item in value if str(item).strip()][:limit]

    sentiment = payload.get("sentiment")
    if not isinstance(sentiment, dict):
        sentiment = fallback["sentiment"]
    return {
        "summary": str(payload.get("summary") or fallback["summary"])[:2000],
        "pain_points": string_list("pain_points"),
        "selling_points": string_list("selling_points"),
        "objections": string_list("objections"),
        "keywords": string_list("keywords", limit=30),
        "sentiment": sentiment,
        "recommendations": string_list("recommendations"),
    }


async def analyze_reviews(
    reviews: list[str],
    *,
    product_title: str,
    platform: str,
    language: str,
    llm: DeepSeekService | None = None,
) -> tuple[dict[str, Any], str]:
    """调用 AI 聚合评论；模型 JSON 不可用时使用确定性降级结果。"""
    generator = llm or DeepSeekService()
    prompt = (
        f"Product: {product_title}\nPlatform: {platform}\nLanguage: {language}\n"
        f"Reviews:\n{json.dumps(reviews, ensure_ascii=False)}\n\n"
        "Return JSON with summary, pain_points, selling_points, objections, "
        "keywords, sentiment {positive,neutral,negative}, recommendations. "
        "Do not repeat buyer names or personal information."
    )
    try:
        raw = await generator.generate(
            "You are a cross-border ecommerce VOC analyst. Return strict JSON only.",
            prompt,
            max_tokens=1600,
        )
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        payload = json.loads(match.group(0)) if match else {}
    except Exception:
        payload = {}
    model_used = provider_config.get("deepseek", "model", settings.DEEPSEEK_MODEL)
    return _normalize_analysis(payload, reviews), model_used


async def latest_voc_for_product(
    db: AsyncSession,
    user_id,
    product_id,
) -> VocAnalysis | None:
    return (
        await db.execute(
            select(VocAnalysis)
            .where(
                VocAnalysis.user_id == user_id,
                VocAnalysis.product_id == product_id,
            )
            .order_by(desc(VocAnalysis.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()


def voc_listing_context(analysis: VocAnalysis | None) -> str:
    if analysis is None:
        return ""
    pain = json.loads(analysis.pain_points_json or "[]")
    selling = json.loads(analysis.selling_points_json or "[]")
    objections = json.loads(analysis.objections_json or "[]")
    return "\n".join(
        [
            f"VOC summary: {analysis.summary}",
            f"Customer pain points: {', '.join(map(str, pain[:5]))}",
            f"Positive selling points: {', '.join(map(str, selling[:5]))}",
            f"Purchase objections: {', '.join(map(str, objections[:5]))}",
        ]
    ).strip()


def serialize_voc(analysis: VocAnalysis) -> dict:
    return {
        "id": str(analysis.id),
        "product_id": str(analysis.product_id) if analysis.product_id else None,
        "platform": analysis.platform,
        "language": analysis.language,
        "review_count": analysis.review_count,
        "summary": analysis.summary,
        "pain_points": json.loads(analysis.pain_points_json or "[]"),
        "selling_points": json.loads(analysis.selling_points_json or "[]"),
        "objections": json.loads(analysis.objections_json or "[]"),
        "keywords": json.loads(analysis.keywords_json or "[]"),
        "sentiment": json.loads(analysis.sentiment_json or "{}"),
        "recommendations": json.loads(analysis.recommendations_json or "[]"),
        "model_used": analysis.model_used,
        "created_at": str(analysis.created_at),
    }
