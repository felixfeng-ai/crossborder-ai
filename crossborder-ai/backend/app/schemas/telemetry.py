"""页面访问和 Web Vitals 上报表结构。"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


WEB_VITAL_NAMES = {"LCP", "FCP", "INP", "CLS", "TTFB"}
WEB_VITAL_RATINGS = {"good", "needs-improvement", "poor"}


class TelemetryEventIn(BaseModel):
    """单条匿名遥测事件。"""

    event_type: Literal["page_view", "web_vital"]
    visitor_id: str = Field(..., min_length=8, max_length=64)
    session_id: str = Field(..., min_length=8, max_length=64)
    path: str = Field(..., min_length=1, max_length=500)
    referrer_host: str = Field("", max_length=255)
    country_hint: str | None = Field(None, max_length=8)
    device_type: Literal["desktop", "tablet", "mobile", "unknown"] = "unknown"
    viewport_width: int | None = Field(None, ge=200, le=10000)
    connection_type: str | None = Field(None, max_length=20)
    metric_name: str | None = Field(None, max_length=16)
    metric_value: float | None = Field(None, ge=0)
    metric_rating: str | None = Field(None, max_length=24)
    release: str = Field("", max_length=64)
    request_id: str | None = Field(None, max_length=36)

    @model_validator(mode="after")
    def validate_metric(self):
        """性能事件必须有白名单指标、数值和合法评级。"""
        if self.event_type != "web_vital":
            return self
        if self.metric_name not in WEB_VITAL_NAMES:
            raise ValueError("不支持的 Web Vitals 指标")
        if self.metric_value is None:
            raise ValueError("性能事件缺少 metric_value")
        if self.metric_rating not in WEB_VITAL_RATINGS:
            raise ValueError("性能事件评级不合法")
        return self


class TelemetryBatchIn(BaseModel):
    """前端批量上报，限制单次体积。"""

    events: list[TelemetryEventIn] = Field(..., min_length=1, max_length=20)
