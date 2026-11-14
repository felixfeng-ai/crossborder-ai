"""管理员运营后台、RUM、反馈和套餐版本接口测试。"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.traffic_event import TrafficEvent
from app.services.data_retention import run_retention_cleanup


ADMIN_EMAIL = "admin@veyaship.com"


async def _register(client: AsyncClient, email: str) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": email.split("@")[0],
            "password": "testpass123",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@test.com"


@pytest_asyncio.fixture
async def admin_headers(client: AsyncClient) -> dict:
    """准备默认管理员账号。"""
    credentials = {
        "email": ADMIN_EMAIL,
        "username": "admin",
        "password": "testpass123",
    }
    response = await client.post("/api/v1/auth/register", json=credentials)
    if response.status_code == 409:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": ADMIN_EMAIL, "password": credentials["password"]},
        )
    assert response.status_code in (200, 201), response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest_asyncio.fixture
async def normal_headers(client: AsyncClient) -> dict:
    """准备普通用户账号。"""
    return await _register(client, _unique_email("normal"))


@pytest.mark.asyncio
async def test_telemetry_collects_pv_uv_and_web_vitals(
    client: AsyncClient,
    admin_headers: dict,
    normal_headers: dict,
):
    """页面事件形成 PV/UV，性能事件聚合出 p75，普通用户不能读取管理分析。"""
    events = {
        "events": [
            {
                "event_type": "page_view",
                "visitor_id": "visitor-a",
                "session_id": "session-a",
                "path": "/",
                "referrer_host": "search.example",
                "device_type": "desktop",
                "viewport_width": 1440,
                "release": "test-release",
            },
            {
                "event_type": "page_view",
                "visitor_id": "visitor-a",
                "session_id": "session-a",
                "path": "/pricing",
                "referrer_host": "",
                "device_type": "desktop",
                "viewport_width": 1440,
                "release": "test-release",
            },
            {
                "event_type": "web_vital",
                "visitor_id": "visitor-a",
                "session_id": "session-a",
                "path": "/",
                "device_type": "desktop",
                "viewport_width": 1440,
                "metric_name": "LCP",
                "metric_value": 1800,
                "metric_rating": "good",
                "release": "test-release",
            },
            {
                "event_type": "web_vital",
                "visitor_id": "visitor-a",
                "session_id": "session-a",
                "path": "/",
                "device_type": "desktop",
                "viewport_width": 1440,
                "metric_name": "LCP",
                "metric_value": 2300,
                "metric_rating": "good",
                "connection_type": "4g",
                "release": "test-release",
            },
        ]
    }
    accepted = await client.post(
        "/api/v1/telemetry/events",
        json=events,
        headers={"X-Country-Code": "CN"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["accepted"] == 4

    denied = await client.get(
        "/api/v1/admin/analytics/overview",
        headers=normal_headers,
    )
    assert denied.status_code == 403

    overview = await client.get(
        "/api/v1/admin/analytics/overview?days=7",
        headers=admin_headers,
    )
    assert overview.status_code == 200, overview.text
    data = overview.json()
    assert data["traffic"]["pv"] == 2
    assert data["traffic"]["uv"] == 1
    assert data["traffic"]["sessions"] == 1
    assert data["performance"]["metrics"]["LCP"]["samples"] == 2
    assert data["performance"]["metrics"]["LCP"]["p75"] == 2175
    assert data["performance"]["groups"]["china"]["metrics"]["LCP"]["samples"] == 2
    assert data["performance"]["groups"]["mobile"]["metrics"]["LCP"]["samples"] == 1


@pytest.mark.asyncio
async def test_telemetry_rejects_unknown_metric(client: AsyncClient):
    """非白名单性能指标必须被拒绝。"""
    response = await client.post(
        "/api/v1/telemetry/events",
        json={
            "events": [
                {
                    "event_type": "web_vital",
                    "visitor_id": "visitor-a",
                    "session_id": "session-a",
                    "path": "/",
                    "device_type": "desktop",
                    "metric_name": "MADE_UP",
                    "metric_value": 1,
                    "metric_rating": "good",
                }
            ]
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_feedback_submission_and_admin_status_update(
    client: AsyncClient,
    admin_headers: dict,
    normal_headers: dict,
):
    """用户可提交并查看反馈，管理员可筛选和处理，普通用户不能进入收件箱。"""
    created = await client.post(
        "/api/v1/feedback",
        json={
            "type": "bug",
            "title": "图片上传后没有显示预览",
            "content": "上传 JPG 成功后，编辑区域仍然为空。",
            "page_path": "/app/images",
            "page_title": "图片工作台",
            "browser_info": {
                "user_agent": "Edge",
                "viewport_width": 1440,
                "request_id": "req-feedback-1",
            },
        },
        headers=normal_headers,
    )
    assert created.status_code == 200, created.text
    feedback = created.json()
    assert feedback["status"] == "open"
    assert feedback["title"] == "图片上传后没有显示预览"

    mine = await client.get("/api/v1/feedback/mine", headers=normal_headers)
    assert mine.status_code == 200
    assert mine.json()["items"][0]["id"] == feedback["id"]

    denied = await client.get("/api/v1/admin/feedback", headers=normal_headers)
    assert denied.status_code == 403

    inbox = await client.get("/api/v1/admin/feedback?status=open", headers=admin_headers)
    assert inbox.status_code == 200, inbox.text
    assert any(item["id"] == feedback["id"] for item in inbox.json()["items"])

    updated = await client.patch(
        f"/api/v1/admin/feedback/{feedback['id']}",
        json={
            "status": "in_progress",
            "priority": "high",
            "assigned_to": ADMIN_EMAIL,
            "note": "已复现，检查前端预览状态。",
        },
        headers=admin_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "in_progress"
    assert updated.json()["priority"] == "high"

    refreshed = await client.get("/api/v1/feedback/mine", headers=normal_headers)
    assert refreshed.json()["items"][0]["status"] == "in_progress"
    audits = await client.get("/api/v1/admin/audits", headers=admin_headers)
    assert audits.status_code == 200
    assert any(item["action"] == "feedback.update" for item in audits.json()["items"])


@pytest.mark.asyncio
async def test_admin_plan_versions_publish_and_keep_order_snapshot(
    client: AsyncClient,
    admin_headers: dict,
    normal_headers: dict,
    monkeypatch,
):
    """套餐新版本发布后影响新订单，但不会修改历史订单快照。"""
    monkeypatch.setattr(
        "app.routers.billing._now",
        lambda: datetime(2026, 11, 15, 4, 0, tzinfo=timezone.utc),
    )

    initial = await client.get("/api/v1/billing/plans")
    assert initial.status_code == 200
    standard = next(item for item in initial.json()["plans"] if item["id"] == "standard")
    assert standard["price"] == 99

    denied = await client.post(
        "/api/v1/admin/plans/standard/versions",
        json={
            "name": "Standard",
            "rank": 1,
            "price_cents": 12900,
            "first_month_price_cents": 10900,
            "annual_price_cents": 129000,
            "annual_full_price_cents": 154800,
            "monthly_credits": 1000,
            "valid_days": 30,
            "features": ["每月 1,000 AI 积分", "商品抓取每月 100 次"],
        },
        headers=normal_headers,
    )
    assert denied.status_code == 403

    draft = await client.post(
        "/api/v1/admin/plans/standard/versions",
        json={
            "name": "Standard",
            "rank": 1,
            "price_cents": 12900,
            "first_month_price_cents": 10900,
            "annual_price_cents": 129000,
            "annual_full_price_cents": 154800,
            "monthly_credits": 1000,
            "valid_days": 30,
            "features": ["每月 1,000 AI 积分", "商品抓取每月 100 次"],
        },
        headers=admin_headers,
    )
    assert draft.status_code == 200, draft.text
    draft_version = draft.json()
    assert draft_version["status"] == "draft"
    assert draft_version["price_cents"] == 12900

    published = await client.post(
        f"/api/v1/admin/plan-versions/{draft_version['id']}/publish",
        json={},
        headers=admin_headers,
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"

    updated = await client.get("/api/v1/billing/plans")
    updated_standard = next(
        item for item in updated.json()["plans"] if item["id"] == "standard"
    )
    assert updated_standard["price"] == 129
    assert updated_standard["first_month_price"] == 109
    assert updated_standard["monthly_credits"] == 1000
    audits = await client.get("/api/v1/admin/audits", headers=admin_headers)
    assert any(item["action"] == "plan.version.publish" for item in audits.json()["items"])

    upgrade = await client.post(
        "/api/v1/billing/upgrade",
        json={"plan": "standard", "contact": "wx-plan-version"},
        headers=normal_headers,
    )
    assert upgrade.status_code == 200, upgrade.text
    assert upgrade.json()["amount"] == 109

    second_draft = await client.post(
        "/api/v1/admin/plans/standard/versions",
        json={
            "name": "Standard",
            "rank": 1,
            "price_cents": 14900,
            "first_month_price_cents": 11900,
            "annual_price_cents": 149000,
            "annual_full_price_cents": 178800,
            "monthly_credits": 1200,
            "valid_days": 30,
            "features": ["每月 1,200 AI 积分"],
        },
        headers=admin_headers,
    )
    assert second_draft.status_code == 200
    await client.post(
        f"/api/v1/admin/plan-versions/{second_draft.json()['id']}/publish",
        json={},
        headers=admin_headers,
    )

    history = await client.get("/api/v1/billing/upgrades", headers=normal_headers)
    assert history.status_code == 200
    assert history.json()["items"][0]["amount"] == 109


@pytest.mark.asyncio
async def test_traffic_events_follow_30_day_retention(db_session):
    """原始匿名事件超过 30 天后由保留任务删除。"""
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            TrafficEvent(
                event_type="page_view",
                visitor_id="old-visitor",
                session_id="old-session",
                path="/",
                country_code="CN",
                device_type="desktop",
                created_at=now - timedelta(days=31),
            ),
            TrafficEvent(
                event_type="page_view",
                visitor_id="new-visitor",
                session_id="new-session",
                path="/",
                country_code="CN",
                device_type="desktop",
                created_at=now - timedelta(days=3),
            ),
        ]
    )
    await db_session.commit()

    result = await run_retention_cleanup(
        db_session,
        now=now,
        retention_days=90,
        telemetry_retention_days=30,
        dry_run=False,
    )
    assert result["deleted"]["traffic_events"] == 1
    remaining = await db_session.scalar(select(func.count(TrafficEvent.id)))
    assert remaining == 1
