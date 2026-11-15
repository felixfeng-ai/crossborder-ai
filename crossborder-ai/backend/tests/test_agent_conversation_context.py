"""Agent 会话延续、工作区角色和结构化确认测试。"""

import json
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.agent_task import AgentTask
from app.models.conversation import Conversation, ConversationMessage
from app.models.user import User
from app.services import agent_task_executor
from app.services.ai.agent_orchestrator import AgentOrchestrator


def test_confirmation_detection_handles_common_phrases():
    from app.services.agent_context import is_confirmation

    assert is_confirmation("可以")
    assert is_confirmation("好的，继续")
    assert is_confirmation("按这个来")
    assert not is_confirmation("先不要生成")
    assert not is_confirmation("可以换成第二个商品吗")


def test_extract_pending_action_from_last_assistant_message():
    from app.services.agent_context import extract_pending_action

    messages = [
        {"role": "user", "content": "生成视频"},
        {
            "role": "assistant",
            "content": "预计消耗 225 积分，请确认",
            "steps": [
                {
                    "action": "generate_product_video",
                    "status": "success",
                    "data": {
                        "requires_confirmation": True,
                        "pending_action": {
                            "action": "generate_product_video",
                            "params": {
                                "source_asset_id": "asset-1",
                                "duration": 15,
                            },
                            "estimated_credits": 225,
                        },
                    },
                }
            ],
        },
    ]

    pending = extract_pending_action(messages)
    assert pending is not None
    assert pending.action == "generate_product_video"
    assert pending.params["source_asset_id"] == "asset-1"
    assert pending.estimated_credits == 225


@pytest.mark.asyncio
async def test_video_tool_returns_structured_pending_action():
    orch = AgentOrchestrator(user=None, db=None, workspace="marketing")

    result = await orch._do_generate_product_video(
        {
            "source_asset_id": "asset-1",
            "prompt": "展示保温杯的冬季使用场景",
            "duration": 15,
            "ratio": "9:16",
            "confirmed": False,
        }
    )

    pending = result["data"]["pending_action"]
    assert pending["action"] == "generate_product_video"
    assert pending["params"]["source_asset_id"] == "asset-1"
    assert pending["params"]["duration"] == 15
    assert pending["estimated_credits"] > 0


@pytest.mark.asyncio
async def test_image_tool_returns_structured_pending_action():
    orch = AgentOrchestrator(user=None, db=None, workspace="general")

    result = await orch._do_generate_image_asset(
        {
            "prompt": "白色咖啡杯放在木质桌面",
            "mode": "free_creation",
            "quality_tier": "standard",
            "num_outputs": 1,
            "confirmed": False,
        }
    )

    pending = result["data"]["pending_action"]
    assert pending["action"] == "generate_image_asset"
    assert pending["params"]["quality_tier"] == "standard"
    assert pending["estimated_credits"] == 5


@pytest.mark.asyncio
async def test_run_react_injects_history_and_marketing_prompt(monkeypatch):
    orch = AgentOrchestrator(
        user=None,
        db=None,
        workspace="marketing",
    )
    captured = {}

    async def fake_chat(messages, tools=None, max_tokens=2000):
        captured["messages"] = messages
        return {"content": "请确认平台后再继续", "tool_calls": []}

    monkeypatch.setattr(orch.llm, "chat_with_tools", fake_chat)

    result = await orch.run_react(
        "可以",
        history=[
            {"role": "user", "content": "做一套 Shopify 营销方案"},
            {"role": "assistant", "content": "请确认平台和预算"},
        ],
    )

    assert result["summary"] == "请确认平台后再继续"
    messages = captured["messages"]
    assert "营销 Agent" in messages[0]["content"]
    assert messages[-2]["content"] == "请确认平台和预算"
    assert messages[-1] == {"role": "user", "content": "可以"}


def _factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine, async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.mark.asyncio
async def test_executor_resumes_pending_action_on_confirmation(monkeypatch):
    engine, factory = _factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(agent_task_executor, "async_session_factory", factory)

    captured = {}

    class FakeOrchestrator:
        def __init__(self, user, db, on_step=None, campaign_id=None):
            self.workspace = "general"

        async def run(self, instruction, history=None):
            captured["run"] = instruction
            return {"summary": "不应走普通模型路径", "status": "success", "steps": []}

        async def run_confirmed_action(self, action, params):
            captured["confirmed"] = (action, params)
            return {
                "summary": "视频任务已提交",
                "status": "success",
                "steps": [{"action": action, "status": "success"}],
            }

    monkeypatch.setattr(agent_task_executor, "AgentOrchestrator", FakeOrchestrator)

    async with factory() as db:
        user = User(
            email=f"pending-{uuid.uuid4().hex[:8]}@test.com",
            username="pending",
            password_hash="x",
            credits=300,
        )
        db.add(user)
        await db.flush()
        conv = Conversation(user_id=user.id, workspace="marketing")
        db.add(conv)
        await db.flush()
        db.add_all(
            [
                ConversationMessage(
                    conversation_id=conv.id,
                    role="user",
                    content="做一条 15 秒视频",
                ),
                ConversationMessage(
                    conversation_id=conv.id,
                    role="assistant",
                    content="预计消耗 225 积分，请确认",
                    steps=json.dumps(
                        [
                            {
                                "action": "generate_product_video",
                                "status": "success",
                                "data": {
                                    "requires_confirmation": True,
                                    "pending_action": {
                                        "action": "generate_product_video",
                                        "params": {
                                            "source_asset_id": "asset-1",
                                            "duration": 15,
                                        },
                                        "estimated_credits": 225,
                                    },
                                },
                            }
                        ],
                        ensure_ascii=False,
                    ),
                ),
                ConversationMessage(
                    conversation_id=conv.id,
                    role="user",
                    content="可以",
                ),
            ]
        )
        task = AgentTask(
            user_id=user.id,
            task_type="agent_run",
            status="running",
            input=json.dumps(
                {
                    "instruction": "可以",
                    "conversation_id": str(conv.id),
                    "workspace": "marketing",
                },
                ensure_ascii=False,
            ),
            cost=1,
        )
        db.add(task)
        await db.commit()
        task_id = task.id

    await agent_task_executor.execute_agent_task(task_id)

    assert "run" not in captured
    assert captured["confirmed"] == (
        "generate_product_video",
        {"source_asset_id": "asset-1", "duration": 15},
    )


@pytest.mark.asyncio
async def test_executor_passes_history_to_regular_run(monkeypatch):
    engine, factory = _factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(agent_task_executor, "async_session_factory", factory)

    captured = {}

    class FakeOrchestrator:
        def __init__(self, user, db, on_step=None, campaign_id=None):
            self.workspace = "general"

        async def run(self, instruction, history=None):
            captured["instruction"] = instruction
            captured["history"] = history
            return {"summary": "继续回答", "status": "success", "steps": []}

    monkeypatch.setattr(agent_task_executor, "AgentOrchestrator", FakeOrchestrator)

    async with factory() as db:
        user = User(
            email=f"history-{uuid.uuid4().hex[:8]}@test.com",
            username="history",
            password_hash="x",
            credits=30,
        )
        db.add(user)
        await db.flush()
        conv = Conversation(user_id=user.id, workspace="general")
        db.add(conv)
        await db.flush()
        db.add_all(
            [
                ConversationMessage(
                    conversation_id=conv.id,
                    role="user",
                    content="推荐一个蓝牙耳机商品",
                ),
                ConversationMessage(
                    conversation_id=conv.id,
                    role="assistant",
                    content="建议先比较三个候选商品",
                ),
                ConversationMessage(
                    conversation_id=conv.id,
                    role="user",
                    content="继续",
                ),
            ]
        )
        task = AgentTask(
            user_id=user.id,
            task_type="agent_run",
            status="running",
            input=json.dumps(
                {
                    "instruction": "继续",
                    "conversation_id": str(conv.id),
                    "workspace": "general",
                },
                ensure_ascii=False,
            ),
            cost=1,
        )
        db.add(task)
        await db.commit()
        task_id = task.id

    await agent_task_executor.execute_agent_task(task_id)

    assert captured["instruction"] == "继续"
    assert any(item["content"] == "建议先比较三个候选商品" for item in captured["history"])
    assert all(item["content"] != "继续" for item in captured["history"])
