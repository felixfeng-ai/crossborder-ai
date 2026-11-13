"""add ip risk reports, items and declarations

Revision ID: 044_ip_risk_screening
Revises: 043_automation_preferences
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision: str = "044_ip_risk_screening"
down_revision: Union[str, None] = "043_automation_preferences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ip_risk_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "listing_id",
            UUID(as_uuid=True),
            sa.ForeignKey("listing_drafts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("listing_version", sa.Integer(), nullable=True),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("overall_risk", sa.String(length=20), nullable=False),
        sa.Column("coverage_json", sa.Text(), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("ruleset_version", sa.String(length=64), nullable=False),
        sa.Column("model_provider", sa.String(length=50), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    for column in ("user_id", "product_id", "listing_id", "input_hash"):
        op.create_index(
            f"ix_ip_risk_reports_{column}",
            "ip_risk_reports",
            [column],
        )
    op.create_table(
        "ip_risk_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "report_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ip_risk_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("suggestion", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_ip_risk_items_report_id",
        "ip_risk_items",
        ["report_id"],
    )
    op.create_index(
        "ix_ip_risk_items_severity",
        "ip_risk_items",
        ["severity"],
    )
    op.create_table(
        "ip_declarations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("claim_type", sa.String(length=30), nullable=False),
        sa.Column("claim_value", sa.String(length=100), nullable=False),
        sa.Column("evidence_url", sa.Text(), nullable=True),
        sa.Column(
            "evidence_status",
            sa.String(length=20),
            nullable=False,
            server_default="unverified",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "product_id",
            "claim_type",
            "claim_value",
            name="uq_ip_declaration_product_claim",
        ),
    )
    op.create_index(
        "ix_ip_declarations_user_id",
        "ip_declarations",
        ["user_id"],
    )
    op.create_index(
        "ix_ip_declarations_product_id",
        "ip_declarations",
        ["product_id"],
    )


def downgrade() -> None:
    op.drop_table("ip_declarations")
    op.drop_table("ip_risk_items")
    op.drop_table("ip_risk_reports")
