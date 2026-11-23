"""create customer channel, thread, message and reply draft tables

Revision ID: 054_customer_channels
Revises: 053_mobile_asset_workspace
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "054_customer_channels"
down_revision: Union[str, None] = "053_mobile_asset_workspace"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer_channels",
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
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column(
            "external_account_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("credentials_ciphertext", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "scopes_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
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
            "provider",
            "external_account_id",
            name="uq_customer_channels_account",
        ),
    )
    for column in (
        "workspace_id",
        "created_by_user_id",
        "status",
    ):
        op.create_index(
            f"ix_customer_channels_{column}",
            "customer_channels",
            [column],
        )

    op.create_table(
        "customer_threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customer_channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "external_thread_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "thread_type",
            sa.String(length=30),
            nullable=False,
            server_default="direct_message",
        ),
        sa.Column("customer_ref", sa.String(length=255), nullable=True),
        sa.Column(
            "customer_email_hash",
            sa.String(length=128),
            nullable=True,
        ),
        sa.Column("customer_address_ciphertext", sa.Text(), nullable=True),
        sa.Column("related_order_id", sa.String(length=128), nullable=True),
        sa.Column("related_product_id", sa.String(length=128), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=True),
        sa.Column(
            "language",
            sa.String(length=20),
            nullable=False,
            server_default="en",
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="new",
        ),
        sa.Column(
            "priority",
            sa.String(length=20),
            nullable=False,
            server_default="normal",
        ),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "unread_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "assigned_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
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
        sa.UniqueConstraint(
            "workspace_id",
            "channel_id",
            "external_thread_id",
            name="uq_customer_threads_external",
        ),
    )
    for column in (
        "workspace_id",
        "channel_id",
        "customer_email_hash",
        "related_order_id",
        "related_product_id",
        "status",
        "last_message_at",
        "assigned_user_id",
    ):
        op.create_index(
            f"ix_customer_threads_{column}",
            "customer_threads",
            [column],
        )
    op.create_index(
        "ix_customer_threads_workspace_status",
        "customer_threads",
        ["workspace_id", "status"],
    )

    op.create_table(
        "customer_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customer_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "external_message_id",
            sa.String(length=500),
            nullable=True,
        ),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column(
            "body_text",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column(
            "asset_ids_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "send_status",
            sa.String(length=20),
            nullable=False,
            server_default="received",
        ),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_customer_messages_idempotency",
        ),
    )
    for column in (
        "workspace_id",
        "thread_id",
        "external_message_id",
        "send_status",
    ):
        op.create_index(
            f"ix_customer_messages_{column}",
            "customer_messages",
            [column],
        )

    op.create_table(
        "reply_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customer_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "language",
            sa.String(length=20),
            nullable=False,
            server_default="en",
        ),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column(
            "risk_level",
            sa.String(length=20),
            nullable=False,
            server_default="low",
        ),
        sa.Column(
            "policy_result_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="generating",
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
        sa.UniqueConstraint(
            "thread_id",
            "version",
            name="uq_reply_drafts_thread_version",
        ),
    )
    for column in (
        "workspace_id",
        "thread_id",
        "agent_run_id",
        "status",
    ):
        op.create_index(
            f"ix_reply_drafts_{column}",
            "reply_drafts",
            [column],
        )


def downgrade() -> None:
    for column in ("status", "agent_run_id", "thread_id", "workspace_id"):
        op.drop_index(f"ix_reply_drafts_{column}", table_name="reply_drafts")
    op.drop_table("reply_drafts")
    for column in (
        "send_status",
        "external_message_id",
        "thread_id",
        "workspace_id",
    ):
        op.drop_index(
            f"ix_customer_messages_{column}",
            table_name="customer_messages",
        )
    op.drop_table("customer_messages")
    op.drop_index(
        "ix_customer_threads_workspace_status",
        table_name="customer_threads",
    )
    for column in (
        "assigned_user_id",
        "last_message_at",
        "status",
        "related_product_id",
        "related_order_id",
        "customer_email_hash",
        "channel_id",
        "workspace_id",
    ):
        op.drop_index(
            f"ix_customer_threads_{column}",
            table_name="customer_threads",
        )
    op.drop_table("customer_threads")
    for column in ("status", "created_by_user_id", "workspace_id"):
        op.drop_index(
            f"ix_customer_channels_{column}",
            table_name="customer_channels",
        )
    op.drop_table("customer_channels")
