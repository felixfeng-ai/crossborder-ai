"""平台能力声明与授权连接接口。"""

import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value, encrypt_value
from app.core.database import get_db
from app.core.security import create_access_token, decode_token_safe
from app.dependencies import get_current_user
from app.models.platform_connection import PlatformConnection
from app.models.user import User
from app.services import provider_config
from app.services.amazon_sp_api import AmazonSpApiService
from app.services.temu_open_api import (
    TemuOpenApiService,
    normalize_region,
    resolve_gateway_region,
)
from app.services.temu_capabilities import derive_temu_capabilities
from app.services.temu_product_read import TemuProductReadService
from app.services.temu_order_read import TemuOrderReadService


router = APIRouter(prefix="/platforms", tags=["Platforms"])


class TemuConnectRequest(BaseModel):
    """Temu 回调授权站点选择。"""

    region: str = "global"


class TemuManualConnectRequest(BaseModel):
    """跨境卖家从 Temu 卖家中心复制的 Access Token。"""

    access_token: str = Field(min_length=8)
    region: str = "global"


@router.get("/capabilities")
async def get_platform_capabilities():
    """明确哪些平台具备真实发布能力，避免前端把文案平台当成铺货平台。"""
    return {
        "platforms": {
            "shopify": {
                "auth_supported": True,
                "publish_supported": True,
                "mode": "draft",
                "reason": "",
                "agent_actions": [
                    "listings.publish",
                    "listings.update",
                    "listing.media.attach",
                    "orders.fulfill",
                    "orders.cancel",
                    "orders.delay_notice",
                    "refunds.create",
                    "pricing.update",
                    "inventory.update",
                ],
            },
            "amazon": {
                "auth_supported": True,
                "publish_supported": True,
                "mode": "listings_items",
                "reason": "需要 Amazon 应用开通 Listings Items 权限并完成卖家授权",
                "agent_actions": [
                    "amazon.listings.publish",
                    "amazon.orders.fulfill",
                    "amazon.inventory.update",
                    "amazon.pricing.update",
                    "amazon.listings.update",
                    "amazon.listing.media.attach",
                    "amazon.listing.media.attach_assets",
                ],
                "read_actions": ["amazon.orders.sync"],
            },
            "temu": {
                "auth_supported": True,
                "publish_supported": True,
                "mode": "temu_v3",
                "reason": (
                    "需要 LOCAL/SEMI 店铺、V3 发布 scope 和商品回读权限；"
                    "真实类目与商品状态仍需测试店铺验收"
                ),
                "agent_actions": [
                    "temu.listings.submit",
                    "temu.orders.fulfill",
                    "temu.inventory.update",
                    "temu.pricing.submit",
                ],
                "read_actions": [
                    "temu.products.list",
                    "temu.orders.sync",
                    "temu.listings.status",
                ],
            },
            "shein": {
                "auth_supported": False,
                "publish_supported": False,
                "mode": "none",
                "reason": "SHEIN 开放平台发布尚未接入",
                "agent_actions": [],
            },
        }
    }


@router.post("/amazon/connect-url")
async def create_amazon_connect_url(
    current_user: User = Depends(get_current_user),
):
    """生成 Amazon Seller Central 授权地址。"""
    state = create_access_token(
        subject=str(current_user.id),
        extra_claims={"type": "amazon_oauth_state"},
        expires_delta=timedelta(minutes=10),
    )
    try:
        auth_url = AmazonSpApiService().build_consent_url(state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"auth_url": auth_url, "expires_in": 600}


@router.post("/temu/connect-url")
async def create_temu_connect_url(
    payload: Optional[TemuConnectRequest] = None,
    current_user: User = Depends(get_current_user),
):
    """生成 Temu 卖家中心回调授权地址。"""

    try:
        region = normalize_region(payload.region if payload else "global")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    state = create_access_token(
        subject=str(current_user.id),
        extra_claims={
            "type": "temu_oauth_state",
            "temu_region": region,
        },
        expires_delta=timedelta(minutes=10),
    )
    try:
        auth_url = TemuOpenApiService().build_consent_url(state, region)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "auth_url": auth_url,
        "expires_in": 600,
        "region": region,
    }


@router.get("/temu/callback")
async def temu_callback(
    request: Request,
    app_key: str = "",
    callback_host: str = "",
    code: str = "",
    state: str = "",
    db: AsyncSession = Depends(get_db),
):
    """处理 Temu 回调授权，用 code 换 Token 并加密保存连接。"""

    origin = str(request.base_url).rstrip("/")

    def redirect(**params: str) -> RedirectResponse:
        return RedirectResponse(
            url=f"{origin}/app/settings?{urlencode(params)}",
            status_code=302,
        )

    payload = decode_token_safe(state) if state else None
    if (
        payload is None
        or payload.get("type") != "temu_oauth_state"
        or not code
    ):
        return redirect(temu_error="invalid_state")
    try:
        user_id = UUID(payload.get("sub", ""))
        region = resolve_gateway_region(
            callback_host or str(payload.get("temu_region") or ""),
            default=str(payload.get("temu_region") or "global"),
        )
    except (ValueError, TypeError):
        return redirect(temu_error="invalid_state")

    configured_app_key = provider_config.get("temu", "app_key").strip()
    if app_key and configured_app_key and app_key != configured_app_key:
        return redirect(temu_error="invalid_app")

    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        return redirect(temu_error="invalid_state")

    service = TemuOpenApiService()
    try:
        token_info = await service.exchange_authorization_code(code, region)
        connection = await _upsert_temu_connection(
            db,
            user=user,
            region=region,
            access_token=str(token_info.get("accessToken") or ""),
            token_info=token_info,
        )
        if connection is None:
            raise ValueError("Temu 未返回有效店铺")
        await db.commit()
    except ValueError as exc:
        return redirect(temu_error=str(exc)[:120])
    return redirect(temu_connected="1")


@router.post("/temu/manual-connect")
async def manual_connect_temu(
    payload: TemuManualConnectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """验证卖家手动 Access Token 后绑定 Temu 店铺。"""

    try:
        region = normalize_region(payload.region)
        token_info = await TemuOpenApiService().get_token_info(
            payload.access_token,
            region,
        )
        connection = await _upsert_temu_connection(
            db,
            user=current_user,
            region=region,
            access_token=payload.access_token,
            token_info=token_info,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if connection is None:
        raise HTTPException(status_code=400, detail="Temu 未返回有效店铺")
    await db.commit()
    return {
        "ok": True,
        "connection": {
            "id": str(connection.id),
            "platform": "temu",
            "external_account_id": connection.external_account_id,
            "region": connection.marketplace_id,
            "status": connection.status,
        },
    }


@router.post("/temu/test")
async def test_temu_connection(
    connection_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """刷新 Temu Token 信息并验证店铺授权。"""

    query = select(PlatformConnection).where(
        PlatformConnection.user_id == current_user.id,
        PlatformConnection.platform == "temu",
    )
    if connection_id is not None:
        query = query.where(PlatformConnection.id == connection_id)
    query = query.order_by(PlatformConnection.updated_at.desc())
    connection = (await db.execute(query)).scalars().first()
    if connection is None:
        raise HTTPException(status_code=404, detail="Temu 店铺尚未绑定")

    try:
        credentials = json.loads(decrypt_value(connection.credentials))
        access_token = str(credentials.get("access_token") or "")
        region = normalize_region(
            connection.marketplace_id or credentials.get("region") or "global"
        )
        token_info = await TemuOpenApiService().get_token_info(access_token, region)
        refreshed = await _upsert_temu_connection(
            db,
            user=current_user,
            region=region,
            access_token=access_token,
            token_info=token_info,
            existing=connection,
        )
        await db.commit()
        return {
            "ok": True,
            "connection_id": str(refreshed.id),
            "mall_id": int(token_info.get("mallId") or 0),
            "expired_time": token_info.get("expiredTime"),
            "api_scope_count": len(token_info.get("apiScopeList") or []),
        }
    except Exception as exc:
        connection.status = "invalid"
        await db.commit()
        raise HTTPException(
            status_code=400,
            detail=f"Temu 连接测试失败：{str(exc)[:160]}",
        )


@router.get("/temu/scopes")
async def list_temu_scope_capabilities(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回每个 Temu 店铺的 API 权限能力；凭据永不返回。"""

    connections = (
        await db.execute(
            select(PlatformConnection)
            .where(
                PlatformConnection.user_id == current_user.id,
                PlatformConnection.platform == "temu",
            )
            .order_by(PlatformConnection.created_at.desc())
        )
    ).scalars().all()
    items = []
    for connection in connections:
        try:
            metadata = json.loads(connection.metadata_json or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        scopes = metadata.get("api_scope_list") or []
        if not isinstance(scopes, list):
            scopes = []
        items.append(
            {
                "id": str(connection.id),
                "account_name": connection.account_name,
                "external_account_id": connection.external_account_id,
                "region": connection.marketplace_id,
                "status": connection.status,
                "store_type": metadata.get("store_type") or "unknown",
                "scope_count": len(scopes),
                "capabilities": derive_temu_capabilities(
                    scopes,
                    store_type=metadata.get("store_type"),
                ),
            }
        )
    return {"connections": items}


@router.get("/temu/{connection_id}/products")
async def list_temu_products(
    connection_id: UUID,
    page_no: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按真实 scope 读取 Temu 商品，不泄露店铺凭据。"""

    try:
        return await TemuProductReadService(
            db,
            user_id=current_user.id,
        ).list_products(
            connection_id=connection_id,
            page_no=page_no,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/temu/{connection_id}/orders")
async def list_temu_orders(
    connection_id: UUID,
    page_number: int = 1,
    page_size: int = 20,
    parent_order_status: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """只对 LOCAL/SEMI 店铺读取 Temu 订单，不读取买家隐私。"""

    try:
        return await TemuOrderReadService(
            db,
            user_id=current_user.id,
        ).list_orders(
            connection_id=connection_id,
            page_number=page_number,
            page_size=page_size,
            parent_order_status=parent_order_status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/amazon/callback")
async def amazon_callback(
    request: Request,
    spapi_oauth_code: str = "",
    state: str = "",
    selling_partner_id: str = "",
    db: AsyncSession = Depends(get_db),
):
    """处理 Amazon 授权回调并加密保存卖家 Refresh Token。"""
    origin = str(request.base_url).rstrip("/")

    def redirect(**params: str) -> RedirectResponse:
        query = "&".join(f"{key}={value}" for key, value in params.items())
        return RedirectResponse(url=f"{origin}/app/settings?{query}", status_code=302)

    payload = decode_token_safe(state) if state else None
    if (
        payload is None
        or payload.get("type") != "amazon_oauth_state"
        or not spapi_oauth_code
    ):
        return redirect(amazon_error="invalid_state")
    try:
        user_id = UUID(payload.get("sub", ""))
    except (ValueError, TypeError):
        return redirect(amazon_error="invalid_state")

    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        return redirect(amazon_error="invalid_state")

    service = AmazonSpApiService()
    try:
        token_data = await service.exchange_authorization_code(
            spapi_oauth_code,
            provider_config_redirect_uri(),
        )
        refresh_token = token_data.get("refresh_token", "")
        if not refresh_token:
            raise ValueError("Amazon 未返回 Refresh Token")
        participations = await service.get_marketplace_participations(refresh_token)
    except ValueError as exc:
        return redirect(amazon_error=str(exc))

    active = next(
        (
            item for item in participations
            if (item.get("participation") or {}).get("isParticipating", True)
        ),
        None,
    )
    if active is None:
        return redirect(amazon_error="no_marketplace")

    marketplace = active.get("marketplace") or {}
    external_id = selling_partner_id or marketplace.get("id", "")
    existing = (
        await db.execute(
            select(PlatformConnection).where(
                PlatformConnection.user_id == user.id,
                PlatformConnection.platform == "amazon",
                PlatformConnection.external_account_id == external_id,
            )
        )
    ).scalar_one_or_none()

    encrypted_credentials = encrypt_value(
        json.dumps({"refresh_token": refresh_token}, ensure_ascii=False)
    )
    metadata = json.dumps(
        {
            "marketplaces": participations,
            "authorization_code_received": True,
        },
        ensure_ascii=False,
    )
    if existing is None:
        existing = PlatformConnection(
            user_id=user.id,
            platform="amazon",
            account_name=marketplace.get("name") or "Amazon",
            external_account_id=external_id,
            marketplace_id=marketplace.get("id"),
            credentials=encrypted_credentials,
            status="active",
            metadata_json=metadata,
        )
        db.add(existing)
    else:
        existing.account_name = marketplace.get("name") or existing.account_name
        existing.marketplace_id = marketplace.get("id") or existing.marketplace_id
        existing.credentials = encrypted_credentials
        existing.status = "active"
        existing.metadata_json = metadata
    await db.commit()
    return redirect(amazon_connected="1")


@router.get("/connections")
async def list_platform_connections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出当前用户平台连接，永不返回授权凭据。"""
    result = await db.execute(
        select(PlatformConnection)
        .where(PlatformConnection.user_id == current_user.id)
        .order_by(PlatformConnection.created_at.desc())
    )
    return {
        "connections": [
            {
                "id": str(item.id),
                "platform": item.platform,
                "account_name": item.account_name,
                "external_account_id": item.external_account_id,
                "marketplace_id": item.marketplace_id,
                "status": item.status,
                "created_at": str(item.created_at),
            }
            for item in result.scalars().all()
        ]
    }


@router.post("/amazon/test")
async def test_amazon_connection(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """刷新 Access Token 并验证 Amazon 卖家授权。"""
    connection = (
        await db.execute(
            select(PlatformConnection).where(
                PlatformConnection.user_id == current_user.id,
                PlatformConnection.platform == "amazon",
            )
        )
    ).scalar_one_or_none()
    if connection is None:
        raise HTTPException(status_code=404, detail="Amazon 店铺尚未绑定")
    try:
        credentials = json.loads(decrypt_value(connection.credentials))
        refresh_token = credentials.get("refresh_token", "")
        participations = await AmazonSpApiService().get_marketplace_participations(
            refresh_token
        )
        connection.status = "active"
        await db.commit()
        return {"ok": True, "marketplaces": participations}
    except Exception as exc:
        connection.status = "invalid"
        await db.commit()
        raise HTTPException(status_code=400, detail=f"Amazon 连接测试失败：{exc}")


def provider_config_redirect_uri() -> str:
    """读取 Amazon OAuth 回调地址；独立函数便于测试替换。"""
    redirect_uri = provider_config.get("amazon", "redirect_uri")
    if not redirect_uri:
        raise ValueError("Amazon SP-API 回调地址尚未配置")
    return redirect_uri


async def _upsert_temu_connection(
    db: AsyncSession,
    *,
    user: User,
    region: str,
    access_token: str,
    token_info: dict,
    existing: PlatformConnection | None = None,
) -> PlatformConnection | None:
    """按 mallId 幂等保存 Temu 店铺，Token 只进入加密字段。"""

    mall_id = str(
        token_info.get("mallId")
        or token_info.get("mall_id")
        or ""
    ).strip()
    access_token = access_token.strip()
    if not mall_id or not access_token:
        raise ValueError("Temu 授权缺少店铺编号或 Access Token")
    if existing is None:
        existing = (
            await db.execute(
                select(PlatformConnection).where(
                    PlatformConnection.user_id == user.id,
                    PlatformConnection.platform == "temu",
                    PlatformConnection.external_account_id == mall_id,
                )
            )
        ).scalar_one_or_none()

    expired_time = token_info.get("expiredTime") or token_info.get("expired_time")
    api_scope_list = token_info.get("apiScopeList") or []
    credentials = encrypt_value(
        json.dumps(
            {
                "access_token": access_token,
                "expired_time": expired_time,
                "region": region,
            },
            ensure_ascii=False,
        )
    )
    metadata = json.dumps(
        {
            "mall_id": mall_id,
            "expired_time": expired_time,
            "api_scope_list": (
                api_scope_list if isinstance(api_scope_list, list) else []
            ),
            "authorized_at": datetime.now(timezone.utc).isoformat(),
        },
        ensure_ascii=False,
    )
    account_name = (
        str(token_info.get("mallName") or "").strip()
        or f"Temu {region.upper()} 店铺 {mall_id}"
    )
    if existing is None:
        existing = PlatformConnection(
            user_id=user.id,
            platform="temu",
            account_name=account_name,
            external_account_id=mall_id,
            marketplace_id=region,
            credentials=credentials,
            status="active",
            metadata_json=metadata,
        )
        db.add(existing)
    else:
        existing.account_name = account_name
        existing.marketplace_id = region
        existing.credentials = credentials
        existing.status = "active"
        existing.metadata_json = metadata
    await db.flush()
    return existing
