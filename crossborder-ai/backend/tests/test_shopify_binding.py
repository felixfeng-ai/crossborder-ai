"""VeyaShip - Shopify 店铺绑定闭环测试（CAP-02）

覆盖：
1. normalize_shop 合法输入（裸域名 / 带 .myshopify.com 全域名 / 空白）
2. normalize_shop 非法输入 → 400
3. GET /auth：未配置 Shopify 应用 → 400；无 shop → 400；未登录 → 401
4. GET /auth：302 跳 Shopify 授权页且不双重域名
5. GET /callback：缺 state → ?error=state_missing
6. GET /callback：state 过期 / 用户不存在 / 店铺不一致 → ?error=invalid_state
7. GET /callback：hmac 错误 → ?error=invalid_hmac
8. GET /callback：成功路径（mock 换 token）→ 落库 shop_name 为裸域名、token 带 enc: 前缀
9. GET /channels：access_token 永不下发明文（只回显掩码）
10. DELETE /channels/{id}：他人渠道 → 403；本人 → ok 并删除
"""

import hashlib
import hmac as hmac_mod
import time
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.core.crypto import decrypt_value
from app.core.security import create_access_token, decode_token
from app.models.shopify_channel import ShopifyChannel
import app.routers.shopify as shopify_router

JWT_TEST_SECRET = "test-jwt-secret-key-0123456789-abcd"
SHOPIFY_KEY = "test-api-key"
SHOPIFY_SECRET = "test-api-secret"
SHOPIFY_REDIRECT = "https://app.example.com/api/v1/shopify/callback"


def _configure(monkeypatch) -> None:
    """统一配置：JWT 密钥 + Shopify 应用三要素（测试内实例属性可 monkeypatch.setattr）。"""
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", JWT_TEST_SECRET)
    monkeypatch.setattr(settings, "SHOPIFY_API_KEY", SHOPIFY_KEY)
    monkeypatch.setattr(settings, "SHOPIFY_API_SECRET", SHOPIFY_SECRET)
    monkeypatch.setattr(settings, "SHOPIFY_REDIRECT_URI", SHOPIFY_REDIRECT)


async def _register(client, email=None):
    """注册一个测试用户并返回 (token, headers)。

    不依赖 conftest 的 auth_token fixture：本文件需要在注册前就完成 JWT 密钥 patch，
    保证注册 token 与后续校验/加密使用同一个密钥。
    """
    email = email or f"u{time.time_ns()}@test.com"
    data = {"email": email, "username": email.split("@")[0], "password": "testpass123"}
    resp = await client.post("/api/v1/auth/register", json=data)
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return token, {"Authorization": f"Bearer {token}"}


# ── normalize_shop ─────────────────────────────────────────────

def test_normalize_shop_valid_bare():
    """合法裸子域原样返回。"""
    assert shopify_router.normalize_shop("my-store") == "my-store"
    assert shopify_router.normalize_shop("yourshop") == "yourshop"


def test_normalize_shop_strips_domain_suffix_and_blank():
    """带 .myshopify.com 后缀 / 前后空白的输入剥壳成裸子域。"""
    assert shopify_router.normalize_shop("yourshop.myshopify.com") == "yourshop"
    assert shopify_router.normalize_shop("  yourshop.myshopify.com  ") == "yourshop"
    assert shopify_router.normalize_shop("   mystore   ") == "mystore"


@pytest.mark.parametrize("bad", [
    None,
    "",
    "   ",
    "UPPER",
    "under_score",
    "-leading",
    "a.b",
    "has space",
    "中文店铺",
    "..bad..",
])
def test_normalize_shop_rejects_invalid(bad):
    """非法输入抛 400 + 中文提示。"""
    with pytest.raises(HTTPException) as exc:
        shopify_router.normalize_shop(bad)
    assert exc.value.status_code == 400
    assert exc.value.detail == "店铺域名格式不正确"


# ── GET /auth ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auth_unconfigured_returns_400(client, monkeypatch):
    """未配置 Shopify 应用（Key/Secret/回调任一缺失）→ 400 中文。"""
    monkeypatch.setattr(settings, "SHOPIFY_API_KEY", None)
    monkeypatch.setattr(settings, "SHOPIFY_API_SECRET", None)
    monkeypatch.setattr(settings, "SHOPIFY_REDIRECT_URI", None)
    _, headers = await _register(client)
    resp = await client.get("/api/v1/shopify/auth", params={"shop": "mystore"}, headers=headers)
    assert resp.status_code == 400
    assert "Shopify 应用尚未配置" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_auth_requires_login(client, monkeypatch):
    """未登录访问 /auth → 401（绑定必须登录用户发起）。"""
    _configure(monkeypatch)
    resp = await client.get("/api/v1/shopify/auth", params={"shop": "mystore"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_missing_shop_returns_400(client, monkeypatch):
    """缺少 shop 参数 → 400 中文（而非 FastAPI 的 422）。"""
    _configure(monkeypatch)
    _, headers = await _register(client)
    resp = await client.get("/api/v1/shopify/auth", headers=headers)
    assert resp.status_code == 400
    assert "店铺域名格式不正确" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_auth_invalid_shop_returns_400(client, monkeypatch):
    """非法店铺名 → 400 中文。"""
    _configure(monkeypatch)
    _, headers = await _register(client)
    resp = await client.get("/api/v1/shopify/auth", params={"shop": "UPPER.SHOP"}, headers=headers)
    assert resp.status_code == 400
    assert "店铺域名格式不正确" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_auth_success_302_and_no_double_domain(client, monkeypatch):
    """合法输入 → 302 跳授权页；传全域名也不产生双重域名。"""
    _configure(monkeypatch)
    _, headers = await _register(client)
    resp = await client.get(
        "/api/v1/shopify/auth",
        params={"shop": "mystore.myshopify.com"},
        headers=headers,
    )
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert location.startswith("https://mystore.myshopify.com/admin/oauth/authorize?")
    assert "mystore.myshopify.com.myshopify.com" not in location
    assert "client_id=" in location
    assert "scope=" in location and "write_products" in location
    assert "redirect_uri=" in location
    assert "state=" in location


@pytest.mark.asyncio
async def test_connect_returns_auth_url_without_exposing_jwt(client, monkeypatch):
    """登录态 POST 换取授权 URL，前端不需要把 JWT 拼进跳转地址。"""
    _configure(monkeypatch)
    token, headers = await _register(client)
    resp = await client.post(
        "/api/v1/shopify/connect",
        json={"shop": "mystore.myshopify.com"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    auth_url = resp.json()["auth_url"]
    assert auth_url.startswith("https://mystore.myshopify.com/admin/oauth/authorize?")
    assert "mystore.myshopify.com.myshopify.com" not in auth_url
    assert f"token={token}" not in auth_url


# ── GET /callback 校验失败分支 ─────────────────────────────────

@pytest.mark.asyncio
async def test_callback_missing_state_redirects(client, monkeypatch):
    """缺 state → 302 到前端 ?error=state_missing。"""
    _configure(monkeypatch)
    resp = await client.get(
        "/api/v1/shopify/callback",
        params={"code": "c", "shop": "mystore.myshopify.com", "timestamp": str(int(time.time()))},
    )
    assert resp.status_code == 302
    assert "error=state_missing" in resp.headers["location"]


@pytest.mark.asyncio
async def test_callback_expired_state_invalid(client, monkeypatch):
    """state 过期（decode 失败）→ ?error=invalid_state。"""
    _configure(monkeypatch)
    token, _ = await _register(client)
    uid = decode_token(token)["sub"]
    state = create_access_token(
        subject=uid,
        extra_claims={"type": "shopify_oauth_state", "shop": "mystore", "ts": int(time.time())},
        expires_delta=timedelta(minutes=-5),  # 已过期
    )
    resp = await client.get(
        "/api/v1/shopify/callback",
        params={"code": "c", "shop": "mystore.myshopify.com", "state": state,
                "timestamp": str(int(time.time()))},
    )
    assert resp.status_code == 302
    assert "error=invalid_state" in resp.headers["location"]


@pytest.mark.asyncio
async def test_callback_unknown_user_invalid(client, monkeypatch):
    """state 对应不到已存在用户 → ?error=invalid_state。"""
    _configure(monkeypatch)
    state = create_access_token(
        subject=str(uuid4()),
        extra_claims={"type": "shopify_oauth_state", "shop": "mystore", "ts": int(time.time())},
        expires_delta=timedelta(minutes=10),
    )
    resp = await client.get(
        "/api/v1/shopify/callback",
        params={"code": "c", "shop": "mystore.myshopify.com", "state": state,
                "timestamp": str(int(time.time()))},
    )
    assert resp.status_code == 302
    assert "error=invalid_state" in resp.headers["location"]


@pytest.mark.asyncio
async def test_callback_shop_mismatch_invalid(client, monkeypatch):
    """state 里店铺与回调 shop 不一致 → ?error=invalid_state。"""
    _configure(monkeypatch)
    token, _ = await _register(client)
    uid = decode_token(token)["sub"]
    state = create_access_token(
        subject=uid,
        extra_claims={"type": "shopify_oauth_state", "shop": "alpha", "ts": int(time.time())},
        expires_delta=timedelta(minutes=10),
    )
    resp = await client.get(
        "/api/v1/shopify/callback",
        params={"code": "c", "shop": "beta.myshopify.com", "state": state,
                "timestamp": str(int(time.time()))},
    )
    assert resp.status_code == 302
    assert "error=invalid_state" in resp.headers["location"]


@pytest.mark.asyncio
async def test_callback_wrong_hmac_invalid(client, monkeypatch):
    """hmac 校验失败 → ?error=invalid_hmac。"""
    _configure(monkeypatch)
    token, _ = await _register(client)
    uid = decode_token(token)["sub"]
    state = create_access_token(
        subject=uid,
        extra_claims={"type": "shopify_oauth_state", "shop": "mystore", "ts": int(time.time())},
        expires_delta=timedelta(minutes=10),
    )
    params = {
        "code": "authcode123",
        "shop": "mystore.myshopify.com",
        "state": state,
        "timestamp": str(int(time.time())),
        "hmac": "0" * 64,  # 错误的签名
    }
    resp = await client.get("/api/v1/shopify/callback", params=params)
    assert resp.status_code == 302
    assert "error=invalid_hmac" in resp.headers["location"]


@pytest.mark.asyncio
async def test_callback_token_exchange_failure_invalid(client, monkeypatch, db_session):
    """换 token 失败（mock 返回 400）→ ?error=token_exchange。"""
    _configure(monkeypatch)
    token, _ = await _register(client)
    uid = decode_token(token)["sub"]

    class _FakeResp:
        status_code = 400

        def json(self):
            return {}

        text = '{"error": "invalid_request"}'

    class _FakeFailClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, **kw):
            return _FakeResp()

    monkeypatch.setattr(shopify_router.httpx, "AsyncClient", _FakeFailClient)

    state = create_access_token(
        subject=uid,
        extra_claims={"type": "shopify_oauth_state", "shop": "mystore", "ts": int(time.time())},
        expires_delta=timedelta(minutes=10),
    )
    params = {
        "code": "authcode123",
        "shop": "mystore.myshopify.com",
        "state": state,
        "timestamp": str(int(time.time())),
    }
    message = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    params["hmac"] = hmac_mod.new(SHOPIFY_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()

    resp = await client.get("/api/v1/shopify/callback", params=params)
    assert resp.status_code == 302
    assert "error=token_exchange" in resp.headers["location"]


# ── GET /callback 成功路径 + 落库 + /channels + DELETE ─────────

@pytest.mark.asyncio
async def test_callback_success_persists_channel_and_masked(client, monkeypatch, db_session):
    """完整成功路径：合法 hmac → mock 换 token → 加密落库；GET /channels 只回显掩码。"""
    _configure(monkeypatch)
    token, headers = await _register(client)
    uid = UUID(decode_token(token)["sub"])

    class _FakeResp:
        status_code = 200

        def json(self):
            return {"access_token": "shpat_fake_123"}

        text = ""

    class _FakeTokenClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, **kw):
            return _FakeResp()

    monkeypatch.setattr(shopify_router.httpx, "AsyncClient", _FakeTokenClient)

    state = create_access_token(
        subject=str(uid),
        extra_claims={"type": "shopify_oauth_state", "shop": "mystore", "ts": int(time.time())},
        expires_delta=timedelta(minutes=10),
    )
    params = {
        "code": "authcode123",
        "shop": "mystore.myshopify.com",
        "state": state,
        "timestamp": str(int(time.time())),
    }
    message = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    params["hmac"] = hmac_mod.new(SHOPIFY_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()

    resp = await client.get("/api/v1/shopify/callback", params=params)
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert "bound=1" in location
    assert "shop=mystore" in location

    # 落库断言：裸店铺名 + 完整域名 + 加密 token（enc: 前缀），且能正确解密
    result = await db_session.execute(
        select(ShopifyChannel).where(ShopifyChannel.user_id == uid)
    )
    ch = result.scalar_one()
    assert ch.shop_name == "mystore"  # 关键：不再存全域名
    assert ch.shop_domain == "mystore.myshopify.com"
    assert ch.is_active is True
    assert ch.access_token.startswith("enc:")
    assert decrypt_value(ch.access_token) == "shpat_fake_123"

    # GET /channels：返回裸名 + 域名 + is_active，access_token 永不下发（仅掩码）
    resp2 = await client.get("/api/v1/shopify/channels", headers=headers)
    assert resp2.status_code == 200
    items = resp2.json()
    assert len(items) == 1
    item = items[0]
    assert item["shop_name"] == "mystore"
    assert item["shop_domain"] == "mystore.myshopify.com"
    assert item["is_active"] is True
    assert "access_token" not in item
    assert "****" in item["token_masked"]


@pytest.mark.asyncio
async def test_unbind_owner_check(client, monkeypatch, db_session):
    """DELETE /channels/{id}：他人渠道 403，本人 ok 且记录删除。"""
    _configure(monkeypatch)
    token_a, headers_a = await _register(client, f"a{time.time_ns()}@test.com")
    _, headers_b = await _register(client, f"b{time.time_ns()}@test.com")
    uid_a = UUID(decode_token(token_a)["sub"])

    ch = ShopifyChannel(
        user_id=uid_a,
        shop_name="mystore",
        shop_domain="mystore.myshopify.com",
        access_token=shopify_router.encrypt_value("shpat_owner"),
    )
    db_session.add(ch)
    await db_session.commit()
    cid = str(ch.id)

    # 用户 B 删除 A 的渠道 → 403（owner 校验）
    resp_b = await client.delete(f"/api/v1/shopify/channels/{cid}", headers=headers_b)
    assert resp_b.status_code == 403
    assert "无权操作" in resp_b.json()["detail"]

    # 用户 A 删除自己的渠道 → ok，且行已删
    resp_a = await client.delete(f"/api/v1/shopify/channels/{cid}", headers=headers_a)
    assert resp_a.status_code == 200
    assert resp_a.json() == {"ok": True}

    gone = await db_session.execute(select(ShopifyChannel).where(ShopifyChannel.id == UUID(cid)))
    assert gone.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_unbind_not_found_404(client, monkeypatch):
    """删除不存在的渠道 → 404。"""
    _configure(monkeypatch)
    _, headers = await _register(client)
    resp = await client.delete(f"/api/v1/shopify/channels/{uuid4()}", headers=headers)
    assert resp.status_code == 404
