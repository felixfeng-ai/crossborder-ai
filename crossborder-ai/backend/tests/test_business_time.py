"""工作区业务日期的 UTC 边界测试。"""

from datetime import date, datetime, timezone

from app.services.business_time import business_day_utc_bounds


def test_asia_shanghai_business_day_uses_local_midnight():
    start, end = business_day_utc_bounds(
        date(2026, 11, 22),
        "Asia/Shanghai",
    )

    assert start == datetime(2026, 11, 21, 16, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 11, 22, 16, 0, tzinfo=timezone.utc)
