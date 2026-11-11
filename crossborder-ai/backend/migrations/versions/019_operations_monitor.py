"""create operations monitor snapshot and alerts

Revision ID: 019_operations_monitor
Revises: 018_image_assets
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision: str = "019_operations_monitor"
down_revision: Union[str, None] = "018_image_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("product_variants") as batch_op:
        batch_op.add_column(
            sa.Column(
                "daily_sales_rate",
                sa.Float(),
                nullable=False,
                server_default="0",
            )
        )

    op.create_table(
        "monitor_settings",
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("target_margin_rate", sa.Float(), nullable=False, server_default="25"),
        sa.Column("low_stock_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("lead_time_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("safety_stock_days", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("platform_fee_rate", sa.Float(), nullable=False, server_default="0.15"),
        sa.Column("shipping_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "cost_increase_alert_rate",
            sa.Float(),
            nullable=False,
            server_default="8",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "variant_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "variant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("product_variants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sku", sa.String(100), nullable=False),
        sa.Column("selling_price", sa.Float(), nullable=True),
        sa.Column("cost_price", sa.Float(), nullable=True),
        sa.Column("stock_quantity", sa.Integer(), nullable=False),
        sa.Column("daily_sales_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("margin_rate", sa.Float(), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_variant_snapshots_user_id", "variant_snapshots", ["user_id"])
    op.create_index("ix_variant_snapshots_variant_id", "variant_snapshots", ["variant_id"])
    op.create_index("ix_variant_snapshots_captured_at", "variant_snapshots", ["captured_at"])

    op.create_table(
        "operation_alerts",
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
            nullable=True,
        ),
        sa.Column(
            "variant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("product_variants.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("sku", sa.String(100), nullable=True),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="warning"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
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
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_operation_alerts_user_id", "operation_alerts", ["user_id"])
    op.create_index("ix_operation_alerts_product_id", "operation_alerts", ["product_id"])
    op.create_index("ix_operation_alerts_variant_id", "operation_alerts", ["variant_id"])
    op.create_index("ix_operation_alerts_alert_type", "operation_alerts", ["alert_type"])
    op.create_index("ix_operation_alerts_status", "operation_alerts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_operation_alerts_status", table_name="operation_alerts")
    op.drop_index("ix_operation_alerts_alert_type", table_name="operation_alerts")
    op.drop_index("ix_operation_alerts_variant_id", table_name="operation_alerts")
    op.drop_index("ix_operation_alerts_product_id", table_name="operation_alerts")
    op.drop_index("ix_operation_alerts_user_id", table_name="operation_alerts")
    op.drop_table("operation_alerts")

    op.drop_index("ix_variant_snapshots_captured_at", table_name="variant_snapshots")
    op.drop_index("ix_variant_snapshots_variant_id", table_name="variant_snapshots")
    op.drop_index("ix_variant_snapshots_user_id", table_name="variant_snapshots")
    op.drop_table("variant_snapshots")

    op.drop_table("monitor_settings")

    with op.batch_alter_table("product_variants") as batch_op:
        batch_op.drop_column("daily_sales_rate")
