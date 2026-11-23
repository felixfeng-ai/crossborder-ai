"""Amazon Orders 2026-01-01 增量读取与 Agent 订单信号同步。"""

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value
from app.models.agent_signal import IntegrationCursor
from app.models.platform_connection import PlatformConnection
from app.models.workspace import Workspace
from app.services.agent_signals import (
    ingest_agent_signal,
    resolve_latest_signal_by_fingerprint,
    save_integration_cursor,
)
from app.services.amazon_sp_api import AmazonSpApiService
from app.services.integration_events import (
    claim_integration_lease,
    release_integration_lease,
)


AMAZON_API_BASE_URLS = {
    "na": "https://sellingpartnerapi-na.amazon.com",
    "eu": "https://sellingpartnerapi-eu.amazon.com",
    "fe": "https://sellingpartnerapi-fe.amazon.com",
}

AMAZON_MARKETPLACE_REGIONS = {
    # North America
    "ATVPDKIKX0DER": "na",  # US
    "A2EUQ1WTGCTBG2": "na",  # Canada
    "A1AM78C64UM0Y8": "na",  # Mexico
    "A2Q3Y263D00KWC": "na",  # Brazil
    # Europe and adjacent marketplaces
    "A1PA6795UKMFR9": "eu",  # Germany
    "A13V1IB3VIYZZH": "eu",  # France
    "APJ6JRA9NG5V4": "eu",  # Italy
    "A1RKKUPIHCS9HS": "eu",  # Spain
    "A1F83G8C2ARO7P": "eu",  # UK
    "A1805IZSGTT6HS": "eu",  # Netherlands
    "A2NODRKZP88ZB9": "eu",  # Sweden
    "A1C3SOZRARQ6R3": "eu",  # Poland
    "AMEN7PMS3EDWL": "eu",  # Belgium
    "A33AVAJ2PDY3EV": "eu",  # Turkey
    "A2VIGQ35RCS4UG": "eu",  # UAE
    "A17E79C6D8DWNP": "eu",  # Saudi Arabia
    "ARBP9OOSHTCHU": "eu",  # Egypt
    # Far East
    "A1VC38T7YXB528": "fe",  # Japan
    "A39IBJ37TRP1C6": "fe",  # Australia
    "A19VAU5U5O7RUS": "fe",  # Singapore
}

AMAZON_COUNTRY_REGIONS = {
    "US": "na",
    "CA": "na",
    "MX": "na",
    "BR": "na",
    "DE": "eu",
    "FR": "eu",
    "IT": "eu",
    "ES": "eu",
    "GB": "eu",
    "NL": "eu",
    "SE": "eu",
    "PL": "eu",
    "BE": "eu",
    "TR": "eu",
    "AE": "eu",
    "SA": "eu",
    "EG": "eu",
    "IN": "eu",
    "JP": "fe",
    "AU": "fe",
    "SG": "fe",
}


class AmazonRateLimitError(RuntimeError):
    """Amazon 限流，调用方必须退避且不能推进游标。"""


class AmazonAuthorizationError(ValueError):
    """Amazon 授权失效，需要重新连接。"""


def resolve_amazon_region(
    marketplace_id: str,
    country_code: str | None = None,
) -> str:
    """按 Marketplace 或国家代码选择 NA、EU、FE 区域。"""

    normalized_country = str(country_code or "").strip().upper()
    if normalized_country in AMAZON_COUNTRY_REGIONS:
        return AMAZON_COUNTRY_REGIONS[normalized_country]
    return AMAZON_MARKETPLACE_REGIONS.get(
        str(marketplace_id or "").strip().upper(),
        "na",
    )


def amazon_api_base_url(region: str) -> str:
    normalized = str(region or "").strip().lower()
    if normalized not in AMAZON_API_BASE_URLS:
        raise ValueError("Amazon SP-API 区域必须是 na、eu 或 fe")
    return AMAZON_API_BASE_URLS[normalized]


def _connection_country_code(connection: PlatformConnection) -> str | None:
    try:
        metadata = json.loads(connection.metadata_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return None
    target = str(connection.marketplace_id or "").strip()
    for item in metadata.get("marketplaces") or []:
        if not isinstance(item, dict):
            continue
        marketplace = item.get("marketplace") or {}
        if str(marketplace.get("id") or "") == target:
            return str(marketplace.get("countryCode") or "").strip() or None
    return None


class AmazonOrdersService:
    """只读取商户自履约订单的非敏感履约字段。"""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self._transport = transport

    async def search_orders(
        self,
        *,
        access_token: str,
        marketplace_id: str,
        last_updated_after: str,
        last_updated_before: str | None = None,
        pagination_token: str | None = None,
        max_results_per_page: int = 100,
        country_code: str | None = None,
        fulfillment_statuses: list[str] | None = None,
    ) -> dict:
        """调用 searchOrders，只请求 FULFILLMENT 数据集。"""

        region = resolve_amazon_region(marketplace_id, country_code)
        params = {
            "marketplaceIds": marketplace_id,
            "lastUpdatedAfter": last_updated_after,
            "fulfilledBy": "MERCHANT",
            "includedData": "FULFILLMENT",
            "maxResultsPerPage": max(1, min(int(max_results_per_page), 100)),
        }
        if last_updated_before:
            params["lastUpdatedBefore"] = last_updated_before
        if pagination_token:
            params["paginationToken"] = pagination_token
        if fulfillment_statuses:
            params["fulfillmentStatuses"] = ",".join(
                str(item).strip().upper()
                for item in fulfillment_statuses
                if str(item).strip()
            )

        url = f"{amazon_api_base_url(region)}/orders/2026-01-01/orders"
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=45,
            ) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers={
                        "x-amz-access-token": access_token,
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            raise RuntimeError("Amazon 订单读取失败，请稍后重试") from exc
        if response.status_code == 429:
            raise AmazonRateLimitError("Amazon 订单接口限流，请稍后重试")
        if response.status_code in {401, 403}:
            raise AmazonAuthorizationError(
                "Amazon 订单权限不足或授权已失效"
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Amazon 订单读取失败：{response.text[:300]}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError("Amazon 订单响应无法解析") from exc
        if not isinstance(body, dict):
            raise RuntimeError("Amazon 订单响应格式不正确")
        return body

    async def get_order(
        self,
        *,
        access_token: str,
        marketplace_id: str,
        order_id: str,
        included_data: list[str] | None = None,
        country_code: str | None = None,
    ) -> dict:
        """读取单个订单，只请求调用方明确指定的数据集。"""

        region = resolve_amazon_region(marketplace_id, country_code)
        url = (
            f"{amazon_api_base_url(region)}/orders/2026-01-01/orders/"
            f"{quote(order_id, safe='')}"
        )
        params = {}
        if included_data:
            params["includedData"] = ",".join(
                str(item).strip().upper()
                for item in included_data
                if str(item).strip()
            )
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=45,
            ) as client:
                response = await client.get(
                    url,
                    params=params or None,
                    headers={
                        "x-amz-access-token": access_token,
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            raise RuntimeError("Amazon 订单读取失败，请稍后重试") from exc
        if response.status_code == 429:
            raise AmazonRateLimitError("Amazon 订单接口限流，请稍后重试")
        if response.status_code in {401, 403}:
            raise AmazonAuthorizationError(
                "Amazon 订单权限不足或授权已失效"
            )
        if response.status_code == 404:
            raise AmazonAuthorizationError("Amazon 订单不存在或无权读取")
        if response.status_code >= 400:
            raise RuntimeError(
                f"Amazon 订单读取失败：{response.text[:300]}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError("Amazon 订单响应无法解析") from exc
        order = body.get("order") if isinstance(body, dict) else None
        if not isinstance(order, dict):
            raise RuntimeError("Amazon 订单响应缺少订单对象")
        return order

    async def confirm_shipment(
        self,
        *,
        access_token: str,
        marketplace_id: str,
        order_id: str,
        package_detail: dict,
        country_code: str | None = None,
    ) -> None:
        """通过 Orders v0 shipmentConfirmation 确认 FBM 发货。"""

        region = resolve_amazon_region(marketplace_id, country_code)
        url = (
            f"{amazon_api_base_url(region)}/orders/v0/orders/"
            f"{quote(order_id, safe='')}/shipmentConfirmation"
        )
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=45,
            ) as client:
                response = await client.post(
                    url,
                    json={
                        "marketplaceId": marketplace_id,
                        "packageDetail": package_detail,
                    },
                    headers={
                        "x-amz-access-token": access_token,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            raise RuntimeError("Amazon 发货确认请求失败，请稍后重试") from exc
        if response.status_code == 429:
            raise AmazonRateLimitError("Amazon 发货接口限流，请稍后重试")
        if response.status_code in {401, 403}:
            raise AmazonAuthorizationError(
                "Amazon 订单权限不足或授权已失效"
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(
                f"Amazon 发货确认失败：{response.text[:300]}"
            )


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _order_age_hours(order: dict) -> int:
    created = _parse_time(order.get("createdTime"))
    if created is None:
        return 0
    return max(
        0,
        int((datetime.now(timezone.utc) - created).total_seconds() // 3600),
    )


async def sync_amazon_order_signals(
    db: AsyncSession,
    *,
    workspace_id,
    connection: PlatformConnection,
    service: AmazonOrdersService | None = None,
) -> dict:
    """同步单个 Amazon 连接的商户自履约订单。"""

    workspace = await db.get(Workspace, workspace_id)
    if (
        workspace is None
        or workspace.type != "personal"
        or workspace.owner_user_id != connection.user_id
    ):
        raise ValueError("Amazon 店铺不属于当前个人工作区")
    if (
        connection.platform != "amazon"
        or connection.status != "active"
        or not connection.marketplace_id
    ):
        raise ValueError("Amazon 店铺连接不可用")

    credentials = json.loads(decrypt_value(connection.credentials))
    refresh_token = str(credentials.get("refresh_token") or "").strip()
    if not refresh_token:
        raise AmazonAuthorizationError("Amazon 店铺授权缺少 Refresh Token")

    try:
        access_token = await AmazonSpApiService().refresh_access_token(
            refresh_token
        )
    except ValueError as exc:
        connection.status = "invalid"
        await ingest_agent_signal(
            db,
            workspace_id=workspace_id,
            actor_user_id=connection.user_id,
            source_type="platform_connection",
            source_id=str(connection.id),
            signal_type="authorization_expired",
            severity="urgent",
            title="Amazon 店铺授权已失效",
            summary="请重新连接 Amazon 后继续同步订单。",
            payload={
                "connection_id": str(connection.id),
                "platform": "amazon",
            },
            fingerprint=f"amazon-connection:{connection.id}:authorization",
            channel_type="amazon",
            channel_id=str(connection.id),
        )
        await db.flush()
        raise AmazonAuthorizationError(str(exc)) from exc

    channel_id = f"amazon:{connection.id}"
    cursor = (
        await db.execute(
            select(IntegrationCursor).where(
                IntegrationCursor.workspace_id == workspace_id,
                IntegrationCursor.channel_id == channel_id,
                IntegrationCursor.resource_type == "amazon_orders",
            )
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    upper_bound = now - timedelta(minutes=2)
    if cursor is not None:
        cursor_time = _parse_time(cursor.cursor_value)
        lower_bound = (
            cursor_time - timedelta(seconds=max(0, cursor.overlap_seconds))
            if cursor_time is not None
            else now - timedelta(days=7)
        )
    else:
        lower_bound = now - timedelta(days=7)

    service = service or AmazonOrdersService()
    country_code = _connection_country_code(connection)
    orders: list[dict] = []
    pagination_token: str | None = None
    pages = 0
    while pages < 5:
        body = await service.search_orders(
            access_token=access_token,
            marketplace_id=str(connection.marketplace_id),
            last_updated_after=lower_bound.isoformat(),
            last_updated_before=upper_bound.isoformat(),
            pagination_token=pagination_token,
            country_code=country_code,
        )
        page_orders = body.get("orders") or []
        if isinstance(page_orders, list):
            orders.extend(
                item for item in page_orders if isinstance(item, dict)
            )
        pages += 1
        pagination_token = str(
            body.get("paginationToken")
            or body.get("nextToken")
            or ""
        ).strip() or None
        if pagination_token is None:
            break
    if pagination_token is not None:
        raise RuntimeError("Amazon 待处理订单超过单次同步上限")

    created = 0
    updated = 0
    resolved = 0
    for order in orders:
        order_id = str(order.get("orderId") or "").strip()
        if not order_id:
            continue
        marketplace_id = str(
            (order.get("salesChannel") or {}).get("marketplaceId")
            or ""
        ).strip()
        if marketplace_id != str(connection.marketplace_id):
            continue
        fulfillment = order.get("fulfillment") or {}
        fulfilled_by = str(
            fulfillment.get("fulfilledBy") or ""
        ).upper()
        status = str(
            fulfillment.get("fulfillmentStatus") or ""
        ).upper()
        if fulfilled_by != "MERCHANT":
            continue

        fingerprint = (
            f"amazon-order:{connection.id}:{marketplace_id}:"
            f"{order_id}:unshipped"
        )
        if status in {"SHIPPED", "CANCELLED", "UNFULFILLABLE"}:
            resolved_signal = await resolve_latest_signal_by_fingerprint(
                db,
                workspace_id=workspace_id,
                fingerprint=fingerprint,
                summary="Amazon 订单已完成履约或已取消。",
            )
            if resolved_signal is not None:
                resolved += 1
            continue
        if status not in {"UNSHIPPED", "PARTIALLY_SHIPPED"}:
            continue

        age_hours = _order_age_hours(order)
        severity = (
            "urgent"
            if age_hours >= 48
            else "attention"
            if age_hours >= 24
            else "normal"
        )
        item_count = sum(
            max(0, int(item.get("quantityOrdered") or 0))
            for item in order.get("orderItems") or []
            if isinstance(item, dict)
        )
        result = await ingest_agent_signal(
            db,
            workspace_id=workspace_id,
            actor_user_id=connection.user_id,
            source_type="amazon_order",
            source_id=order_id,
            signal_type="amazon_order_awaiting_shipment",
            severity=severity,
            title=f"Amazon 订单 {order_id} 等待发货",
            summary=(
                f"{item_count or '若干'} 件商品 · 已等待 {age_hours} 小时"
            ),
            payload={
                "order_id": order_id,
                "marketplace_id": marketplace_id,
                "fulfillment_status": status,
                "item_count": item_count,
                "age_hours": age_hours,
            },
            fingerprint=fingerprint,
            channel_type="amazon",
            channel_id=str(connection.id),
        )
        if result.created:
            created += 1
        else:
            updated += 1

    await save_integration_cursor(
        db,
        workspace_id=workspace_id,
        channel_id=channel_id,
        resource_type="amazon_orders",
        cursor_value=upper_bound.isoformat(),
        overlap_seconds=600,
    )
    return {
        "orders_scanned": len(orders),
        "pages_scanned": pages,
        "signals_created": created,
        "signals_updated": updated,
        "signals_resolved": resolved,
        "cursor_value": upper_bound.isoformat(),
    }


async def sync_all_amazon_order_signals(db: AsyncSession) -> dict:
    """同步全部有效 Amazon 个人店铺，单店失败不阻塞其他店铺。"""

    connections = (
        await db.execute(
            select(PlatformConnection).where(
                PlatformConnection.platform == "amazon",
                PlatformConnection.status == "active",
            )
        )
    ).scalars().all()
    summary = {
        "connections_scanned": len(connections),
        "connections_succeeded": 0,
        "connections_failed": 0,
        "connections_skipped": 0,
        "connections_rate_limited": 0,
        "signals_created": 0,
        "signals_resolved": 0,
        "failures": [],
    }
    for connection in connections:
        workspace = (
            await db.execute(
                select(Workspace)
                .where(
                    Workspace.owner_user_id == connection.user_id,
                    Workspace.type == "personal",
                    Workspace.status == "active",
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if workspace is None:
            summary["connections_skipped"] += 1
            continue
        channel_id = f"amazon:{connection.id}"
        owner = f"amazon-order-sync:{uuid4().hex}"
        lease = await claim_integration_lease(
            db,
            workspace_id=workspace.id,
            channel_id=channel_id,
            resource_type="amazon_orders",
            owner_token=owner,
        )
        await db.commit()
        if lease is None:
            summary["connections_skipped"] += 1
            continue
        try:
            result = await sync_amazon_order_signals(
                db,
                workspace_id=workspace.id,
                connection=connection,
            )
            await db.commit()
            summary["connections_succeeded"] += 1
            summary["signals_created"] += result["signals_created"]
            summary["signals_resolved"] += result["signals_resolved"]
        except AmazonRateLimitError as exc:
            await db.rollback()
            summary["connections_rate_limited"] += 1
            summary["failures"].append(
                {"connection_id": str(connection.id), "error": str(exc)}
            )
        except AmazonAuthorizationError as exc:
            # 连接失效状态和重连任务在同步函数内产生，必须保留提交。
            await db.commit()
            summary["connections_failed"] += 1
            summary["failures"].append(
                {"connection_id": str(connection.id), "error": str(exc)}
            )
        except Exception as exc:
            await db.rollback()
            summary["connections_failed"] += 1
            summary["failures"].append(
                {
                    "connection_id": str(connection.id),
                    "error": str(exc)[:200],
                }
            )
        finally:
            await release_integration_lease(
                db,
                workspace_id=workspace.id,
                channel_id=channel_id,
                resource_type="amazon_orders",
                owner_token=owner,
            )
            await db.commit()
    return summary
