"""VeyaShip - 1688 商品爬虫（CAP-01：健壮抓取 + 稳定错误分类 + 降级直抓）

数据流向：
  卖家粘贴 1688 链接 → products 路由（平台 Key 就绪检查）
  → scrape_1688（Just One → Onebound → 失败再降级直抓 HTML）
  → 统一清洗字段 → 返回 data_source 标注 + 结构化数据 → 落库

为什么做这套「错误分类」而不直接抛底层异常？
- 使用方是非技术跨境卖家：raw 异常（httpx.TimeoutException / HTTPStatusError…）
  会让前端拿到 500 或英文/技术栈信息，卖家无法决定下一步。
- 统一成「稳定错误码 + 中文可读 message」，前端按 code 给引导、运维按 code 统计。
- 所有业务错误都以 4xx 暴露给卖家（错误在卖家这一侧，不是服务器崩溃）。

兼容约束：
- ScrapeError 继承 RuntimeError → 旧 `except RuntimeError` 调用方不破。
- InvalidUrlError 多重继承 ValueError + ScrapeError → 既有安全测试
  （`pytest.raises(ValueError)`）不回归。
- 成功返回固定含 url/title/main_image_url/price/sales_count/shop_name，
  radar / Agent 直接调用 scrape_1688 不破。
"""

import ipaddress
import re
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from app.core.config import settings

# ════════════════════════════════════════════════════════════════
# 稳定错误码 + 中文可读信息（CAP-01 / C2）
# ════════════════════════════════════════════════════════════════


class ScrapeError(RuntimeError):
    """1688 抓取业务错误基类。

    Attributes:
        code: 稳定错误码（前端映射提示 / 运维统计），见各子类。
        message: 面向非技术卖家的中文可读提示。
        http_status: 建议路由返回的 HTTP 状态（本模块业务错误统一 < 500）。
    """

    code: str = "scrape_error"
    http_status: int = 400

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        http_status: int | None = None,
    ):
        super().__init__(message)
        self._message = message
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status

    @property
    def message(self) -> str:
        """中文可读提示。

        InvalidUrlError 多重继承后 __init__ 解析到 ValueError（更靠前），
        不会调用本类 __init__ 设置 _message → 从 args[0] 兜底。
        """
        msg = getattr(self, "_message", None)
        if msg is None and self.args:
            msg = str(self.args[0])
        return msg or self.code

    def __str__(self) -> str:
        # 保留旧 `str(e)` 契约：直接返回可读中文 message，而非异常元组
        return self.message


class InvalidUrlError(ValueError, ScrapeError):
    """链接无效：不是 1688 商品链接 / 无 offer ID / SSRF 类输入。

    同时继承 ValueError：既有代码/测试用 ``except ValueError`` 捕获仍兼容。
    """

    code = "invalid_url"
    http_status = 400


class ProductNotFoundError(ScrapeError):
    """商品不存在 / 已下架（数据源明确返回，无需再降级重试）。"""

    code = "product_not_found"
    http_status = 404


class ParseError(ScrapeError):
    """页面/接口能打开，但拿不到有效商品信息（标题为空、价格显式为 0 等）。"""

    code = "parse_error"
    http_status = 400


class AntiBotError(ScrapeError):
    """直抓被 1688 风控拦截（验证码 / x5sec / 访问过于频繁 / 超短页面）。"""

    code = "anti_bot"
    http_status = 400


class ScrapeTimeoutError(ScrapeError):
    """请求超时（Onebound 或直抓站点响应超时）。"""

    code = "timeout"
    http_status = 400


class ServiceUnavailableError(ScrapeError):
    """数据服务暂时不可用（Onebound 服务端错误 / Key 无效 / 兜底失败）。"""

    code = "service_unavailable"
    http_status = 400


# 常用提示文案集中定义，便于多入口复用一致
SERVICE_NOT_CONFIGURED_MSG = "数据抓取服务暂未开通，请联系平台客服开通后再试"


async def scrape_1688(
    url: str,
    api_key: str = "",
    api_secret: str = "",
    justone_token: str = "",
) -> dict[str, Any]:
    """抓取 1688 商品。

    数据源优先级：Just One API -> Onebound -> 直抓 HTML。

    Args:
        url: 1688 商品详情页 URL。
        api_key: Onebound API Key（平台管理员在设置页配置，存于 SystemConfig）。
        api_secret: Onebound API Secret。
        justone_token: Just One API Token。

    Returns:
        dict: url / data_source(justone|onebound|direct) / title / main_image_url /
        price / sales_count / shop_name。缺失字段为 None（字段兜底，不整单失败）。

    Raises:
        InvalidUrlError: 链接不是 1688 商品链接 / 无法识别商品 ID。
        ProductNotFoundError: 商品不存在或已下架。
        ParseError: 信息解析异常（标题空 / 价格显式异常）。
        AntiBotError / ScrapeTimeoutError / ServiceUnavailableError: 抓取被拦 / 超时 / 服务不可用。
    """
    # 环境变量只作为数据库配置缺失时的兜底。
    if not justone_token and settings.JUSTONE_API_TOKEN:
        justone_token = settings.JUSTONE_API_TOKEN
    if not api_key and settings.ONEBOUND_API_KEY:
        api_key = settings.ONEBOUND_API_KEY
        api_secret = settings.ONEBOUND_API_SECRET or api_secret

    # ── 1. 校验链接（防 SSRF） + 识别商品 ID ──────────────────
    _validate_1688_url(url)
    offer_id = _extract_offer_id(url)
    if not offer_id:
        raise InvalidUrlError(
            "链接里没有识别到商品 ID，请粘贴完整的 1688 商品链接"
            "（示例：https://detail.1688.com/offer/123456789.html）"
        )

    justone_err: ScrapeError | None = None
    onebound_err: ScrapeError | None = None
    raw: Optional[dict] = None
    source = ""

    # ── 2. 方案一：Just One API（最高优先级）──────────────────
    if justone_token:
        try:
            raw = await _fetch_justone(offer_id, justone_token)
            source = "justone"
        except ProductNotFoundError:
            # 明确不存在时停止降级，避免继续消耗其他数据源额度。
            raise
        except ScrapeError as e:
            justone_err = e

    # ── 3. 方案二：Onebound API（Just One 未配置或失败时）──────
    if raw is None and api_key:
        try:
            raw = await _fetch_onebound(offer_id, api_key, api_secret)
            source = "onebound"
        except ProductNotFoundError:
            # 服务商明确「不存在/已下架」→ 直接结束，再降级直抓没有意义
            raise
        except ScrapeError as e:
            # 超时 / 服务异常等暂时性失败 → 记为一次失败，继续尝试直抓
            onebound_err = e

    # ── 4. 方案三：直抓 HTML（两个数据 API 均不可用时）────────
    if raw is None:
        try:
            raw = await _direct_fetch(url)
            source = "direct"
        except ProductNotFoundError:
            raise
        except ScrapeError as e:
            # 所有数据源失败时，优先暴露最高优先级数据源的错误。
            if justone_err is not None:
                raise justone_err from e
            if onebound_err is not None:
                raise onebound_err from e
            raise

    # 理论上 _fetch_onebound/_direct_fetch 不会返回 None 且不抛错；兜底防御
    if raw is None:
        if justone_err is not None:
            raise justone_err
        if onebound_err is not None:
            raise onebound_err
        raise ServiceUnavailableError("获取商品信息失败，请稍后再试")

    # ── 5. 统一清洗 + 字段兜底 ───────────────────────────────
    product = (
        _normalize_justone_product(raw)
        if source == "justone"
        else _normalize_product(raw, source=source)
    )
    return {"url": url, "data_source": source, **product}


def _validate_1688_url(url: str) -> None:
    """校验 URL 必须是 1688.com 的商品链接，阻止 SSRF。

    攻击面：用户/Agent 传入任意 URL，后端会用 httpx / curl_cffi 直接抓取。
    之前只用 ``"1688.com" in url`` 子串判断，可被 ``http://evil.com/1688.com``
    或 ``http://127.0.0.1/...`` 绕过，变成内网探测（SSRF）。
    现在要求：
    - scheme 只能是 http/https
    - 主机名必须是 ``1688.com`` 或 ``*.1688.com`` 子域名（detail/m/www…）
    - 拒绝 IP 直连（私网/环回/保留地址，如 127.0.0.1、169.254.169.254 云元数据）

    Raises:
        InvalidUrlError（ScrapeError + ValueError 双继承）
    """
    _bad = lambda: InvalidUrlError("仅支持 1688.com 的商品链接")
    try:
        parsed = urlparse(url)
    except ValueError:
        raise _bad()

    if parsed.scheme not in ("http", "https"):
        raise _bad()

    # hostname 自动剥离端口与 userinfo（http://1688.com@127.0.0.1 → 127.0.0.1）
    host = (parsed.hostname or "").lower()
    if not host:
        raise _bad()

    # 域名必须精确匹配 1688.com 或其子域名，封死 evil.com/1688.com 这类伪装
    if host != "1688.com" and not host.endswith(".1688.com"):
        raise _bad()

    # IP 直连兜底：1688 商品链接不会用 IP，一律拒绝（含私网/环回）
    if all(ch in "0123456789." for ch in host):
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            raise _bad()
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise _bad()


def _extract_offer_id(url: str) -> str | None:
    """从 1688 URL 中提取商品 ID

    支持的 URL 格式：
    - https://detail.1688.com/offer/123456789.html
    - https://detail.1688.com/offer/123456789.html?spm=a...
    """
    m = re.search(r"/offer/(\d+)", url)
    return m.group(1) if m else None


# ════════════════════════════════════════════════════════════════
# 方案一：Just One API
# ════════════════════════════════════════════════════════════════

JUSTONE_URL = "https://api.justoneapi.com/api/1688/get-item-detail/v2"


async def _fetch_justone(offer_id: str, token: str) -> dict:
    """调用 Just One API V2 获取 1688 商品详情。

    Just One 的业务结果必须通过返回体 `code` 判断：
    - 0：成功
    - 100：Token 无效
    - 301：采集失败，可重试
    - 302/303：限流或配额耗尽
    - 600/601/602：权限、余额或 Token 限额问题
    """
    params = {
        "token": token,
        "itemId": offer_id,
        "language": "zh",
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(JUSTONE_URL, params=params)
    except httpx.TimeoutException:
        raise ScrapeTimeoutError("Just One API 响应超时，请稍后再试")
    except Exception:
        raise ServiceUnavailableError("Just One API 暂时不可用，请稍后再试")

    if response.status_code in (401, 403):
        raise ServiceUnavailableError("Just One API Token 无效或权限不足")
    if response.status_code == 429:
        raise ServiceUnavailableError("Just One API 调用过于频繁，请稍后再试")
    if response.status_code >= 500:
        raise ServiceUnavailableError("Just One API 暂时不可用，请稍后再试")
    if response.status_code != 200:
        raise ServiceUnavailableError("Just One API 请求失败，请稍后再试")

    try:
        result = response.json()
    except ValueError:
        raise ServiceUnavailableError("Just One API 返回格式异常")

    code = result.get("code")
    if code == 0:
        data = result.get("data")
        if not data:
            # 官方约定：商品不存在是成功计费查询，data 为空。
            raise ProductNotFoundError("该商品不存在或已下架，请换一个 1688 商品链接试试")
        return data

    if code in (100, 600):
        raise ServiceUnavailableError("Just One API Token 无效或权限不足")
    if code in (302, 303, 602):
        raise ServiceUnavailableError("Just One API 配额或调用频率已达上限")
    if code in (601,):
        raise ServiceUnavailableError("Just One API 账户余额不足")
    if code == 301:
        raise ServiceUnavailableError("Just One API 采集失败，请稍后再试")
    raise ServiceUnavailableError("Just One API 暂时不可用，请稍后再试")


def _normalize_justone_product(data: dict) -> dict:
    """把 Just One V1/V2 常见字段结构归一成项目商品字段。"""
    if not data:
        raise ProductNotFoundError("该商品不存在或已下架，请换一个 1688 商品链接试试")

    title_node = data.get("title")
    item = data.get("item") or {}
    price_node = data.get("price") or {}
    main_pic = data.get("mainPic") or {}

    title = None
    if isinstance(title_node, dict):
        title = title_node.get("title")
    elif isinstance(title_node, str):
        title = title_node
    title = title or item.get("offerTitle") or data.get("offerTitle")
    title = _clean_text(title, max_len=500)
    if not title:
        raise ParseError(
            "未能从 Just One API 识别商品标题，请稍后重试，或手动录入该商品"
        )

    # V2 使用 main_imgs；V1 使用 mainPic.offerImgList。
    images = data.get("main_imgs") or main_pic.get("offerImgList") or []
    main_image_url = images[0] if images else item.get("defaultOfferImg")
    if not main_image_url:
        for image in data.get("images") or []:
            if isinstance(image, dict):
                main_image_url = image.get("fullPathImageURI")
                if main_image_url:
                    break

    raw_price = item.get("price")
    if raw_price is None:
        price_info = data.get("price_info") or {}
        raw_price = price_info.get("price_min") or price_info.get("price")
    if raw_price is None:
        price_model = price_node.get("priceModel") or {}
        prices = price_model.get("currentPrices") or []
        if prices and isinstance(prices[0], dict):
            raw_price = prices[0].get("price")
        if raw_price is None:
            raw_price = price_model.get("originalPriceDisplay")
    price, price_present = _clean_price(raw_price)
    if price_present and (price is None or price <= 0):
        raise ParseError("Just One API 商品价格解析异常，请稍后重试")

    sales = item.get("saledCount")
    if sales is None:
        sale_info = data.get("sale_info") or {}
        sales = (
            sale_info.get("sale_quantity_year")
            or sale_info.get("sale_quantity_90days")
            or data.get("sale_count")
        )
    if sales is None and isinstance(title_node, dict):
        sales = title_node.get("selledNumber")

    shop_info = data.get("shop_info") or {}
    return {
        "title": title,
        "main_image_url": _clean_image_url(main_image_url),
        "price": round(price, 2) if price is not None else None,
        "sales_count": _clean_int(sales),
        "shop_name": _clean_text(
            shop_info.get("shop_name")
            or shop_info.get("seller_login_id")
            or item.get("companyName")
            or item.get("sellerLoginId"),
            max_len=255,
        ),
    }


# ════════════════════════════════════════════════════════════════
# 方案二：Onebound API
# ════════════════════════════════════════════════════════════════

ONEBOUND_URL = "https://api-gw.onebound.cn/1688/item_get"


async def _fetch_onebound(
    offer_id: str,
    api_key: str,
    api_secret: str,
) -> dict:
    """调用 Onebound API 获取商品原始字段。

    Onebound 的 API 格式：
    GET https://api-gw.onebound.cn/1688/item_get?key=xxx&secret=xxx&num_iid=xxx

    Returns:
        dict（title / main_image_url / price / sales_count / shop_name，可为 None）

    Raises:
        ProductNotFoundError: 接口 code=0 但无 data（商品在服务商侧不存在）。
        ScrapeTimeoutError: 请求超时。
        ServiceUnavailableError: 服务端错误 / Key 无效 / 响应异常（触发直抓降级）。
    """
    params = {"key": api_key, "secret": api_secret, "num_iid": offer_id}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(ONEBOUND_URL, params=params)
    except httpx.TimeoutException:
        raise ScrapeTimeoutError("数据服务响应超时，请稍后再试")
    except Exception:
        raise ServiceUnavailableError("数据服务暂时不可用，请稍后再试")

    if resp.status_code != 200:
        raise ServiceUnavailableError("数据服务暂时不可用，请稍后再试")
    try:
        result = resp.json()
    except ValueError:
        raise ServiceUnavailableError("数据服务返回异常，请稍后再试")

    # code=0 表示 API 调用成功
    if result.get("code") != 0:
        raise ServiceUnavailableError("数据服务暂时不可用，请稍后再试")

    data = result.get("data") or {}
    # code=0 但没有任何 data → 服务商侧查不到该商品（等价已下架/链接失效）
    if not data:
        raise ProductNotFoundError("该商品不存在或已下架，请换一个 1688 商品链接试试")

    return {
        "title": data.get("title"),
        "main_image_url": data.get("pic_url") or data.get("main_pic"),
        "price": data.get("price") or data.get("batch_price"),
        "sales_count": data.get("sales") or data.get("sales_30day"),
        "shop_name": data.get("shop_name") or data.get("nick"),
    }


# ════════════════════════════════════════════════════════════════
# 方案二：直接抓取 HTML（降级链路）
# ════════════════════════════════════════════════════════════════

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.1688.com/",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 反爬拦截特征（命中即视为被风控）
_BLOCK_MARKERS = ("验证码", "x5sec", "访问过于频繁", "访问验证", "滑动验证")
# 已下架/失效特征（命中即视为商品不存在）
_DELISTED_MARKERS = (
    "商品已下架",
    "此宝贝已下架",
    "宝贝不存在",
    "该商品已删除",
    "商品不存在",
    "很抱歉，您查看的宝贝不存在",
)


async def _fetch_html(url: str) -> str:
    """抓取 1688 详情页 HTML（两层：httpx → curl_cffi 模拟 Chrome TLS 指纹）。

    1688 会检查 TLS 握手特征与 UA，curl_cffi impersonate 可提高直抓通过率。

    Returns:
        HTML 文本（长度 > 5000，短内容视为被拦/跳转页）。

    Raises:
        ProductNotFoundError: 返回 404。
        AntiBotError / ScrapeTimeoutError / ServiceUnavailableError: 抓取被拦 / 超时 / 失败。
    """
    failures: list[ScrapeError] = []

    # ── 第 1 层：httpx ─────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers=_BROWSER_HEADERS)
        if resp.status_code == 404:
            raise ProductNotFoundError("该商品不存在或已下架，请换一个 1688 商品链接试试")
        resp.raise_for_status()
        if resp.text and len(resp.text) > 5000:
            return resp.text
        failures.append(AntiBotError("1688 有访问保护，暂时无法自动抓取，请稍后重试，或手动录入商品"))
    except ProductNotFoundError:
        raise
    except httpx.TimeoutException:
        failures.append(ScrapeTimeoutError("抓取超时，请稍后再试"))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (403, 406, 429):
            failures.append(AntiBotError("1688 有访问保护，暂时无法自动抓取，请稍后重试，或手动录入商品"))
        else:
            failures.append(ServiceUnavailableError("页面暂时无法访问，请稍后再试"))
    except Exception:
        failures.append(ServiceUnavailableError("网络请求失败，请稍后再试"))

    # ── 第 2 层：curl_cffi（模拟 Chrome 120 的 TLS 指纹） ──
    try:
        from curl_cffi.requests import AsyncSession as CurlSession

        async with CurlSession() as session:
            resp = await session.get(url, headers=_BROWSER_HEADERS, impersonate="chrome120")
        if resp.status_code == 404:
            raise ProductNotFoundError("该商品不存在或已下架，请换一个 1688 商品链接试试")
        if resp.text and len(resp.text) > 5000:
            return resp.text
        failures.append(AntiBotError("1688 有访问保护，暂时无法自动抓取，请稍后重试，或手动录入商品"))
    except ProductNotFoundError:
        raise
    except Exception:
        failures.append(ServiceUnavailableError("实时抓取失败，请稍后再试"))

    if failures:
        raise failures[-1]
    raise ServiceUnavailableError("无法获取商品页面，请稍后再试")


async def _direct_fetch(url: str) -> dict:
    """直抓降级入口：取 HTML → 反爬/下架检测 → 解析原始字段。

    Returns:
        dict（title / main_image_url / price / sales_count / shop_name）

    Raises:
        ProductNotFoundError / AntiBotError / ScrapeTimeoutError / ServiceUnavailableError
    """
    html = await _fetch_html(url)

    # 命中反爬特征（长页面也可能夹带验证码浮层）
    if any(m in html for m in _BLOCK_MARKERS):
        raise AntiBotError("1688 有访问保护，暂时无法自动抓取，请稍后重试，或手动录入商品")

    # 命中下架/失效特征 → 404 类错误，引导换链接
    if any(m in html for m in _DELISTED_MARKERS):
        raise ProductNotFoundError("该商品不存在或已下架，请换一个 1688 商品链接试试")

    return _parse_html(html)


def _parse_html(html: str) -> dict:
    """从 HTML 中解析商品信息。

    使用 BeautifulSoup 解析，选择器是"碰运气"式的（不同页面结构不同），
    这就是为什么 API 方案比 HTML 解析更可靠。标题没抓到时返回空 dict，
    由上层 _normalize_product 归类为 parse_error。

    Returns:
        dict: 可能包含 title、main_image_url、price、shop_name、sales_count
    """
    soup = BeautifulSoup(html, "lxml")
    result: dict = {}

    # ── 提取标题（优先 og:title，其次各 CSS 选择器）─────────
    meta = soup.find("meta", attrs={"property": "og:title"})
    if meta and meta.get("content"):
        result["title"] = meta["content"].split(" - ")[0].strip()

    if not result.get("title"):
        for sel in ["h1[class*='title']", "h1", "[class*='offer-title']"]:
            tag = soup.select_one(sel)
            if tag and (t := tag.get_text(strip=True)) and len(t) > 5:
                result["title"] = t
                break

    # ── 提取主图（og:image） ────────────────────────────────
    meta = soup.find("meta", attrs={"property": "og:image"})
    if meta and meta.get("content"):
        result["main_image_url"] = meta["content"]

    # ── 提取价格 ────────────────────────────────────────────
    for sel in ["[class*='price']", "[itemprop='price']"]:
        tag = soup.select_one(sel)
        if tag:
            text = tag.get_text(strip=True)
            nums = re.findall(r"[\d.]+", text)
            if nums:
                result["price"] = nums[0]  # 留字符串，交给 _clean_price 统一解析
                break

    # ── 提取销量（如「已售 1.2万件」） ───────────────────────
    for sel in ["[class*='sale']", "[class*='sales']", "[class*='deal-count']"]:
        tag = soup.select_one(sel)
        if tag and (t := tag.get_text(strip=True)) and re.search(r"\d", t):
            result["sales_count"] = t
            break

    # ── 提取店铺名 ──────────────────────────────────────────
    for sel in ["[class*='shop-name']", "[class*='company']"]:
        tag = soup.select_one(sel)
        if tag and (t := tag.get_text(strip=True)) and len(t) > 1:
            result["shop_name"] = t
            break

    return result


# ════════════════════════════════════════════════════════════════
# 数据清洗 / 字段兜底（CAP-01 / C4）
# ════════════════════════════════════════════════════════════════


def _clean_text(value: Any, max_len: int = 500) -> str | None:
    """清洗文本：折叠空白；超长截断；空值返回 None。"""
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text:
        return None
    return text[:max_len]


def _clean_price(value: Any) -> tuple[float | None, bool]:
    """把价格解析为 float；返回 (值或 None, 字段是否「显式存在」)。

    显式存在但解析失败 / ≤ 0 → (None, True)，由上层判为 parse_error；
    字段本身缺失（None / 空串）→ (None, False)，走字段兜底（落库为 None）。
    兼容常见格式：「¥9.90」「US $1.2」「1.2-3.4（阶梯价取首价）」。
    """
    if value is None:
        return None, False
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None, False
        # 阶梯价「1.2-3.4」取第一个数值；去掉货币符号/千分位
        m = re.search(r"(\d+(?:\.\d+)?)", s)
        if not m:
            return None, True
        try:
            parsed = float(m.group(1))
        except ValueError:
            return None, True
        return parsed, True
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None, True
    return parsed, True


_CN_MAGNITUDE = {"千": 1_000, "万": 10_000, "亿": 100_000_000}


def _clean_int(value: Any) -> int | None:
    """把销量等转 int。

    兼容 1688 常见中文数量文本：
    - 「已售1.2万+」「10万+」等带量级后缀 → 按 千/万/亿 换算成整数（12000 / 100000）
    - 「已售123件」等纯数字文本 → 提取数字位（123）
    失败/缺失 → None。

    注：老版本直接剥掉所有非数字，会把「1.2万」错读成 12，已修复。
    """
    if value is None:
        return None
    if isinstance(value, str):
        text = value.replace(",", "").replace("，", "").strip()
        if not text:
            return None
        # 1) 带量级写法：数字 + 千/万/亿（前后允许中文/符号，如「已售1.2万+」）
        m = re.search(r"(\d+(?:\.\d+)?)\s*([万亿千])", text)
        if m:
            try:
                return int(float(m.group(1)) * _CN_MAGNITUDE[m.group(2)])
            except (ValueError, KeyError):
                return None
        # 2) 纯数字兜底：取全部数字位
        digits = re.sub(r"\D", "", text)
        if not digits:
            return None
        try:
            return int(digits)
        except ValueError:
            return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _clean_image_url(value: Any) -> str | None:
    """归一主图地址：协议相对「//x」补 https；仅保留 http(s)。"""
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.startswith("//"):
        s = "https:" + s
    if not s.lower().startswith(("http://", "https://")):
        return None
    return s[:1000]


def _normalize_product(raw: dict, source: str) -> dict:
    """清洗与字段兜底：缺失字段给 None，不因单个字段缺失整单失败。

    Raises:
        ParseError: 标题为空 / 价格字段「显式存在但解析为 0 或无法解析」。
    """
    title = _clean_text(raw.get("title"), max_len=500)
    if not title:
        raise ParseError(
            "未能识别出商品标题，页面结构可能已变化，请稍后重试，或手动录入该商品"
        )

    price, price_present = _clean_price(raw.get("price"))
    if price_present and (price is None or price <= 0):
        raise ParseError(
            "商品价格解析异常，请换一个商品链接试试，或手动录入该商品"
        )

    return {
        "title": title,
        "main_image_url": _clean_image_url(raw.get("main_image_url")),
        "price": round(price, 2) if price is not None else None,
        "sales_count": _clean_int(raw.get("sales_count")),
        "shop_name": _clean_text(raw.get("shop_name"), max_len=255),
    }
