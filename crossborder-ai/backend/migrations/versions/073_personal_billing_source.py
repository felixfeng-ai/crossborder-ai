"""make workspace wallet the personal billing source

Revision ID: 073_personal_billing_source
Revises: 072_user_workspace_lifecycle
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "073_personal_billing_source"
down_revision: Union[str, None] = "072_user_workspace_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("workspace_credit_wallets") as batch:
        batch.add_column(
            sa.Column(
                "credit_period_start",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )

    # 存量数据只执行一次单向迁移，保留旧周期以支持回滚窗口。
    wallets = sa.table(
        "workspace_credit_wallets",
        sa.column("workspace_id"),
        sa.column("credit_period_start"),
    )
    workspaces = sa.table(
        "workspaces",
        sa.column("id"),
        sa.column("owner_user_id"),
        sa.column("type"),
    )
    users = sa.table(
        "users",
        sa.column("id"),
        sa.column("credit_period_start"),
    )
    legacy_period = (
        sa.select(users.c.credit_period_start)
        .select_from(
            workspaces.join(
                users,
                users.c.id == workspaces.c.owner_user_id,
            )
        )
        .where(
            workspaces.c.id == wallets.c.workspace_id,
            workspaces.c.type == "personal",
        )
        .scalar_subquery()
    )
    op.execute(
        sa.update(wallets)
        .where(wallets.c.credit_period_start.is_(None))
        .values(credit_period_start=legacy_period)
    )


def downgrade() -> None:
    with op.batch_alter_table("workspace_credit_wallets") as batch:
        batch.drop_column("credit_period_start")
