"""平台能力声明与授权连接接口。"""

import json
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value, encrypt_value
from app.core.database import get_db
from app.core.security import create_access_token, decode_token_safe
from app.dependencies import get_current_user
from app.models.platform_connection import PlatformConnection
from app.models.user import User
from app.services.amazon_sp_api import AmazonSpApiService


router = APIRouter(prefix="/platforms", tags=["Platforms"])


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
            },
            "amazon": {
                "auth_supported": True,
                "publish_supported": True,
                "mode": "listings_items",
                "reason": "需要 Amazon 应用开通 Listings Items 权限并完成卖家授权",
            },
            "temu": {
                "auth_supported": False,
                "publish_supported": False,
                "mode": "none",
                "reason": "Temu 开放平台发布尚未接入",
            },
            "shein": {
                "auth_supported": False,
                "publish_supported": False,
                "mode": "none",
                "reason": "SHEIN 开放平台发布尚未接入",
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
    from app.services import provider_config

    redirect_uri = provider_config.get("amazon", "redirect_uri")
    if not redirect_uri:
        raise ValueError("Amazon SP-API 回调地址尚未配置")
    return redirect_uri
