"""Temu 开放平台网关、签名与授权服务。"""

import hashlib
import json
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from app.services import provider_config


TEMU_GATEWAY_URLS = {
    "us": "https://openapi-b-us.temu.com/openapi/router",
    "eu": "https://openapi-b-eu.temu.com/openapi/router",
    "global": "https://openapi-b-global.temu.com/openapi/router",
}

# 跨境卖家与本地卖家的回调授权入口不同；US 和 GLOBAL 共用美国卖家中心。
TEMU_SELLER_CENTER_URLS = {
    "us": "https://seller.temu.com",
    "eu": "https://seller-eu.temu.com",
    "global": "https://seller.temu.com",
}

TEMU_REGION_ALIASES = {
    "us": "us",
    "usa": "us",
    "united_states": "us",
    "eu": "eu",
    "europe": "eu",
    "global": "global",
}


class TemuOpenApiError(ValueError):
    """保留 Temu 业务错误码，供动作层做精确幂等和恢复判断。"""

    def __init__(
        self,
        message: str,
        *,
        error_code: int | str | None,
        error_message: str = "",
    ):
        super().__init__(message)
        self.error_code = error_code
        self.error_message = error_message


def normalize_region(value: str | None) -> str:
    """把卖家站点统一成 us、eu 或 global。"""

    normalized = str(value or "").strip().lower()
    region = TEMU_REGION_ALIASES.get(normalized)
    if region is None:
        raise ValueError("Temu 站点区域必须是 us、eu 或 global")
    return region


def resolve_gateway_region(value: str | None, default: str = "global") -> str:
    """从区域名或回调 host 解析实际网关区域。"""

    normalized = str(value or "").strip().lower()
    if "openapi-b-us" in normalized:
        return "us"
    if "openapi-b-eu" in normalized:
        return "eu"
    if "openapi-b-global" in normalized:
        return "global"
    if not normalized:
        return normalize_region(default)
    return normalize_region(normalized)


def gateway_url(region: str) -> str:
    """返回指定区域的官方 POST 网关。"""

    return TEMU_GATEWAY_URLS[normalize_region(region)]


class TemuOpenApiService:
    """封装 Temu 请求签名、授权码交换和 Token 验权。"""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        # 测试可注入 MockTransport；生产保持默认 TLS 网络栈。
        self._transport = transport

    def _app_credentials(self) -> tuple[str, str]:
        app_key = provider_config.get("temu", "app_key").strip()
        app_secret = provider_config.get("temu", "app_secret").strip()
        if not app_key or not app_secret:
            raise ValueError("Temu 开放平台应用尚未配置")
        return app_key, app_secret

    def _redirect_uri(self) -> str:
        redirect_uri = provider_config.get("temu", "redirect_uri").strip()
        if not redirect_uri:
            raise ValueError("Temu 授权回调地址尚未配置")
        return redirect_uri

    def _default_region(self) -> str:
        return normalize_region(
            provider_config.get("temu", "region") or "global"
        )

    @staticmethod
    def generate_sign(params: dict[str, Any], app_secret: str) -> str:
        """按 Temu 官方规则生成大写 MD5 签名。

        字符串使用原值；列表和对象使用紧凑 JSON。`None` 与 sign 本身不参与
        签名，避免客户端序列化差异引入不可排查的验签失败。
        """

        parts: list[str] = []
        for key, value in sorted(params.items(), key=lambda item: str(item[0])):
            if key == "sign" or value is None:
                continue
            if isinstance(value, str):
                rendered = value
            else:
                rendered = json.dumps(
                    value,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            parts.append(f"{key}{rendered}")
        raw = f"{app_secret}{''.join(parts)}{app_secret}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()

    def build_consent_url(self, state: str, region: str | None = None) -> str:
        """生成卖家中心回调授权地址，不把 App Secret 暴露到浏览器。"""

        app_key, _app_secret = self._app_credentials()
        redirect_uri = self._redirect_uri()
        selected_region = normalize_region(region or self._default_region())
        query = urlencode(
            {
                "appKey": app_key,
                "redirect_uri": redirect_uri,
                "state": state,
            }
        )
        return (
            f"{TEMU_SELLER_CENTER_URLS[selected_region]}"
            f"/open-platform/client-manage/authorization?{query}"
        )

    async def _post(
        self,
        *,
        api_type: str,
        access_token: str,
        region: str,
        request_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """发送已签名 JSON 请求，并统一校验 Temu 业务错误。"""

        if not access_token.strip():
            raise ValueError("Temu Access Token 不能为空")
        app_key, app_secret = self._app_credentials()
        selected_region = normalize_region(region)
        payload: dict[str, Any] = {
            "app_key": app_key,
            "access_token": access_token.strip(),
            "data_type": "JSON",
            "timestamp": int(time.time()),
            "type": api_type,
            "version": "V1",
        }
        if request_data:
            reserved = set(payload) | {"sign"}
            overlap = reserved.intersection(request_data)
            if overlap:
                raise ValueError(
                    f"Temu 请求参数包含保留字段：{', '.join(sorted(overlap))}"
                )
            payload.update(request_data)
        payload["sign"] = self.generate_sign(payload, app_secret)

        try:
            async with httpx.AsyncClient(
                timeout=30,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    gateway_url(selected_region),
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
        except httpx.HTTPError as exc:
            raise ValueError("Temu 开放平台连接失败，请稍后重试") from exc
        if response.status_code != 200:
            raise ValueError(f"Temu 开放平台请求失败：HTTP {response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            raise ValueError("Temu 开放平台返回了非 JSON 响应") from exc
        if not isinstance(body, dict):
            raise ValueError("Temu 开放平台响应格式不正确")

        error_code = body.get("errorCode")
        success = body.get("success")
        if success is False or error_code not in (None, 0, 1000000):
            message = str(body.get("errorMsg") or "").strip()
            try:
                normalized_code = int(error_code)
            except (TypeError, ValueError):
                normalized_code = error_code
            raise TemuOpenApiError(
                f"Temu 开放平台返回错误 {error_code or 'unknown'}"
                f"{f'：{message}' if message else ''}",
                error_code=normalized_code,
                error_message=message,
            )
        return body

    async def request(
        self,
        *,
        api_type: str,
        access_token: str,
        region: str,
        request_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """供业务服务调用的公共签名请求入口。"""

        return await self._post(
            api_type=api_type,
            access_token=access_token,
            region=region,
            request_data=request_data,
        )

    async def exchange_authorization_code(
        self,
        code: str,
        region: str = "global",
    ) -> dict[str, Any]:
        """用卖家中心回调 code 换取店铺 Access Token。"""

        authorization_code = code.strip()
        if not authorization_code:
            raise ValueError("Temu 授权码不能为空")
        body = await self._post(
            api_type="bg.open.accesstoken.create",
            access_token=authorization_code,
            region=region,
            request_data={"code": authorization_code},
        )
        result = body.get("result")
        if not isinstance(result, dict) or not result.get("accessToken"):
            raise ValueError("Temu 未返回有效 Access Token")
        return result

    async def get_token_info(
        self,
        access_token: str,
        region: str = "global",
    ) -> dict[str, Any]:
        """读取 Token 对应店铺、过期时间和授权范围。"""

        body = await self._post(
            api_type="bg.open.accesstoken.info.get",
            access_token=access_token,
            region=region,
        )
        result = body.get("result")
        if not isinstance(result, dict):
            raise ValueError("Temu 未返回 Token 店铺信息")
        return result
