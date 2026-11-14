"""读取已发布套餐版本并提供公开响应结构。"""

import json

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan_version import CreditPackVersion, PlanVersion
from app.services.plan_defaults import CREDIT_PACKS, PLAN_CATALOG


def _yuan(cents: int) -> int | float:
    """把整数分格式化为前端使用的元。"""
    value = int(cents or 0) / 100
    return int(value) if value.is_integer() else round(value, 2)


def _features_for_plan(plan_key: str, config: dict, stored: list[str] | None) -> list[str]:
    """数据库版本优先使用管理员发布的完整功能清单。"""
    if stored:
        return stored
    monthly = int(config.get("monthly_credits", 0))
    if plan_key == "free":
        return [
            f"每月 {monthly:,} AI 积分",
            "1688 商品抓取与利润测算",
            "Listing、合规与 VOC 评论洞察",
            "品类分析与 AI Insights 各 10 次/月",
        ]
    if plan_key == "standard":
        return [
            f"每月 {monthly:,} AI 积分",
            "AI Agent、批量处理与自动巡检",
            "Shopify 草稿发布与运营同步",
            "11 个平台 Listing 文案生成",
            "每月 10 次手动整店巡检",
            "商品抓取每月 100 次",
        ]
    return [
        f"每月 {monthly:,} AI 积分",
        "所有 Standard 功能",
        "AI 图片、商品视频与营销成片",
        "字幕、AI 配音与素材中心",
        "每月 20 次手动整店巡检",
        "优先技术支持",
    ]


async def get_effective_plan_config(
    db: AsyncSession,
    plan_key: str,
) -> dict | None:
    """读取指定套餐最新已发布版本，缺失时回退代码默认值。"""
    row = (
        await db.execute(
            select(PlanVersion)
            .where(
                PlanVersion.plan_key == plan_key,
                PlanVersion.status == "published",
            )
            .order_by(desc(PlanVersion.version))
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        fallback = PLAN_CATALOG.get(plan_key)
        if fallback is None:
            return None
        return {
            **fallback,
            "features": _features_for_plan(plan_key, fallback, None),
        }
    try:
        features = json.loads(row.features_json or "[]")
    except json.JSONDecodeError:
        features = []
    config = {
        "name": row.name,
        "description": row.description,
        "rank": row.rank,
        "price": _yuan(row.price_cents),
        "first_month_price": _yuan(row.first_month_price_cents or row.price_cents),
        "annual_price": _yuan(row.annual_price_cents or row.price_cents * 12),
        "annual_full_price": _yuan(
            row.annual_full_price_cents or row.price_cents * 12
        ),
        "monthly_credits": row.monthly_credits,
        "first_month_bonus_credits": row.first_month_bonus_credits,
        "valid_days": row.valid_days,
        "features": _features_for_plan(plan_key, {"monthly_credits": row.monthly_credits}, features),
    }
    return config


async def list_public_plans(db: AsyncSession) -> list[dict]:
    """生成公开套餐列表，保持旧接口字段兼容。"""
    plans: list[dict] = []
    for plan_key in ("free", "standard", "professional"):
        config = await get_effective_plan_config(db, plan_key)
        if config is None:
            continue
        plans.append(
            {
                "id": plan_key,
                "name": config["name"],
                "price": config["price"],
                "price_label": (
                    "免费"
                    if config["price"] == 0
                    else f"¥{config['price']}/月"
                ),
                "first_month_price": config.get(
                    "first_month_price", config["price"]
                ),
                "first_month_bonus_credits": config.get(
                    "first_month_bonus_credits", 0
                ),
                "annual_price": config.get("annual_price", config["price"] * 12),
                "annual_full_price": config.get(
                    "annual_full_price", config["price"] * 12
                ),
                "monthly_credits": config["monthly_credits"],
                "description": config.get("description") or (
                    "试试基本功能"
                    if plan_key == "free"
                    else "适合个人卖家"
                    if plan_key == "standard"
                    else "适合工作室与专业卖家"
                ),
                "features": config["features"],
                "validity_days": config["valid_days"],
                "recommended": plan_key == "professional",
                "rank": config.get("rank", 0),
            }
        )
    return plans


async def get_plan_rank(db: AsyncSession, plan_key: str) -> int:
    """读取套餐等级，用于禁止降级申请。"""
    config = await get_effective_plan_config(db, plan_key)
    return int(config.get("rank", 0)) if config else 0


async def list_public_credit_packs(db: AsyncSession) -> list[dict]:
    """读取已发布积分包，缺失时回退当前默认价格。"""
    rows = (
        await db.execute(
            select(CreditPackVersion)
            .where(CreditPackVersion.status == "published")
            .order_by(CreditPackVersion.pack_key, desc(CreditPackVersion.version))
        )
    ).scalars().all()
    published = {}
    for row in rows:
        published.setdefault(row.pack_key, row)
    if not published:
        return [dict(item) for item in CREDIT_PACKS]
    return [
        {
            "id": row.pack_key,
            "name": row.name,
            "credits": row.credits,
            "price": _yuan(row.price_cents),
            "trial_once": row.trial_once,
        }
        for row in sorted(published.values(), key=lambda item: item.credits)
    ]
