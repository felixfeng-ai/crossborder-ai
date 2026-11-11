"""VeyaShip - Shopify 路由（F8 Publisher + F7 Concierge）

功能：
1. Shopify OAuth 授权绑定（CAP-02：修复 OAuth 断链闭环）
2. 合规审查（违禁词检测）
3. 推送商品到 Shopify
4. 拉取订单（F7）
5. 自动退款（F7，真调 Shopify Refund API，带 CAP-03 护栏）
"""

import asyncio
import hashlib
import hmac as hmac_mod
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.access_control import check_feature_access
from app.core.crypto import decrypt_value, encrypt_value, mask_secret
from app.core.security import create_access_token, decode_token_safe
from app.dependencies import get_current_user
from app.models.product import Product
from app.models.shopify_channel import ShopifyChannel
from app.models.shopify_compliance_event import ShopifyComplianceEvent
from app.models.publication import Publication
from app.models.user import User
from app.services.listing_service import (
    get_current_compliance_report,
    get_owned_listing,
)
from app.services import provider_config
from app.services.publication_service import (
    find_publication_by_idempotency,
    publication_response,
)
from app.services.shopify_publish_service import (
    ShopifyPublishError,
    publish_shopify_product,
    serialize_shopify_publish_result,
)
from app.services.shopify_operations_sync import (
    ShopifyOperationsSyncError,
    sync_shopify_operations,
)
router = APIRouter(prefix="/shopify", tags=["Shopify"])

# ── 违禁词正则（F8 合规审查）─────────────────────────────────
BANNED_PATTERNS = [
    r"最[好优棒强劲大低价实惠](?!.*[的之])",
    r"第[一二三123][名位]",
    r"绝对[^不]",
    r"永不[^能会]",
    r"全网[最唯第]",
    r"100%[^的]",
    r"零风险",
    r"无效退款",
    r"全国第一",
    r"销量[第冠]",
]


def compliance_check(text: str) -> list[str]:
    """合规审查：检测文本中是否含违禁词

    Args:
        text: 要检查的文本

    Returns:
        匹配到的违禁词列表（空列表表示通过）
    """
    hits = []
    for pattern in BANNED_PATTERNS:
        found = re.findall(pattern, text)
        hits.extend(found)
    return hits


async def ai_compliance_check(text: str) -> dict:
    """AI 合规复查：调 DeepSeek 审查文本是否含平台违规风险。

    作为正则审查的补充层。AI 调用失败时降级为正则结果，不阻断流程。

    Returns:
        {"safe": bool, "reason": str | None}
    """
    try:
        from app.services.ai.deepseek import DeepSeekService
        llm = DeepSeekService()
        prompt = (
            "你是电商内容合规审核员。检查以下文本是否存在问题。\n"
            "违规类型包括：\n"
            "1. 侮辱/攻击性用语（如：傻子、白痴、蠢货等）\n"
            "2. 虚假宣传、夸大功效\n"
            "3. 绝对化用语（最好、第一、100%等）\n"
            "4. 其他违规内容\n\n"
            f"文本：{text[:2000]}\n\n"
            "返回 JSON：{\"safe\": boolean, \"reason\": string|null}\n"
            "safe=false 时 reason 说明违规原因，safe=true 时 reason 为 null。"
        )
        result = await llm.generate(
            "你是一个严格的电商平台合规审核员，只返回 JSON。",
            prompt,
            max_tokens=300,
        )
        import json, re
        match = re.search(r'\{.*\}', result, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    # 降级：AI 调用失败时返回通过，依赖正则拦截
    return {"safe": True, "reason": None}


# ── 数据模型 ──────────────────────────────────────────────────

class ComplianceRequest(BaseModel):
    text: str = ""


class ComplianceResult(BaseModel):
    passed: bool
    violations: list[str] = []


class PushProductRequest(BaseModel):
    product_id: str = Field("", description="兼容旧调用的商品 ID")
    listing_id: str = Field("", description="ListingDraft ID，优先使用")
    channel_id: str = Field(..., description="Shopify 渠道 ID")
    variant_ids: list[str] = Field(
        default_factory=list,
        description="可选：只发布指定 SKU 变体；为空时发布全部启用变体",
    )

    @model_validator(mode="after")
    def require_product_or_listing(self):
        if not self.listing_id and not self.product_id:
            raise ValueError("product_id 或 listing_id 至少提供一个")
        return self


class ConnectShopifyRequest(BaseModel):
    shop: str = Field(..., description="Shopify 店铺名或 .myshopify.com 域名")


# ── 工具函数 ──────────────────────────────────────────────────

async def get_channel(channel_id: str, user_id, db) -> ShopifyChannel:
    from uuid import UUID
    try:
        uid = UUID(channel_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的渠道 ID")
    result = await db.execute(
        select(ShopifyChannel).where(ShopifyChannel.id == uid, ShopifyChannel.user_id == user_id)
    )
    ch = result.scalar_one_or_none()
    if not ch:
        raise HTTPException(status_code=404, detail="Shopify 渠道不存在")
    return ch


# ── Shopify 店铺名 / OAuth / 退款护栏 工具 ──────────────────────
# root cause（CAP-02）：旧 /auth 用 f"https://{shop}.myshopify.com/..." 拼域，
# 但前端传的 shop 已含 .myshopify.com 全域名 → 双重域名；旧 /callback 又把全域名当 shop_name 落库，
# 下游 push / orders / auto-refund 再用 f"{shop_name}.myshopify.com" 拼一次 → 请求全部打错地址。
# 修法：全仓只在 shop_domain() 一个点拼域名，入库 shop_name 只存裸子域。
SHOPIFY_SHOP_SUFFIX = ".myshopify.com"
# OAuth scope 说明（保持最小化）：
#   write_products / read_products —— F8 Publisher 推商品为草稿 + 读商品；
#   read_orders / write_orders    —— F7 Concierge 拉订单 + 自动退款需要。
# 不要追加 settings/theme 等无关权限。
SHOPIFY_OAUTH_SCOPES = "write_products,read_products,read_orders,write_orders"
# 绑定 state 令牌有效期：只需覆盖用户从点击授权到 Shopify 跳回的过程，10 分钟足够且降低被重放风险。
SHOPIFY_STATE_TTL_MINUTES = 10
# Shopify 回调时间戳允许偏差（秒）：防重放，见 CAP-02 spec。
SHOPIFY_HMAC_MAX_SKEW = 300

SHOPIFY_COMPLIANCE_TOPICS = {
    "customers/data_request",
    "customers/redact",
    "shop/redact",
}

# CAP-03 自动退款护栏常量。
# 进程内 dict 计数：单机可用，生产多副本应换 Redis/DB 原子计数，见 specs/shopify-binding/spec.md。
MAX_REFUND_AMOUNT = 100.0         # 单次自动退款请求的总金额上限（按订单币种计）
MAX_DAILY_REFUND_TOTAL = 300.0    # 同一用户/店铺单日累计自动退款上限
_DAILY_REFUND_TOTALS: dict[str, list] = {}  # user_id -> [date, total]，进程内，重启清零
_REFUND_LOCK = asyncio.Lock()


def normalize_shop(raw: str | None) -> str:
    """把用户输入规范成 Shopify 裸子域（如 yourshop）。

    兼容传 .myshopify.com 全域名 / 带空白的输入：先剥后缀与空白，
    再用 ^[a-z0-9][a-z0-9-]*$ 校验（Shopify 子域规则：小写字母数字、可含中划线）。
    非法时抛 400，中文提示面向卖家。

    Raises:
        HTTPException 400: 店铺域名格式不正确
    """
    if not raw or not isinstance(raw, str):
        raise HTTPException(status_code=400, detail="店铺域名格式不正确")
    s = raw.strip()
    if s.endswith(SHOPIFY_SHOP_SUFFIX):
        s = s[: -len(SHOPIFY_SHOP_SUFFIX)].strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", s):
        raise HTTPException(status_code=400, detail="店铺域名格式不正确")
    return s


def shop_domain(bare: str) -> str:
    """由裸子域拼完整店铺域名。全仓拼域唯一入口，杜绝双重域名。"""
    return f"{bare}{SHOPIFY_SHOP_SUFFIX}"


def _channel_domain(channel: ShopifyChannel) -> str:
    """渠道域名：优先取库里的全域名 shop_domain，旧数据为空时兜底拼一次。"""
    return channel.shop_domain or shop_domain(channel.shop_name)


def _build_oauth_url(user: User, shop: str) -> str:
    api_key, _api_secret, redirect_uri = _require_shopify_config()
    bare = normalize_shop(shop)
    state = create_access_token(
        subject=str(user.id),
        extra_claims={
            "type": "shopify_oauth_state",
            "shop": bare,
            "ts": int(time.time()),
        },
        expires_delta=timedelta(minutes=SHOPIFY_STATE_TTL_MINUTES),
    )
    params = urlencode(
        {
            "client_id": api_key,
            "scope": SHOPIFY_OAUTH_SCOPES,
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    return f"https://{shop_domain(bare)}/admin/oauth/authorize?{params}"


def _require_shopify_config() -> tuple[str, str, str]:
    """校验 Shopify 应用三要素（Key/Secret/回调地址）已配置，缺一抛 400。

    root cause：平台级 API Key 由运维在 .env 配置，卖家不可见；
    未配置时旧实现只报"未配置 API Key"，语义不清，统一为"Shopify 应用尚未配置"。
    """
    api_key = provider_config.get("shopify", "api_key")
    api_secret = provider_config.get("shopify", "api_secret")
    redirect_uri = provider_config.get("shopify", "redirect_uri")
    if not api_key or not api_secret or not redirect_uri:
        raise HTTPException(status_code=400, detail="Shopify 应用尚未配置")
    return api_key, api_secret, redirect_uri


async def _require_binding_user(request: Request, token_param: str | None, db: AsyncSession) -> User:
    """解析发起 OAuth 绑定的当前用户。

    root cause：绑定由浏览器整页跳转发起（window.location），
    纯整页跳转带不了 Authorization 头（与 api/sse.ts 的 EventSource 同限制），
    因此支持 query token 兜底；Authorization 头优先，二者都无则 401。
    """
    raw: str | None = None
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        raw = auth[7:].strip()
    if not raw:
        raw = token_param or None
    if not raw:
        raise HTTPException(status_code=401, detail="未登录，请先登录")
    payload = decode_token_safe(raw)
    if payload is None:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    try:
        uid = UUID(payload.get("sub", ""))
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def _shopify_hmac_ok(request: Request, api_secret: str, provided: str | None) -> bool:
    """校验 Shopify 回调的 HMAC-SHA256 签名。

    root cause：旧实现不验 hmac，回调可被第三方伪造。
    算法：取除 hmac/signature 外的全部 query 参数，按 key 字母序拼成 k=v&...，
    以 client_secret 为密钥做 HMAC-SHA256 hexdigest；
    用 hmac.compare_digest 固定时间比较，防时序侧信道。
    """
    if not provided:
        return False
    pairs: list[tuple[str, str]] = []
    for part in request.url.query.split("&"):
        if not part:
            continue
        k, _, v = part.partition("=")
        if k in ("hmac", "signature"):
            continue
        pairs.append((k, v))
    pairs.sort(key=lambda kv: kv[0])
    message = "&".join(f"{k}={v}" for k, v in pairs)
    digest = hmac_mod.new(
        api_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac_mod.compare_digest(digest, provided)


def _shopify_webhook_hmac_ok(raw_body: bytes, api_secret: str, provided: str | None) -> bool:
    """校验 Webhook 原始请求体 HMAC，必须使用 body 而不是解析后的 JSON。"""
    if not provided or not api_secret:
        return False
    digest = hmac_mod.new(
        api_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac_mod.compare_digest(digest, provided)


async def _handle_shopify_compliance_webhook(
    request: Request,
    expected_topic: str,
    db: AsyncSession,
) -> dict:
    """验证并处理 Shopify 强制隐私 Webhook，不保存客户 PII。"""
    raw_body = await request.body()
    api_secret = provider_config.get(
        "shopify",
        "api_secret",
        settings.SHOPIFY_API_SECRET or "",
    )
    if not api_secret:
        raise HTTPException(status_code=503, detail="Shopify Webhook 密钥未配置")

    signature = request.headers.get("X-Shopify-Hmac-Sha256", "")
    if not _shopify_webhook_hmac_ok(raw_body, api_secret, signature):
        raise HTTPException(status_code=401, detail="Shopify Webhook 签名无效")

    topic = request.headers.get("X-Shopify-Topic", "")
    if topic != expected_topic or topic not in SHOPIFY_COMPLIANCE_TOPICS:
        raise HTTPException(status_code=400, detail="Shopify Webhook Topic 不匹配")

    webhook_id = (request.headers.get("X-Shopify-Webhook-Id") or "").strip()
    if not webhook_id:
        raise HTTPException(status_code=400, detail="缺少 Shopify Webhook ID")

    existing = (
        await db.execute(
            select(ShopifyComplianceEvent).where(
                ShopifyComplianceEvent.webhook_id == webhook_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {"ok": True, "duplicate": True}

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Shopify Webhook payload 无效")

    shop_domain = str(
        request.headers.get("X-Shopify-Shop-Domain")
        or payload.get("shop_domain")
        or ""
    ).strip().lower()
    event = ShopifyComplianceEvent(
        webhook_id=webhook_id,
        topic=topic,
        shop_domain=shop_domain or None,
        status="processing",
        action_summary="{}",
    )
    db.add(event)

    try:
        summary: dict[str, object] = {"stored_customer_data": False}
        if topic == "shop/redact":
            bare = shop_domain.removesuffix(SHOPIFY_SHOP_SUFFIX)
            channels = (
                await db.execute(
                    select(ShopifyChannel).where(
                        or_(
                            ShopifyChannel.shop_domain == shop_domain,
                            ShopifyChannel.shop_name == bare,
                        )
                    )
                )
            ).scalars().all()
            channel_ids = [str(channel.id) for channel in channels]
            publications_deleted = 0
            if channel_ids:
                publication_result = await db.execute(
                    delete(Publication).where(
                        Publication.platform == "shopify",
                        Publication.channel_id.in_(channel_ids),
                    )
                )
                publications_deleted = max(publication_result.rowcount or 0, 0)
                await db.execute(
                    delete(ShopifyChannel).where(
                        ShopifyChannel.id.in_([channel.id for channel in channels])
                    )
                )
            summary.update(
                {
                    "channels_deleted": len(channels),
                    "publications_deleted": publications_deleted,
                }
            )

        event.status = "processed"
        event.action_summary = json.dumps(summary, ensure_ascii=False)
        event.processed_at = datetime.now(timezone.utc)
        await db.commit()
        return {"ok": True, "duplicate": False}
    except Exception as exc:
        await db.rollback()
        failed = await db.get(ShopifyComplianceEvent, event.id)
        if failed is None:
            failed = event
            db.add(failed)
        failed.status = "failed"
        failed.error = str(exc)[:1000]
        failed.processed_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(status_code=500, detail="Shopify Webhook 处理失败")


@router.post("/webhooks/customers/data_request")
async def shopify_customers_data_request_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Shopify 客户数据查看请求；平台不保存客户 PII。"""
    return await _handle_shopify_compliance_webhook(
        request,
        "customers/data_request",
        db,
    )


@router.post("/webhooks/customers/redact")
async def shopify_customers_redact_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Shopify 客户数据删除请求；平台不保存客户 PII。"""
    return await _handle_shopify_compliance_webhook(
        request,
        "customers/redact",
        db,
    )


@router.post("/webhooks/shop/redact")
async def shopify_shop_redact_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """店铺卸载后的数据删除请求：清除渠道 Token 与发布记录。"""
    return await _handle_shopify_compliance_webhook(
        request,
        "shop/redact",
        db,
    )


async def _check_daily_refund_cap(user_id: str, amount: float) -> bool:
    """单日累计退款上限检查（含当次请求金额）。

    进程内 dict 计数（{user_id: (date, total)}）；跨进程/重启安全做法见 spec，
    生产建议换 Redis INCRBY + 过期时间或 DB 当日汇总。
    """
    async with _REFUND_LOCK:
        today = date.today().isoformat()
        rec = _DAILY_REFUND_TOTALS.get(user_id)
        used = rec[1] if rec and rec[0] == today else 0.0
        return used + amount <= MAX_DAILY_REFUND_TOTAL


async def _record_daily_refund(user_id: str, amount: float) -> None:
    """把本次实际退款金额累加进当日计数（仅成功退款才计）。"""
    async with _REFUND_LOCK:
        today = date.today().isoformat()
        rec = _DAILY_REFUND_TOTALS.get(user_id)
        used = rec[1] if rec and rec[0] == today else 0.0
        _DAILY_REFUND_TOTALS[user_id] = [today, used + amount]


# ── 路由 ──────────────────────────────────────────────────────

@router.get("/auth")
async def shopify_oauth_url(
    request: Request,
    shop: str | None = Query(None, description="Shopify 店铺名（裸子域或全域名均可）"),
    token: str | None = Query(None, description="整页跳转兜底 JWT（浏览器跳转无法带 Authorization 头）"),
    db: AsyncSession = Depends(get_db),
):
    """302 跳转 Shopify OAuth 授权页（而不是返回 JSON）。

    root cause：旧实现返回 {"auth_url": ...} JSON，且 f"https://{shop}.myshopify.com" 拼域，
    前端传的 shop 已带 .myshopify.com → 双重域名、整页跳转只看到 JSON。
    绑定是已登录用户点按钮触发的 → 先鉴权拿到 user id，签 10 分钟 state 防 CSRF/重放。
    """
    current_user = await _require_binding_user(request, token, db)
    if not shop:
        raise HTTPException(status_code=400, detail="店铺域名格式不正确")
    auth_url = _build_oauth_url(current_user, shop)
    return RedirectResponse(url=auth_url, status_code=302)


@router.post("/connect")
async def create_shopify_connect_url(
    payload: ConnectShopifyRequest,
    current_user: User = Depends(get_current_user),
):
    """Authenticated entry for SPA binding flow.

    The browser receives a Shopify URL and navigates itself, so the access token
    never needs to be placed in a query string.
    """
    return {"auth_url": _build_oauth_url(current_user, payload.shop), "expires_in": 600}


@router.get("/callback")
async def shopify_oauth_callback(
    request: Request,
    code: str | None = Query(None, description="Shopify 授权码"),
    shop: str | None = Query(None, description="店铺域名（可能带 .myshopify.com 后缀）"),
    timestamp: str | None = Query(None, description="Shopify 回传的 Unix 时间戳"),
    hmac_sig: str | None = Query(None, alias="hmac", description="Shopify HMAC-SHA256 签名"),
    state: str | None = Query(None, description="绑定 state 令牌"),
    db: AsyncSession = Depends(get_db),
):
    """Shopify OAuth 回调（浏览器 302 跳回，不鉴权）。

    root cause（CAP-02）：
    1. 旧实现挂 Depends(get_current_user)——浏览器跳回无 JWT，必然 401；
    2. 无 state 校验 → 存在 CSRF/伪造绑定；
    3. 无 hmac/timestamp 校验 → 回调可被伪造/重放；
    4. shop 全域名直接当 shop_name 存库 → 下游请求双重域名。
    现流程：state 缺失 → 验 state → 店铺一致性 → 时间戳窗口 → hmac → 换 token → 加密落库 → 302 回前端。
    """
    origin = str(request.base_url).rstrip("/")

    def _front_redirect(**params: str) -> RedirectResponse:
        """拼回 SPA 页面路径 /app/shopify 的 302（?error=... 或 ?bound=1&shop=...）。"""
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        return RedirectResponse(url=f"{origin}/app/shopify?{qs}", status_code=302)

    # ① state 缺失
    if not state:
        return _front_redirect(error="state_missing")

    # ② state 校验：验签/过期/类型/店铺一致/用户存在
    payload = decode_token_safe(state)
    try:
        bare = normalize_shop(shop)
    except HTTPException:
        return _front_redirect(error="invalid_state")
    if payload is None:
        return _front_redirect(error="invalid_state")
    if payload.get("type") != "shopify_oauth_state":
        return _front_redirect(error="invalid_state")
    if payload.get("shop") != bare:
        return _front_redirect(error="invalid_state")
    try:
        uid = UUID(payload.get("sub", ""))
    except (ValueError, TypeError):
        return _front_redirect(error="invalid_state")
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if user is None:
        return _front_redirect(error="invalid_state")

    # ③ Shopify 时间戳 5 分钟内（防重放）
    try:
        ts = int(timestamp or "")
    except (ValueError, TypeError):
        return _front_redirect(error="invalid_state")
    if abs(time.time() - ts) > SHOPIFY_HMAC_MAX_SKEW:
        return _front_redirect(error="invalid_state")

    # ④ 平台配置 + hmac 校验
    try:
        api_key, api_secret, _redirect_uri = _require_shopify_config()
    except HTTPException:
        return _front_redirect(error="config")
    if not _shopify_hmac_ok(request, api_secret, hmac_sig):
        return _front_redirect(error="invalid_hmac")

    # ⑤ 用 code 换 access_token
    domain = shop_domain(bare)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://{domain}/admin/oauth/access_token",
                json={"client_id": api_key, "client_secret": api_secret, "code": code},
            )
    except httpx.HTTPError:
        return _front_redirect(error="token_exchange")
    if resp.status_code != 200:
        return _front_redirect(error="token_exchange")
    token_data = resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        return _front_redirect(error="token_exchange")

    # ⑥ upsert 落库：唯一键 (user_id, 裸店铺名)，access_token 加密存储
    enc_token = encrypt_value(access_token)
    sel = await db.execute(
        select(ShopifyChannel).where(
            ShopifyChannel.user_id == user.id,
            ShopifyChannel.shop_name == bare,
        )
    )
    existing = sel.scalar_one_or_none()
    if existing:
        existing.access_token = enc_token
        existing.shop_domain = domain
        existing.is_active = True
    else:
        db.add(ShopifyChannel(
            user_id=user.id,
            shop_name=bare,
            shop_domain=domain,
            access_token=enc_token,
            is_active=True,
        ))
    await db.flush()

    # ⑦ 成功 → 302 回前端
    return _front_redirect(bound="1", shop=bare)


@router.get("/channels")
async def list_channels(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查看当前用户绑定的全部 Shopify 店铺。

    返回：裸店铺名（shop_name）+ 完整域名（shop_domain/domain）+ 是否激活。
    安全：access_token 永不下发明文，仅回显掩码 token_masked（crypto.mask_secret）。
    """
    result = await db.execute(
        select(ShopifyChannel).where(ShopifyChannel.user_id == current_user.id)
    )
    channels = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "shop_name": c.shop_name,
            "shop_domain": c.shop_domain,
            "domain": c.shop_domain,  # 兼容旧前端字段名
            "is_active": c.is_active,
            "token_masked": mask_secret(c.access_token),
            "created_at": str(c.created_at),
            "updated_at": str(c.updated_at) if c.updated_at else None,
        }
        for c in channels
    ]


@router.delete("/channels/{channel_id}")
async def unbind_channel(
    channel_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """解绑（删除）一个 Shopify 渠道。

    root cause/安全：删除必须先做 owner 校验（channel.user_id == 当前用户），
    否则任意登录用户可越权删除他人店铺绑定。
    """
    try:
        cid = UUID(channel_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的渠道 ID")
    result = await db.execute(select(ShopifyChannel).where(ShopifyChannel.id == cid))
    channel = result.scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=404, detail="Shopify 渠道不存在")
    if channel.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作该渠道")
    await db.delete(channel)
    await db.flush()
    return {"ok": True}


@router.post("/compliance")
async def check_compliance(
    payload: ComplianceRequest,
):
    """合规审查：正则检测违禁词 + AI 检测不当用语"""
    violations = compliance_check(payload.text)

    # AI 二次检测不当内容
    ai_result = await ai_compliance_check(payload.text)
    if not ai_result.get("safe", True):
        violations.append(ai_result.get("reason", "内容不当"))

    return ComplianceResult(passed=len(violations) == 0, violations=violations)


@router.post("/push")
async def push_product(
    payload: PushProductRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
):
    """推送商品到 Shopify（含合规审查）

    流程：
    1. 套餐检查
    2. 查商品
    2. 查 Shopify 渠道
    3. 合规审查 → 不通过则拦截
    4. 调 Shopify API 创建商品
    """
    from uuid import UUID

    # 套餐检查
    if not check_feature_access(current_user, "shopify_publish"):
        raise HTTPException(status_code=403, detail="Shopify 发布功能仅限 Standard 及以上套餐使用")

    # 幂等检查必须先于 Listing 状态检查：首次发布成功后 Listing 已变为 published。
    existing_publication = await find_publication_by_idempotency(
        db,
        current_user.id,
        "shopify",
        idempotency_key,
    )
    if existing_publication is not None:
        if existing_publication.status == "completed":
            return publication_response(existing_publication)
        raise HTTPException(
            status_code=409,
            detail="相同发布请求正在处理或上次已失败，请使用新的幂等键重试",
        )

    listing = None
    if payload.listing_id:
        listing = await get_owned_listing(db, payload.listing_id, current_user.id)
        if listing is None:
            raise HTTPException(status_code=404, detail="Listing 不存在")
        if listing.compliance_status == "unknown" or listing.status == "draft":
            raise HTTPException(
                status_code=409,
                detail="Listing 已修改，合规报告已失效，请重新检查",
            )
        if listing.status != "ready" or listing.compliance_status != "pass":
            raise HTTPException(status_code=409, detail="Listing 未通过合规审查，无法发布")

        report = await get_current_compliance_report(db, listing)
        if report is None or report.status != "pass":
            raise HTTPException(status_code=409, detail="Listing 合规报告已失效，请重新检查")

        # 发布前再次做轻量正则校验，防止数据库状态与正文不一致。
        listing_text = " ".join(
            filter(
                None,
                [
                    listing.title,
                    listing.description,
                    listing.seo_title,
                    listing.seo_description,
                ],
            )
        )
        current_violations = compliance_check(listing_text)
        if current_violations:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Listing 未通过合规审查，无法发布",
                    "violations": current_violations,
                },
            )

        pid = listing.product_id
    else:
        try:
            pid = UUID(payload.product_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的商品 ID")

    # 归属过滤：只允许推送自己的商品，他人商品等同不存在
    result = await db.execute(
        select(Product).where(
            Product.id == pid,
            Product.user_id == current_user.id,
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    # 查 Shopify 渠道
    channel = await get_channel(payload.channel_id, current_user.id, db)

    # 合规审查（双重：正则 + AI 复查）
    content_title = listing.title if listing is not None else product.title
    content_description = (
        listing.description if listing is not None else product.description
    )
    check_text = f"{content_title or ''} {content_description or ''}"

    # 第一层：正则快速拦截
    violations = compliance_check(check_text)
    if violations:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "商品内容含违禁词，发布被拦截",
                "violations": violations,
            },
        )

    # Listing 路径已持有版本化 AI+正则报告；旧 Product 路径继续做即时 AI 复查。
    if listing is None:
        ai_result = await ai_compliance_check(check_text)
        if not ai_result.get("safe", True):
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "AI 合规审查未通过",
                    "reason": ai_result.get("reason", "未知违规"),
                },
            )

    # 网页与 Agent 统一从这里构建完整 Payload、调用 Shopify 并落发布记录。
    selected_variant_ids: list[UUID] | None = None
    if payload.variant_ids:
        try:
            selected_variant_ids = [UUID(value) for value in payload.variant_ids]
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="无效的 SKU 变体 ID")

    public_app_url = (settings.APP_URL or "").strip().rstrip("/")
    if not public_app_url or "localhost" in public_app_url or "127.0.0.1" in public_app_url:
        public_app_url = str(request.base_url).rstrip("/")
    try:
        result = await publish_shopify_product(
            db,
            user=current_user,
            product=product,
            listing=listing,
            channel=channel,
            idempotency_key=idempotency_key,
            app_url=public_app_url,
            variant_ids=selected_variant_ids,
        )
    except ShopifyPublishError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return serialize_shopify_publish_result(result)


@router.post("/sync-operations")
async def sync_operations(
    channel_id: str = Query(..., description="Shopify 渠道 ID"),
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """同步 Shopify 最近订单销量与本平台已发布商品库存。"""
    if not check_feature_access(current_user, "shopify_publish"):
        raise HTTPException(
            status_code=403,
            detail="Shopify 运营同步仅限 Standard 及以上套餐使用",
        )
    channel = await get_channel(channel_id, current_user.id, db)
    try:
        return await sync_shopify_operations(
            db,
            user=current_user,
            channel=channel,
            days=days,
        )
    except ShopifyOperationsSyncError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ════════════════════════════════════════════════════════════════
# F7 Concierge — 订单拉取 + 自动退款
# ════════════════════════════════════════════════════════════════

@router.get("/orders")
async def list_shopify_orders(
    channel_id: str = Query(..., description="Shopify 渠道 ID"),
    limit: int = Query(50, ge=1, le=250),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """拉取 Shopify 订单列表（F7 Concierge）

    从绑定的 Shopify 店铺拉取最近订单，
    返回订单 ID、金额、状态等信息。
    """
    channel = await get_channel(channel_id, current_user.id, db)
    # root cause：旧实现用 channel.shop_name 拼域，而 shop_name 曾存全域名 → 双重域名打错地址。
    # 统一走 _channel_domain；token 是密文，调 API 前解密。
    shop_url = (
        f"https://{_channel_domain(channel)}"
        f"/admin/api/{settings.SHOPIFY_API_VERSION}"
    )
    headers = {"X-Shopify-Access-Token": decrypt_value(channel.access_token)}

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{shop_url}/orders.json", headers=headers, params={
            "status": "any",
            "limit": limit,
            "order": "created_at desc",
        })
        if (
            resp.status_code == 403
            and "protected customer data" in resp.text.lower()
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Shopify 尚未批准受保护客户数据访问，"
                    "请先在 Partner Dashboard 申请订单数据权限"
                ),
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"获取订单失败：{resp.text[:200]}")

        orders = resp.json().get("orders", [])
        return [
            {
                "id": o["id"],
                "order_number": o.get("order_number"),
                "total_price": o.get("total_price"),
                "currency": o.get("currency"),
                "financial_status": o.get("financial_status"),
                "fulfillment_status": o.get("fulfillment_status"),
                "created_at": o.get("created_at"),
            }
            for o in orders
        ]


@router.post("/auto-refund")
async def auto_refund(
    channel_id: str = Query(..., description="Shopify 渠道 ID"),
    threshold: float = Query(10.0, description="自动退款阈值，低于此金额的订单自动退"),
    confirm: bool = Query(False, description="二次确认开关：必须显式 confirm=true 才会执行真实退款"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """自动退款（F7 Concierge，带 CAP-03 护栏的真实扣款）。

    CAP-03 护栏（生产计数应换 Redis/DB，见 specs/shopify-binding/spec.md）：
    1. 必须显式 confirm=true —— 前端二次确认后才调，防脚本/误触直接打真实扣款接口。
    2. 单次请求退款总金额 ≤ MAX_REFUND_AMOUNT，超限整体拒绝（400）。
    3. 同一用户单日累计退款 ≤ MAX_DAILY_REFUND_TOTAL（进程内 dict），超限拒绝（400）。
    4. 每笔失败/异常项带原因返回，不吞错；只在实际退款成功后才累加当日计数。

    ⚠️ 真实退款操作，会真扣 Shopify 商户账户余额。
    """
    # ① 渠道归属校验（owner 过滤在 get_channel 内，防越权）
    channel = await get_channel(channel_id, current_user.id, db)

    # ② 显式确认护栏：没有 confirm=true 一律拒绝
    if not confirm:
        raise HTTPException(status_code=400, detail="请确认后再发起退款")

    # root cause：shop_name 存裸子域，拼域走 _channel_domain；token 密文先解密再用。
    shop_url = (
        f"https://{_channel_domain(channel)}"
        f"/admin/api/{settings.SHOPIFY_API_VERSION}"
    )
    headers = {"X-Shopify-Access-Token": decrypt_value(channel.access_token)}

    # ③ 拉取已付款订单
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{shop_url}/orders.json", headers=headers, params={
            "status": "any",
            "limit": 50,
            "financial_status": "paid",
            "order": "created_at desc",
        })
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"获取订单失败：{resp.text[:200]}")
    orders = resp.json().get("orders", [])

    # ④ 过滤出金额在 (0, threshold) 的已付款订单
    refundable: list[dict] = []
    for o in orders:
        try:
            price = float(o.get("total_price", 0))
            if price > 0 and price < threshold:
                refundable.append(o)
        except (ValueError, TypeError):
            continue
    requested_total = sum(float(o.get("total_price", 0)) for o in refundable)

    # ⑤ 单次金额上限：整体拒绝（不做部分退，保证用户可预期）
    if requested_total > MAX_REFUND_AMOUNT:
        raise HTTPException(
            status_code=400,
            detail=(
                f"本次将退款 {requested_total:.2f}，已超过单次上限 "
                f"{MAX_REFUND_AMOUNT:.0f}，请调低阈值或分批操作"
            ),
        )

    # ⑥ 单日累计上限
    if not await _check_daily_refund_cap(str(current_user.id), requested_total):
        raise HTTPException(
            status_code=400,
            detail=f"今日累计退款已达上限 {MAX_DAILY_REFUND_TOTAL:.0f}，请明天再试",
        )

    # ⑦ 逐笔退款（真调 Shopify Refund API）
    results: list[dict] = []
    async with httpx.AsyncClient() as client:
        for order in refundable:
            order_id = order["id"]
            total = str(order.get("total_price", "0"))
            refund_data = {
                "refund": {
                    "notify": False,
                    "note": "VeyaShip 自动退款：金额低于阈值",
                    "transactions": [
                        {
                            "kind": "refund",
                            "amount": total,
                            "gateway": order.get("gateway", ""),
                        }
                    ],
                    "refund_line_items": [],
                }
            }
            try:
                r = await client.post(
                    f"{shop_url}/orders/{order_id}/refunds.json",
                    json=refund_data,
                    headers=headers,
                )
                if r.status_code in (200, 201):
                    refund = r.json().get("refund", {})
                    results.append({
                        "order_id": order_id,
                        "amount": total,
                        "status": "refunded",
                        "refund_id": refund.get("id"),
                    })
                else:
                    results.append({
                        "order_id": order_id,
                        "amount": total,
                        "status": "failed",
                        "error": r.text[:200],
                    })
            except httpx.HTTPError as e:
                results.append({
                    "order_id": order_id,
                    "amount": total,
                    "status": "error",
                    "error": str(e),
                })

    refunded_amount = sum(float(r["amount"]) for r in results if r["status"] == "refunded")
    if refunded_amount > 0:
        # 只在实际发生退款时累加当日计数（全部失败/空跑不应占用当日额度）
        await _record_daily_refund(str(current_user.id), refunded_amount)

    succeeded = sum(1 for r in results if r["status"] == "refunded")
    failed = sum(1 for r in results if r["status"] in ("failed", "error"))
    return {
        "summary": {
            "attempted": len(refundable),
            "succeeded": succeeded,
            "failed": failed,
            "skipped": len(orders) - len(refundable),  # 拉到的已付款订单里不满足阈值、本次不退的
            "requested_amount": round(requested_total, 2),
            "refunded_amount": round(refunded_amount, 2),
        },
        # 兼容旧字段
        "total_orders_checked": len(orders),
        "refundable_count": len(refundable),
        "refunded_count": succeeded,
        "total_refunded_amount": round(refunded_amount, 2),
        "results": results,
    }
