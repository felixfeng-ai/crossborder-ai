"""VeyaShip AI - Agent 异步任务模型

异步任务队列：/agent/run 与 /agent/workflow 不再同步阻塞执行，
而是创建一条 agent_task 记录立即返回 task_id，由后台调度器
（APScheduler + PG advisory lock）消费执行，前端轮询结果。

状态机：
  pending → running → succeeded | failed
  卡在 running 超过 5 分钟 → 重新置回 pending（attempt+1），
  attempt ≥ 3 → 标记 failed（防止 worker 重启后任务永久滞留）。
"""

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgentTask(Base):
    """Agent 任务表 —— 每次提交一条任务，后台异步执行"""

    __tablename__ = "agent_tasks"
    __table_args__ = (
        # 幂等：同一工作区同一用户同一 Idempotency-Key 只允许一条任务。
        UniqueConstraint(
            "workspace_id",
            "user_id",
            "idempotency_key",
            name="uq_agent_task_workspace_idem",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # agent_run / agent_workflow
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # pending / running / succeeded / failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    # 任务入参（JSON）：agent_run → {instruction, conversation_id}；agent_workflow → {workflow, params}
    input: Mapped[str] = mapped_column(Text, nullable=False)
    # 执行中间进度（JSON）：{steps: [...]}，每完成一步由执行器写入，SSE 端点轮询推流
    progress: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 任务结果（JSON）：{summary, steps, conversation_id}
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 失败原因（用户可读中文）
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 幂等键（前端每次发送生成一个，防重复提交双扣积分/双建对话）
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 任务消耗积分（agent_run=1，agent_workflow=2），成功才扣
    cost: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # 已尝试执行次数（僵尸任务重新入队时递增）
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
