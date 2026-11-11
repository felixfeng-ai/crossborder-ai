"""服务商运行时配置中心。

敏感字段加密后存入 SystemConfig；业务服务读取进程内缓存，避免每次 AI 调用查询数据库。
管理员更新当前进程立即刷新，其他 worker 由调度器周期同步。
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_value, encrypt_value, mask_secret
from app.models.system_config import SystemConfig


SECRET_FIELDS = {"api_key", "api_secret", "token", "client_secret"}

PROVIDER_FIELDS: dict[str, tuple[str, ...]] = {
    "deepseek": ("api_key", "model"),
    "onebound": ("api_key", "api_secret"),
    "justone": ("token",),
    "aliyun": ("api_key", "model"),
    "replicate": ("api_key", "model"),
    "shopify": ("api_key", "api_secret", "redirect_uri"),
    "amazon": ("app_id", "client_id", "client_secret", "redirect_uri"),
    "minimax": ("api_key", "base_url", "model", "resolution"),
}


def _env_fallback(provider: str, field: str) -> str:
    fallbacks = {
        ("deepseek", "api_key"): settings.DEEPSEEK_API_KEY or "",
        ("deepseek", "model"): settings.DEEPSEEK_MODEL,
        ("onebound", "api_key"): settings.ONEBOUND_API_KEY or "",
        ("onebound", "api_secret"): settings.ONEBOUND_API_SECRET or "",
        ("justone", "token"): settings.JUSTONE_API_TOKEN or "",
        ("aliyun", "api_key"): settings.ALIYUN_DASHSCOPE_API_KEY or "",
        ("aliyun", "model"): settings.ALIYUN_IMAGE_MODEL,
        ("replicate", "api_key"): settings.REPLICATE_API_KEY or "",
        ("replicate", "model"): settings.REPLICATE_MODEL,
        ("shopify", "api_key"): settings.SHOPIFY_API_KEY or "",
        ("shopify", "api_secret"): settings.SHOPIFY_API_SECRET or "",
        ("shopify", "redirect_uri"): settings.SHOPIFY_REDIRECT_URI or "",
        ("amazon", "app_id"): settings.AMAZON_APP_ID or "",
        ("amazon", "client_id"): settings.AMAZON_CLIENT_ID or "",
        ("amazon", "client_secret"): settings.AMAZON_CLIENT_SECRET or "",
        ("amazon", "redirect_uri"): settings.AMAZON_REDIRECT_URI or "",
        ("minimax", "api_key"): settings.MINIMAX_API_KEY or "",
        ("minimax", "base_url"): settings.MINIMAX_VIDEO_BASE_URL,
        ("minimax", "model"): settings.MINIMAX_VIDEO_MODEL,
        ("minimax", "resolution"): settings.MINIMAX_VIDEO_RESOLUTION,
    }
    return fallbacks.get((provider, field), "")


_cache: dict[str, dict[str, str]] = {}


def clear_cache() -> None:
    _cache.clear()


def get(provider: str, field: str, default: str | None = None) -> str:
    values = _cache.get(provider)
    if values is not None and field in values:
        return values[field]
    if default is not None:
        return default
    return _env_fallback(provider, field)


async def refresh(db: AsyncSession) -> None:
    """从加密的 SystemConfig 行重新加载全部服务商配置。"""
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.key.like("provider:%"))
    )
    loaded: dict[str, dict[str, str]] = {}
    for row in result.scalars().all():
        parts = row.key.split(":", 2)
        if len(parts) != 3:
            continue
        _, provider, field = parts
        if provider not in PROVIDER_FIELDS or field not in PROVIDER_FIELDS[provider]:
            continue
        value = decrypt_value(row.value or "")
        loaded.setdefault(provider, {})[field] = value

    # 兼容旧版 Onebound 设置接口，避免升级后已保存的 Key 丢失。
    legacy = await db.execute(
        select(SystemConfig).where(
            SystemConfig.key.in_(["onebound_api_key", "onebound_api_secret"])
        )
    )
    legacy_values = {
        row.key: decrypt_value(row.value or "")
        for row in legacy.scalars().all()
    }
    if legacy_values:
        onebound = loaded.setdefault("onebound", {})
        onebound.setdefault("api_key", legacy_values.get("onebound_api_key", ""))
        onebound.setdefault(
            "api_secret",
            legacy_values.get("onebound_api_secret", ""),
        )

    # 一次性原子替换进程内缓存，避免读取到只加载了一半的配置。
    _cache.clear()
    _cache.update(loaded)


async def update_provider(
    db: AsyncSession,
    provider: str,
    values: dict[str, Any],
) -> None:
    """更新指定服务商配置并立即刷新当前进程缓存。"""
    if provider not in PROVIDER_FIELDS:
        raise KeyError(provider)

    allowed = set(PROVIDER_FIELDS[provider])
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"未知配置项：{', '.join(sorted(unknown))}")

    for field, raw_value in values.items():
        value = "" if raw_value is None else str(raw_value).strip()
        # 密钥类字段落库前加密，普通模型名和回调地址按明文保存。
        stored = encrypt_value(value) if field in SECRET_FIELDS else value
        key = f"provider:{provider}:{field}"
        row = (
            await db.execute(
                select(SystemConfig).where(SystemConfig.key == key)
            )
        ).scalar_one_or_none()
        if row is None:
            db.add(SystemConfig(key=key, value=stored))
        else:
            row.value = stored

    await db.flush()
    await refresh(db)


def provider_status(provider: str) -> dict[str, Any]:
    """返回可安全下发给管理端的服务商状态，绝不回显密钥明文。"""
    if provider not in PROVIDER_FIELDS:
        raise KeyError(provider)
    fields: dict[str, str] = {}
    for field in PROVIDER_FIELDS[provider]:
        value = get(provider, field)
        fields[field] = mask_secret(value) if field in SECRET_FIELDS else value
    # 不同服务商的必填凭据字段不同，Just One 使用 token 而不是 api_key。
    required = "token" if provider == "justone" else "api_key"
    return {
        "configured": bool(get(provider, required)),
        "required_field": required,
        "fields": fields,
    }


def all_provider_status() -> dict[str, dict[str, Any]]:
    return {
        provider: provider_status(provider)
        for provider in PROVIDER_FIELDS
    }
