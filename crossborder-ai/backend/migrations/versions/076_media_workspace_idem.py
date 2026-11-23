"""scope media idempotency keys to workspaces

Revision ID: 076_media_workspace_idem
Revises: 075_workspace_history_backfill
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "076_media_workspace_idem"
down_revision: Union[str, None] = "075_workspace_history_backfill"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONSTRAINTS = {
    "image_generation_tasks": (
        "uq_image_generation_tasks_user_idempotency",
        "uq_image_generation_tasks_workspace_idempotency",
    ),
    "video_generation_tasks": (
        "uq_video_tasks_user_idempotency",
        "uq_video_tasks_workspace_idempotency",
    ),
    "marketing_video_projects": (
        "uq_marketing_video_user_idempotency",
        "uq_marketing_video_workspace_idempotency",
    ),
}


def _unique_names(
    inspector: sa.Inspector,
    table_name: str,
) -> set[str]:
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


def _replace_unique(
    table_name: str,
    old_name: str,
    new_name: str,
    *,
    reverse: bool = False,
) -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return
    names = _unique_names(inspector, table_name)
    source_name, target_name = (
        (new_name, old_name) if reverse else (old_name, new_name)
    )
    target_columns = (
        ["user_id", "idempotency_key"]
        if reverse
        else ["workspace_id", "user_id", "idempotency_key"]
    )
    with op.batch_alter_table(table_name) as batch:
        if source_name in names:
            batch.drop_constraint(source_name, type_="unique")
        if target_name not in names:
            batch.create_unique_constraint(target_name, target_columns)


def upgrade() -> None:
    for table_name, (old_name, new_name) in CONSTRAINTS.items():
        _replace_unique(table_name, old_name, new_name)


def downgrade() -> None:
    for table_name, (old_name, new_name) in CONSTRAINTS.items():
        _replace_unique(
            table_name,
            old_name,
            new_name,
            reverse=True,
        )
