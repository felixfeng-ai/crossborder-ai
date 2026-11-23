"""受控领域动作的持久化运行记录。"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ActionRun(Base):
    """一次动作从计划、确认到执行和回读核验的完整轨迹。"""

    __tablename__ = "action_runs"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "action_id",
            "idempotency_key",
            name="uq_action_runs_workspace_action_idempotency",
        ),
        Index("ix_action_runs_workspace_status", "workspace_id", "status"),
        Index("ix_action_runs_workspace_platform", "workspace_id", "platform"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    work_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("work_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_turn_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_turns.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    action_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1.0",
        server_default="1.0",
    )
    platform: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(60), nullable=False)
    target_id: Mapped[str] = mapped_column(String(200), nullable=False)
    input_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        server_default="{}",
    )
    before_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="planned",
        server_default="planned",
        index=True,
    )
    risk_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="low",
        server_default="low",
    )
    autonomy_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="confirm",
        server_default="confirm",
    )
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_autonomy_policies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    policy_version: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    policy_snapshot_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    attempt: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    verification_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
