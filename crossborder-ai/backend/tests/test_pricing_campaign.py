"""套餐活动、年付与新客资格契约测试。"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.credit_wallet import CreditWallet
from app.models.plan_upgrade import PlanUpgradeRequest
from app.models.subscription import UserSubscription
from app.models.user import User
from app.routers import billing as billing_router


@pytest_asyncio.fixture
async def admin_headers(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "admin@veyaship.com",
            "username": "admin",
            "password": "testpass123",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _campaign_now() -> datetime:
    return datetime(2026, 11, 15, 4, 0, tzinfo=timezone.utc)


async def _auth_user(db_session) -> User:
    return (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_campaign_eligibility_for_new_user(
    client,
    auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(billing_router, "_now", _campaign_now)

    response = await client.get("/api/v1/billing/campaign", headers=auth_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["active"] is True
    assert body["first_month_eligible"] is True
    assert body["trial_pack_eligible"] is True
    plans = {item["id"]: item for item in body["plans"]}
    assert plans["standard"]["first_month_price"] == 79
    assert plans["professional"]["first_month_price"] == 199
    assert plans["professional"]["first_month_bonus_credits"] == 100
    assert plans["standard"]["annual_price"] == 990
    assert plans["professional"]["annual_price"] == 2490


@pytest.mark.asyncio
async def test_new_user_upgrade_uses_server_side_first_month_price(
    client,
    auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(billing_router, "_now", _campaign_now)

    response = await client.post(
        "/api/v1/billing/upgrade",
        json={
            "plan": "professional",
            "contact": "wx-new-user",
            "billing_cycle": "monthly",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["amount"] == 199
    assert body["original_amount"] == 249
    assert body["billing_cycle"] == "monthly"
    assert body["duration_days"] == 30
    assert body["bonus_credits"] == 100
    assert body["promotion_code"] == "new_customer_first_month"


@pytest.mark.asyncio
async def test_annual_upgrade_uses_server_side_annual_price(
    client,
    auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(billing_router, "_now", _campaign_now)

    response = await client.post(
        "/api/v1/billing/upgrade",
        json={
            "plan": "standard",
            "contact": "wx-annual",
            "billing_cycle": "annual",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["amount"] == 990
    assert body["original_amount"] == 1188
    assert body["billing_cycle"] == "annual"
    assert body["duration_days"] == 365
    assert body["bonus_credits"] == 0
    assert body["promotion_code"] == "annual_10_for_12"


@pytest.mark.asyncio
async def test_existing_paid_user_does_not_get_first_month_price(
    client,
    auth_headers,
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(billing_router, "_now", _campaign_now)
    user = await _auth_user(db_session)
    now = _campaign_now()
    db_session.add(
        UserSubscription(
            user_id=user.id,
            plan="standard",
            status="expired",
            starts_at=now - timedelta(days=60),
            expires_at=now - timedelta(days=30),
            source="test_history",
        )
    )
    await db_session.flush()

    response = await client.post(
        "/api/v1/billing/upgrade",
        json={
            "plan": "standard",
            "contact": "wx-existing",
            "billing_cycle": "monthly",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["amount"] == 99
    assert body["original_amount"] == 99
    assert body["promotion_code"] is None
    assert body["bonus_credits"] == 0


@pytest.mark.asyncio
async def test_professional_user_cannot_downgrade_or_reapply(
    client,
    auth_headers,
    db_session,
):
    user = await _auth_user(db_session)
    user.plan = "professional"
    await db_session.flush()

    for target in ("free", "standard", "professional"):
        response = await client.post(
            "/api/v1/billing/upgrade",
            json={
                "plan": target,
                "contact": "wx-downgrade",
                "billing_cycle": "monthly",
            },
            headers=auth_headers,
        )
        assert response.status_code == 409, response.text
        assert "高于当前套餐" in response.json()["detail"]


@pytest.mark.asyncio
async def test_admin_cannot_approve_stale_downgrade_request(
    client,
    auth_headers,
    admin_headers,
    db_session,
):
    user = await _auth_user(db_session)
    user.plan = "professional"
    request = PlanUpgradeRequest(
        user_id=user.id,
        plan="standard",
        contact="wx-stale",
        order_id="VS-STALE-DOWNGRADE",
        amount=99,
        original_amount=99,
        billing_cycle="monthly",
        status="pending",
    )
    db_session.add(request)
    await db_session.flush()

    response = await client.post(
        f"/api/v1/billing/upgrades/{request.id}/approve",
        json={"note": "尝试开通"},
        headers=admin_headers,
    )

    assert response.status_code == 409, response.text
    await db_session.refresh(request)
    assert request.status == "rejected"
    assert "低档或同级" in (request.note or "")


@pytest.mark.asyncio
async def test_pending_first_month_request_consumes_offer(
    client,
    auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(billing_router, "_now", _campaign_now)
    first = await client.post(
        "/api/v1/billing/upgrade",
        json={
            "plan": "standard",
            "contact": "wx-first",
            "billing_cycle": "monthly",
        },
        headers=auth_headers,
    )
    assert first.status_code == 200, first.text
    assert first.json()["amount"] == 79

    second = await client.post(
        "/api/v1/billing/upgrade",
        json={
            "plan": "professional",
            "contact": "wx-second",
            "billing_cycle": "monthly",
        },
        headers=auth_headers,
    )
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["plan"] == "standard"
    assert "已有待处理" in second.json()["message"]


@pytest.mark.asyncio
async def test_inactive_campaign_uses_regular_price(
    client,
    auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(
        billing_router,
        "_now",
        lambda: datetime(2027, 1, 1, 4, 0, tzinfo=timezone.utc),
    )

    response = await client.post(
        "/api/v1/billing/upgrade",
        json={
            "plan": "professional",
            "contact": "wx-regular",
            "billing_cycle": "monthly",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["amount"] == 249
    assert body["promotion_code"] is None
    assert body["bonus_credits"] == 0


@pytest.mark.asyncio
async def test_approve_first_month_grants_bonus_and_sets_duration(
    client,
    auth_headers,
    admin_headers,
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(billing_router, "_now", _campaign_now)
    submitted = await client.post(
        "/api/v1/billing/upgrade",
        json={
            "plan": "professional",
            "contact": "wx-bonus",
            "billing_cycle": "monthly",
        },
        headers=auth_headers,
    )
    assert submitted.status_code == 200, submitted.text

    approved = await client.post(
        f"/api/v1/billing/upgrades/{submitted.json()['id']}/approve",
        json={"note": "已确认活动款"},
        headers=admin_headers,
    )
    assert approved.status_code == 200, approved.text

    user = await _auth_user(db_session)
    await db_session.refresh(user)
    wallet = (
        await db_session.execute(
            select(CreditWallet).where(CreditWallet.user_id == user.id)
        )
    ).scalar_one()
    subscription = (
        await db_session.execute(
            select(UserSubscription).where(
                UserSubscription.user_id == user.id,
                UserSubscription.status == "active",
            )
        )
    ).scalar_one()
    assert user.plan == "professional"
    assert wallet.plan_credits == 2000
    assert wallet.purchased_credits == 100
    assert user.credits == 2100
    assert (subscription.expires_at - subscription.starts_at).days == 30


@pytest.mark.asyncio
async def test_trial_pack_is_listed_and_can_only_succeed_once(
    client,
    auth_headers,
    admin_headers,
):
    packs = await client.get("/api/v1/billing/credit-packs")
    assert packs.status_code == 200
    trial = next(
        item for item in packs.json()["packs"] if item["id"] == "pack_trial_50"
    )
    assert trial["credits"] == 50
    assert trial["price"] == 9.9
    assert trial["trial_once"] is True

    created = await client.post(
        "/api/v1/billing/credit-packs/purchase",
        json={"pack_id": "pack_trial_50", "contact": "wx-trial"},
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text
    order = created.json()
    assert order["credits"] == 50
    assert order["amount"] == 9.9

    duplicate = await client.post(
        "/api/v1/billing/credit-packs/purchase",
        json={"pack_id": "pack_trial_50", "contact": "wx-trial"},
        headers=auth_headers,
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == order["id"]

    approved = await client.post(
        f"/api/v1/billing/credit-packs/{order['id']}/approve",
        json={"note": "已到账"},
        headers=admin_headers,
    )
    assert approved.status_code == 200, approved.text

    reused = await client.post(
        "/api/v1/billing/credit-packs/purchase",
        json={"pack_id": "pack_trial_50", "contact": "wx-trial"},
        headers=auth_headers,
    )
    assert reused.status_code == 409
    assert "首购" in reused.json()["detail"]
