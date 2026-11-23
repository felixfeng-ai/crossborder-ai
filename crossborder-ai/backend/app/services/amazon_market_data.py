"""Amazon US 市场数据 Provider 与选品决策。

模型不生成市场数字。Jungle Scout 提供第三方估算，服务层负责归一化、聚合和
可追溯证据；缺少数据时明确标为不足，而不是用 0 或猜测值补齐。
"""

from __future__ import annotations

import asyncio
import json
import math
import re
import statistics
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Protocol

import httpx


PROVIDER_NAME = "jungle_scout"
JUSTONE_PROVIDER_NAME = "justone_api"
SUPPORTED_MARKETPLACE = "us"
ALLOWED_VERDICTS = {
    "有机会",
    "有机会但需验证",
    "谨慎",
    "数据不足",
}


class AmazonMarketDataError(RuntimeError):
    """Amazon 市场数据错误基类。"""


class AmazonMarketDataNotConfigured(AmazonMarketDataError):
    """Provider 凭据未配置。"""


class AmazonMarketDataAuthorizationError(AmazonMarketDataError):
    """Provider 鉴权失败或套餐权限不足。"""

    def __init__(self, message: str, *, code: int | None = None):
        super().__init__(message)
        self.code = code


class AmazonMarketDataRequestError(AmazonMarketDataError):
    """Provider 超时、限流或响应异常。"""

    def __init__(self, message: str, *, code: int | None = None):
        super().__init__(message)
        self.code = code


class AmazonMarketQueryError(AmazonMarketDataError):
    """中文品类无法转换为可查询的英文搜索词。"""


@dataclass(frozen=True)
class MarketQuery:
    """一个可独立取证的市场搜索方向。"""

    key: str
    label_zh: str
    keyword: str


@dataclass(frozen=True)
class CategoryBlueprint:
    """宽泛品类拆成基准词和细分方向。"""

    key: str
    label_zh: str
    base: MarketQuery
    segments: tuple[MarketQuery, ...]


@dataclass(frozen=True)
class AmazonProductSample:
    """Provider 返回并归一化后的单个商品样本。"""

    asin: str
    title: str
    brand: str | None
    price: float | None
    reviews: int | None
    rating: float | None
    monthly_units: int | None
    monthly_revenue: float | None
    bsr: int | None
    sellers: int | None
    listing_quality_score: float | None
    referral_fee_rate: float | None
    fulfillment_fee_usd: float | None
    date_first_available: datetime | None
    url: str
    purchase_volume_raw: str | None = None
    purchase_volume_min: int | None = None
    purchase_volume_period: str | None = None
    purchase_volume_is_lower_bound: bool = False
    offer_count: int | None = None
    availability: str | None = None
    is_best_seller: bool = False
    is_amazon_choice: bool = False
    review_titles: list[str] = field(default_factory=list)
    review_comments: list[str] = field(default_factory=list)
    source_provider: str = PROVIDER_NAME
    payload: dict[str, Any] = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class ProductDatabaseResult:
    """Product Database 单次或分页聚合结果。"""

    items: list[AmazonProductSample]
    total_results: int | None
    observed_at: datetime
    pages_read: int
    provider: str = PROVIDER_NAME


class AmazonMarketProvider(Protocol):
    """市场 Provider 最小契约，便于后续接入 Keepa。"""

    async def query_product_database(
        self,
        keyword: str,
        *,
        page_size: int = 100,
        max_pages: int = 2,
    ) -> ProductDatabaseResult:
        ...

    async def historical_search_volume(
        self,
        keyword: str,
        *,
        days: int = 35,
    ) -> int | None:
        ...


def _number(value: Any) -> float | None:
    """提取数值，兼容金额对象、百分数字符串和千分位。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, dict):
        for key in ("amount", "value", "price", "fee", "minimum", "max"):
            if key in value:
                return _number(value.get(key))
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip().replace(",", "").replace("$", "").replace("¥", "")
    percent = text.endswith("%")
    text = text.rstrip("%").strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number / 100 if percent else number


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(round(number)) if number is not None else None


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(str(value)[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _fee_value(fee_breakdown: Any, *keys: str) -> float | None:
    if not isinstance(fee_breakdown, dict):
        return None
    for key in keys:
        if key in fee_breakdown:
            return _number(fee_breakdown.get(key))
        nested = fee_breakdown.get(key.replace("_usd", ""))
        if nested is not None:
            return _number(nested)
    return None


def _parse_purchase_volume(raw: Any) -> dict[str, Any]:
    """解析 Amazon 前台购买量展示，绝不推断成精确月销。"""
    text = str(raw or "").strip()
    if not text:
        return {
            "raw": None,
            "minimum": None,
            "period": None,
            "is_lower_bound": False,
        }
    match = re.search(
        r"([\d][\d,.]*)\s*([KMB])?\+?\s*(?:bought|purchased)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return {
            "raw": text,
            "minimum": None,
            "period": "past_month" if "past month" in text.lower() else None,
            "is_lower_bound": "+" in text,
        }
    number = _number(match.group(1))
    multiplier = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(
        (match.group(2) or "").upper(),
        1,
    )
    minimum = (
        int(round(number * multiplier)) if number is not None else None
    )
    return {
        "raw": text,
        "minimum": minimum,
        "period": "past_month" if "past month" in text.lower() else None,
        "is_lower_bound": "+" in text,
    }


def _brand_from_byline(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    labeled = re.search(r"Brand\s*:\s*(.+)", text, re.IGNORECASE)
    if labeled:
        return labeled.group(1).strip()[:120] or None
    by = re.search(r"\bby\s+(.+)", text, re.IGNORECASE)
    if by:
        return by.group(1).strip()[:120] or None
    return text[:120]


def _rank_value(value: Any) -> int | None:
    """从详情中的 BSR 数组、对象或展示文本提取首个数字。"""
    if isinstance(value, list):
        return _rank_value(value[0]) if value else None
    if isinstance(value, dict):
        return _integer(_first(value, "rank", "value", "product_rank"))
    if value is None:
        return None
    match = re.search(r"#?\s*([\d,]+)", str(value))
    return _integer(match.group(1)) if match else None


_REVIEW_PAIN_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("噪音", ("noise", "noisy", "loud", "buzzing")),
    ("泵体故障", ("pump", "motor", "stopped working")),
    ("清洗困难", ("hard to clean", "cleaning", "disassemble")),
    ("漏水", ("leak", "leaking", "spill")),
    ("滤芯耗材", ("filter", "replacement")),
    ("耐用性", ("broke", "broken", "durable", "short life")),
)


def _review_pain_points(
    products: list[AmazonProductSample],
) -> list[str]:
    """用固定关键词规则识别评论痛点，不让模型生成不存在的问题。"""
    texts = " ".join(
        [
            *(title for item in products for title in item.review_titles),
            *(comment for item in products for comment in item.review_comments),
        ]
    ).lower()
    if not texts:
        return []
    return [
        label
        for label, patterns in _REVIEW_PAIN_PATTERNS
        if any(pattern in texts for pattern in patterns)
    ]


def _normalize_product_node(node: dict[str, Any]) -> AmazonProductSample | None:
    attributes = node.get("attributes")
    if not isinstance(attributes, dict):
        attributes = node
    product = attributes.get("product")
    if isinstance(product, dict):
        attributes = {**product, **attributes}

    asin = str(
        _first(attributes, "asin", "id", "product_id") or node.get("id") or ""
    ).strip()
    title = str(
        _first(attributes, "title", "product_title", "name") or ""
    ).strip()
    if not asin or not title:
        return None

    price = _number(_first(attributes, "price", "buy_box_price", "current_price"))
    if price is not None and price <= 0:
        price = None
    reviews = _integer(
        _first(attributes, "reviews", "review_count", "ratings_total")
    )
    rating = _number(_first(attributes, "rating", "review_rating"))
    monthly_units = _integer(
        _first(
            attributes,
            "approximate_30_day_units_sold",
            "estimated_30_day_units",
            "monthly_units_sold",
        )
    )
    monthly_revenue = _number(
        _first(
            attributes,
            "approximate_30_day_revenue",
            "estimated_30_day_revenue",
        )
    )
    fee_breakdown = (
        attributes.get("fee_breakdown")
        or attributes.get("fees")
        or attributes.get("estimated_fees")
    )
    referral_fee = _fee_value(
        fee_breakdown,
        "referral_fee_usd",
        "referral_fee",
        "referral_fee_amount",
    )
    fulfillment_fee = _fee_value(
        fee_breakdown,
        "fulfillment_fee_usd",
        "fulfillment_fee",
        "fba_fee",
        "fba_fulfillment_fee",
    )
    referral_rate = (
        referral_fee / price
        if referral_fee is not None and price is not None and price > 0
        else None
    )

    return AmazonProductSample(
        asin=asin,
        title=title,
        brand=str(_first(attributes, "brand", "brand_name") or "").strip() or None,
        price=price,
        reviews=reviews,
        rating=rating,
        monthly_units=monthly_units,
        monthly_revenue=monthly_revenue,
        bsr=_integer(
            _first(attributes, "product_rank", "bsr", "best_sellers_rank")
        ),
        sellers=_integer(
            _first(attributes, "number_of_sellers", "sellers", "seller_count")
        ),
        listing_quality_score=_number(
            _first(attributes, "listing_quality_score", "lqs")
        ),
        referral_fee_rate=referral_rate,
        fulfillment_fee_usd=fulfillment_fee,
        date_first_available=_parse_datetime(
            _first(
                attributes,
                "date_first_available",
                "first_available",
                "listed_since",
            )
        ),
        url=f"https://www.amazon.com/dp/{asin}",
        payload=attributes,
    )


class JungleScoutAmazonProvider:
    """Jungle Scout Amazon US 数据 Provider。"""

    def __init__(
        self,
        *,
        key_name: str,
        api_key: str,
        marketplace: str = SUPPORTED_MARKETPLACE,
        base_url: str = "https://developer.junglescout.com",
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 45,
    ):
        self.key_name = str(key_name or "").strip()
        self.api_key = str(api_key or "").strip()
        self.marketplace = str(marketplace or SUPPORTED_MARKETPLACE).strip().lower()
        self.base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def _ensure_configured(self) -> None:
        if not self.key_name or not self.api_key:
            raise AmazonMarketDataNotConfigured(
                "Amazon 市场数据源未配置，请在管理员服务商设置中填写 "
                "Jungle Scout Key Name 和 API Key"
            )
        if self.marketplace != SUPPORTED_MARKETPLACE:
            raise AmazonMarketDataNotConfigured(
                "当前选品决策只支持 Amazon US（marketplace=us）"
            )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"{self.key_name}:{self.api_key}",
            "X-API-Type": "junglescout",
            "Accept": "application/vnd.junglescout.v1+json",
            "Content-Type": "application/vnd.api+json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._ensure_configured()
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=self._timeout,
            ) as client:
                response = await client.request(
                    method,
                    url,
                    params={"marketplace": self.marketplace, **(params or {})},
                    headers=self._headers(),
                    json=json_body,
                )
        except httpx.TimeoutException as exc:
            raise AmazonMarketDataRequestError(
                "Amazon 市场数据源响应超时，请稍后重试"
            ) from exc
        except httpx.HTTPError as exc:
            raise AmazonMarketDataRequestError(
                "Amazon 市场数据源暂时不可用"
            ) from exc

        if response.status_code in {401, 403}:
            raise AmazonMarketDataAuthorizationError(
                "Jungle Scout 鉴权失败或当前套餐没有对应数据权限"
            )
        if response.status_code == 429:
            raise AmazonMarketDataRequestError(
                "Amazon 市场数据源调用过于频繁，请稍后重试"
            )
        if response.status_code >= 400:
            raise AmazonMarketDataRequestError(
                f"Amazon 市场数据请求失败（HTTP {response.status_code}）"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise AmazonMarketDataRequestError(
                "Amazon 市场数据源返回了无法解析的响应"
            ) from exc
        if not isinstance(body, dict):
            raise AmazonMarketDataRequestError(
                "Amazon 市场数据源响应格式不正确"
            )
        return body

    async def query_product_database(
        self,
        keyword: str,
        *,
        page_size: int = 100,
        max_pages: int = 2,
    ) -> ProductDatabaseResult:
        """读取 Product Database，按页去重并保留样本观察时间。"""
        normalized_keyword = str(keyword or "").strip()
        if len(normalized_keyword) < 2:
            raise AmazonMarketDataRequestError("Amazon 市场搜索词不能为空")
        page_size = max(1, min(int(page_size), 100))
        max_pages = max(1, min(int(max_pages), 5))
        items: list[AmazonProductSample] = []
        seen: set[str] = set()
        total_results: int | None = None
        pages_read = 0
        observed_at = datetime.now(timezone.utc)

        for page_number in range(1, max_pages + 1):
            body = await self._request(
                "POST",
                "/api/product_database_query",
                params={
                    "page[size]": page_size,
                    "page[number]": page_number,
                },
                json_body={
                    "data": {
                        "type": "product_database_query",
                        "attributes": {
                            "include_keywords": [normalized_keyword],
                            "exclude_unavailable_products": True,
                        },
                    }
                },
            )
            pages_read += 1
            raw_items = body.get("data")
            if not isinstance(raw_items, list):
                raw_items = []
            for node in raw_items:
                if not isinstance(node, dict):
                    continue
                sample = _normalize_product_node(node)
                if sample is None or sample.asin in seen:
                    continue
                seen.add(sample.asin)
                items.append(sample)

            meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
            page_meta = meta.get("page") if isinstance(meta.get("page"), dict) else {}
            total_results = _integer(
                _first(page_meta, "total_results", "total")
                or _first(meta, "total_results", "total")
                or total_results
            )
            links = body.get("links") if isinstance(body.get("links"), dict) else {}
            has_next = bool(links.get("next"))
            if (
                not has_next
                and total_results is not None
                and len(items) < total_results
                and len(raw_items) >= page_size
            ):
                has_next = True
            if not has_next:
                break

        return ProductDatabaseResult(
            items=items,
            total_results=total_results,
            observed_at=observed_at,
            pages_read=pages_read,
        )

    async def historical_search_volume(
        self,
        keyword: str,
        *,
        days: int = 35,
    ) -> int:
        """汇总最近指定天数的周度精确搜索量估算。"""
        normalized_keyword = str(keyword or "").strip()
        if len(normalized_keyword) < 2:
            raise AmazonMarketDataRequestError("Amazon 搜索词不能为空")
        days = max(7, min(int(days), 365))
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days)
        body = await self._request(
            "GET",
            "/api/keywords/historical_search_volume",
            params={
                "keyword": normalized_keyword,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )
        data = body.get("data")
        total = 0
        if isinstance(data, list):
            for node in data:
                if not isinstance(node, dict):
                    continue
                attributes = node.get("attributes")
                if not isinstance(attributes, dict):
                    attributes = node
                value = _number(
                    _first(
                        attributes,
                        "estimated_exact_search_volume",
                        "estimated_search_volume",
                        "search_volume",
                    )
                )
                if value is not None:
                    total += int(round(value))
        elif isinstance(data, dict):
            attributes = data.get("attributes")
            if isinstance(attributes, dict):
                value = _number(
                    _first(
                        attributes,
                        "estimated_exact_search_volume",
                        "estimated_search_volume",
                    )
                )
                total = int(round(value or 0))
        return total


class JustOneAmazonProvider:
    """JustOneAPI Amazon Provider。

    搜索负责发现样本，详情和评论只按全局 Top 数量补证，避免逐个 ASIN 展开调用。
    """

    default_max_pages = 1

    def __init__(
        self,
        *,
        token: str,
        marketplace: str = SUPPORTED_MARKETPLACE,
        base_url: str = "https://api.justoneapi.com",
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 120,
    ):
        self.token = str(token or "").strip()
        self.marketplace = str(marketplace or SUPPORTED_MARKETPLACE).strip().lower()
        self.base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def _ensure_configured(self) -> None:
        if not self.token:
            raise AmazonMarketDataNotConfigured(
                "Amazon 市场数据源未配置，请在管理员服务商设置中填写 "
                "JustOneAPI Token"
            )
        if self.marketplace != SUPPORTED_MARKETPLACE:
            raise AmazonMarketDataNotConfigured(
                "当前选品决策只支持 Amazon US（country=US）"
            )

    async def _request(
        self,
        path: str,
        *,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        self._ensure_configured()
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=self._timeout,
            ) as client:
                response = await client.get(
                    f"{self.base_url}{path}",
                    params={
                        "token": self.token,
                        "country": self.marketplace.upper(),
                        **params,
                    },
                )
        except httpx.TimeoutException as exc:
            raise AmazonMarketDataRequestError(
                "JustOneAPI Amazon 接口响应超时，请稍后重试"
            ) from exc
        except httpx.HTTPError as exc:
            raise AmazonMarketDataRequestError(
                "JustOneAPI Amazon 接口暂时不可用"
            ) from exc

        if response.status_code in {401, 403}:
            raise AmazonMarketDataAuthorizationError(
                "JustOneAPI Token 无效或没有 Amazon 接口权限"
            )
        if response.status_code == 429:
            raise AmazonMarketDataRequestError(
                "JustOneAPI Amazon 接口调用频率或每日额度已达上限"
            )
        if response.status_code >= 400:
            raise AmazonMarketDataRequestError(
                f"JustOneAPI Amazon 请求失败（HTTP {response.status_code}）"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise AmazonMarketDataRequestError(
                "JustOneAPI Amazon 返回了无法解析的响应"
            ) from exc
        if not isinstance(body, dict):
            raise AmazonMarketDataRequestError(
                "JustOneAPI Amazon 响应格式不正确"
            )

        code = _integer(body.get("code"))
        if code == 0:
            return body
        if code in {100, 600}:
            raise AmazonMarketDataAuthorizationError(
                "JustOneAPI Token 无效、未激活或没有 Amazon 接口权限",
                code=code,
            )
        if code in {302}:
            raise AmazonMarketDataRequestError(
                "JustOneAPI Amazon 调用过于频繁，请稍后重试",
                code=code,
            )
        if code in {303}:
            raise AmazonMarketDataRequestError(
                "JustOneAPI Amazon 每日额度已耗尽",
                code=code,
            )
        if code == 601:
            raise AmazonMarketDataRequestError(
                "JustOneAPI 账户余额不足，无法继续读取 Amazon 数据",
                code=code,
            )
        if code == 602:
            raise AmazonMarketDataRequestError(
                "JustOneAPI 当前 Token 预算已用完",
                code=code,
            )
        if code == 301:
            raise AmazonMarketDataRequestError(
                "JustOneAPI Amazon 本次采集失败，可稍后重试",
                code=code,
            )
        raise AmazonMarketDataRequestError(
            f"JustOneAPI Amazon 返回业务错误 {code or 'unknown'}"
        )

    @staticmethod
    def _normalize_search_product(
        raw: dict[str, Any],
    ) -> AmazonProductSample | None:
        if not isinstance(raw, dict):
            return None
        asin = str(raw.get("asin") or "").strip()
        title = str(raw.get("product_title") or "").strip()
        if not asin or not title:
            return None
        purchase_volume = _parse_purchase_volume(raw.get("sales_volume"))
        offer_count = _integer(raw.get("product_num_offers"))
        return AmazonProductSample(
            asin=asin,
            title=title,
            brand=_brand_from_byline(raw.get("product_byline")),
            price=(
                _number(raw.get("product_price_value"))
                or _number(raw.get("product_price"))
            ),
            reviews=_integer(raw.get("product_num_ratings")),
            rating=_number(raw.get("product_star_rating")),
            monthly_units=None,
            monthly_revenue=None,
            bsr=None,
            sellers=None,
            listing_quality_score=None,
            referral_fee_rate=None,
            fulfillment_fee_usd=None,
            date_first_available=None,
            url=(
                str(raw.get("product_url") or "").strip()
                or f"https://www.amazon.com/dp/{asin}"
            ),
            purchase_volume_raw=purchase_volume["raw"],
            purchase_volume_min=purchase_volume["minimum"],
            purchase_volume_period=purchase_volume["period"],
            purchase_volume_is_lower_bound=purchase_volume["is_lower_bound"],
            offer_count=offer_count,
            availability=str(raw.get("product_availability") or "").strip() or None,
            is_best_seller=bool(raw.get("is_best_seller")),
            is_amazon_choice=bool(raw.get("is_amazon_choice")),
            source_provider=JUSTONE_PROVIDER_NAME,
            payload=raw,
        )

    @staticmethod
    def _detail_seller_count(raw: dict[str, Any]) -> int | None:
        seller_ids = {
            str(item.get("seller_id"))
            for item in raw.get("buy_boxes") or []
            if isinstance(item, dict)
            and item.get("seller_id") not in (None, "")
        }
        if seller_ids:
            return len(seller_ids)
        return _integer(raw.get("product_num_offers"))

    async def query_product_database(
        self,
        keyword: str,
        *,
        page_size: int = 100,
        max_pages: int = 1,
    ) -> ProductDatabaseResult:
        del page_size  # JustOneAPI 以 page 为单位，不接收 page_size。
        normalized_keyword = str(keyword or "").strip()
        if len(normalized_keyword) < 2:
            raise AmazonMarketDataRequestError("Amazon 市场搜索词不能为空")
        items: list[AmazonProductSample] = []
        seen: set[str] = set()
        total_results: int | None = None
        pages_read = 0
        observed_at = datetime.now(timezone.utc)
        for page_number in range(1, max(1, min(int(max_pages), 3)) + 1):
            body = await self._request(
                "/api/amazon/search-products/v1",
                params={
                    "keyword": normalized_keyword,
                    "sortBy": "RELEVANCE",
                    "productCondition": "NEW",
                    "page": page_number,
                },
            )
            pages_read += 1
            data = body.get("data")
            if not isinstance(data, dict):
                data = {}
            total_results = (
                _integer(_first(data, "total_products", "totalProducts"))
                or total_results
            )
            raw_products = data.get("products")
            if not isinstance(raw_products, list):
                raw_products = []
            for raw in raw_products:
                item = self._normalize_search_product(raw)
                if item is None or item.asin in seen:
                    continue
                seen.add(item.asin)
                items.append(item)
            if len(raw_products) == 0:
                break
        return ProductDatabaseResult(
            items=items,
            total_results=total_results,
            observed_at=observed_at,
            pages_read=pages_read,
            provider=JUSTONE_PROVIDER_NAME,
        )

    async def historical_search_volume(
        self,
        keyword: str,
        *,
        days: int = 35,
    ) -> None:
        del keyword, days
        return None

    async def get_product_detail(self, asin: str) -> dict[str, Any]:
        normalized_asin = str(asin or "").strip()
        if not normalized_asin:
            raise AmazonMarketDataRequestError("缺少 Amazon ASIN")
        body = await self._request(
            "/api/amazon/get-product-detail/v1",
            params={"asin": normalized_asin},
        )
        data = body.get("data")
        if not isinstance(data, dict):
            raise AmazonMarketDataRequestError(
                "JustOneAPI 商品详情响应缺少 data"
            )
        return data

    async def get_product_top_reviews(self, asin: str) -> dict[str, list[str]]:
        body = await self._request(
            "/api/amazon/get-product-top-reviews/v1",
            params={"asin": str(asin or "").strip()},
        )
        data = body.get("data")
        if not isinstance(data, dict):
            return {"titles": [], "comments": []}
        raw_reviews = data.get("top_reviews")
        if not isinstance(raw_reviews, list):
            return {"titles": [], "comments": []}
        titles: list[str] = []
        comments: list[str] = []
        for review in raw_reviews:
            if not isinstance(review, dict):
                continue
            rating_match = re.search(
                r"([1-5](?:\.\d+)?)",
                str(review.get("review_star_rating") or ""),
            )
            if rating_match is None or float(rating_match.group(1)) > 3:
                continue
            title = str(review.get("review_title") or "").strip()
            comment = str(review.get("review_comment") or "").strip()
            if title:
                titles.append(title[:200])
            if comment:
                comments.append(comment[:500])
        return {"titles": titles, "comments": comments}

    async def enrich_products(
        self,
        products: list[AmazonProductSample],
        *,
        detail_limit: int = 6,
        review_limit: int = 3,
    ) -> list[AmazonProductSample]:
        """按购买量和评论排序后，只补证全局 Top ASIN。"""
        if not products:
            return []
        ordered = sorted(
            products,
            key=lambda item: (
                item.purchase_volume_min or 0,
                item.reviews or 0,
                int(item.is_best_seller),
            ),
            reverse=True,
        )[: max(1, min(int(detail_limit), 10))]
        enriched: list[AmazonProductSample] = []
        semaphore = asyncio.Semaphore(3)

        async def enrich_one(item: AmazonProductSample, index: int):
            async with semaphore:
                try:
                    raw = await self.get_product_detail(item.asin)
                except AmazonMarketDataAuthorizationError:
                    raise
                except AmazonMarketDataError as exc:
                    if getattr(exc, "code", None) in {
                        100,
                        302,
                        303,
                        600,
                        601,
                        602,
                    }:
                        raise
                    return item
                purchase_volume = _parse_purchase_volume(
                    raw.get("sales_volume") or item.purchase_volume_raw
                )
                price = (
                    _number(raw.get("product_price_value"))
                    or _number(raw.get("product_price"))
                    or item.price
                )
                updated = (
                    replace(
                        item,
                        title=str(
                            raw.get("product_title") or item.title
                        ).strip(),
                        price=price,
                        reviews=(
                            _integer(raw.get("product_num_ratings"))
                            or item.reviews
                        ),
                        rating=(
                            _number(raw.get("product_star_rating"))
                            or item.rating
                        ),
                        bsr=_rank_value(raw.get("best_sellers_rank")),
                        sellers=self._detail_seller_count(raw),
                        offer_count=(
                            _integer(raw.get("product_num_offers"))
                            or item.offer_count
                        ),
                        availability=(
                            str(
                                raw.get("product_availability") or ""
                            ).strip()
                            or item.availability
                        ),
                        purchase_volume_raw=purchase_volume["raw"],
                        purchase_volume_min=purchase_volume["minimum"],
                        purchase_volume_period=purchase_volume["period"],
                        purchase_volume_is_lower_bound=(
                            purchase_volume["is_lower_bound"]
                        ),
                        source_provider=JUSTONE_PROVIDER_NAME,
                        payload=raw,
                    )
                )
                if index < max(1, min(int(review_limit), 5)):
                    try:
                        reviews = await self.get_product_top_reviews(item.asin)
                        updated = replace(
                            updated,
                            review_titles=reviews["titles"][:5],
                            review_comments=reviews["comments"][:5],
                        )
                    except AmazonMarketDataError as exc:
                        if getattr(exc, "code", None) in {
                            100,
                            302,
                            303,
                            600,
                            601,
                            602,
                        }:
                            raise
                        pass
                return updated

        enriched = await asyncio.gather(
            *(enrich_one(item, index) for index, item in enumerate(ordered))
        )
        enriched_by_asin = {item.asin: item for item in enriched}
        return [enriched_by_asin.get(item.asin, item) for item in products]


def _extract_json_object(text: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


async def plan_queries_with_deepseek(
    keyword: str,
    context: str | None = None,
) -> list[MarketQuery]:
    """只让模型翻译和拆分英文搜索词，不接收任何数字。"""
    from app.services.ai.deepseek import DeepSeekService

    raw = await DeepSeekService().generate(
        (
            "你是跨境选品搜索词规划器。只输出 JSON。"
            "你只能把中文商品概念翻译成英文 Amazon 搜索词，绝不能生成销量、"
            "搜索量、价格、竞争度或利润数字。"
        ),
        (
            f"品类：{keyword}\n"
            f"商品标题或补充信息：{context or '无'}\n"
            "拆成 2 至 6 个可独立搜索的英文方向。返回："
            '{"concept":"英文核心词","queries":['
            '{"key":"wireless","label_zh":"无线款",'
            '"keyword":"wireless pet water fountain"}]}'
        ),
        max_tokens=700,
        temperature=0.1,
    )
    parsed = _extract_json_object(raw)
    raw_queries = parsed.get("queries") if parsed else None
    if not isinstance(raw_queries, list):
        raise AmazonMarketQueryError(
            "暂时无法把该品类转换为 Amazon 英文搜索词，请直接输入英文品类"
        )
    queries: list[MarketQuery] = []
    seen: set[str] = set()
    for item in raw_queries:
        if not isinstance(item, dict):
            continue
        english = str(item.get("keyword") or "").strip()
        if not english or english in seen:
            continue
        if len(english) > 80 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 +-]*", english):
            continue
        seen.add(english)
        queries.append(
            MarketQuery(
                key=str(item.get("key") or f"query_{len(queries) + 1}")[:40],
                label_zh=str(item.get("label_zh") or english)[:60],
                keyword=english,
            )
        )
    if not queries:
        raise AmazonMarketQueryError(
            "暂时无法把该品类转换为 Amazon 英文搜索词，请直接输入英文品类"
        )
    return queries[:6]


_BLUEPRINTS: tuple[CategoryBlueprint, ...] = (
    CategoryBlueprint(
        key="pet_water_fountain",
        label_zh="宠物饮水机",
        base=MarketQuery("base", "宠物饮水机", "pet water fountain"),
        segments=(
            MarketQuery(
                "wireless",
                "无线易拆洗",
                "wireless pet water fountain",
            ),
            MarketQuery(
                "stainless",
                "不锈钢大容量",
                "stainless steel large capacity pet water fountain",
            ),
            MarketQuery(
                "uv",
                "UV 多宠",
                "UV pet water fountain",
            ),
            MarketQuery(
                "quiet",
                "静音易清洗",
                "quiet easy clean pet water fountain",
            ),
            MarketQuery(
                "cat",
                "猫用饮水机",
                "cat water fountain",
            ),
        ),
    ),
    CategoryBlueprint(
        key="bluetooth_earbuds",
        label_zh="蓝牙耳机",
        base=MarketQuery("base", "蓝牙耳机", "bluetooth earbuds"),
        segments=(
            MarketQuery("open_ear", "开放式", "open ear earbuds"),
            MarketQuery(
                "noise_cancelling",
                "降噪",
                "noise cancelling earbuds",
            ),
            MarketQuery(
                "sport",
                "运动防汗",
                "sports earbuds waterproof",
            ),
            MarketQuery(
                "long_battery",
                "长续航",
                "long battery life earbuds",
            ),
        ),
    ),
)


def _contains_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _pct(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator) * 100, 1)


def _percentile(values: list[float], fraction: float) -> float | None:
    """线性插值分位数，避免使用极值作为利润情景售价。"""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


class AmazonMarketDecisionService:
    """把 Provider 样本聚合成可解释的品类和细分方向决策。"""

    def __init__(
        self,
        provider: AmazonMarketProvider,
        *,
        query_planner: Callable[
            [str, str | None],
            Awaitable[list[MarketQuery]],
        ]
        | None = None,
        concurrency: int = 4,
    ):
        self.provider = provider
        self.query_planner = query_planner
        self._semaphore = asyncio.Semaphore(max(1, concurrency))

    @staticmethod
    def resolve_known_blueprint(keyword: str) -> CategoryBlueprint | None:
        """优先使用人工校验过的中英文映射。"""
        normalized = re.sub(r"\s+", "", str(keyword or "")).lower()
        aliases = {
            "宠物饮水机": "pet_water_fountain",
            "宠物自动饮水机": "pet_water_fountain",
            "自动饮水机": "pet_water_fountain",
            "猫饮水机": "pet_water_fountain",
            "猫用饮水机": "pet_water_fountain",
            "狗饮水机": "pet_water_fountain",
            "狗用饮水机": "pet_water_fountain",
            "petwaterfountain": "pet_water_fountain",
            "蓝牙耳机": "bluetooth_earbuds",
            "无线耳机": "bluetooth_earbuds",
            "bluetoothearbuds": "bluetooth_earbuds",
        }
        blueprint_key = aliases.get(normalized)
        if blueprint_key:
            return next(
                item for item in _BLUEPRINTS if item.key == blueprint_key
            )
        # 1688 标题通常包含“无线/静音/大容量”等修饰词，命中核心中文词即可。
        for alias, key in aliases.items():
            if _contains_chinese(alias) and alias in normalized:
                return next(
                    item for item in _BLUEPRINTS if item.key == key
                )
        for blueprint in _BLUEPRINTS:
            for query in (blueprint.base, *blueprint.segments):
                if query.keyword.lower() in normalized:
                    return blueprint
        return None

    async def _resolve_blueprint(
        self,
        keyword: str,
        *,
        context: str | None = None,
    ) -> CategoryBlueprint:
        known = self.resolve_known_blueprint(keyword)
        if known is not None:
            return known
        normalized = str(keyword or "").strip()
        if not normalized:
            raise AmazonMarketQueryError("缺少品类关键词")
        if not _contains_chinese(normalized):
            query = MarketQuery("base", normalized, normalized)
            return CategoryBlueprint(
                key="custom",
                label_zh=normalized,
                base=query,
                segments=(query,),
            )
        if self.query_planner is None:
            raise AmazonMarketQueryError(
                "暂时无法把中文品类转换为 Amazon 英文搜索词，"
                "请直接输入英文品类"
            )
        queries = await self.query_planner(normalized, context)
        if not queries:
            raise AmazonMarketQueryError(
                "无法生成 Amazon 英文搜索词，请补充商品标题或英文品类"
            )
        base = queries[0]
        return CategoryBlueprint(
            key="custom",
            label_zh=normalized,
            base=base,
            segments=tuple(queries),
        )

    async def _collect_query(self, query: MarketQuery) -> dict[str, Any]:
        async with self._semaphore:
            max_pages = int(
                getattr(self.provider, "default_max_pages", 2)
            )
            product_data = await self.provider.query_product_database(
                query.keyword,
                page_size=100,
                max_pages=max_pages,
            )
            raw_volume = await self.provider.historical_search_volume(
                query.keyword,
                days=35,
            )
        # 周度搜索量按 35 天汇总，统一折算为 30 天口径。
        monthly_volume = (
            int(round(raw_volume * 30 / 35))
            if raw_volume is not None and raw_volume > 0
            else None
        )
        return {
            "query": query,
            "products": product_data.items,
            "total_results": product_data.total_results,
            "monthly_search_volume": monthly_volume,
            "observed_at": product_data.observed_at,
            "pages_read": product_data.pages_read,
            "provider": product_data.provider,
        }

    @staticmethod
    def _aggregate(
        *,
        products: list[AmazonProductSample],
        total_results: int | None,
        monthly_search_volume: int | None,
        observed_at: datetime,
    ) -> dict[str, Any]:
        prices = [item.price for item in products if item.price is not None]
        units = [
            item.monthly_units
            for item in products
            if item.monthly_units is not None
        ]
        purchase_volumes = [
            item.purchase_volume_min
            for item in products
            if item.purchase_volume_min is not None
        ]
        reviews = [
            item.reviews for item in products if item.reviews is not None
        ]
        sellers = [
            item.sellers for item in products if item.sellers is not None
        ]
        offer_counts = [
            item.offer_count
            for item in products
            if item.offer_count is not None
        ]
        ratings = [
            item.rating for item in products if item.rating is not None
        ]
        lqs_values = [
            item.listing_quality_score
            for item in products
            if item.listing_quality_score is not None
        ]
        referral_rates = [
            item.referral_fee_rate
            for item in products
            if item.referral_fee_rate is not None
        ]
        fulfillment_fees = [
            item.fulfillment_fee_usd
            for item in products
            if item.fulfillment_fee_usd is not None
        ]
        dated_products = [
            item for item in products if item.date_first_available is not None
        ]
        now = datetime.now(timezone.utc)
        new_products = [
            item
            for item in dated_products
            if now - item.date_first_available <= timedelta(days=365)
        ]

        brand_units: dict[str, int] = {}
        for item in products:
            if not item.brand or item.monthly_units is None:
                continue
            brand_units[item.brand] = (
                brand_units.get(item.brand, 0) + item.monthly_units
            )
        top_brand_share = (
            _pct(max(brand_units.values()), sum(brand_units.values()))
            if brand_units
            else None
        )
        median_price = statistics.median(prices) if prices else None
        price_war_share = (
            _pct(
                sum(1 for price in prices if price < median_price * 0.8),
                len(prices),
            )
            if median_price
            else None
        )
        median_reviews = (
            statistics.median(reviews) if reviews else None
        )
        median_sellers = (
            statistics.median(sellers) if sellers else None
        )

        competition_level = None
        if median_reviews is not None or median_sellers is not None:
            score = 0
            if median_reviews is not None:
                score += (
                    2
                    if median_reviews >= 1000
                    else 1
                    if median_reviews >= 200
                    else 0
                )
            if median_sellers is not None:
                score += (
                    2
                    if median_sellers >= 8
                    else 1
                    if median_sellers >= 3
                    else 0
                )
            if top_brand_share is not None:
                score += (
                    1
                    if top_brand_share >= 65
                    else 0
                )
            competition_level = max(1, min(5, score))

        price_war_level = None
        if price_war_share is not None:
            price_war_level = min(
                5,
                1
                + int(price_war_share // 15),
            )

        new_product_share_pct = (
            _pct(len(new_products), len(dated_products))
            if dated_products
            else None
        )
        median_units = (
            int(round(statistics.median(units))) if units else None
        )
        median_purchase_volume = (
            int(round(statistics.median(purchase_volumes)))
            if purchase_volumes
            else None
        )
        purchase_volume_coverage = _pct(
            len(purchase_volumes),
            len(products),
        )
        demand_signal_type = (
            "third_party_monthly_units"
            if median_units is not None
            else "amazon_purchase_display"
            if median_purchase_volume is not None
            else None
        )

        metrics = {
            "marketplace": "us",
            "currency": "USD",
            "monthly_search_volume": monthly_search_volume,
            "active_listings": total_results,
            "sample_size": len(products),
            "avg_price_usd": round(statistics.mean(prices), 2) if prices else None,
            "median_price_usd": (
                round(median_price, 2) if median_price is not None else None
            ),
            "price_min_usd": round(min(prices), 2) if prices else None,
            "price_max_usd": round(max(prices), 2) if prices else None,
            "price_p25_usd": (
                round(_percentile(prices, 0.25), 2)
                if prices
                else None
            ),
            "price_p75_usd": (
                round(_percentile(prices, 0.75), 2)
                if prices
                else None
            ),
            "monthly_units": (
                median_units
            ),
            "median_monthly_units": (
                median_units
            ),
            "median_purchase_volume_min": median_purchase_volume,
            "purchase_volume_coverage_pct": purchase_volume_coverage,
            "purchase_volume_sample_count": len(purchase_volumes),
            "purchase_volume_is_lower_bound": any(
                item.purchase_volume_is_lower_bound
                for item in products
                if item.purchase_volume_min is not None
            ),
            "demand_signal_type": demand_signal_type,
            "median_reviews": (
                int(round(median_reviews))
                if median_reviews is not None
                else None
            ),
            "median_rating": (
                round(statistics.median(ratings), 2) if ratings else None
            ),
            "median_listing_quality_score": (
                round(statistics.median(lqs_values), 1)
                if lqs_values
                else None
            ),
            "median_sellers": (
                int(round(median_sellers))
                if median_sellers is not None
                else None
            ),
            "median_offers": (
                int(round(statistics.median(offer_counts)))
                if offer_counts
                else None
            ),
            "head_concentration": top_brand_share,
            "new_product_share_pct": new_product_share_pct,
            "competition_level": competition_level,
            "price_war_level": price_war_level,
            "price_war_share_pct": price_war_share,
            "referral_fee_rate": (
                round(statistics.median(referral_rates), 4)
                if referral_rates
                else None
            ),
            "fulfillment_fee_usd": (
                round(statistics.median(fulfillment_fees), 2)
                if fulfillment_fees
                else None
            ),
            "data_as_of": observed_at.isoformat(),
            "source_provider": (
                products[0].source_provider if products else PROVIDER_NAME
            ),
        }
        required = [
            "active_listings",
            "sample_size",
            "avg_price_usd",
            "median_reviews",
            "head_concentration",
            "new_product_share_pct",
        ]
        if metrics["demand_signal_type"] is None:
            missing_demand = True
        else:
            missing_demand = False
        if metrics["median_sellers"] is None and metrics["median_offers"] is None:
            offers_missing = True
        else:
            offers_missing = False
        missing = [
            key
            for key in required
            if metrics.get(key) is None
            or (key == "sample_size" and metrics.get(key, 0) < 10)
        ]
        if missing_demand:
            missing.append("demand_signal")
        if offers_missing:
            missing.append("seller_or_offer_count")
        if metrics.get("monthly_search_volume") is None:
            missing.append("monthly_search_volume")
        if metrics.get("monthly_units") is None:
            missing.append("monthly_units")
        completeness = round(
            (len(required) + 2 - len(missing)) / (len(required) + 2) * 100
        )
        metrics["data_completeness_pct"] = completeness
        metrics["missing_fields"] = missing
        return metrics

    @staticmethod
    def _score(metrics: dict[str, Any]) -> float:
        units = metrics.get("monthly_units")
        purchase_volume = metrics.get("median_purchase_volume_min")
        reviews = metrics.get("median_reviews")
        concentration = metrics.get("head_concentration")
        new_share = metrics.get("new_product_share_pct")
        score = 0.0
        demand = units if units is not None else purchase_volume
        if demand is not None:
            score += 3 if demand >= 1000 else 2 if demand >= 200 else 1 if demand >= 50 else 0
        if reviews is not None:
            score += 3 if reviews <= 50 else 2 if reviews <= 200 else 1 if reviews <= 1000 else 0
        if concentration is not None:
            score += 2 if concentration <= 40 else 1 if concentration <= 65 else 0
        if new_share is not None:
            score += 2 if new_share >= 25 else 1 if new_share >= 10 else 0
        return round(score, 1)

    @staticmethod
    def _decision_status(metrics: dict[str, Any], score: float) -> str:
        demand_signal = metrics.get("demand_signal_type")
        if demand_signal is None and metrics.get("monthly_units") is not None:
            demand_signal = "third_party_monthly_units"
        if (
            metrics.get("data_completeness_pct", 0) < 50
            or metrics.get("sample_size", 0) < 10
            or demand_signal is None
            or metrics.get("avg_price_usd") is None
        ):
            return "数据不足"
        if score >= 7:
            return "有机会"
        if score >= 5:
            return "有机会但需验证"
        return "谨慎"

    @staticmethod
    def _risk_flags(
        query: MarketQuery,
        metrics: dict[str, Any],
    ) -> list[str]:
        risks: list[str] = []
        keyword = query.keyword.lower()
        if "pet water fountain" in keyword or "water fountain" in keyword:
            risks.append("涉水电气安全与认证")
            risks.append("包装体积和运输破损")
        if metrics.get("median_reviews") is not None and metrics["median_reviews"] >= 300:
            risks.append("评论门槛较高")
        if metrics.get("head_concentration") is not None and metrics["head_concentration"] >= 65:
            risks.append("头部品牌集中")
        if metrics.get("price_war_level") is not None and metrics["price_war_level"] >= 4:
            risks.append("低价竞争明显")
        return risks[:4]

    @staticmethod
    def _evidence(
        metrics: dict[str, Any],
        *,
        keyword: str,
        observed_at: datetime,
    ) -> list[dict[str, Any]]:
        definitions = (
            (
                "monthly_search_volume",
                "月搜索量",
                "third_party_estimate",
                "Jungle Scout 周度精确搜索量估算按 30/35 折算",
                "medium",
            ),
            (
                "monthly_units",
                "样本月销中位数",
                "third_party_estimate",
                "Jungle Scout 30 天销量估算的样本中位数",
                "medium",
            ),
            (
                "median_purchase_volume_min",
                "Amazon 前台购买量下限",
                "observed_display_range",
                "Amazon 前台 bought in past month 展示文本的可解析下限中位数",
                "medium",
            ),
            (
                "active_listings",
                "在售 Listing",
                "third_party_estimate",
                "Product Database 匹配结果总数",
                "medium",
            ),
            (
                "median_reviews",
                "评论数中位数",
                "observed",
                "当前商品样本的评论数中位数",
                "high",
            ),
            (
                "head_concentration",
                "头部品牌集中度",
                "derived",
                "最高品牌 30 天销量 ÷ 有销量样本总销量",
                "medium",
            ),
            (
                "new_product_share_pct",
                "新品占比",
                "derived",
                "首次可售日期在 365 天内的样本占比",
                "medium",
            ),
        )
        result: list[dict[str, Any]] = []
        provider = str(metrics.get("source_provider") or PROVIDER_NAME)
        for key, label, evidence_type, basis, confidence in definitions:
            value = metrics.get(key)
            if value is None:
                continue
            if provider == JUSTONE_PROVIDER_NAME and key == "active_listings":
                evidence_type = "observed"
            result.append(
                {
                    "metric": key,
                    "label": label,
                    "value": value,
                    "type": evidence_type,
                    "provider": provider,
                    "observed_at": observed_at.isoformat(),
                    "basis": f"{basis}；搜索词：{keyword}",
                    "confidence": confidence,
                }
            )
        return result

    @staticmethod
    def _sample_product_cards(
        products: list[AmazonProductSample],
        metrics: dict[str, Any],
        risks: list[str],
    ) -> list[dict[str, Any]]:
        ordered = sorted(
            products,
            key=lambda item: (
                item.monthly_units is not None,
                item.monthly_units or 0,
                item.reviews or 0,
            ),
            reverse=True,
        )
        cards = []
        for item in ordered[:5]:
            cards.append(
                {
                    "name": item.title,
                    "asin": item.asin,
                    "url": item.url,
                    "suggested_price_usd": item.price,
                    "observed_price_usd": item.price,
                    "monthly_units": item.monthly_units,
                    "purchase_volume_raw": item.purchase_volume_raw,
                    "purchase_volume_min": item.purchase_volume_min,
                    "purchase_volume_period": item.purchase_volume_period,
                    "purchase_volume_is_lower_bound": item.purchase_volume_is_lower_bound,
                    "reviews": item.reviews,
                    "rating": item.rating,
                    "bsr": item.bsr,
                    "offer_count": item.offer_count,
                    "availability": item.availability,
                    "is_best_seller": item.is_best_seller,
                    "is_amazon_choice": item.is_amazon_choice,
                    "review_titles": item.review_titles[:3],
                    "cost_cny": None,
                    "net_profit_usd": None,
                    "net_margin": None,
                    "competition": metrics.get("competition_level"),
                    "risk_tips": risks,
                    "data_type": "third_party_estimate",
                }
            )
        return cards

    async def analyze(
        self,
        keyword: str,
        *,
        context: str | None = None,
        include_products: bool = False,
    ) -> dict[str, Any]:
        """执行品类取证并返回 App 可直接消费的结构化结果。"""
        blueprint = await self._resolve_blueprint(keyword, context=context)
        query_list = [blueprint.base, *blueprint.segments]
        collected = await asyncio.gather(
            *(self._collect_query(query) for query in query_list)
        )
        enricher = getattr(self.provider, "enrich_products", None)
        if callable(enricher):
            unique_products: dict[str, AmazonProductSample] = {}
            for result in collected:
                for product in result["products"]:
                    unique_products.setdefault(product.asin, product)
            enriched = await enricher(
                list(unique_products.values()),
                detail_limit=6,
                review_limit=3,
            )
            enriched_by_asin = {item.asin: item for item in enriched}
            for result in collected:
                result["products"] = [
                    enriched_by_asin.get(product.asin, product)
                    for product in result["products"]
                ]
        base_result = collected[0]
        base_metrics = self._aggregate(
            products=base_result["products"],
            total_results=base_result["total_results"],
            monthly_search_volume=base_result["monthly_search_volume"],
            observed_at=base_result["observed_at"],
        )

        segments: list[dict[str, Any]] = []
        for result in collected[1:]:
            query = result["query"]
            metrics = self._aggregate(
                products=result["products"],
                total_results=result["total_results"],
                monthly_search_volume=result["monthly_search_volume"],
                observed_at=result["observed_at"],
            )
            score = self._score(metrics)
            status = self._decision_status(metrics, score)
            risks = list(
                dict.fromkeys(
                    [
                        *_review_pain_points(result["products"]),
                        *self._risk_flags(query, metrics),
                    ]
                )
            )[:5]
            segments.append(
                {
                    "key": query.key,
                    "label_zh": query.label_zh,
                    "keyword": query.keyword,
                    "status": status,
                    "score": score,
                    "metrics": metrics,
                    "sample_products": self._sample_product_cards(
                        result["products"],
                        metrics,
                        risks,
                    ),
                    "risk_flags": risks,
                    "evidence": self._evidence(
                        metrics,
                        keyword=query.keyword,
                        observed_at=result["observed_at"],
                    ),
                }
            )

        segments.sort(
            key=lambda item: (
                item["status"] != "数据不足",
                item["score"],
                item["metrics"].get("monthly_units") or 0,
            ),
            reverse=True,
        )
        top = segments[0]
        recommendation = {
            "top_pick": top["label_zh"],
            "verdict": top["status"],
            "score": top["score"],
            "reasons": self._reasons(top),
            "risks": top["risk_flags"] or ["仍需验证真实供应链和合规要求"],
            "entry_advice": (
                "先用 1 至 2 个差异化 SKU 小批量测试，"
                "补齐采购、物流和认证成本后再扩大采购。"
            ),
        }
        products = []
        if include_products:
            products = [
                product
                for segment in segments
                for product in segment["sample_products"]
            ][:8]

        provider_name = str(
            base_result.get("provider")
            or base_metrics.get("source_provider")
            or PROVIDER_NAME
        )
        is_justone = provider_name == JUSTONE_PROVIDER_NAME
        data_quality = {
            "provider": provider_name,
            "marketplace": "us",
            "currency": "USD",
            "sample_size": base_metrics["sample_size"],
            "completeness_pct": base_metrics["data_completeness_pct"],
            "missing_fields": list(base_metrics.get("missing_fields") or []),
            "observed_at": base_result["observed_at"].isoformat(),
            "limitations": (
                [
                    "商品价格、评论和 BSR 来自 Amazon 前台实时采集",
                    "购买量为前台展示范围，可能为空，不是精确月销",
                    "未提供关键词搜索量；不能把搜索结果数当成关键词搜索量",
                ]
                if is_justone
                else [
                    "销量和搜索量为 Jungle Scout 第三方估算，不是 Amazon 官方事实",
                    "汇率、采购价、运费和认证费用未包含在市场数据中",
                ]
            ),
        }
        return {
            "keyword": str(keyword).strip(),
            "market": base_metrics,
            "segments": segments,
            "products": products,
            "recommendation": recommendation,
            "data_quality": data_quality,
            "evidence": self._evidence(
                base_metrics,
                keyword=blueprint.base.keyword,
                observed_at=base_result["observed_at"],
            ),
            "query_plan": [
                {
                    "key": query.key,
                    "label_zh": query.label_zh,
                    "keyword": query.keyword,
                }
                for query in query_list
            ],
            "data_sources": [
                {
                    "provider": provider_name,
                    "marketplace": "us",
                    "observed_at": base_result["observed_at"].isoformat(),
                    "data_type": (
                        "observed"
                        if is_justone
                        else "third_party_estimate"
                    ),
                }
            ],
        }

    async def analyze_category(self, keyword: str) -> dict[str, Any]:
        """品类分析入口，默认不把样本商品当作利润候选。"""
        return await self.analyze(keyword, include_products=False)

    @staticmethod
    def _reasons(segment: dict[str, Any]) -> list[str]:
        metrics = segment["metrics"]
        reasons: list[str] = []
        if metrics.get("monthly_units") is not None:
            reasons.append(
                f"样本月销中位数约 {metrics['monthly_units']} 件"
            )
        elif metrics.get("median_purchase_volume_min") is not None:
            coverage = metrics.get("purchase_volume_coverage_pct") or 0
            reasons.append(
                f"Amazon 前台购买量下限中位数约 "
                f"{metrics['median_purchase_volume_min']} 件，"
                f"覆盖 {coverage:.1f}% 样本"
            )
        if metrics.get("median_price_usd") is not None:
            reasons.append(
                f"售价中位数约 US${metrics['median_price_usd']:.2f}"
            )
        if metrics.get("median_reviews") is not None:
            reasons.append(
                f"评论数中位数约 {metrics['median_reviews']} 条"
            )
        if metrics.get("head_concentration") is not None:
            reasons.append(
                f"头部品牌销量占比约 {metrics['head_concentration']:.1f}%"
            )
        return reasons[:4]

    async def analyze_product_link_facts(
        self,
        *,
        title: str,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        """先用标题匹配细分词，再复用相同取证链路。"""
        seed = str(keyword or title or "").strip()
        return await self.analyze(seed, context=title, include_products=False)


def build_runtime_amazon_market_service(
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AmazonMarketDecisionService:
    """从管理员 Provider 配置构建生产实例。"""
    from app.services import provider_config

    justone_token = provider_config.get("justone", "token")
    jungle_key = provider_config.get("jungle_scout", "api_key")
    if justone_token:
        provider: AmazonMarketProvider = JustOneAmazonProvider(
            token=justone_token,
            marketplace=SUPPORTED_MARKETPLACE,
            transport=transport,
        )
    elif jungle_key:
        provider = JungleScoutAmazonProvider(
            key_name=provider_config.get("jungle_scout", "key_name"),
            api_key=jungle_key,
            marketplace=(
                provider_config.get("jungle_scout", "marketplace")
                or SUPPORTED_MARKETPLACE
            ),
            transport=transport,
        )
    else:
        raise AmazonMarketDataNotConfigured(
            "Amazon 市场数据源未配置，请在管理员服务商设置中配置 "
            "JustOneAPI Token，或使用 Jungle Scout 作为增强数据源"
        )
    planner = (
        plan_queries_with_deepseek
        if provider_config.get("deepseek", "api_key")
        else None
    )
    return AmazonMarketDecisionService(provider, query_planner=planner)
