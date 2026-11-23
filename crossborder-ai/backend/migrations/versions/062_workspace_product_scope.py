"""scope products and variants to workspaces

Revision ID: 062_workspace_product_scope
Revises: 061_integration_event_retry
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "062_workspace_product_scope"
down_revision: Union[str, None] = "061_integration_event_retry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_product_scope(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch:
        batch.add_column(
            sa.Column(
                "workspace_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "created_by_user_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            )
        )
        batch.create_foreign_key(
            f"fk_{table_name}_workspace_id",
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            f"fk_{table_name}_created_by_user_id",
            "users",
            ["created_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(
            f"ix_{table_name}_workspace_id",
            ["workspace_id"],
        )
        batch.create_index(
            f"ix_{table_name}_created_by_user_id",
            ["created_by_user_id"],
        )


def upgrade() -> None:
    _add_product_scope("products")
    _add_product_scope("product_variants")


def _drop_product_scope(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch:
        batch.drop_index(f"ix_{table_name}_created_by_user_id")
        batch.drop_index(f"ix_{table_name}_workspace_id")
        batch.drop_constraint(
            f"fk_{table_name}_created_by_user_id",
            type_="foreignkey",
        )
        batch.drop_constraint(
            f"fk_{table_name}_workspace_id",
            type_="foreignkey",
        )
        batch.drop_column("created_by_user_id")
        batch.drop_column("workspace_id")


def downgrade() -> None:
    _drop_product_scope("product_variants")
    _drop_product_scope("products")
