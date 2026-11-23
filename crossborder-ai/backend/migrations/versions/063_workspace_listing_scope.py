"""scope listing drafts and legacy listings to workspaces

Revision ID: 063_workspace_listing_scope
Revises: 062_workspace_product_scope
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "063_workspace_listing_scope"
down_revision: Union[str, None] = "062_workspace_product_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_listing_scope(table_name: str) -> None:
    if table_name not in sa.inspect(op.get_bind()).get_table_names():
        return
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
    _add_listing_scope("listing_drafts")
    _add_listing_scope("listings")


def _drop_listing_scope(table_name: str) -> None:
    if table_name not in sa.inspect(op.get_bind()).get_table_names():
        return
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
    _drop_listing_scope("listings")
    _drop_listing_scope("listing_drafts")
