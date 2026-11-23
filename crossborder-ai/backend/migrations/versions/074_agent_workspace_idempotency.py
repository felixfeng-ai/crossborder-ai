"""scope agent idempotency to workspaces

Revision ID: 074_agent_workspace_idem
Revises: 073_personal_billing_source
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "074_agent_workspace_idem"
down_revision: Union[str, None] = "073_personal_billing_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector: sa.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _unique_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    names = {
        item.get("name")
        for item in inspector.get_unique_constraints(table_name)
    }
    names.update(
        item.get("name")
        for item in inspector.get_indexes(table_name)
        if item.get("unique")
    )
    return {name for name in names if name}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_table(inspector, "agent_tasks"):
        return
    columns = {
        item["name"] for item in inspector.get_columns("agent_tasks")
    }
    if "workspace_id" not in columns:
        uuid_type = (
            sa.String(36)
            if bind.dialect.name == "sqlite"
            else postgresql.UUID(as_uuid=True)
        )
        op.add_column(
            "agent_tasks",
            sa.Column("workspace_id", uuid_type, nullable=True),
        )
        op.create_index(
            "ix_agent_tasks_workspace_id",
            "agent_tasks",
            ["workspace_id"],
        )
    inspector = sa.inspect(bind)
    unique_names = _unique_names(inspector, "agent_tasks")
    with op.batch_alter_table("agent_tasks") as batch:
        if "uq_agent_task_idem" in unique_names:
            batch.drop_constraint("uq_agent_task_idem", type_="unique")
        if "uq_agent_task_workspace_idem" not in unique_names:
            batch.create_unique_constraint(
                "uq_agent_task_workspace_idem",
                ["workspace_id", "user_id", "idempotency_key"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_table(inspector, "agent_tasks"):
        return
    unique_names = _unique_names(inspector, "agent_tasks")
    with op.batch_alter_table("agent_tasks") as batch:
        if "uq_agent_task_workspace_idem" in unique_names:
            batch.drop_constraint(
                "uq_agent_task_workspace_idem",
                type_="unique",
            )
        if "uq_agent_task_idem" not in unique_names:
            batch.create_unique_constraint(
                "uq_agent_task_idem",
                ["user_id", "idempotency_key"],
            )
