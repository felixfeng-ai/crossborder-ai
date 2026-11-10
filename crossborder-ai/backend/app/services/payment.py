"""VeyaShip 支付服务。

封装 Creem.io 结账、订阅管理和 webhook 验签。
"""

import hashlib
import hmac
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings


class PaymentService:
    """Creem.io 支付服务。

    核心安全边界：任何 webhook 都必须先完成 HMAC-SHA256 验签，
    未配置密钥或签名异常时一律拒绝，不能降级为放行。
    """

    CREEM_API_URL = "https://api.creem.io/v1"

    def __init__(self):
        self.api_key = settings.CREEM_API_KEY
        self.webhook_secret = settings.CREEM_WEBHOOK_SECRET

    def _headers(self) -> Dict[str, str]:
        # Creem 官方 API 使用 x-api-key，而不是通用的 Bearer Token。
        return {
            "x-api-key": self.api_key or "",
            "Content-Type": "application/json",
        }

    async def create_checkout_session(
        self,
        plan_name: str,
        billing_interval: str,
        success_url: str,
        cancel_url: str,
        customer_email: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a Creem.io checkout session.

        Args:
            plan_name: Subscription plan identifier.
            billing_interval: monthly or yearly.
            success_url: Redirect on successful payment.
            cancel_url: Redirect on cancellation.
            customer_email: Pre-fill customer email.
            metadata: Additional data to attach.

        Returns:
            Checkout session data with URL.
        """
        payload = {
            "plan": plan_name,
            "billing_interval": billing_interval,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "mode": "subscription",
        }
        if customer_email:
            payload["customer_email"] = customer_email
        if metadata:
            payload["metadata"] = metadata

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.CREEM_API_URL}/checkout/sessions",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def verify_webhook(self, payload: bytes, signature: str) -> bool:
        """校验 Creem.io webhook 签名。

        Args:
            payload: 原始请求体字节，不能使用重新序列化后的 JSON。
            signature: `creem-signature` 请求头中的十六进制签名。

        Returns:
            签名合法返回 True；任何配置或格式异常均返回 False。
        """
        # 未配置密钥时必须 fail closed，避免伪造事件触发开通套餐或加积分。
        if not self.webhook_secret or not signature:
            return False

        normalized = signature.strip().lower()
        if len(normalized) != 64:
            return False
        try:
            provided = bytes.fromhex(normalized)
        except ValueError:
            # 非十六进制签名直接拒绝，不能把格式错误当成验签通过。
            return False

        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).digest()
        # 固定时间比较，降低时序侧信道风险。
        return hmac.compare_digest(expected, provided)

    async def cancel_subscription(self, creem_subscription_id: str) -> bool:
        """Cancel a subscription in Creem.io.

        Args:
            creem_subscription_id: The Creem.io subscription ID.

        Returns:
            True if cancellation succeeded.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.CREEM_API_URL}/subscriptions/{creem_subscription_id}/cancel",
                headers=self._headers(),
            )
            return response.is_success

    async def get_subscription(self, creem_subscription_id: str) -> Optional[Dict[str, Any]]:
        """Get subscription details from Creem.io."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.CREEM_API_URL}/subscriptions/{creem_subscription_id}",
                headers=self._headers(),
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
