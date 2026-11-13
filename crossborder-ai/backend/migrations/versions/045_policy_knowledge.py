"""create platform policy knowledge tables

Revision ID: 045_policy_knowledge
Revises: 044_ip_risk_screening
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "045_policy_knowledge"
down_revision: Union[str, None] = "044_ip_risk_screening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "policy_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=30), nullable=False),
        sa.Column("market", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("document_type", sa.String(length=50), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_policy_sources_platform", "policy_sources", ["platform"])
    op.create_index("ix_policy_sources_market", "policy_sources", ["market"])
    op.create_index("ix_policy_sources_category", "policy_sources", ["category"])
    op.create_index("ix_policy_sources_checksum", "policy_sources", ["checksum"])
    op.create_index("ix_policy_sources_status", "policy_sources", ["status"])

    op.create_table(
        "policy_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("policy_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("heading_path", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("estimated_tokens", sa.Integer(), nullable=False),
        sa.Column("chunk_hash", sa.String(length=64), nullable=False),
        sa.Column("qdrant_point_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_policy_chunks_source_id", "policy_chunks", ["source_id"])
    op.create_index("ix_policy_chunks_chunk_hash", "policy_chunks", ["chunk_hash"])

    op.create_table(
        "policy_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("added", sa.Integer(), nullable=False),
        sa.Column("updated", sa.Integer(), nullable=False),
        sa.Column("removed", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("policy_sync_runs")
    op.drop_index("ix_policy_chunks_chunk_hash", table_name="policy_chunks")
    op.drop_index("ix_policy_chunks_source_id", table_name="policy_chunks")
    op.drop_table("policy_chunks")
    op.drop_index("ix_policy_sources_status", table_name="policy_sources")
    op.drop_index("ix_policy_sources_checksum", table_name="policy_sources")
    op.drop_index("ix_policy_sources_category", table_name="policy_sources")
    op.drop_index("ix_policy_sources_market", table_name="policy_sources")
    op.drop_index("ix_policy_sources_platform", table_name="policy_sources")
    op.drop_table("policy_sources")
