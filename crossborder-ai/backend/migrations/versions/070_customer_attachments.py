"""add customer attachments and delivery errors

Revision ID: 070_customer_attachments
Revises: 069_billing_reconciliation
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "070_customer_attachments"
down_revision: Union[str, None] = "069_billing_reconciliation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("customer_messages") as batch:
        batch.add_column(
            sa.Column("delivery_error_code", sa.String(length=80), nullable=True)
        )
        batch.add_column(
            sa.Column("delivery_error_message", sa.Text(), nullable=True)
        )

    op.create_table(
        "customer_attachments",
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
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customer_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "storage_key",
            name="uq_customer_attachments_storage_key",
        ),
    )
    for column in ("workspace_id", "thread_id", "message_id"):
        op.create_index(
            f"ix_customer_attachments_{column}",
            "customer_attachments",
            [column],
        )
    op.create_index(
        "ix_customer_attachments_message",
        "customer_attachments",
        ["workspace_id", "message_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_customer_attachments_message",
        table_name="customer_attachments",
    )
    for column in ("message_id", "thread_id", "workspace_id"):
        op.drop_index(
            f"ix_customer_attachments_{column}",
            table_name="customer_attachments",
        )
    op.drop_table("customer_attachments")
    with op.batch_alter_table("customer_messages") as batch:
        batch.drop_column("delivery_error_message")
        batch.drop_column("delivery_error_code")
