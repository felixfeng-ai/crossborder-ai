"""1688 货源发现与供应商候选归一化。

Amazon 选品结果只提供市场需求线索。本模块负责把 Amazon 候选商品转成
1688 货源搜索，归一化价格、MOQ、销量、店铺和工厂信号；不负责询价、
下单或把相似商品宣称为同款。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx


JUSTONE_SEARCH_URL = (
    "https://api.justoneapi.com/api/1688/search-item-list/v2"
)
JUSTONE_IMAGE_SEARCH_URL = (
    "https://api.justoneapi.com/api/1688/search-item-by-image/v1"
)
ONEBOUND_SEARCH_URL = "https://api-gw.onebound.cn/1688/item_search"


class SourceDiscoveryError(RuntimeError):
    """可安全展示给卖家的 1688 货源查询失败。"""


class SourceDiscoveryInputError(SourceDiscoveryError):
    """关键词或图片参数无效。"""


async def search_1688_sources(
    keyword: str,
    *,
    image_url: str | None = None,
    justone_token: str = "",
    onebound_api_key: str = "",
    onebound_api_secret: str = "",
    limit: int = 10,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """搜索 1688 货源，优先图片搜索，再关键词和 Onebound 降级。"""

    clean_keyword = str(keyword or "").strip()
    if not clean_keyword:
        raise SourceDiscoveryInputError("缺少 1688 货源搜索关键词")
    clean_image_url = str(image_url or "").strip()
    if clean_image_url and not clean_image_url.startswith(("https://", "http://")):
        raise SourceDiscoveryInputError("商品图片地址无效")

    token = str(justone_token or "").strip()
    onebound_key = str(onebound_api_key or "").strip()
    onebound_secret = str(onebound_api_secret or "").strip()
    if not any((token, onebound_key and onebound_secret)):
        raise SourceDiscoveryError("1688 货源搜索服务尚未配置")

    page_size = max(1, min(int(limit or 10), 20))
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=60.0)
    image_fallback_reason: str | None = None
    provider_fallback_reason: str | None = None
    try:
        if token and clean_image_url:
            try:
                payload = await _justone_search(
                    http,
                    url=JUSTONE_IMAGE_SEARCH_URL,
                    token=token,
                    page_size=page_size,
                    params={"imgUrl": clean_image_url},
                )
                items = _normalize_justone_items(payload)
                if items:
                    return _build_result(
                        keyword=clean_keyword,
                        provider="justone",
                        search_mode="image",
                        items=items,
                        image_search_used=True,
                        image_fallback_reason=None,
                        provider_fallback_reason=None,
                        total_count=_integer(
                            (payload.get("data") or {}).get("total_count")
                        ),
                    )
                image_fallback_reason = "图片搜索未返回货源，已改用关键词搜索"
            except SourceDiscoveryError:
                image_fallback_reason = (
                    "图片搜索暂时不可用，已改用关键词搜索"
                )

        justone_error: SourceDiscoveryError | None = None
        if token:
            try:
                payload = await _justone_search(
                    http,
                    url=JUSTONE_SEARCH_URL,
                    token=token,
                    page_size=page_size,
                    params={"keyword": clean_keyword, "sort": "sales"},
                )
                items = _normalize_justone_items(payload)
                return _build_result(
                    keyword=clean_keyword,
                    provider="justone",
                    search_mode="text",
                    items=items,
                    image_search_used=False,
                    image_fallback_reason=image_fallback_reason,
                    provider_fallback_reason=None,
                    total_count=_integer(
                        (payload.get("data") or {}).get("total_count")
                    ),
                )
            except SourceDiscoveryError as exc:
                justone_error = exc
                provider_fallback_reason = (
                    "Just One 搜索暂时不可用，已改用 Onebound"
                )

        if onebound_key and onebound_secret:
            items = await _onebound_search(
                http,
                keyword=clean_keyword,
                api_key=onebound_key,
                api_secret=onebound_secret,
                page_size=page_size,
            )
            return _build_result(
                keyword=clean_keyword,
                provider="onebound",
                search_mode="text",
                items=items,
                image_search_used=False,
                image_fallback_reason=image_fallback_reason,
                provider_fallback_reason=provider_fallback_reason,
                total_count=None,
            )

        if justone_error is not None:
            raise SourceDiscoveryError("1688 货源搜索暂时不可用") from None
        raise SourceDiscoveryError("1688 货源搜索服务尚未配置")
    finally:
        if owns_client:
            await http.aclose()


async def _justone_search(
    client: httpx.AsyncClient,
    *,
    url: str,
    token: str,
    page_size: int,
    params: dict[str, Any],
) -> dict[str, Any]:
    """执行 Just One 搜索并只保留安全业务码。"""

    request_params = {
        "token": token,
        "page": 1,
        "pageSize": page_size,
        **params,
    }
    try:
        response = await client.get(url, params=request_params)
    except httpx.HTTPError:
        raise SourceDiscoveryError("1688 货源搜索请求失败") from None
    if response.status_code >= 400:
        raise SourceDiscoveryError("1688 货源搜索暂时不可用")
    try:
        payload = response.json()
    except ValueError:
        raise SourceDiscoveryError("1688 货源搜索响应格式异常") from None
    if not isinstance(payload, dict):
        raise SourceDiscoveryError("1688 货源搜索响应格式异常")
    code = _integer(payload.get("code"))
    if code not in (None, 0):
        raise SourceDiscoveryError(
            _justone_code_message(code)
        )
    return payload


async def _onebound_search(
    client: httpx.AsyncClient,
    *,
    keyword: str,
    api_key: str,
    api_secret: str,
    page_size: int,
) -> list[dict[str, Any]]:
    """Onebound 不支持图片搜索，作为关键词搜索降级通道。"""

    try:
        response = await client.get(
            ONEBOUND_SEARCH_URL,
            params={
                "key": api_key,
                "secret": api_secret,
                "q": keyword,
                "page": 1,
                "page_size": page_size,
                "sort": "_sale",
            },
        )
    except httpx.HTTPError:
        raise SourceDiscoveryError("Onebound 货源搜索请求失败") from None
    if response.status_code >= 400:
        raise SourceDiscoveryError("Onebound 货源搜索暂时不可用")
    try:
        payload = response.json()
    except ValueError:
        raise SourceDiscoveryError("Onebound 货源搜索响应格式异常") from None
    if not isinstance(payload, dict):
        raise SourceDiscoveryError("Onebound 货源搜索响应格式异常")
    items_container = payload.get("items")
    if isinstance(items_container, dict):
        raw_items = items_container.get("item")
    else:
        raw_items = items_container or payload.get("item")
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    if not isinstance(raw_items, list):
        raw_items = []
    return [
        normalized
        for raw in raw_items
        if (normalized := _normalize_onebound_item(raw)) is not None
    ][:page_size]


def _normalize_justone_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        return []
    return [
        normalized
        for raw in raw_items
        if (normalized := _normalize_justone_item(raw)) is not None
    ]


def _normalize_justone_item(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    item_id = str(raw.get("item_id") or "").strip()
    title = str(raw.get("title") or "").strip()
    if not item_id or not title:
        return None
    shop = raw.get("shop_info")
    if not isinstance(shop, dict):
        shop = {}
    delivery = raw.get("delivery_info")
    if not isinstance(delivery, dict):
        delivery = {}
    sale = raw.get("sale_info")
    if not isinstance(sale, dict):
        sale = {}
    price_info = raw.get("price_info")
    if not isinstance(price_info, dict):
        price_info = {}
    score_info = shop.get("score_info")
    if not isinstance(score_info, dict):
        score_info = {}
    price = str(
        raw.get("price")
        or price_info.get("sale_price")
        or ""
    ).strip()
    price_min, price_max = _price_range(price)
    location = _join_values(
        delivery.get("area_from") or shop.get("location")
    )
    fallback_url = f"https://detail.1688.com/offer/{item_id}.html"
    return {
        "item_id": item_id,
        "title": title,
        "url": _safe_http_url(raw.get("product_url")) or fallback_url,
        "image_url": _safe_http_url(raw.get("img")),
        "price": price or None,
        "price_min_cny": price_min,
        "price_max_cny": price_max,
        "moq": _integer(raw.get("moq") or raw.get("quantity_begin")),
        "sale_quantity": _quantity(
            sale.get("sale_quantity_int") or sale.get("sale_quantity")
        ),
        "orders_count": _integer(sale.get("orders_count")),
        "shop_name": str(shop.get("company_name") or "").strip() or None,
        "shop_url": str(shop.get("shop_url") or "").strip() or None,
        "shop_years": _integer(shop.get("shop_years")),
        "location": location or None,
        "business_type": str(shop.get("biz_type") or "").strip() or None,
        "is_factory": bool(shop.get("is_factory")),
        "is_super_factory": bool(shop.get("is_super_factory")),
        "factory_inspection": bool(shop.get("factory_inspection")),
        "service_tags": _string_list(shop.get("service_tags")),
        "product_tags": _string_list(raw.get("tags")),
        "composite_score": str(
            score_info.get("composite_new_score")
            or raw.get("goods_score")
            or ""
        ).strip()
        or None,
        "rating_star": str(raw.get("rating_star") or "").strip() or None,
        "repurchase_rate": str(
            raw.get("item_repurchase_rate") or ""
        ).strip()
        or None,
        "source_provider": "justone",
    }


def _normalize_onebound_item(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    item_id = str(
        raw.get("num_iid") or raw.get("item_id") or raw.get("offerId") or ""
    ).strip()
    title = str(raw.get("title") or raw.get("offerTitle") or "").strip()
    if not item_id or not title:
        return None
    price = str(raw.get("price") or "").strip()
    price_min, price_max = _price_range(price)
    fallback_url = f"https://detail.1688.com/offer/{item_id}.html"
    return {
        "item_id": item_id,
        "title": title,
        "url": _safe_http_url(raw.get("detail_url")) or fallback_url,
        "image_url": _safe_http_url(raw.get("pic_url") or raw.get("picUrl")),
        "price": price or None,
        "price_min_cny": price_min,
        "price_max_cny": price_max,
        "moq": _integer(
            raw.get("min_num") or raw.get("moq") or raw.get("quantity_begin")
        ),
        "sale_quantity": _quantity(
            raw.get("sales") or raw.get("sale_quantity")
        ),
        "orders_count": None,
        "shop_name": str(
            raw.get("seller_nick") or raw.get("company_name") or ""
        ).strip()
        or None,
        "shop_url": str(raw.get("shop_url") or "").strip() or None,
        "shop_years": None,
        "location": str(
            raw.get("location") or raw.get("area") or ""
        ).strip()
        or None,
        "business_type": None,
        "is_factory": bool(raw.get("is_factory")),
        "is_super_factory": False,
        "factory_inspection": False,
        "service_tags": _string_list(raw.get("service_tags")),
        "product_tags": [],
        "composite_score": None,
        "rating_star": None,
        "repurchase_rate": None,
        "source_provider": "onebound",
    }


def _build_result(
    *,
    keyword: str,
    provider: str,
    search_mode: str,
    items: list[dict[str, Any]],
    image_search_used: bool,
    image_fallback_reason: str | None,
    provider_fallback_reason: str | None,
    total_count: int | None,
) -> dict[str, Any]:
    limitations = [
        "采购价、MOQ、库存和销量为 1688 展示快照，下单前需向供应商确认",
        "相似图片或相似标题不代表同款，材质、尺寸和批次可能不同",
    ]
    if image_search_used:
        limitations.insert(0, "图片搜索返回相似货源，不保证与 Amazon 商品完全相同")
    if provider == "onebound":
        limitations.append("Onebound 降级结果字段可能少于 Just One，需进入详情复核")
    return {
        "keyword": keyword,
        "provider": provider,
        "search_mode": search_mode,
        "image_search_used": image_search_used,
        "image_fallback_reason": image_fallback_reason,
        "provider_fallback_reason": provider_fallback_reason,
        "total_count": total_count,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
        "limitations": limitations,
    }


def _price_range(value: str) -> tuple[float | None, float | None]:
    numbers = [
        float(match)
        for match in re.findall(r"\d+(?:\.\d+)?", str(value or ""))
    ]
    if not numbers:
        return None, None
    return min(numbers), max(numbers)


def _number(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "").replace("¥", "").strip())
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _quantity(value: Any) -> int | None:
    """兼容接口返回的“1.2万”“2万+”等中文销量文本。"""

    number = _number(value)
    if number is not None:
        return int(number)
    text = str(value or "").strip().replace(",", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(万|w)\+?", text, re.IGNORECASE)
    if match:
        return int(float(match.group(1)) * 10000)
    return None


def _safe_http_url(value: Any) -> str | None:
    """只允许可点击的 HTTP(S) 地址，防止第三方响应注入脚本协议。"""

    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = urlsplit(text)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return text


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _join_values(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def _justone_code_message(code: int) -> str:
    if code in {100, 600}:
        return "1688 货源搜索凭据无效或权限不足"
    if code in {302, 602}:
        return "1688 货源搜索已达到限流或额度上限"
    if code in {303, 601}:
        return "1688 货源搜索账户余额或额度不足"
    if code == 400:
        return "1688 货源搜索参数无效"
    return "1688 货源搜索暂时不可用"
