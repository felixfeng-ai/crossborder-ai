"""create agent turns, work items and commands

Revision ID: 051_agent_work_items
Revises: 050_workspace_core
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "051_agent_work_items"
down_revision: Union[str, None] = "050_workspace_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("input_type", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "created_by_user_id",
            "idempotency_key",
            name="uq_agent_turns_workspace_actor_idempotency",
        ),
    )
    op.create_index("ix_agent_turns_workspace_id", "agent_turns", ["workspace_id"])
    op.create_index(
        "ix_agent_turns_created_by_user_id",
        "agent_turns",
        ["created_by_user_id"],
    )
    op.create_index("ix_agent_turns_status", "agent_turns", ["status"])
    op.create_index(
        "ix_agent_turns_workspace_status",
        "agent_turns",
        ["workspace_id", "status"],
    )

    op.create_table(
        "agent_turn_inputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_turn_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_turns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("input_type", sa.String(length=20), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="received",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_agent_turn_inputs_workspace_id",
        "agent_turn_inputs",
        ["workspace_id"],
    )
    op.create_index(
        "ix_agent_turn_inputs_agent_turn_id",
        "agent_turn_inputs",
        ["agent_turn_id"],
    )
    op.create_index(
        "ix_agent_turn_inputs_asset_id",
        "agent_turn_inputs",
        ["asset_id"],
    )
    op.create_index(
        "ix_agent_turn_inputs_status",
        "agent_turn_inputs",
        ["status"],
    )

    op.create_table(
        "work_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_work_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("work_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            server_default="agent",
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "summary",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="waiting_user",
        ),
        sa.Column(
            "priority",
            sa.String(length=20),
            nullable=False,
            server_default="normal",
        ),
        sa.Column(
            "requires_action",
            sa.String(length=30),
            nullable=False,
            server_default="none",
        ),
        sa.Column(
            "current_step",
            sa.String(length=200),
            nullable=False,
            server_default="等待处理",
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "assignee_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_type", sa.String(length=50), nullable=True),
        sa.Column("source_id", sa.String(length=128), nullable=True),
        sa.Column("source_version", sa.String(length=64), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    for column in (
        "workspace_id",
        "parent_work_item_id",
        "kind",
        "status",
        "priority",
        "assignee_user_id",
        "source_type",
        "source_id",
        "due_at",
    ):
        op.create_index(f"ix_work_items_{column}", "work_items", [column])
    op.create_index(
        "ix_work_items_workspace_status",
        "work_items",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_work_items_workspace_due",
        "work_items",
        ["workspace_id", "due_at"],
    )

    op.create_table(
        "work_item_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "work_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("work_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_work_item_events_workspace_id",
        "work_item_events",
        ["workspace_id"],
    )
    op.create_index(
        "ix_work_item_events_work_item_id",
        "work_item_events",
        ["work_item_id"],
    )
    op.create_index(
        "ix_work_item_events_event_type",
        "work_item_events",
        ["event_type"],
    )

    op.create_table(
        "work_item_commands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "work_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("work_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column(
            "payload_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="accepted",
        ),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "workspace_id",
            "actor_user_id",
            "idempotency_key",
            name="uq_work_item_commands_actor_idempotency",
        ),
    )
    for column in ("workspace_id", "work_item_id", "actor_user_id", "status"):
        op.create_index(
            f"ix_work_item_commands_{column}",
            "work_item_commands",
            [column],
        )


def downgrade() -> None:
    for column in ("status", "actor_user_id", "work_item_id", "workspace_id"):
        op.drop_index(
            f"ix_work_item_commands_{column}",
            table_name="work_item_commands",
        )
    op.drop_table("work_item_commands")

    op.drop_index(
        "ix_work_item_events_event_type",
        table_name="work_item_events",
    )
    op.drop_index(
        "ix_work_item_events_work_item_id",
        table_name="work_item_events",
    )
    op.drop_index(
        "ix_work_item_events_workspace_id",
        table_name="work_item_events",
    )
    op.drop_table("work_item_events")

    op.drop_index("ix_work_items_workspace_due", table_name="work_items")
    op.drop_index("ix_work_items_workspace_status", table_name="work_items")
    for column in (
        "due_at",
        "source_id",
        "source_type",
        "assignee_user_id",
        "priority",
        "status",
        "kind",
        "parent_work_item_id",
        "workspace_id",
    ):
        op.drop_index(f"ix_work_items_{column}", table_name="work_items")
    op.drop_table("work_items")

    op.drop_index(
        "ix_agent_turn_inputs_status",
        table_name="agent_turn_inputs",
    )
    op.drop_index(
        "ix_agent_turn_inputs_asset_id",
        table_name="agent_turn_inputs",
    )
    op.drop_index(
        "ix_agent_turn_inputs_agent_turn_id",
        table_name="agent_turn_inputs",
    )
    op.drop_index(
        "ix_agent_turn_inputs_workspace_id",
        table_name="agent_turn_inputs",
    )
    op.drop_table("agent_turn_inputs")

    op.drop_index(
        "ix_agent_turns_workspace_status",
        table_name="agent_turns",
    )
    op.drop_index("ix_agent_turns_status", table_name="agent_turns")
    op.drop_index(
        "ix_agent_turns_created_by_user_id",
        table_name="agent_turns",
    )
    op.drop_index("ix_agent_turns_workspace_id", table_name="agent_turns")
    op.drop_table("agent_turns")
