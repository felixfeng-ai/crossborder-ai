"""VeyaShip - 设置路由（爬虫配置 + 品牌调性）"""

import json
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value, encrypt_value, mask_secret
from app.core.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models.persona import Persona
from app.models.system_config import SystemConfig
from app.models.user import User
from app.services import provider_config
from pydantic import BaseModel, Field

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("/providers")
async def list_provider_configs(
    admin: User = Depends(require_admin),
):
    return {"providers": provider_config.all_provider_status()}


@router.put("/providers/{provider}")
async def update_provider_config(
    provider: str,
    payload: dict[str, str] = Body(...),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        await provider_config.update_provider(db, provider, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="未知的服务商")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "provider": provider,
        **provider_config.provider_status(provider),
    }


# ── 白名单管理（测试账号免限制） ────────────────────────────

class WhitelistRequest(BaseModel):
    email: str = Field(..., description="要添加/移除的邮箱")


@router.post("/whitelist/add")
async def add_whitelist(
    payload: WhitelistRequest,
    admin: User = Depends(require_admin),
):
    """添加白名单账号（仅管理员；白名单可绕过套餐限制，绝不能开放给普通用户）"""
    from app.core.access_control import add_whitelist as _add
    _add(payload.email)
    return {"message": f"已添加白名单: {payload.email}"}


@router.post("/whitelist/remove")
async def remove_whitelist(
    payload: WhitelistRequest,
    admin: User = Depends(require_admin),
):
    """移除白名单账号（仅管理员）"""
    from app.core.access_control import remove_whitelist as _remove
    _remove(payload.email)
    return {"message": f"已移除白名单: {payload.email}"}


@router.get("/whitelist")
async def list_whitelist(
    admin: User = Depends(require_admin),
):
    """查看所有白名单账号（仅管理员）"""
    from app.core.access_control import WHITELIST_EMAILS
    return {"emails": list(WHITELIST_EMAILS)}

# ════════════════════════════════════════════════════════════════
# 爬虫配置
# ════════════════════════════════════════════════════════════════

class ScrapingConfigRequest(BaseModel):
    api_key: str = Field("", description="Onebound API Key")
    api_secret: str = Field("", description="Onebound API Secret")

class ScrapingConfigResponse(BaseModel):
    api_key: str = ""
    api_secret: str = ""
    configured: bool = False

@router.get("/scraping", response_model=ScrapingConfigResponse)
async def get_scraping_config(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.key.in_(["onebound_api_key", "onebound_api_secret"]))
    )
    config = {row.key: row.value or "" for row in result.scalars().all()}
    # 密文解密后掩码回显，API Key 明文不落前端
    return ScrapingConfigResponse(
        api_key=mask_secret(decrypt_value(config.get("onebound_api_key", ""))),
        api_secret=mask_secret(decrypt_value(config.get("onebound_api_secret", ""))),
        configured=bool(config.get("onebound_api_key")),
    )

@router.put("/scraping", response_model=ScrapingConfigResponse)
async def update_scraping_config(
    payload: ScrapingConfigRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # 仅管理员可改全局 Onebound 密钥（任意用户覆写会导致平台级服务不可用/滥用）
    # 落库前加密（Fernet），DB 泄漏时服务商密钥不暴露
    encrypted = {
        "onebound_api_key": encrypt_value(payload.api_key),
        "onebound_api_secret": encrypt_value(payload.api_secret),
    }
    for key, value in encrypted.items():
        result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
        existing = result.scalar_one_or_none()
        if existing:
            existing.value = value
        else:
            db.add(SystemConfig(key=key, value=value))
    await db.flush()
    await provider_config.refresh(db)
    return ScrapingConfigResponse(
        api_key=mask_secret(payload.api_key),
        api_secret=mask_secret(payload.api_secret),
        configured=bool(payload.api_key),
    )


# ════════════════════════════════════════════════════════════════
# 品牌调性（F5 Persona）
# ════════════════════════════════════════════════════════════════

class PersonaRequest(BaseModel):
    brand_name: Optional[str] = Field(None, max_length=200)
    tagline: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    tone: str = "professional"
    tone_custom: Optional[str] = Field(None, max_length=500)
    banned_words: list[str] = []
    # Brand Kit 扩展字段（CAP-04，均可空）
    target_market: Optional[str] = Field(None, max_length=200, description="目标市场/站点，如 amazon.com、日本站")
    product_category: Optional[str] = Field(None, max_length=200, description="主营类目")
    image_style: Optional[str] = Field(None, max_length=500, description="图片风格提示词")

class PersonaResponse(BaseModel):
    brand_name: Optional[str] = None
    tagline: Optional[str] = None
    description: Optional[str] = None
    tone: str = "professional"
    tone_custom: Optional[str] = None
    banned_words: list[str] = []
    # Brand Kit 扩展字段（CAP-04）
    target_market: Optional[str] = None
    product_category: Optional[str] = None
    image_style: Optional[str] = None


@router.get("/persona", response_model=PersonaResponse)
async def get_persona(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的品牌调性配置"""
    result = await db.execute(select(Persona).where(Persona.user_id == current_user.id))
    p = result.scalar_one_or_none()
    if not p:
        return PersonaResponse()
    return PersonaResponse(
        brand_name=p.brand_name,
        tagline=p.tagline,
        description=p.description,
        tone=p.tone,
        tone_custom=p.tone_custom,
        banned_words=json.loads(p.banned_words) if p.banned_words else [],
        target_market=p.target_market,
        product_category=p.product_category,
        image_style=p.image_style,
    )


@router.put("/persona", response_model=PersonaResponse)
async def update_persona(
    payload: PersonaRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """保存品牌调性配置"""
    result = await db.execute(select(Persona).where(Persona.user_id == current_user.id))
    persona = result.scalar_one_or_none()
    if not persona:
        persona = Persona(user_id=current_user.id)
        db.add(persona)
    persona.brand_name = payload.brand_name
    persona.tagline = payload.tagline
    persona.description = payload.description
    persona.tone = payload.tone
    persona.tone_custom = payload.tone_custom
    persona.banned_words = json.dumps(payload.banned_words, ensure_ascii=False)
    persona.target_market = payload.target_market
    persona.product_category = payload.product_category
    persona.image_style = payload.image_style
    await db.flush()
    return PersonaResponse(
        brand_name=persona.brand_name,
        tagline=persona.tagline,
        description=persona.description,
        tone=persona.tone,
        tone_custom=persona.tone_custom,
        banned_words=json.loads(persona.banned_words) if persona.banned_words else [],
        target_market=persona.target_market,
        product_category=persona.product_category,
        image_style=persona.image_style,
    )
