"""Amazon Selling Partner API 授权与基础连接服务。"""

from typing import Any
from urllib.parse import urlencode

import httpx

from app.services import provider_config


LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
AMAZON_SELLER_CENTRAL_CONSENT_URL = "https://sellercentral.amazon.com/apps/authorize/consent"
SP_API_NA_BASE_URL = "https://sellingpartnerapi-na.amazon.com"


class AmazonSpApiService:
    """处理 LWA Token 交换和 Marketplace 授权验证。"""

    def _config(self) -> tuple[str, str, str, str]:
        app_id = provider_config.get("amazon", "app_id")
        client_id = provider_config.get("amazon", "client_id")
        client_secret = provider_config.get("amazon", "client_secret")
        redirect_uri = provider_config.get("amazon", "redirect_uri")
        if not app_id or not client_id or not client_secret or not redirect_uri:
            raise ValueError("Amazon SP-API 应用尚未配置")
        return app_id, client_id, client_secret, redirect_uri

    def build_consent_url(self, state: str) -> str:
        """生成 Seller Central 应用授权地址。"""
        app_id, _client_id, _client_secret, _redirect_uri = self._config()
        query = urlencode({
            "application_id": app_id,
            "state": state,
            "version": "beta",
        })
        return f"{AMAZON_SELLER_CENTRAL_CONSENT_URL}?{query}"

    async def exchange_authorization_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> dict[str, Any]:
        """用授权码换 LWA Refresh Token。"""
        _app_id, client_id, client_secret, _configured_redirect = self._config()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                LWA_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                },
            )
        if response.status_code != 200:
            raise ValueError("Amazon 授权码交换失败")
        return response.json()

    async def refresh_access_token(self, refresh_token: str) -> str:
        """用卖家 Refresh Token 换取短期 Access Token。"""
        _app_id, client_id, client_secret, _redirect_uri = self._config()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                LWA_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
        if response.status_code != 200:
            raise ValueError("Amazon 授权已失效，请重新绑定")
        access_token = response.json().get("access_token")
        if not access_token:
            raise ValueError("Amazon Access Token 获取失败")
        return access_token

    async def get_marketplace_participations(
        self,
        refresh_token: str,
    ) -> list[dict[str, Any]]:
        """验证卖家授权并获取参与站点。"""
        access_token = await self.refresh_access_token(refresh_token)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{SP_API_NA_BASE_URL}/sellers/v1/marketplaceParticipations",
                headers={"x-amz-access-token": access_token},
            )
        if response.status_code != 200:
            raise ValueError("Amazon Marketplace 授权校验失败")
        payload = response.json()
        return payload.get("payload") or []
