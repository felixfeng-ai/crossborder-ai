"""add agent conversation workspace scope

Revision ID: 036_agent_workspace
Revises: 035_video_provider_abstraction
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision: str = "036_agent_workspace"
down_revision: Union[str, None] = "035_video_provider_abstraction"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("conversations"):
        op.add_column(
            "conversations",
            sa.Column(
                "workspace",
                sa.String(length=20),
                nullable=False,
                server_default="general",
            ),
        )
    else:
        # 生产历史上存在被错误 stamp 且缺少 Agent 表的库，补建最小完整结构。
        op.create_table(
            "conversations",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("title", sa.String(length=200), nullable=True),
            sa.Column(
                "workspace",
                sa.String(length=20),
                nullable=False,
                server_default="general",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
            ),
        )
        op.create_index(
            "ix_conversations_user_id",
            "conversations",
            ["user_id"],
        )
        if not inspector.has_table("conversation_messages"):
            op.create_table(
                "conversation_messages",
                sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
                sa.Column(
                    "conversation_id",
                    UUID(as_uuid=True),
                    sa.ForeignKey("conversations.id", ondelete="CASCADE"),
                    nullable=False,
                ),
                sa.Column("role", sa.String(length=20), nullable=False),
                sa.Column("content", sa.Text(), nullable=False),
                sa.Column("steps", sa.Text(), nullable=True),
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                ),
            )
            op.create_index(
                "ix_conversation_messages_conversation_id",
                "conversation_messages",
                ["conversation_id"],
            )
    op.create_index(
        "ix_conversations_workspace",
        "conversations",
        ["workspace"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversations_workspace",
        table_name="conversations",
    )
    op.drop_column("conversations", "workspace")
