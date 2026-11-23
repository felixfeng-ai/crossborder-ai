"""create workspace core tables

Revision ID: 050_workspace_core
Revises: 049_product_media
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "050_workspace_core"
down_revision: Union[str, None] = "049_product_media"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False, unique=True),
        sa.Column(
            "type",
            sa.String(length=20),
            nullable=False,
            server_default="personal",
        ),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "settings_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
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
    op.create_index("ix_workspaces_slug", "workspaces", ["slug"])
    op.create_index("ix_workspaces_type", "workspaces", ["type"])
    op.create_index(
        "ix_workspaces_owner_user_id",
        "workspaces",
        ["owner_user_id"],
    )
    op.create_index("ix_workspaces_status", "workspaces", ["status"])
    op.create_index(
        "uq_workspaces_personal_owner",
        "workspaces",
        ["owner_user_id"],
        unique=True,
        postgresql_where=sa.text("type = 'personal'"),
        sqlite_where=sa.text("type = 'personal'"),
    )

    op.create_table(
        "workspace_members",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "joined_at",
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
        "ix_workspace_members_status",
        "workspace_members",
        ["status"],
    )

    op.create_table(
        "workspace_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "invited_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_workspace_invitations_token",
        ),
    )
    op.create_index(
        "ix_workspace_invitations_workspace_id",
        "workspace_invitations",
        ["workspace_id"],
    )
    op.create_index(
        "ix_workspace_invitations_email",
        "workspace_invitations",
        ["email"],
    )
    op.create_index(
        "ix_workspace_invitations_expires_at",
        "workspace_invitations",
        ["expires_at"],
    )

    op.create_table(
        "workspace_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=True),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("before_json", sa.Text(), nullable=True),
        sa.Column("after_json", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(length=80), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_workspace_audit_logs_workspace_id",
        "workspace_audit_logs",
        ["workspace_id"],
    )
    op.create_index(
        "ix_workspace_audit_logs_actor_user_id",
        "workspace_audit_logs",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_workspace_audit_logs_action",
        "workspace_audit_logs",
        ["action"],
    )
    op.create_index(
        "ix_workspace_audit_logs_resource_type",
        "workspace_audit_logs",
        ["resource_type"],
    )
    op.create_index(
        "ix_workspace_audit_logs_resource_id",
        "workspace_audit_logs",
        ["resource_id"],
    )
    op.create_index(
        "ix_workspace_audit_logs_request_id",
        "workspace_audit_logs",
        ["request_id"],
    )
    op.create_index(
        "ix_workspace_audit_logs_created_at",
        "workspace_audit_logs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_audit_logs_created_at",
        table_name="workspace_audit_logs",
    )
    op.drop_index(
        "ix_workspace_audit_logs_request_id",
        table_name="workspace_audit_logs",
    )
    op.drop_index(
        "ix_workspace_audit_logs_resource_id",
        table_name="workspace_audit_logs",
    )
    op.drop_index(
        "ix_workspace_audit_logs_resource_type",
        table_name="workspace_audit_logs",
    )
    op.drop_index(
        "ix_workspace_audit_logs_action",
        table_name="workspace_audit_logs",
    )
    op.drop_index(
        "ix_workspace_audit_logs_actor_user_id",
        table_name="workspace_audit_logs",
    )
    op.drop_index(
        "ix_workspace_audit_logs_workspace_id",
        table_name="workspace_audit_logs",
    )
    op.drop_table("workspace_audit_logs")

    op.drop_index(
        "ix_workspace_invitations_expires_at",
        table_name="workspace_invitations",
    )
    op.drop_index(
        "ix_workspace_invitations_email",
        table_name="workspace_invitations",
    )
    op.drop_index(
        "ix_workspace_invitations_workspace_id",
        table_name="workspace_invitations",
    )
    op.drop_table("workspace_invitations")

    op.drop_index(
        "ix_workspace_members_status",
        table_name="workspace_members",
    )
    op.drop_table("workspace_members")

    op.drop_index(
        "uq_workspaces_personal_owner",
        table_name="workspaces",
    )
    op.drop_index("ix_workspaces_status", table_name="workspaces")
    op.drop_index(
        "ix_workspaces_owner_user_id",
        table_name="workspaces",
    )
    op.drop_index("ix_workspaces_type", table_name="workspaces")
    op.drop_index("ix_workspaces_slug", table_name="workspaces")
    op.drop_table("workspaces")
