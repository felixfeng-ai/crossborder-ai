"""VeyaShip - Agent 流式输出（SSE）测试

覆盖：
1. 编排器 on_step 回调：工作流每完成一步触发一次，回调收到当前累积的 steps
2. _sse_event 纯函数：pending/running/步骤增长/succeeded/failed/无变化 各状态的事件计算
3. SSE 端点 HTTP 层：succeeded 任务推 `event: done` 并自动关闭；running 任务推 `event: step`
"""

import asyncio
import copy
import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.main import app
from app.models.agent_task import AgentTask
from app.models.user import User
from app.routers.agent import _sse_event
from app.services.ai.agent_orchestrator import AgentOrchestrator


# ── 编排器 on_step 回调 ────────────────────────────────────────
@pytest.mark.asyncio
async def test_run_workflow_emits_step_callback(monkeypatch):
    """工作流每完成一步触发一次 on_step，回调收到当前累积的 steps。"""
    calls: list[int] = []

    async def fake_on_step(steps: list[dict]) -> None:
        calls.append(len(steps))

    orch = AgentOrchestrator(user=None, db=None, on_step=fake_on_step)

    async def fake_store_check(params: dict) -> dict:
        return {"action": "store_check", "status": "success", "summary": "巡检完成"}

    monkeypatch.setattr(orch, "_do_store_check", fake_store_check)

    result = await orch.run_workflow("store_check", {})

    assert calls == [1], "单步工作流应恰好触发一次回调，steps 长度 1"
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_run_react_emits_running_step_before_tool_completes(monkeypatch):
    """外部查询开始时就推送阶段，避免用户只看到通用加载动画。"""
    calls: list[list[dict]] = []

    async def capture_steps(steps: list[dict]) -> None:
        calls.append(copy.deepcopy(steps))

    orch = AgentOrchestrator(user=None, db=None, on_step=capture_steps)
    responses = [
        {
            "content": "",
            "tool_calls": [{
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "select_products",
                    "arguments": '{"keyword": "宠物碗"}',
                },
            }],
        },
        {"content": "推荐完成", "tool_calls": []},
    ]

    async def fake_chat(messages, tools=None, max_tokens=2000):
        return responses.pop(0)

    async def fake_execute(action, params):
        return {
            "action": action,
            "status": "success",
            "summary": "市场数据已读取",
        }

    monkeypatch.setattr(orch.llm, "chat_with_tools", fake_chat)
    monkeypatch.setattr(orch, "_execute_step", fake_execute)

    await orch.run_react("推荐几个宠物碗")

    assert len(calls) == 2
    assert calls[0][0]["action"] == "select_products"
    assert calls[0][0]["status"] == "running"
    assert "宠物碗" in calls[0][0]["summary"]
    assert calls[1][0]["status"] == "success"
    assert isinstance(calls[1][0]["duration_ms"], int)
    assert calls[1][0]["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_run_react_parallelizes_safe_reads_and_preserves_order(monkeypatch):
    """只并发安全读取工具，结果仍按模型原始 tool_calls 顺序落库。"""
    orch = AgentOrchestrator(user=None, db=None)
    started: set[str] = set()
    both_started = asyncio.Event()
    responses = [
        {
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "analyze_category",
                        "arguments": '{"keyword": "蓝牙耳机"}',
                    },
                },
                {
                    "id": "call-2",
                    "type": "function",
                    "function": {
                        "name": "find_1688_sources",
                        "arguments": '{"keyword": "蓝牙耳机"}',
                    },
                },
            ],
        },
        {"content": "完成", "tool_calls": []},
    ]

    async def fake_chat(messages, tools=None, max_tokens=2000):
        return responses.pop(0)

    async def fake_execute(action, params):
        started.add(action)
        if len(started) == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=0.5)
        if action == "analyze_category":
            await asyncio.sleep(0.03)
        return {"action": action, "status": "success", "summary": action}

    monkeypatch.setattr(orch.llm, "chat_with_tools", fake_chat)
    monkeypatch.setattr(orch, "_execute_step", fake_execute)

    result = await orch.run_react("比较品类和货源")

    assert started == {"analyze_category", "find_1688_sources"}
    assert [step["action"] for step in result["steps"]] == [
        "analyze_category",
        "find_1688_sources",
    ]
    assert all(isinstance(step["duration_ms"], int) for step in result["steps"])


# ── _sse_event 纯函数 ──────────────────────────────────────────
def _task(**overrides) -> AgentTask:
    base = dict(
        user_id=uuid.uuid4(),
        task_type="agent_run",
        status="running",
        input=json.dumps({"instruction": "hi"}, ensure_ascii=False),
    )
    base.update(overrides)
    return AgentTask(**base)


def test_sse_event_pending():
    """pending → 推 event: step，携带空 steps"""
    changed, event, count = _sse_event(_task(status="pending"), None, 0)
    assert changed
    assert "event: step" in event
    assert '"status": "pending"' in event
    assert '"steps": []' in event
    assert count == 0


def test_sse_event_step_growth():
    """步骤数增长 → 推 event: step，携带全部累积 steps"""
    steps = [{"action": "store_check", "status": "success", "summary": "巡检完成"}]
    progress = json.dumps({"steps": steps}, ensure_ascii=False)
    changed, event, count = _sse_event(_task(status="running", progress=progress), "running", 0)
    assert changed
    assert count == 1
    assert "event: step" in event
    assert "store_check" in event


def test_sse_event_no_change():
    """状态与步骤数都没变 → 不推事件"""
    steps = [{"action": "answer", "status": "success"}]
    progress = json.dumps({"steps": steps}, ensure_ascii=False)
    changed, event, _ = _sse_event(_task(status="running", progress=progress), "running", 1)
    assert not changed
    assert event is None


def test_sse_event_detects_same_count_progress_transition():
    """同一步从 running 变 success 时步骤数不变，也必须推送最新内容。"""
    running_progress = json.dumps({
        "steps": [{
            "action": "select_products",
            "status": "running",
            "summary": "正在获取 Amazon 市场样本",
        }],
    }, ensure_ascii=False)
    completed_progress = json.dumps({
        "steps": [{
            "action": "select_products",
            "status": "success",
            "summary": "市场样本已读取",
        }],
    }, ensure_ascii=False)

    changed, event, count = _sse_event(
        _task(status="running", progress=completed_progress),
        "running",
        1,
        last_progress=running_progress,
    )

    assert changed
    assert count == 1
    assert "event: step" in event
    assert '"status": "success"' in event


def test_sse_event_succeeded():
    """succeeded → 推 event: done，带 summary/steps/conversation_id"""
    steps = [{"action": "answer", "status": "success"}]
    task = _task(
        status="succeeded",
        progress=json.dumps({"steps": steps}, ensure_ascii=False),
        result=json.dumps(
            {"summary": "全部完成", "steps": steps, "conversation_id": "abc"},
            ensure_ascii=False,
        ),
    )
    changed, event, _ = _sse_event(task, "running", 1)
    assert changed
    assert "event: done" in event
    assert '"status": "succeeded"' in event
    assert '"summary": "全部完成"' in event
    assert '"conversation_id": "abc"' in event


def test_sse_event_failed():
    """failed → 推 event: done，带错误信息"""
    task = _task(status="failed", error="积分不足")
    changed, event, _ = _sse_event(task, "running", 0)
    assert changed
    assert "event: done" in event
    assert '"status": "failed"' in event
    assert "积分不足" in event


def test_sse_event_partial_is_terminal_done():
    """partial 也是终态，不能继续占着 SSE 到三分钟超时。"""
    task = _task(
        status="partial",
        result=json.dumps(
            {"summary": "部分完成", "steps": [], "conversation_id": ""},
            ensure_ascii=False,
        ),
    )
    changed, event, _ = _sse_event(task, "running", 0)
    assert changed
    assert "event: done" in event
    assert '"status": "partial"' in event


# ── SSE 端点 HTTP 层 ───────────────────────────────────────────
async def _register(client, db_session, email: str) -> dict:
    """注册唯一邮箱用户，返回 auth header + user_id。"""
    resp = await client.post("/api/v1/auth/register", json={
        "email": email,
        "username": email.split("@")[0],
        "password": "testpass123",
    })
    assert resp.status_code == 201, resp.text
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    return {"Authorization": f"Bearer {resp.json()['access_token']}", "user_id": user.id}


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_status", ["succeeded", "partial"])
async def test_agent_task_stream_terminal_done(
    client,
    db_session,
    terminal_status,
):
    """成功和部分成功任务都必须推 event: done 并自动关闭。"""
    reg = await _register(
        client,
        db_session,
        f"stream-{terminal_status}{uuid.uuid4().hex[:8]}@test.com",
    )
    steps = [{"action": "store_check", "status": "success", "summary": "巡检完成"}]
    task = AgentTask(
        user_id=reg["user_id"],
        task_type="agent_workflow",
        status=terminal_status,
        input=json.dumps({"workflow": "store_check", "params": {}}, ensure_ascii=False),
        result=json.dumps(
            {"summary": "全部完成", "steps": steps, "conversation_id": ""},
            ensure_ascii=False,
        ),
        cost=1,
    )
    db_session.add(task)
    await db_session.commit()
    task_id = str(task.id)

    lines: list[str] = []

    async def read_until_closed():
        async with client.stream(
            "GET",
            f"/api/v1/agent/tasks/{task_id}/stream",
            headers={"Authorization": reg["Authorization"]},
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            async for line in resp.aiter_lines():
                lines.append(line)

    await asyncio.wait_for(read_until_closed(), timeout=3)

    assert any("event: done" in line for line in lines), lines
    data_line = next(line for line in lines if line.startswith("data: "))
    payload = json.loads(data_line[len("data: "):])
    assert payload["status"] == terminal_status
    assert payload["summary"] == "全部完成"
    assert payload["steps"][0]["action"] == "store_check"


@pytest.mark.asyncio
async def test_agent_task_stream_running_step():
    """running 任务 → 流推 event: step；执行器完成后 → 流推 event: done 并自然关闭

    用独立文件型 SQLite + 后台任务模拟执行器：ASGITransport 会等整个 ASGI 应用
    结束才返回（SSE 永续流需自然收尾），后台任务把任务从 running 改为 succeeded，
    让生成器走完 step → done 完整生命周期。
    """
    import os
    import tempfile

    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker as _asm

    from app.core.database import get_db as _get_db

    db_file = os.path.join(tempfile.gettempdir(), f"veya_stream_{uuid.uuid4().hex[:8]}.db")
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    async with engine.begin() as conn:
        # 文件型 SQLite 默认 rollback journal 模式：流读线程与后台写线程
        # 是两条连接，读写短暂重叠就可能让后台写撞 database is locked，
        # 任务永远成功不了 → SSE 流卡在 running，测试挂起（全套件下时序漂移更明显）。
        # 开 WAL + busy_timeout，模拟生产 PG 的「读不阻塞写」语义，让测试确定化。
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA busy_timeout=5000"))
        await conn.run_sync(Base.metadata.create_all)
    factory = _asm(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as db:
        async def override_get_db():
            yield db

        app.dependency_overrides[_get_db] = override_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
                reg = await _register(client, db, f"stream-run{uuid.uuid4().hex[:8]}@test.com")
                steps = [{"action": "scrape_1688", "status": "success", "summary": "已抓取商品"}]
                task = AgentTask(
                    user_id=reg["user_id"],
                    task_type="agent_run",
                    status="running",
                    input=json.dumps({"instruction": "hi", "conversation_id": ""}, ensure_ascii=False),
                    progress=json.dumps({"steps": steps}, ensure_ascii=False),
                    cost=1,
                )
                db.add(task)
                await db.commit()
                task_id = str(task.id)
                # 快照 UUID：流开始后 SSE 生成器的 db.rollback() 会让外层 task 对象
                # 过期（expire）。后台任务稍后在编译查询时访问 task.id 会触发
                # 异步刷新 → MissingGreenlet。这里先取出来，后台只用普通值。
                task_uuid = task.id

                async def complete_task_later():
                    """延迟模拟执行器完成任务（succeeded）。"""
                    await asyncio.sleep(1.5)
                    async with factory() as upd:
                        # 用快照 UUID 查（id 是 PG_UUID 列，SQLite 下存无连字符 hex；
                        # str(task.id) 带连字符会对不上 → NoResultFound）。
                        t = (await upd.execute(select(AgentTask).where(AgentTask.id == task_uuid))).scalar_one()
                        t.status = "succeeded"
                        t.result = json.dumps(
                            {"summary": "全部完成", "steps": steps, "conversation_id": ""},
                            ensure_ascii=False,
                        )
                        await upd.commit()

                bg = asyncio.create_task(complete_task_later())

                async def read_stream_until_done() -> list[str]:
                    """读 SSE 流直到收到 succeeded（流随后自然关闭）。"""
                    lines_list: list[str] = []
                    async with client.stream(
                        "GET",
                        f"/api/v1/agent/tasks/{task_id}/stream",
                        headers={"Authorization": reg["Authorization"]},
                    ) as resp:
                        assert resp.status_code == 200
                        async for line in resp.aiter_lines():
                            lines_list.append(line)
                            if line.startswith("data: "):
                                payload = json.loads(line[len("data: "):])
                                if payload.get("status") == "succeeded":
                                    break  # 读到完成事件，流将自然关闭
                    return lines_list

                # 硬超时兜底：万一流异常挂起，快速失败而不是拖死整套测试
                try:
                    lines = await asyncio.wait_for(read_stream_until_done(), timeout=20)
                except asyncio.TimeoutError:
                    if bg.done():
                        exc = bg.exception()
                        if exc is not None:
                            raise exc  # 直接抛原始异常，带完整 traceback 定位失败行
                    raise

                await bg  # 后台任务应已完成；若它失败，这里会抛出真实异常
        finally:
            app.dependency_overrides.clear()
            await engine.dispose()
            for suffix in ("", "-wal", "-shm"):
                if os.path.exists(db_file + suffix):
                    os.remove(db_file + suffix)

    assert any("event: step" in line for line in lines), lines
    assert any("event: done" in line for line in lines), lines
    step_payload = next(
        json.loads(line[len("data: "):])
        for line in lines
        if line.startswith("data: ") and '"running"' in line
    )
    assert step_payload["steps"][0]["action"] == "scrape_1688"
    done_payload = next(
        json.loads(line[len("data: "):])
        for line in lines
        if line.startswith("data: ") and '"succeeded"' in line
    )
    assert done_payload["summary"] == "全部完成"


@pytest.mark.asyncio
async def test_agent_task_stream_other_users_task_404(client, db_session):
    """不能订阅别人的任务：非本人任务 404"""
    reg_a = await _register(client, db_session, f"stream-owner{uuid.uuid4().hex[:8]}@test.com")
    reg_b = await _register(client, db_session, f"stream-voyeur{uuid.uuid4().hex[:8]}@test.com")
    task = AgentTask(
        user_id=reg_a["user_id"],
        task_type="agent_run",
        status="running",
        input=json.dumps({"instruction": "hi", "conversation_id": ""}, ensure_ascii=False),
        cost=1,
    )
    db_session.add(task)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/agent/tasks/{task.id}/stream",
        headers={"Authorization": reg_b["Authorization"]},
    )
    assert resp.status_code == 404
