"""可解释、可复现的 IP 风险文本初筛。"""

import hashlib
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ip_risk import IpDeclaration, IpRiskItem, IpRiskReport
from app.models.image_asset import ImageAsset
from app.models.listing_draft import ListingDraft
from app.models.product import Product
from app.models.user import User
from app.services.ai.compliance import PLATFORM_EXTREME_WORDS, check_text


CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "ip"
SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3}
VALID_EVIDENCE_STATUSES = {"provided", "manually_verified"}
FIELD_ORDER = {
    "title": 0,
    "description": 1,
    "bullet_points": 2,
    "seo_title": 3,
    "seo_description": 4,
    "category_code": 5,
}
DEFAULT_AUTHORIZATION_CLAIMS = [
    "official partner",
    "authorized dealer",
    "official reseller",
    "official store",
    "品牌授权店",
    "官方授权",
    "官方合作",
    "独家代理",
]
CATEGORY_ALIASES = {
    "玩具": "toys",
    "电子": "electronics",
    "数码": "electronics",
    "美妆": "cosmetics",
    "个护": "cosmetics",
    "汽车配件": "automotive",
}


@lru_cache(maxsize=4)
def _load_config(filename: str) -> dict[str, Any]:
    with (CONFIG_DIR / filename).open(encoding="utf-8") as handle:
        return json.load(handle)


def load_ip_configs() -> tuple[dict, dict, dict, str]:
    """加载品牌、认证、类目配置和联合规则版本。"""
    brands = _load_config("brand_terms.json")
    certs = _load_config("certification_terms.json")
    categories = _load_config("category_authorization.json")
    rule = _load_config("rule_version.json")
    version = "|".join(
        [
            str(rule.get("version") or ""),
            str(brands.get("version") or ""),
            str(certs.get("version") or ""),
            str(categories.get("version") or ""),
        ]
    )
    return brands, certs, categories, version


def normalize_category_code(value: str | None) -> str | None:
    normalized = (value or "").strip().lower()
    if not normalized:
        return None
    return CATEGORY_ALIASES.get(normalized, normalized)


def _parse_expiry(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _declaration_is_valid(declaration: dict, claim_type: str, value: str) -> bool:
    if declaration.get("claim_type") != claim_type:
        return False
    if str(declaration.get("claim_value") or "").strip().lower() != value.lower():
        return False
    if declaration.get("evidence_status") not in VALID_EVIDENCE_STATUSES:
        return False
    expires_at = _parse_expiry(declaration.get("expires_at"))
    return expires_at is None or expires_at >= datetime.now(timezone.utc)


def _iter_term_matches(
    text: str,
    term: str,
) -> list[re.Match]:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]*", term):
        pattern = rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])"
    else:
        pattern = re.escape(term)
    return list(re.finditer(pattern, text, re.IGNORECASE))


def _authorization_claim_regex(phrase: str) -> re.Pattern:
    if re.search(r"[\u4e00-\u9fff]", phrase):
        return re.compile(re.escape(phrase), re.IGNORECASE)
    words = phrase.split()
    if len(words) == 2:
        return re.compile(
            rf"{re.escape(words[0])}\s+(?:[A-Za-z0-9-]+\s+){{0,2}}{re.escape(words[1])}",
            re.IGNORECASE,
        )
    return re.compile(re.escape(phrase), re.IGNORECASE)


def _risk(
    *,
    code: str,
    category: str,
    severity: str,
    field: str,
    text: str,
    start: int,
    end: int,
    suggestion: str,
    source: str,
) -> dict:
    return {
        "code": code,
        "category": category,
        "severity": severity,
        "evidence": {
            "type": "text",
            "field": field,
            "text": text[start:end],
            "start": start,
            "end": end,
        },
        "suggestion": suggestion,
        "source": source,
    }


def _dedupe_and_sort(risks: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for item in risks:
        evidence = item["evidence"]
        key = (
            item["code"],
            evidence.get("field"),
            evidence.get("start"),
            evidence.get("end"),
            evidence.get("asset_id"),
            tuple(evidence.get("bbox") or []),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return sorted(
        unique,
        key=lambda item: (
            -SEVERITY_RANK.get(item["severity"], 0),
            item["code"],
            FIELD_ORDER.get(
                str(item["evidence"].get("field") or ""),
                99,
            ),
            int(item["evidence"].get("start") or 0),
        ),
    )


def _finalize_result(
    risks: list[dict],
    *,
    text_coverage: str,
    image_coverage: str,
    image_required: bool = False,
) -> dict:
    risks = _dedupe_and_sort(risks)
    if any(item["severity"] == "high" for item in risks):
        overall_risk = "high"
    elif any(item["severity"] == "medium" for item in risks):
        overall_risk = "medium"
    else:
        overall_risk = "low"
    if (
        image_required
        and image_coverage in {"not_checked", "failed"}
        and overall_risk != "high"
    ):
        overall_risk = "unknown"
    return {
        "status": (
            "completed"
            if image_coverage == "checked"
            else "partial"
            if image_required and image_coverage in {"not_checked", "failed"}
            else "completed"
        ),
        "overall_risk": overall_risk,
        "coverage": {"text": text_coverage, "image": image_coverage},
        "summary": {
            "high": sum(item["severity"] == "high" for item in risks),
            "medium": sum(item["severity"] == "medium" for item in risks),
            "low": sum(item["severity"] == "low" for item in risks),
            "info": sum(item["severity"] == "info" for item in risks),
        },
        "risks": risks,
    }


def screen_ip_text(
    text_fields: dict[str, str],
    *,
    declarations: list[dict],
    platform: str,
    category_code: str | None,
    brand_config: dict,
    certification_config: dict,
    category_config: dict,
) -> dict:
    """执行确定性 IP 文本检测；同一输入返回完全相同的风险顺序。"""
    risks: list[dict] = []
    matched_brands: list[str] = []
    authorized_brands: set[str] = set()
    normalized_platform = (platform or "").strip().lower()

    for brand in brand_config.get("brands") or []:
        platforms = {
            str(item).strip().lower()
            for item in brand.get("platforms") or []
        }
        if platforms and normalized_platform not in platforms:
            continue
        aliases = [
            str(item).strip()
            for item in brand.get("aliases") or []
            if str(item).strip()
        ]
        authorized = any(
            _declaration_is_valid(
                declaration,
                "brand_authorization",
                str(brand.get("display_name") or ""),
            )
            or any(
                _declaration_is_valid(
                    declaration,
                    "brand_authorization",
                    alias,
                )
                for alias in aliases
            )
            for declaration in declarations
        )
        for field, content in text_fields.items():
            for alias in aliases:
                for match in _iter_term_matches(content or "", alias):
                    matched_brands.append(alias)
                    if authorized:
                        authorized_brands.add(str(brand.get("brand_key") or alias))
                    risks.append(
                        _risk(
                            code="TRADEMARK_TERM",
                            category="trademark",
                            severity="info" if authorized else str(
                                brand.get("severity") or "high"
                            ),
                            field=field,
                            text=content,
                            start=match.start(),
                            end=match.end(),
                            suggestion=(
                                "已提供品牌授权依据，请人工核验授权范围与有效期"
                                if authorized
                                else "请提供目标市场有效品牌授权，或删除相关品牌声明"
                            ),
                            source="brand_rule",
                        )
                    )

    any_brand_authorized = bool(authorized_brands)
    for phrase in (
        brand_config.get("authorization_claim_patterns")
        or DEFAULT_AUTHORIZATION_CLAIMS
    ):
        regex = _authorization_claim_regex(str(phrase))
        for field, content in text_fields.items():
            for match in regex.finditer(content or ""):
                risks.append(
                    _risk(
                        code="AUTHORIZATION_CLAIM_UNVERIFIED",
                        category="authorization",
                        severity="info" if any_brand_authorized else "high",
                        field=field,
                        text=content,
                        start=match.start(),
                        end=match.end(),
                        suggestion=(
                            "已提供品牌授权依据，请人工核验该授权声明是否覆盖当前商品"
                            if any_brand_authorized
                            else "请提供官方合作或授权证明，否则删除该授权声明"
                        ),
                        source="brand_rule",
                    )
                )

    for claim in certification_config.get("claims") or []:
        code = str(claim.get("code") or "")
        has_evidence = any(
            _declaration_is_valid(
                declaration,
                "certification",
                code,
            )
            for declaration in declarations
        )
        for pattern in claim.get("patterns") or []:
            for field, content in text_fields.items():
                for match in re.finditer(
                    re.escape(str(pattern)),
                    content or "",
                    re.IGNORECASE,
                ):
                    risks.append(
                        _risk(
                            code=(
                                "CERTIFICATION_EVIDENCE_PROVIDED"
                                if has_evidence
                                else "CERTIFICATION_CLAIM_WITHOUT_EVIDENCE"
                            ),
                            category="certification",
                            severity=(
                                "info"
                                if has_evidence
                                else str(
                                    claim.get("severity_without_evidence")
                                    or "medium"
                                )
                            ),
                            field=field,
                            text=content,
                            start=match.start(),
                            end=match.end(),
                            suggestion=(
                                f"已提供 {code} 证据，请人工核验证书主体和有效期"
                                if has_evidence
                                else f"请提供 {code} 证书或授权依据，否则删除相关认证声称"
                            ),
                            source="certification_rule",
                        )
                    )

    category_rule = (
        (category_config.get("categories") or {}).get(category_code)
        if category_code
        else None
    )
    if category_rule:
        risks.append(
            {
                "code": "CATEGORY_AUTHORIZATION_REVIEW",
                "category": "category",
                "severity": str(category_rule.get("severity") or "medium"),
                "evidence": {
                    "type": "category",
                    "field": "category_code",
                    "text": category_code,
                    "start": 0,
                    "end": len(category_code or ""),
                },
                "suggestion": str(
                    category_rule.get("authorization_hint")
                    or "请人工核对目标市场类目授权链"
                ),
                "source": "category_rule",
            }
        )

    for field, text in text_fields.items():
        for word in check_text(text or "", PLATFORM_EXTREME_WORDS):
            for match in _iter_term_matches(text or "", word):
                risks.append(
                    _risk(
                        code="ABSOLUTE_OR_FALSE_CLAIM",
                        category="claim",
                        severity="medium",
                        field=field,
                        text=text,
                        start=match.start(),
                        end=match.end(),
                        suggestion="删除绝对化或无法证明的宣传表述",
                        source="shared_compliance",
                    )
                )

    result = _finalize_result(
        risks,
        text_coverage="checked",
        image_coverage="not_checked",
        image_required=False,
    )
    result["matched_brands"] = sorted(set(matched_brands))
    return result


async def _declarations_for_product(
    db: AsyncSession,
    user_id,
    product_id,
) -> list[dict]:
    rows = (
        await db.execute(
            select(IpDeclaration).where(
                IpDeclaration.user_id == user_id,
                IpDeclaration.product_id == product_id,
            )
        )
    ).scalars().all()
    return [
        {
            "claim_type": row.claim_type,
            "claim_value": row.claim_value,
            "evidence_url": row.evidence_url,
            "evidence_status": row.evidence_status,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        }
        for row in rows
    ]


def serialize_ip_report(
    report: IpRiskReport,
    items: list[IpRiskItem],
) -> dict:
    coverage = json.loads(report.coverage_json or "{}")
    summary = json.loads(report.summary_json or "{}")
    risks = []
    for item in items:
        evidence = json.loads(item.evidence_json or "{}")
        risks.append(
            {
                "id": str(item.id),
                "code": item.code,
                "category": item.category,
                "severity": item.severity,
                "evidence": evidence,
                "suggestion": item.suggestion,
                "source": item.source,
            }
        )
    return {
        "report_id": str(report.id),
        "status": report.status,
        "overall_risk": report.overall_risk,
        "coverage": coverage,
        "summary": summary,
        "risks": risks,
        "ruleset_version": report.ruleset_version,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


async def persist_ip_report(
    db: AsyncSession,
    *,
    user: User,
    product: Product,
    listing: ListingDraft | None,
    scope: str,
    text_fields: dict[str, str],
    declarations: list[dict],
    platform: str,
    category_code: str | None,
    trigger: str,
    extra_risks: list[dict] | None = None,
    text_coverage: str = "checked",
    image_coverage: str = "not_checked",
    image_asset_ids: list[str] | None = None,
    model_provider: str | None = None,
    model_name: str | None = None,
) -> dict:
    brands, certs, categories, version = load_ip_configs()
    result = screen_ip_text(
        text_fields,
        declarations=declarations,
        platform=platform,
        category_code=category_code,
        brand_config=brands,
        certification_config=certs,
        category_config=categories,
    )
    result = _finalize_result(
        [*result["risks"], *(extra_risks or [])],
        text_coverage=text_coverage,
        image_coverage=image_coverage,
        image_required=scope in {"image", "both"},
    )

    input_payload = {
        "text": text_fields,
        "scope": scope,
        "platform": platform,
        "category": category_code,
        "ruleset": version,
        "listing_version": listing.version if listing else None,
        "images": sorted(image_asset_ids or []),
        "declarations": sorted(
            [
                {
                    "type": str(item.get("claim_type") or ""),
                    "value": str(item.get("claim_value") or "").lower(),
                    "status": str(item.get("evidence_status") or ""),
                    "expires": str(item.get("expires_at") or ""),
                }
                for item in declarations
            ],
            key=lambda item: (
                item["type"],
                item["value"],
                item["status"],
                item["expires"],
            ),
        ),
    }
    input_hash = hashlib.sha256(
        json.dumps(input_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    existing = (
        await db.execute(
            select(IpRiskReport).where(
                IpRiskReport.user_id == user.id,
                IpRiskReport.product_id == product.id,
                IpRiskReport.listing_id == (listing.id if listing else None),
                IpRiskReport.listing_version == (listing.version if listing else None),
                IpRiskReport.scope == scope,
                IpRiskReport.input_hash == input_hash,
                IpRiskReport.ruleset_version == version,
            ).order_by(desc(IpRiskReport.created_at)).limit(1)
        )
    ).scalar_one_or_none()
    if existing:
        items = (
            await db.execute(
                select(IpRiskItem).where(IpRiskItem.report_id == existing.id)
            )
        ).scalars().all()
        return serialize_ip_report(existing, list(items))

    report = IpRiskReport(
        user_id=user.id,
        product_id=product.id,
        listing_id=listing.id if listing else None,
        listing_version=listing.version if listing else None,
        scope=scope,
        status=result["status"],
        overall_risk=result["overall_risk"],
        coverage_json=json.dumps(result["coverage"], ensure_ascii=False),
        summary_json=json.dumps(result["summary"], ensure_ascii=False),
        input_hash=input_hash,
        ruleset_version=version,
        model_provider=model_provider,
        model_name=model_name,
    )
    db.add(report)
    await db.flush()
    items = []
    for risk_value in result["risks"]:
        item = IpRiskItem(
            report_id=report.id,
            code=risk_value["code"],
            category=risk_value["category"],
            severity=risk_value["severity"],
            evidence_json=json.dumps(risk_value["evidence"], ensure_ascii=False),
            suggestion=risk_value["suggestion"],
            source=risk_value["source"],
        )
        db.add(item)
        items.append(item)
    await db.flush()
    for item in items:
        await db.refresh(item)
    await db.refresh(report)
    return serialize_ip_report(report, items)


async def screen_product_text(
    db: AsyncSession,
    *,
    user: User,
    product: Product,
    listing: ListingDraft | None,
    platform: str,
    category_code: str | None = None,
    trigger: str = "manual",
    scope: str = "text",
    text_fields: dict[str, str] | None = None,
    image_assets: list[ImageAsset] | None = None,
) -> dict:
    category_code = normalize_category_code(category_code)
    if text_fields is None:
        if listing is not None:
            try:
                bullets = json.loads(listing.bullet_points or "[]")
            except (json.JSONDecodeError, TypeError):
                bullets = []
            text_fields = {
                "title": listing.title or "",
                "description": listing.description or "",
                "bullet_points": "\n".join(str(item) for item in bullets),
                "seo_title": listing.seo_title or "",
                "seo_description": listing.seo_description or "",
            }
        else:
            text_fields = {
                "title": product.title or "",
                "description": product.description or "",
            }
    declarations = await _declarations_for_product(db, user.id, product.id)
    if scope == "image":
        text_fields = {}
    text_coverage = "not_checked" if scope == "image" else "checked"
    visual_risks: list[dict] = []
    image_coverage = "not_checked"
    model_provider = None
    model_name = None
    selected_assets = list(image_assets or [])[:6]
    if scope in {"image", "both"} and selected_assets:
        from app.services.ip_vision import (
            analyze_image_asset,
            get_vision_config,
            visual_items_to_risks,
        )

        config = get_vision_config()
        if config is None:
            visual_risks.append(
                {
                    "code": "VISUAL_CHECK_NOT_CONFIGURED",
                    "category": "coverage",
                    "severity": "info",
                    "evidence": {"type": "system"},
                    "suggestion": "当前未配置视觉模型，图片 IP 风险未检查",
                    "source": "system_rule",
                }
            )
        else:
            _api_key, model_name, _base_url = config
            model_provider = "aliyun_dashscope"
            authorized_brands = {
                str(item.get("claim_value") or "")
                for item in declarations
                if item.get("claim_type") == "brand_authorization"
                and _declaration_is_valid(
                    item,
                    "brand_authorization",
                    str(item.get("claim_value") or ""),
                )
            }
            failures = 0
            for asset in selected_assets:
                try:
                    items = await analyze_image_asset(asset)
                    visual_risks.extend(
                        visual_items_to_risks(
                            items,
                            asset_id=str(asset.id),
                            authorized_brands=authorized_brands,
                        )
                    )
                except Exception:
                    failures += 1
            image_coverage = "failed" if failures else "checked"
            if failures:
                visual_risks.append(
                    {
                        "code": "VISUAL_CHECK_FAILED",
                        "category": "coverage",
                        "severity": "info",
                        "evidence": {
                            "type": "system",
                            "failed_images": failures,
                        },
                        "suggestion": "部分图片视觉检查失败，请重试或人工复核",
                        "source": "system_rule",
                    }
                )
    return await persist_ip_report(
        db,
        user=user,
        product=product,
        listing=listing,
        scope=scope,
        text_fields=text_fields,
        declarations=declarations,
        platform=platform,
        category_code=category_code,
        trigger=trigger,
        extra_risks=visual_risks,
        text_coverage=text_coverage,
        image_coverage=image_coverage,
        image_asset_ids=[str(asset.id) for asset in selected_assets],
        model_provider=model_provider,
        model_name=model_name,
    )


async def get_owned_ip_report(
    db: AsyncSession,
    *,
    user_id,
    report_id,
) -> dict | None:
    report = await db.get(IpRiskReport, report_id)
    if report is None or report.user_id != user_id:
        return None
    items = (
        await db.execute(
            select(IpRiskItem)
            .where(IpRiskItem.report_id == report.id)
            .order_by(
                desc(IpRiskItem.severity),
                IpRiskItem.code,
            )
        )
    ).scalars().all()
    return serialize_ip_report(report, list(items))


async def latest_ip_report_for_listing(
    db: AsyncSession,
    *,
    user_id,
    listing: ListingDraft,
) -> dict | None:
    report = (
        await db.execute(
            select(IpRiskReport)
            .where(
                IpRiskReport.user_id == user_id,
                IpRiskReport.listing_id == listing.id,
                IpRiskReport.listing_version == listing.version,
            )
            .order_by(desc(IpRiskReport.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if report is None:
        return None
    items = (
        await db.execute(
            select(IpRiskItem).where(IpRiskItem.report_id == report.id)
        )
    ).scalars().all()
    return serialize_ip_report(report, list(items))


async def ensure_ip_report_for_publish(
    db: AsyncSession,
    *,
    user: User,
    product: Product,
    listing: ListingDraft | None,
    platform: str,
) -> dict:
    """发布前复用当前版本报告；缺失时补跑一次文本初筛。"""
    report = (
        await latest_ip_report_for_listing(
            db,
            user_id=user.id,
            listing=listing,
        )
        if listing is not None
        else None
    )
    if report is not None:
        return report
    return await screen_product_text(
        db,
        user=user,
        product=product,
        listing=listing,
        platform=platform,
        trigger="publish",
        scope="text",
    )


def ip_publish_block_reason(report: dict) -> str | None:
    """返回发布拦截原因；纯文本报告不会被可选的图片检查误伤。"""
    if report.get("overall_risk") == "high":
        return "high_risk"

    coverage = report.get("coverage") or {}
    if report.get("overall_risk") == "unknown":
        return "check_incomplete"
    if coverage.get("text") != "checked":
        return "check_incomplete"
    if report.get("status") in {"partial", "failed"}:
        return "check_incomplete"
    if coverage.get("image") == "failed":
        return "check_incomplete"
    return None
