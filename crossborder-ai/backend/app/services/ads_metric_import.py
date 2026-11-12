"""Amazon Ads、TikTok Ads、Meta Ads 标准指标导入适配器。"""

import csv
import io
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


class AdsMetricImportError(ValueError):
    """广告报表无法安全转换为标准指标。"""


@dataclass
class NormalizedAdMetrics:
    """不同广告平台报表统一后的活动效果指标。"""

    provider: str
    platform: str
    source: str
    impressions: int
    clicks: int
    orders: int
    conversions: int
    spend: float
    revenue: float
    currency: str = "USD"


@dataclass(frozen=True)
class ProviderSpec:
    platform: str
    source: str
    aliases: dict[str, tuple[str, ...]]


_COMMON_ALIASES = {
    "impressions": ("impressions", "impression", "曝光", "展示"),
    "clicks": ("clicks", "click", "link clicks", "点击"),
    "spend": ("cost", "spend", "amount spent", "amount spent usd", "广告花费"),
    "orders": (
        "purchases",
        "purchase",
        "complete payment",
        "conversions",
        "conversion",
        "orders",
        "订单",
    ),
    "revenue": (
        "sales",
        "revenue",
        "purchase conversion value",
        "complete payment value",
        "conversion value",
        "销售额",
    ),
    "currency": ("currency", "币种"),
}

PROVIDER_SPECS = {
    "amazon_ads": ProviderSpec(
        platform="amazon",
        source="amazon_ads_csv",
        aliases=_COMMON_ALIASES,
    ),
    "tiktok_ads": ProviderSpec(
        platform="tiktok",
        source="tiktok_ads_csv",
        aliases=_COMMON_ALIASES,
    ),
    "meta_ads": ProviderSpec(
        platform="meta",
        source="meta_ads_csv",
        aliases=_COMMON_ALIASES,
    ),
}


def _normalize_header(value: str) -> str:
    """统一表头大小写、货币单位和标点，兼容平台导出差异。"""
    normalized = (value or "").strip().lower().lstrip("\ufeff")
    normalized = normalized.replace("$", " ").replace("%", " ")
    normalized = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _parse_number(value: str, *, line_number: int, field: str) -> Decimal:
    """解析千分位、货币符号和括号负数；错误必须指出具体行。"""
    raw = (value or "").strip()
    if not raw:
        return Decimal("0")
    negative = raw.startswith("(") and raw.endswith(")")
    cleaned = re.sub(r"[^0-9.\-]", "", raw)
    if negative:
        cleaned = f"-{cleaned.lstrip('-')}"
    try:
        parsed = Decimal(cleaned or "0")
    except InvalidOperation as exc:
        raise AdsMetricImportError(
            f"第 {line_number} 行的 {field} 不是有效数字：{value}"
        ) from exc
    return parsed


def _resolve_columns(
    fieldnames: list[str],
    aliases: dict[str, tuple[str, ...]],
) -> dict[str, str]:
    by_normalized = {
        _normalize_header(name): name
        for name in fieldnames
        if name
    }
    resolved: dict[str, str] = {}
    for field, candidates in aliases.items():
        for candidate in candidates:
            source = by_normalized.get(_normalize_header(candidate))
            if source:
                resolved[field] = source
                break
    return resolved


def parse_ad_metrics_csv(provider: str, csv_text: str) -> NormalizedAdMetrics:
    """把平台导出的 CSV 汇总为一条可入库的标准效果快照。"""
    spec = PROVIDER_SPECS.get(provider)
    if spec is None:
        raise AdsMetricImportError(f"不支持的广告平台：{provider}")
    if not (csv_text or "").strip():
        raise AdsMetricImportError("CSV 内容为空")

    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    if not reader.fieldnames:
        raise AdsMetricImportError("CSV 缺少表头")
    columns = _resolve_columns(list(reader.fieldnames), spec.aliases)
    required = {"impressions", "clicks", "spend", "orders", "revenue"}
    missing = sorted(required - set(columns))
    if missing:
        raise AdsMetricImportError(
            "CSV 缺少标准指标列：" + "、".join(missing)
        )

    totals = {
        "impressions": Decimal("0"),
        "clicks": Decimal("0"),
        "orders": Decimal("0"),
        "spend": Decimal("0"),
        "revenue": Decimal("0"),
    }
    currency = "USD"
    row_count = 0
    for line_number, row in enumerate(reader, start=2):
        if not any((value or "").strip() for value in row.values()):
            continue
        row_count += 1
        for field in totals:
            totals[field] += _parse_number(
                row.get(columns[field], ""),
                line_number=line_number,
                field=field,
            )
        if columns.get("currency"):
            value = (row.get(columns["currency"], "") or "").strip().upper()
            if value:
                currency = value[:10]

    if row_count == 0:
        raise AdsMetricImportError("CSV 没有可导入的数据行")

    return NormalizedAdMetrics(
        provider=provider,
        platform=spec.platform,
        source=spec.source,
        impressions=max(0, int(totals["impressions"])),
        clicks=max(0, int(totals["clicks"])),
        orders=max(0, int(totals["orders"])),
        conversions=max(0, int(totals["orders"])),
        spend=round(max(0.0, float(totals["spend"])), 2),
        revenue=round(max(0.0, float(totals["revenue"])), 2),
        currency=currency,
    )
