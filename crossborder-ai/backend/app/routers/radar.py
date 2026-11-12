"""VeyaShip - 竞品分析路由（F6 Radar）

功能：
1. 输入竞品链接/关键词 → 抓取竞品数据
2. 展示价格、销量对比
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import RateLimit
from app.dependencies import get_current_user
from app.models.user import User
from app.services.scraper import scrape_1688
from app.services.plan_service import (
    consume_feature_allowance,
    feature_allowance_snapshot,
)
from app.services import provider_config
from pydantic import BaseModel, Field

router = APIRouter(prefix="/radar", tags=["竞品分析"])


@router.get("/scrape")
async def scrape_competitor(
    url: str = Query(..., description="竞品 1688 链接"),
    current_user: User = Depends(get_current_user),
    _ratelimit=Depends(RateLimit("ai_generate")),
    db: AsyncSession = Depends(get_db),
):
    """抓取竞品商品信息

    提取竞品的标题、价格、销量、店铺名，
    供卖家做竞品对比分析。
    """
    scrape_usage = await feature_allowance_snapshot(
        db,
        current_user,
        "radar_scrape",
    )
    if not scrape_usage["included"] and current_user.credits < 2:
        raise HTTPException(status_code=402, detail="积分不足，超额竞品抓取需要 2 积分")
    try:
        await provider_config.refresh(db)
        data = await scrape_1688(
            url,
            justone_token=provider_config.get("justone", "token"),
            api_key=provider_config.get("onebound", "api_key"),
            api_secret=provider_config.get("onebound", "api_secret"),
        )
        await consume_feature_allowance(
            db,
            current_user,
            "radar_scrape",
            overage_credits=2,
        )
        return {"competitor": data}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"竞品抓取失败：{str(e)}")
