"""营销活动 A/B 版本效果计算与自动暂停策略。"""

import json
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marketing_copy import MarketingCopyAsset
from app.models.marketing_distribution import MarketingPerformanceSnapshot


# 保守阈值：样本不足时只标记待观察，绝不自动暂停。
MIN_IMPRESSIONS = 500
MIN_CLICKS = 20
LOSER_SCORE_RATIO = 0.75


def aggregate_snapshot_metrics(
    snapshots: Iterable[MarketingPerformanceSnapshot],
) -> dict:
    """汇总单个 A/B 版本的曝光、点击、转化和收入。"""
    items = list(snapshots)
    impressions = sum(item.impressions for item in items)
    clicks = sum(item.clicks for item in items)
    orders = sum(item.orders for item in items)
    conversions = sum(item.conversions for item in items)
    spend = round(sum(item.spend for item in items), 2)
    revenue = round(sum(item.revenue for item in items), 2)
    return {
        "impressions": impressions,
        "clicks": clicks,
        "orders": orders,
        "conversions": conversions,
        "spend": spend,
        "revenue": revenue,
        "ctr": round(clicks / impressions * 100, 2) if impressions else 0,
        "cvr": round(orders / clicks * 100, 2) if clicks else 0,
        "roas": round(revenue / spend, 2) if spend else 0,
    }


def _score(metrics: dict) -> float:
    """优先用 ROAS；没有花费时依次使用 CVR 和 CTR。"""
    if metrics["spend"] > 0:
        return float(metrics["roas"])
    if metrics["clicks"] > 0:
        return float(metrics["cvr"])
    return float(metrics["ctr"])


def _score_is_qualified(metrics: dict) -> bool:
    if metrics["spend"] > 0:
        return metrics["roas"] >= 1.5
    if metrics["clicks"] > 0:
        return metrics["cvr"] >= 2
    return metrics["ctr"] >= 1


def evaluate_variant_performance(
    copies: list[MarketingCopyAsset],
    snapshots: list[MarketingPerformanceSnapshot],
    *,
    now: datetime | None = None,
    persist: bool = True,
) -> list[dict]:
    """按平台计算 A/B 表现，并返回可持久化的版本状态。

    只有同平台至少两个版本样本充足、最高分达到业务门槛且存在明显差距时，
    才产生 winner 和 paused；否则统一保持 insufficient_data/active。
    """
    evaluated_at = now or datetime.now(timezone.utc)
    snapshots_by_copy: dict[str, list[MarketingPerformanceSnapshot]] = {}
    for snapshot in snapshots:
        if snapshot.copy_id is None:
            continue
        snapshots_by_copy.setdefault(str(snapshot.copy_id), []).append(snapshot)

    platforms = sorted({item.platform for item in copies})
    status_by_id: dict[str, str] = {}
    reason_by_id: dict[str, str] = {}
    for platform in platforms:
        platform_copies = [item for item in copies if item.platform == platform]
        ready_scores: dict[str, float] = {}
        qualified_ids: set[str] = set()
        metrics_by_id: dict[str, dict] = {}
        for asset in platform_copies:
            metrics = aggregate_snapshot_metrics(
                snapshots_by_copy.get(str(asset.id), [])
            )
            metrics_by_id[str(asset.id)] = metrics
            if (
                metrics["impressions"] >= MIN_IMPRESSIONS
                and metrics["clicks"] >= MIN_CLICKS
            ):
                ready_scores[str(asset.id)] = _score(metrics)
                if _score_is_qualified(metrics):
                    qualified_ids.add(str(asset.id))

        best_id = (
            max(qualified_ids, key=lambda item: ready_scores[item])
            if qualified_ids
            else None
        )
        best_score = ready_scores.get(best_id, 0) if best_id else 0
        losers = [
            item.id
            for item in platform_copies
            if str(item.id) in ready_scores
            and str(item.id) != best_id
            and ready_scores[str(item.id)] < best_score * LOSER_SCORE_RATIO
        ]
        for asset in platform_copies:
            asset_id = str(asset.id)
            metrics = metrics_by_id[asset_id]
            if (
                metrics["impressions"] < MIN_IMPRESSIONS
                or metrics["clicks"] < MIN_CLICKS
            ):
                status_by_id[asset_id] = "insufficient_data"
                reason_by_id[asset_id] = "样本量不足，继续积累效果数据"
            elif len(ready_scores) < 2 or best_id is None:
                status_by_id[asset_id] = "active"
                reason_by_id[asset_id] = "暂未达到明确的赢家门槛"
            elif asset_id == best_id and losers:
                status_by_id[asset_id] = "winner"
                reason_by_id[asset_id] = "样本充足且相对表现领先"
            elif asset.id in losers:
                status_by_id[asset_id] = "paused"
                reason_by_id[asset_id] = "样本充足但相对表现明显落后"
            else:
                status_by_id[asset_id] = "active"
                reason_by_id[asset_id] = "与领先版本差距尚不明确"

    results = []
    for asset in copies:
        asset_id = str(asset.id)
        metrics = aggregate_snapshot_metrics(
            snapshots_by_copy.get(asset_id, [])
        )
        status = status_by_id.get(asset_id, "active")
        payload = {
            "copy_id": asset_id,
            "platform": asset.platform,
            "variant_key": asset.variant_key,
            "headline": asset.headline,
            "performance_status": status,
            "reason": reason_by_id.get(asset_id, ""),
            "metrics": metrics,
            "evaluated_at": evaluated_at.isoformat(),
        }
        if persist:
            asset.performance_status = status
            asset.performance_metrics_json = json.dumps(
                {**metrics, "reason": payload["reason"]},
                ensure_ascii=False,
            )
            asset.last_evaluated_at = evaluated_at
        results.append(payload)
    return results


async def evaluate_campaign_ab_performance(
    db: AsyncSession,
    *,
    campaign_id,
    user_id,
) -> list[dict]:
    """加载活动文案和效果快照，并持久化 A/B 状态。"""
    copies = (
        await db.execute(
            select(MarketingCopyAsset)
            .where(
                MarketingCopyAsset.campaign_id == campaign_id,
                MarketingCopyAsset.user_id == user_id,
            )
            .order_by(
                MarketingCopyAsset.platform,
                MarketingCopyAsset.variant_key,
            )
        )
    ).scalars().all()
    snapshots = (
        await db.execute(
            select(MarketingPerformanceSnapshot).where(
                MarketingPerformanceSnapshot.campaign_id == campaign_id,
                MarketingPerformanceSnapshot.user_id == user_id,
                MarketingPerformanceSnapshot.copy_id.is_not(None),
            )
        )
    ).scalars().all()
    return evaluate_variant_performance(list(copies), list(snapshots))


def build_optimization_asset_actions(
    variant_analysis: list[dict],
) -> list[dict]:
    """把 A/B 状态转成文案、图片和视频的可执行优化动作。"""
    if not variant_analysis:
        return []
    winner = next(
        (item for item in variant_analysis if item["performance_status"] == "winner"),
        None,
    )
    paused = [
        item
        for item in variant_analysis
        if item["performance_status"] == "paused"
    ]
    actions = []
    for item in paused[:2]:
        actions.append(
            {
                "asset_type": "copy",
                "copy_id": item["copy_id"],
                "variant_key": item["variant_key"],
                "title": f"重写 {item['variant_key']} 版本的前 3 秒钩子",
                "detail": (
                    f"CTR {item['metrics']['ctr']}%、CVR "
                    f"{item['metrics']['cvr']}%；保留卖点，替换开场利益表达。"
                ),
            }
        )
    if winner:
        actions.append(
            {
                "asset_type": "image",
                "copy_id": winner["copy_id"],
                "variant_key": winner["variant_key"],
                "title": "复用赢家首帧与封面结构",
                "detail": "沿用高表现版本的主体构图、对比色和利益点文案。",
            }
        )
    actions.append(
        {
            "asset_type": "video",
            "copy_id": winner["copy_id"] if winner else None,
            "variant_key": winner["variant_key"] if winner else None,
            "title": "保持镜头顺序，强化产品演示",
            "detail": "优先替换低转化段落，增加真实使用动作和使用前后对比。",
        }
    )
    return actions
