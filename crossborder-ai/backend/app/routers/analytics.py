"""VeyaShip - 数据统计与看板路由（F1 Dashboard）

提供卖家真正关心的业务数据，而不是冰冷的数字。
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import RateLimit
from app.dependencies import get_current_user
from app.models.product import Product
from app.models.user import User
from app.services.dashboard_service import build_dashboard_data
from app.services.plan_service import consume_feature_allowance
from app.services.store_check_service import STORE_CHECK_SCOPES, run_store_check as execute_store_check
from app.services import provider_config
from app.services.amazon_market_data import (
    AmazonMarketDataNotConfigured,
    AmazonMarketQueryError,
    build_runtime_amazon_market_service,
)

router = APIRouter(prefix="/analytics", tags=["数据统计"])


@router.get("/dashboard")
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取看板业务数据"""
    return await build_dashboard_data(db, current_user)


@router.get("/category")
async def analyze_category(
    keyword: str = Query(..., description="品类关键词，如：蓝牙耳机"),
    current_user: User = Depends(get_current_user),
    _ratelimit=Depends(RateLimit("ai_generate")),
    db: AsyncSession = Depends(get_db),
):
    """Amazon US 品类分析：只返回 Provider 可追溯数据。"""
    await provider_config.refresh(db)
    try:
        structured = await build_runtime_amazon_market_service().analyze_category(
            keyword
        )
    except AmazonMarketDataNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AmazonMarketQueryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    recommendation = structured.get("recommendation") or {}
    market = structured.get("market") or {}
    quality = structured.get("data_quality") or {}
    provider_name = quality.get("provider") or "unknown"
    source_note = (
        "JustOneAPI Amazon 前台事实，购买量为展示范围"
        if provider_name == "justone_api"
        else "Jungle Scout 第三方估算，不是 Amazon 官方销量"
    )
    report = (
        f"## 「{keyword}」Amazon US 市场分析\n\n"
        f"- 结论：{recommendation.get('verdict', '数据不足')}\n"
        f"- 优先方向：{recommendation.get('top_pick', '待补充')}\n"
        f"- 样本量：{market.get('sample_size', 0)}\n"
        f"- 数据完整度：{market.get('data_completeness_pct', 0)}%\n"
        f"- 数据来源：{source_note}\n"
    )
    usage = await consume_feature_allowance(
        db,
        current_user,
        "category_analysis",
    )
    return {
        "category": keyword,
        "report": report,
        "structured": structured,
        "market": "Amazon US",
        "provider": provider_name,
        "usage": usage,
    }


@router.get("/store-check-history")
async def get_store_check_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取用户的整店巡检历史记录"""
    from app.models.store_check_log import StoreCheckLog
    import json

    result = await db.execute(
        select(StoreCheckLog)
        .where(StoreCheckLog.user_id == current_user.id)
        .order_by(StoreCheckLog.created_at.desc())
        .limit(20)
    )
    logs = result.scalars().all()

    return {
        "items": [
            {
                "id": str(l.id),
                "total": l.total,
                "healthy": l.healthy,
                "issue_count": l.issue_count,
                "issues": json.loads(l.issues_json) if l.issues_json else [],
                "checked_scopes": list(STORE_CHECK_SCOPES),
                "created_at": str(l.created_at),
            }
            for l in logs
        ]
    }


@router.post("/store-check")
async def run_store_check(
    request: Request,
    current_user: User = Depends(get_current_user),
    _ratelimit=Depends(RateLimit("ai_generate")),
    db: AsyncSession = Depends(get_db),
):
    """手动触发整店巡检：检查当前用户所有商品，记录结果"""
    result = await execute_store_check(db, current_user)
    usage = await consume_feature_allowance(
        db,
        current_user,
        "manual_store_check",
    )
    return {**result, "usage": usage}


@router.get("/insights")
async def get_ai_insights(
    current_user: User = Depends(get_current_user),
    _ratelimit=Depends(RateLimit("ai_generate")),
    db: AsyncSession = Depends(get_db),
):
    """AI 分析经营数据，给出经营建议"""
    from app.services.ai.deepseek import DeepSeekService

    total = (await db.execute(select(func.count(Product.id)).where(Product.user_id == current_user.id))).scalar() or 0
    no_title = (await db.execute(select(func.count(Product.id)).where(Product.user_id == current_user.id, Product.title.is_(None)))).scalar() or 0

    data = f"商品总数：{total}个\n待补充信息：{no_title}个\n剩余积分：{current_user.credits}\n套餐：{current_user.plan}"

    try:
        llm = DeepSeekService()
        advice = await llm.generate("你是跨境电商运营顾问。根据数据给出3条简短建议，每条一行用数字开头。", data, max_tokens=500)
        lines = [l.strip() for l in advice.strip().split("\n") if l.strip() and l[0].isdigit()]
    except Exception:
        lines = ["1. 完善商品信息，补充标题和描述", "2. 利用 AI 批量生成 Listing", "3. 定期检查商品销售数据"]

    usage = await consume_feature_allowance(
        db,
        current_user,
        "ai_insights",
    )
    return {
        "stats": {"total": total, "pending": no_title, "credits": current_user.credits},
        "advice": lines[:3],
        "usage": usage,
    }
