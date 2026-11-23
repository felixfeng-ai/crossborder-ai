"""add billing reconciliation stop-payment cases

Revision ID: 069_billing_reconciliation
Revises: 068_media_library
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "069_billing_reconciliation"
down_revision: Union[str, None] = "068_media_library"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "billing_reconciliation_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="open",
        ),
        sa.Column(
            "snapshot_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "note",
            sa.String(length=500),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "approved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
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
    op.create_index(
        "ix_billing_reconciliation_cases_workspace_id",
        "billing_reconciliation_cases",
        ["workspace_id"],
    )
    op.create_index(
        "ix_billing_reconciliation_cases_status",
        "billing_reconciliation_cases",
        ["status"],
    )
    op.create_index(
        "ix_billing_reconciliation_cases_approved_by_user_id",
        "billing_reconciliation_cases",
        ["approved_by_user_id"],
    )
    op.create_index(
        "ix_billing_reconciliation_cases_status_created",
        "billing_reconciliation_cases",
        ["status", "created_at"],
    )
    op.create_index(
        "uq_billing_reconciliation_cases_open_workspace",
        "billing_reconciliation_cases",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
        sqlite_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_billing_reconciliation_cases_open_workspace",
        table_name="billing_reconciliation_cases",
    )
    op.drop_index(
        "ix_billing_reconciliation_cases_status_created",
        table_name="billing_reconciliation_cases",
    )
    op.drop_index(
        "ix_billing_reconciliation_cases_approved_by_user_id",
        table_name="billing_reconciliation_cases",
    )
    op.drop_index(
        "ix_billing_reconciliation_cases_status",
        table_name="billing_reconciliation_cases",
    )
    op.drop_index(
        "ix_billing_reconciliation_cases_workspace_id",
        table_name="billing_reconciliation_cases",
    )
    op.drop_table("billing_reconciliation_cases")
