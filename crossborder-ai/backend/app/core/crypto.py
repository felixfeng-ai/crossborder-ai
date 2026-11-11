"""VeyaShip - 敏感数据加密工具

服务商 API Key、Shopify Token 等敏感字段在数据库中密文存储
（Fernet 对称加密），避免 DB 泄漏时凭证直接暴露。

- 优先使用独立的 DATA_ENCRYPTION_KEY（SHA-256 → Fernet key）；
- DATA_ENCRYPTION_PREVIOUS_KEYS 支持密钥轮换期间的旧密文解密；
- 未配置独立密钥时回退到 JWT_SECRET_KEY / SECRET_KEY，兼容存量部署；
- 本地开发无密钥时降级为明文存储，避免阻塞开箱即用。
- 存储格式：``enc:<base64 密文>`` —— ``enc:`` 前缀标记已加密；
  无前缀的旧数据按明文原样返回，兼容存量行。
"""

import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import settings

PREFIX = "enc:"


def _fernet_key(secret: str) -> bytes:
    """把任意高熵密钥确定性转换为 Fernet 所需的 32 字节密钥。"""
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


def _encryption_secrets() -> list[str]:
    """返回去重后的加密/解密候选密钥，顺序即优先级。"""
    candidates = [
        settings.DATA_ENCRYPTION_KEY,
        *settings.DATA_ENCRYPTION_PREVIOUS_KEYS.replace("\n", ",").split(","),
        settings.JWT_SECRET_KEY,
        settings.SECRET_KEY,
    ]
    return list(
        dict.fromkeys(
            secret.strip()
            for secret in candidates
            if secret and secret.strip()
        )
    )


def encrypt_value(plain: str | None) -> str:
    """加密。无可用密钥（本地开发）时原样返回明文。"""
    if not plain:
        return plain or ""
    secrets = _encryption_secrets()
    if not secrets:
        return plain
    return PREFIX + Fernet(_fernet_key(secrets[0])).encrypt(
        plain.encode("utf-8")
    ).decode("utf-8")


def decrypt_value(stored: str | None) -> str:
    """解密。``enc:`` 前缀 → 解密；失败或无前缀 → 按原样返回（兼容存量明文）。"""
    if not stored:
        return stored or ""
    if not stored.startswith(PREFIX):
        return stored
    for secret in _encryption_secrets():
        try:
            return Fernet(_fernet_key(secret)).decrypt(
                stored[len(PREFIX):].encode("utf-8")
            ).decode("utf-8")
        except Exception:
            continue
    # 所有候选密钥均失败时保留原值，避免把密文误当明文继续扩散。
    return stored


def mask_secret(value: str | None) -> str:
    """回显掩码：保留前 4 + 后 4，中间 ****，避免 API Key 明文暴露在前端。"""
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}****{value[-4:]}"
