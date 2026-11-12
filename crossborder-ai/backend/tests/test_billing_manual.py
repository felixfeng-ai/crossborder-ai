"""VeyaShip - 支付人工闭环测试

覆盖：用户提交升级申请落库 / 重复申请去重 / 查看自己的申请状态 /
管理员权限（非管理员 403）/ 管理员 approve 开通套餐 + 加积分 /
管理员 reject / 已处理申请不可重复操作。
"""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.models.plan_upgrade import PlanUpgradeRequest
from app.models.credit_wallet import CreditWallet
from app.models.subscription import UserSubscription
from app.models.user import User

ADMIN_EMAIL = "admin@veyaship.com"


async def _register(client: AsyncClient, email: str) -> dict:
    """注册一个测试用户，返回带 token 的 headers。"""
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": email.split("@")[0],
            "password": "testpass123",
        },
    )
    assert resp.status_code == 201, f"注册失败: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@test.com"


@pytest_asyncio.fixture
async def buyer_headers(client: AsyncClient) -> dict:
    """一个已注册的普通买家（非管理员）"""
    return await _register(client, _unique_email("buyer"))


@pytest_asyncio.fixture
async def admin_headers(client: AsyncClient) -> dict:
    """管理员账号（邮箱在 ADMIN_EMAILS 默认配置里）。

    测试库跨测试共享（conftest 内存 SQLite），管理员已注册过就登录拿 token。
    """
    creds = {"email": ADMIN_EMAIL, "username": "admin", "password": "testpass123"}
    resp = await client.post("/api/v1/auth/register", json=creds)
    if resp.status_code == 409:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": ADMIN_EMAIL, "password": creds["password"]},
        )
    assert resp.status_code in (200, 201), f"管理员账号准备失败: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _submit_upgrade(client: AsyncClient, headers: dict, plan: str = "standard"):
    resp = await client.post(
        "/api/v1/billing/upgrade",
        json={"plan": plan, "contact": "微信 wx-123"},
        headers=headers,
    )
    assert resp.status_code == 200, f"提交申请失败: {resp.text}"
    return resp.json()


@pytest.mark.asyncio
async def test_submit_upgrade_request_creates_pending(
    client: AsyncClient,
    buyer_headers: dict,
    monkeypatch,
):
    """提交升级申请 → 落库为 pending，带订单号和金额"""
    monkeypatch.setattr(
        "app.routers.billing._now",
        lambda: datetime(2026, 11, 15, 4, 0, tzinfo=timezone.utc),
    )
    data = await _submit_upgrade(client, buyer_headers, "standard")

    assert data["status"] == "pending"
    assert data["plan"] == "standard"
    assert data["amount"] == 79
    assert data["original_amount"] == 99
    assert data["billing_cycle"] == "monthly"
    assert data["promotion_code"] == "new_customer_first_month"
    assert data["order_id"].startswith("VS")
    assert len(data["order_id"]) > 8
    assert "申请已提交" in data["message"]


@pytest.mark.asyncio
async def test_duplicate_pending_request_returns_same_order(client: AsyncClient, buyer_headers: dict):
    """同一套餐已有待处理申请 → 不重复落库，返回原申请"""
    first = await _submit_upgrade(client, buyer_headers, "standard")
    second = await _submit_upgrade(client, buyer_headers, "standard")

    assert second["order_id"] == first["order_id"]
    assert second["id"] == first["id"]
    assert "已有待处理" in second["message"]


@pytest.mark.asyncio
async def test_list_my_upgrades_shows_status(client: AsyncClient, buyer_headers: dict):
    """用户能查到自己的申请记录"""
    submitted = await _submit_upgrade(client, buyer_headers, "standard")

    resp = await client.get("/api/v1/billing/upgrades", headers=buyer_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == submitted["id"]
    assert items[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_approve_requires_admin(client: AsyncClient, buyer_headers: dict):
    """非管理员调用 approve → 403"""
    submitted = await _submit_upgrade(client, buyer_headers, "standard")

    resp = await client.post(
        f"/api/v1/billing/upgrades/{submitted['id']}/approve",
        json={"note": ""},
        headers=buyer_headers,
    )
    assert resp.status_code == 403
    assert "管理员" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_admin_upgrades_list_filtered_by_status(client: AsyncClient, buyer_headers: dict, admin_headers: dict):
    """管理员可查看待办列表；普通用户访问管理接口 → 403"""
    await _submit_upgrade(client, buyer_headers, "standard")

    # 管理员能看到待办（测试库共享，可能有其他测试的申请，只断言全为 pending 且非空）
    resp = await client.get("/api/v1/billing/admin/upgrades?status=pending", headers=admin_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1
    assert all(i["status"] == "pending" for i in items)

    # 普通用户访问管理接口 → 403
    denied = await client.get("/api/v1/billing/admin/upgrades", headers=buyer_headers)
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_admin_approve_opens_plan(
    client: AsyncClient,
    db_session,
    buyer_headers: dict,
    admin_headers: dict,
):
    """管理员 approve → 买家套餐升级 + 积分加满 + 申请标记已处理"""
    submitted = await _submit_upgrade(client, buyer_headers, "standard")

    resp = await client.post(
        f"/api/v1/billing/upgrades/{submitted['id']}/approve",
        json={"note": "已确认收款"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "approved"
    assert body["note"] == "已确认收款"

    # 查数据库确认买家已开通套餐
    req = (await db_session.execute(
        select(PlanUpgradeRequest).where(PlanUpgradeRequest.id == uuid.UUID(submitted["id"]))
    )).scalar_one()
    buyer = (await db_session.execute(
        select(User).where(User.id == req.user_id)
    )).scalar_one()
    assert buyer.plan == "standard"
    assert buyer.credits == 800
    wallet = (
        await db_session.execute(
            select(CreditWallet).where(CreditWallet.user_id == buyer.id)
        )
    ).scalar_one()
    assert wallet.plan_credits == 800
    subscription = (
        await db_session.execute(
            select(UserSubscription).where(UserSubscription.user_id == buyer.id)
        )
    ).scalar_one()
    assert subscription.plan == "standard"
    assert subscription.status == "active"


@pytest.mark.asyncio
async def test_admin_reject_keeps_plan(client: AsyncClient, db_session, buyer_headers: dict, admin_headers: dict):
    """管理员 reject → 申请标记拒绝，买家套餐不变"""
    submitted = await _submit_upgrade(client, buyer_headers, "professional")

    resp = await client.post(
        f"/api/v1/billing/upgrades/{submitted['id']}/reject",
        json={"note": "未收到转账"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["note"] == "未收到转账"

    # 买家套餐未被改动
    req = (await db_session.execute(
        select(PlanUpgradeRequest).where(PlanUpgradeRequest.id == uuid.UUID(submitted["id"]))
    )).scalar_one()
    buyer = (await db_session.execute(
        select(User).where(User.id == req.user_id)
    )).scalar_one()
    assert buyer.plan == "free"
    assert buyer.credits == 30


@pytest.mark.asyncio
async def test_approve_twice_rejected_400(client: AsyncClient, buyer_headers: dict, admin_headers: dict):
    """已处理的申请不能重复 approve → 400"""
    submitted = await _submit_upgrade(client, buyer_headers, "standard")

    first = await client.post(
        f"/api/v1/billing/upgrades/{submitted['id']}/approve",
        json={},
        headers=admin_headers,
    )
    assert first.status_code == 200

    second = await client.post(
        f"/api/v1/billing/upgrades/{submitted['id']}/approve",
        json={},
        headers=admin_headers,
    )
    assert second.status_code == 400
    assert "已处理" in second.json()["detail"]


@pytest.mark.asyncio
async def test_credit_pack_purchase_and_admin_approval(
    client: AsyncClient,
    buyer_headers: dict,
    admin_headers: dict,
):
    created = await client.post(
        "/api/v1/billing/credit-packs/purchase",
        json={"pack_id": "pack_200", "contact": "wx-test"},
        headers=buyer_headers,
    )
    assert created.status_code == 200, created.text
    purchase = created.json()
    assert purchase["credits"] == 200

    approved = await client.post(
        f"/api/v1/billing/credit-packs/{purchase['id']}/approve",
        json={"note": "已到账"},
        headers=admin_headers,
    )
    assert approved.status_code == 200, approved.text

    repeated = await client.post(
        f"/api/v1/billing/credit-packs/{purchase['id']}/approve",
        json={"note": "重复"},
        headers=admin_headers,
    )
    assert repeated.status_code == 400

    wallet_response = await client.get(
        "/api/v1/billing/wallet",
        headers=buyer_headers,
    )
    assert wallet_response.status_code == 200, wallet_response.text
    wallet = wallet_response.json()
    assert wallet["purchased_credits"] == 200
    assert wallet["total_credits"] == 230
