"""create admin operations, feedback and telemetry tables

Revision ID: 046_admin_operations
Revises: 045_policy_knowledge
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "046_admin_operations"
down_revision: Union[str, None] = "045_policy_knowledge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "traffic_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("visitor_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("referrer_host", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("country_code", sa.String(length=8), nullable=False, server_default="unknown"),
        sa.Column("device_type", sa.String(length=20), nullable=False, server_default="unknown"),
        sa.Column("viewport_width", sa.Integer(), nullable=True),
        sa.Column("connection_type", sa.String(length=20), nullable=True),
        sa.Column("metric_name", sa.String(length=16), nullable=True),
        sa.Column("metric_value", sa.Float(), nullable=True),
        sa.Column("metric_rating", sa.String(length=24), nullable=True),
        sa.Column("release", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("request_id", sa.String(length=36), nullable=True),
        sa.Column("is_bot", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_traffic_events_event_type", "traffic_events", ["event_type"])
    op.create_index("ix_traffic_events_visitor_id", "traffic_events", ["visitor_id"])
    op.create_index("ix_traffic_events_session_id", "traffic_events", ["session_id"])
    op.create_index("ix_traffic_events_path", "traffic_events", ["path"])
    op.create_index("ix_traffic_events_is_bot", "traffic_events", ["is_bot"])
    op.create_index("ix_traffic_events_created_at", "traffic_events", ["created_at"])

    op.create_table(
        "feedback_tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("page_path", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("page_title", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("browser_info_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(length=24), nullable=False, server_default="normal"),
        sa.Column("assigned_to", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
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
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_feedback_tickets_user_id", "feedback_tickets", ["user_id"])
    op.create_index("ix_feedback_tickets_type", "feedback_tickets", ["type"])
    op.create_index("ix_feedback_tickets_status", "feedback_tickets", ["status"])
    op.create_index("ix_feedback_tickets_priority", "feedback_tickets", ["priority"])
    op.create_index("ix_feedback_tickets_created_at", "feedback_tickets", ["created_at"])

    op.create_table(
        "feedback_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("feedback_tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_feedback_comments_ticket_id", "feedback_comments", ["ticket_id"])

    op.create_table(
        "admin_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "admin_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.String(length=80), nullable=False),
        sa.Column("changes_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_admin_audit_logs_admin_user_id", "admin_audit_logs", ["admin_user_id"])
    op.create_index("ix_admin_audit_logs_action", "admin_audit_logs", ["action"])
    op.create_index("ix_admin_audit_logs_target_type", "admin_audit_logs", ["target_type"])
    op.create_index("ix_admin_audit_logs_target_id", "admin_audit_logs", ["target_id"])
    op.create_index("ix_admin_audit_logs_created_at", "admin_audit_logs", ["created_at"])

    op.create_table(
        "plan_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_key", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("rank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "first_month_price_cents", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("annual_price_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "annual_full_price_cents", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("monthly_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "first_month_bonus_credits", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("valid_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("features_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("plan_key", "version", name="uq_plan_key_version"),
    )
    op.create_index("ix_plan_versions_plan_key", "plan_versions", ["plan_key"])
    op.create_index("ix_plan_versions_status", "plan_versions", ["status"])

    op.create_table(
        "credit_pack_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("pack_key", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("trial_once", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("pack_key", "version", name="uq_pack_key_version"),
    )
    op.create_index("ix_credit_pack_versions_pack_key", "credit_pack_versions", ["pack_key"])
    op.create_index("ix_credit_pack_versions_status", "credit_pack_versions", ["status"])

    _seed_default_catalog()


def _seed_default_catalog() -> None:
    """把当前上线价格写成首个已发布版本，避免迁移后公开接口回落。"""
    now = datetime.now(timezone.utc)
    plan_table = sa.table(
        "plan_versions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("plan_key", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("rank", sa.Integer()),
        sa.column("price_cents", sa.Integer()),
        sa.column("first_month_price_cents", sa.Integer()),
        sa.column("annual_price_cents", sa.Integer()),
        sa.column("annual_full_price_cents", sa.Integer()),
        sa.column("monthly_credits", sa.Integer()),
        sa.column("first_month_bonus_credits", sa.Integer()),
        sa.column("valid_days", sa.Integer()),
        sa.column("features_json", sa.Text()),
        sa.column("status", sa.String()),
        sa.column("effective_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    plans = [
        {
            "plan_key": "free",
            "name": "Free",
            "description": "试试基本功能",
            "rank": 0,
            "price_cents": 0,
            "first_month_price_cents": 0,
            "annual_price_cents": 0,
            "annual_full_price_cents": 0,
            "monthly_credits": 30,
            "first_month_bonus_credits": 0,
            "valid_days": 0,
            "features": [
                "每月 30 AI 积分",
                "1688 商品抓取与利润测算",
                "Listing、合规与 VOC 评论洞察",
                "品类分析与 AI Insights 各 10 次/月",
            ],
        },
        {
            "plan_key": "standard",
            "name": "Standard",
            "description": "适合个人卖家",
            "rank": 1,
            "price_cents": 9900,
            "first_month_price_cents": 7900,
            "annual_price_cents": 99000,
            "annual_full_price_cents": 118800,
            "monthly_credits": 800,
            "first_month_bonus_credits": 0,
            "valid_days": 30,
            "features": [
                "每月 800 AI 积分",
                "AI Agent、批量处理与自动巡检",
                "Shopify 草稿发布与运营同步",
                "11 个平台 Listing 文案生成",
                "每月 10 次手动整店巡检",
                "商品抓取每月 100 次",
            ],
        },
        {
            "plan_key": "professional",
            "name": "Professional",
            "description": "适合工作室与专业卖家",
            "rank": 2,
            "price_cents": 24900,
            "first_month_price_cents": 19900,
            "annual_price_cents": 249000,
            "annual_full_price_cents": 298800,
            "monthly_credits": 3000,
            "first_month_bonus_credits": 100,
            "valid_days": 30,
            "features": [
                "每月 3,000 AI 积分",
                "所有 Standard 功能",
                "AI 图片、商品视频与营销成片",
                "约 6 条 30 秒 768P 高质量营销成片",
                "约 660 张 AI 图片",
                "字幕、AI 配音与素材中心",
                "每月 20 次手动整店巡检",
                "优先技术支持",
            ],
        },
    ]
    op.bulk_insert(
        plan_table,
        [
            {
                "id": uuid.uuid4(),
                "plan_key": plan["plan_key"],
                "version": 1,
                "name": plan["name"],
                "description": plan["description"],
                "rank": plan["rank"],
                "price_cents": plan["price_cents"],
                "first_month_price_cents": plan["first_month_price_cents"],
                "annual_price_cents": plan["annual_price_cents"],
                "annual_full_price_cents": plan["annual_full_price_cents"],
                "monthly_credits": plan["monthly_credits"],
                "first_month_bonus_credits": plan["first_month_bonus_credits"],
                "valid_days": plan["valid_days"],
                "features_json": json.dumps(plan["features"], ensure_ascii=False),
                "status": "published",
                "effective_at": now,
                "created_at": now,
            }
            for plan in plans
        ],
    )

    pack_table = sa.table(
        "credit_pack_versions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("pack_key", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("credits", sa.Integer()),
        sa.column("price_cents", sa.Integer()),
        sa.column("trial_once", sa.Boolean()),
        sa.column("status", sa.String()),
        sa.column("effective_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    packs = [
        ("pack_trial_50", "首购体验包", 50, 990, True),
        ("pack_200", "入门积分包", 200, 1900, False),
        ("pack_500", "常用积分包", 500, 4500, False),
        ("pack_1200", "专业积分包", 1200, 9900, False),
    ]
    op.bulk_insert(
        pack_table,
        [
            {
                "id": uuid.uuid4(),
                "pack_key": key,
                "version": 1,
                "name": name,
                "credits": credits,
                "price_cents": price_cents,
                "trial_once": trial_once,
                "status": "published",
                "effective_at": now,
                "created_at": now,
            }
            for key, name, credits, price_cents, trial_once in packs
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_credit_pack_versions_status", table_name="credit_pack_versions")
    op.drop_index("ix_credit_pack_versions_pack_key", table_name="credit_pack_versions")
    op.drop_table("credit_pack_versions")
    op.drop_index("ix_plan_versions_status", table_name="plan_versions")
    op.drop_index("ix_plan_versions_plan_key", table_name="plan_versions")
    op.drop_table("plan_versions")
    op.drop_index("ix_admin_audit_logs_created_at", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_target_id", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_target_type", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_action", table_name="admin_audit_logs")
    op.drop_index("ix_admin_audit_logs_admin_user_id", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")
    op.drop_index("ix_feedback_comments_ticket_id", table_name="feedback_comments")
    op.drop_table("feedback_comments")
    op.drop_index("ix_feedback_tickets_created_at", table_name="feedback_tickets")
    op.drop_index("ix_feedback_tickets_priority", table_name="feedback_tickets")
    op.drop_index("ix_feedback_tickets_status", table_name="feedback_tickets")
    op.drop_index("ix_feedback_tickets_type", table_name="feedback_tickets")
    op.drop_index("ix_feedback_tickets_user_id", table_name="feedback_tickets")
    op.drop_table("feedback_tickets")
    op.drop_index("ix_traffic_events_created_at", table_name="traffic_events")
    op.drop_index("ix_traffic_events_is_bot", table_name="traffic_events")
    op.drop_index("ix_traffic_events_path", table_name="traffic_events")
    op.drop_index("ix_traffic_events_session_id", table_name="traffic_events")
    op.drop_index("ix_traffic_events_visitor_id", table_name="traffic_events")
    op.drop_index("ix_traffic_events_event_type", table_name="traffic_events")
    op.drop_table("traffic_events")
