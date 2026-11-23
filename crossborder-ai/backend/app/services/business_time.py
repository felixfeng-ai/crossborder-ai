"""工作区业务日期的时区换算。"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def resolve_timezone(timezone_name: str | None) -> ZoneInfo | timezone:
    """解析 IANA 时区，非法值安全降级为 UTC。"""

    try:
        return ZoneInfo((timezone_name or "").strip() or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc


def business_date_in_timezone(
    timezone_name: str | None,
    *,
    now: datetime | None = None,
) -> date:
    """返回指定时区此刻对应的业务日期。"""

    zone = resolve_timezone(timezone_name)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(zone).date()


def business_day_utc_bounds(
    business_date: date,
    timezone_name: str | None,
) -> tuple[datetime, datetime]:
    """把本地业务日转换成左闭右开的 UTC 时间边界。"""

    zone = resolve_timezone(timezone_name)
    local_start = datetime.combine(business_date, time.min, tzinfo=zone)
    local_end = local_start + timedelta(days=1)
    return (
        local_start.astimezone(timezone.utc),
        local_end.astimezone(timezone.utc),
    )
