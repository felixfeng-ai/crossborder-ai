"""匿名页面访问与 Web Vitals 上报接口。"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import RateLimit
from app.models.traffic_event import TrafficEvent
from app.schemas.telemetry import TelemetryBatchIn


router = APIRouter(prefix="/telemetry", tags=["遥测"])


def _country_code(request: Request) -> str:
    """优先使用边缘节点注入的国家代码，缺失时保持 unknown。"""
    return (request.headers.get("X-Country-Code") or "unknown")[:8].upper()


@router.post("/events")
async def ingest_events(
    payload: TelemetryBatchIn,
    request: Request,
    _ratelimit=Depends(RateLimit("default", max_requests=120, window=60)),
    db: AsyncSession = Depends(get_db),
):
    """批量接收匿名事件，不保存 IP 和完整 User-Agent。"""
    user_agent = request.headers.get("User-Agent", "").lower()
    is_bot = any(token in user_agent for token in ("bot", "crawler", "spider"))
    created_at = datetime.now(timezone.utc)
    edge_country = _country_code(request)

    rows = [
        TrafficEvent(
            event_type=event.event_type,
            visitor_id=event.visitor_id,
            session_id=event.session_id,
            path=event.path.split("?", 1)[0][:500],
            referrer_host=event.referrer_host[:255],
            country_code=(
                edge_country
                if edge_country != "UNKNOWN"
                else (event.country_hint or "unknown").upper()[:8]
            ),
            device_type=event.device_type,
            viewport_width=event.viewport_width,
            connection_type=event.connection_type,
            metric_name=event.metric_name,
            metric_value=event.metric_value,
            metric_rating=event.metric_rating,
            release=event.release[:64],
            request_id=event.request_id,
            is_bot=is_bot,
            created_at=created_at,
        )
        for event in payload.events
    ]
    db.add_all(rows)
    await db.commit()
    return {"accepted": len(rows)}
