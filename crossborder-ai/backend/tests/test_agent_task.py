"""VeyaShip - Agent 异步任务队列测试

覆盖：
1. POST /agent/run 立即返回 task_id（202），status=pending，带 conversation_id
2. GET /agent/tasks/{task_id} 轮询端点返回任务状态
3. Idempotency-Key 幂等：同 key 重复提交返回同一任务，不重复建对话/任务
4. 执行器成功路径：助手消息落库、对话标题生成、扣 1 分、任务 succeeded
5. 执行器积分不足：任务 failed 且提示"积分不足"，不扣分
6. 调度器抢占 + 僵尸任务恢复：running 超时任务重新入队，pending 被抢占为 running

注意：conftest 的 test_engine 是 session 级，内存 SQLite 连接在测试间复用，
因此 HTTP 测试必须用唯一邮箱注册用户，不能依赖 auth_headers 固定的
test@example.com（跨测试重复注册会 409）。
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.agent_task import AgentTask
from app.models.conversation import Conversation, ConversationMessage
from app.models.user import User
from app.services import agent_task_executor as exe


# ── 工具 ────────────────────────────────────────────────────────
def _make_static_factory():
    """创建独立内存 SQLite（StaticPool 单连接，测试库互相隔离）。

    SQLite 内存模式必须用同一连接，否则建表和查询看到的是两个库。
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.mark.asyncio
async def _register_agent_user(client, db_session, email: str) -> dict:
    """注册用户并升级到 standard 套餐（agent 功能 free 无权限），返回 auth headers。"""
    resp = await client.post("/api/v1/auth/register", json={
        "email": email,
        "username": email.split("@")[0],
        "password": "testpass123",
    })
    assert resp.status_code == 201, resp.text
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    user.plan = "standard"
    await db_session.commit()
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ── HTTP 层：提交任务 / 轮询 / 幂等 ────────────────────────────
@pytest.mark.asyncio
async def test_agent_run_returns_task_id(client, db_session):
    """POST /agent/run 应 202 立即返回 task_id + conversation_id，不阻塞执行。"""
    headers = await _register_agent_user(client, db_session, f"agent-a{uuid.uuid4().hex[:8]}@test.com")

    resp = await client.post(
        "/api/v1/agent/run",
        json={"instruction": "蓝牙耳机能不能做"},
        headers=headers,
    )
    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert data["task_id"]
    assert data["status"] == "pending"
    assert data["conversation_id"], "应返回 conversation_id 供前端绑定对话"
    assert data["summary"] == ""  # 尚未执行完成


@pytest.mark.asyncio
async def test_agent_task_status_endpoint(client, db_session):
    """GET /agent/tasks/{task_id} 返回任务当前状态。"""
    headers = await _register_agent_user(client, db_session, f"agent-b{uuid.uuid4().hex[:8]}@test.com")
    created = (await client.post(
        "/api/v1/agent/run",
        json={"instruction": "帮我算利润"},
        headers=headers,
    )).json()

    resp = await client.get(f"/api/v1/agent/tasks/{created['task_id']}", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_agent_run_idempotent_by_key(client, db_session):
    """同一 Idempotency-Key 重复提交应返回同一任务，不重复创建。"""
    headers = await _register_agent_user(client, db_session, f"agent-c{uuid.uuid4().hex[:8]}@test.com")
    idem_headers = {**headers, "Idempotency-Key": f"idem-{uuid.uuid4().hex[:8]}"}
    payload = {"instruction": "生成 Listing，英文"}

    first = (await client.post("/api/v1/agent/run", json=payload, headers=idem_headers)).json()
    second = (await client.post("/api/v1/agent/run", json=payload, headers=idem_headers)).json()

    assert first["task_id"] == second["task_id"]
    rows = (await db_session.execute(
        select(AgentTask).where(AgentTask.idempotency_key == idem_headers["Idempotency-Key"])
    )).scalars().all()
    assert len(rows) == 1


# ── 执行器：成功 / 积分不足 ────────────────────────────────────
class _FakeOrchestrator:
    """与 AgentOrchestrator 同签名：接收 on_step 进度回调，模拟逐步执行。"""

    def __init__(self, user, db, on_step=None):
        self.on_step = on_step
        self.steps = [
            {"action": "analyze", "status": "success", "title": "分析商品"},
            {"action": "answer", "status": "success", "title": "给出结论"},
        ]

    async def run(self, instruction):
        if self.on_step:
            await self.on_step(self.steps[:1])
            await self.on_step(self.steps)
        return {"summary": "可以做", "status": "success", "steps": self.steps}

    async def run_workflow(self, workflow, params):
        return {"summary": "工作流完成", "status": "success", "steps": []}


class _PartialOrchestrator(_FakeOrchestrator):
    async def run(self, instruction):
        return {
            "summary": "部分完成",
            "status": "partial",
            "steps": [{"action": "scrape_1688", "status": "failed", "error": "抓取失败"}],
        }


@pytest.mark.asyncio
async def test_execute_agent_task_success(monkeypatch):
    """执行器成功：助手消息落库、标题生成、扣 1 分、任务 succeeded。"""
    engine, factory = _make_static_factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(exe, "async_session_factory", factory)
    monkeypatch.setattr(exe, "AgentOrchestrator", _FakeOrchestrator)

    async with factory() as db:
        user = User(email="task-ok@test.com", username="taskok", password_hash="x", credits=30)
        db.add(user)
        await db.flush()
        conv = Conversation(user_id=user.id)
        db.add(conv)
        await db.flush()
        task = AgentTask(
            user_id=user.id,
            task_type="agent_run",
            status="running",
            input=json.dumps({"instruction": "蓝牙耳机能不能做", "conversation_id": str(conv.id)}, ensure_ascii=False),
            cost=1,
        )
        db.add(task)
        await db.commit()
        task_id = task.id
        conv_id = conv.id

    await exe.execute_agent_task(task_id)

    async with factory() as db:
        t = (await db.execute(select(AgentTask).where(AgentTask.id == task_id))).scalar_one()
        assert t.status == "succeeded"

        u = (await db.execute(select(User).where(User.id == t.user_id))).scalar_one()
        assert u.credits == 29  # 成功扣 1 分

        msgs = (await db.execute(
            select(ConversationMessage).where(ConversationMessage.conversation_id == conv_id)
        )).scalars().all()
        assert any(m.role == "assistant" and m.content == "可以做" for m in msgs)


@pytest.mark.asyncio
async def test_execute_agent_task_insufficient_credits(monkeypatch):
    """积分不足：任务 failed 且提示积分不足，不扣分。"""
    engine, factory = _make_static_factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(exe, "async_session_factory", factory)
    monkeypatch.setattr(exe, "AgentOrchestrator", _FakeOrchestrator)

    async with factory() as db:
        user = User(email="task-nocred@test.com", username="tasknocred", password_hash="x", credits=0)
        db.add(user)
        await db.flush()
        task = AgentTask(user_id=user.id, task_type="agent_run", status="running",
                         input=json.dumps({"instruction": "hi", "conversation_id": ""}, ensure_ascii=False),
                         cost=1)
        db.add(task)
        await db.commit()
        task_id = task.id

    await exe.execute_agent_task(task_id)

    async with factory() as db:
        t = (await db.execute(select(AgentTask).where(AgentTask.id == task_id))).scalar_one()
        assert t.status == "failed"
        assert "积分不足" in (t.error or "")


@pytest.mark.asyncio
async def test_execute_agent_task_partial_does_not_charge(monkeypatch):
    """部分完成不能伪装成 succeeded，也不应扣整单积分。"""
    engine, factory = _make_static_factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(exe, "async_session_factory", factory)
    monkeypatch.setattr(exe, "AgentOrchestrator", _PartialOrchestrator)

    async with factory() as db:
        user = User(email="task-partial@test.com", username="partial", password_hash="x", credits=30)
        db.add(user)
        await db.flush()
        task = AgentTask(
            user_id=user.id,
            task_type="agent_run",
            status="running",
            input=json.dumps({"instruction": "抓取商品", "conversation_id": ""}, ensure_ascii=False),
            cost=1,
        )
        db.add(task)
        await db.commit()
        task_id = task.id
        user_id = user.id

    await exe.execute_agent_task(task_id)

    async with factory() as db:
        task_now = (await db.execute(select(AgentTask).where(AgentTask.id == task_id))).scalar_one()
        user_now = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
        assert task_now.status == "partial"
        assert user_now.credits == 30


# ── 调度器抢占 + 僵尸任务恢复 ──────────────────────────────────
@pytest.mark.asyncio
async def test_dispatch_agent_tasks_wires_execution(monkeypatch):
    """分发接线：_dispatch_agent_tasks 抢占后把任务交给执行器（asyncio.gather）。"""
    from app.services import scheduler as sched_module
    from app.services import agent_task_executor as exe_module

    engine, factory = _make_static_factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(sched_module, "async_session_factory", factory)

    executed: list[str] = []

    async def fake_execute(task_id):
        executed.append(str(task_id))

    monkeypatch.setattr(exe_module, "execute_agent_task", fake_execute)

    async with factory() as db:
        user = User(email="wire@test.com", username="wireuser", password_hash="x", credits=30)
        db.add(user)
        await db.flush()
        task = AgentTask(user_id=user.id, task_type="agent_run", status="pending",
                         input=json.dumps({"instruction": "hi"}, ensure_ascii=False), cost=1)
        db.add(task)
        await db.commit()
        task_id = task.id

    sched = sched_module.SchedulerService()
    await sched._dispatch_agent_tasks()

    assert len(executed) == 1
    assert executed[0] == str(task_id)


@pytest.mark.asyncio
async def test_claim_agent_tasks_recovers_stale(monkeypatch):
    """抢占逻辑：running 超时任务重新入队（attempt+1），pending 被抢占为 running。"""
    from app.services import scheduler as sched_module

    engine, factory = _make_static_factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(sched_module, "async_session_factory", factory)

    async with factory() as db:
        user = User(email="claim@test.com", username="claimuser", password_hash="x", credits=30)
        db.add(user)
        await db.flush()
        stale = AgentTask(
            user_id=user.id, task_type="agent_run", status="running", attempt=0,
            input=json.dumps({"instruction": "hi"}, ensure_ascii=False),
            started_at=datetime.now(timezone.utc) - timedelta(minutes=10), cost=1,
        )
        pending = AgentTask(
            user_id=user.id, task_type="agent_run", status="pending",
            input=json.dumps({"instruction": "hi"}, ensure_ascii=False), cost=1,
        )
        db.add_all([stale, pending])
        await db.commit()
        stale_id, pending_id = stale.id, pending.id

    sched = sched_module.SchedulerService()
    claimed = await sched._claim_agent_tasks()

    async with factory() as db:
        stale_now = (await db.execute(select(AgentTask).where(AgentTask.id == stale_id))).scalar_one()
        pending_now = (await db.execute(select(AgentTask).where(AgentTask.id == pending_id))).scalar_one()
        # 僵尸任务重新入队
        assert stale_now.status == "pending"
        assert stale_now.attempt == 1
        assert stale_now.started_at is None
        # 本来 pending 的任务被抢占为 running
        assert pending_now.status == "running"
        assert pending_now.started_at is not None
        # 抢占返回里只有 pending 那条（僵尸任务只是重新入队，不在本轮执行）
        assert len(claimed) == 1
        assert claimed[0].id == pending_id
