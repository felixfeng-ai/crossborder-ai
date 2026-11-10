"""VeyaShip - 全量迁移：创建所有业务表

本迁移覆盖 001/002 之后的所有模型，包括：
- products（商品）
- system_config（系统配置）
- personas（品牌调性）
- shopify_channels（Shopify 渠道）
- batch_jobs（批量任务）
- content_generations（AI 生成记录）
- content_templates（Prompt 模板）
- listings（多平台 Listing）
- listing_variants（Listing 变体）
- subscriptions（订阅）
- payment_invoices（支付记录）

首次部署流程：
  1. app 启动时 init_db() 自动 create_all（创建所有表）
  2. alembic stamp head  标记为已迁移（本文件）
  3. 后续改模型用 alembic revision --autogenerate

Revision ID: 003
Revises: 002
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM

revision: str = "003"
down_revision: Union[str, None] = "002"  # 依赖 002（users 表已存在）
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建所有业务表（如果不存在）"""

    # ── 商品表（F2 Refinery） ──────────────────────────────
    op.create_table(
        "products",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=True, index=True),
        sa.Column("url", sa.String(500), nullable=False, index=True, unique=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("main_image_url", sa.String(1000), nullable=True),
        sa.Column("price", sa.Float, nullable=True),
        sa.Column("sales_count", sa.Integer, nullable=True),
        sa.Column("shop_name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # ── 系统配置（Key-Value 存储） ─────────────────────────
    op.create_table(
        "system_config",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.Text, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # ── 品牌调性表（F5 Persona） ──────────────────────────
    op.create_table(
        "personas",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("brand_name", sa.String(200), nullable=True),
        sa.Column("tagline", sa.String(500), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("tone", sa.String(50), nullable=False, server_default="professional"),
        sa.Column("tone_custom", sa.String(500), nullable=True),
        sa.Column("banned_words", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # ── Shopify 渠道表（F7/F8） ───────────────────────────
    op.create_table(
        "shopify_channels",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("shop_name", sa.String(255), nullable=False),
        sa.Column("access_token", sa.Text, nullable=False),
        sa.Column("shop_domain", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # ── 批量任务表（F4 Batch） ────────────────────────────
    op.create_table(
        "batch_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("source_type", sa.String(50), server_default="csv"),
        sa.Column("source_filename", sa.String(255), nullable=True),
        sa.Column("row_index", sa.Integer, server_default="0"),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("price", sa.String(50), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── 内容生成记录表 ─────────────────────────────────────
    op.create_table(
        "content_generations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("listing_id", sa.Integer,
                  sa.ForeignKey("listings.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("source_language", sa.String(20), server_default="en"),
        sa.Column("target_language", sa.String(20), nullable=True),
        sa.Column("source_text", sa.Text, nullable=True),
        sa.Column("source_image_url", sa.String(1000), nullable=True),
        sa.Column("generated_text", sa.Text, nullable=True),
        sa.Column("generated_image_url", sa.String(1000), nullable=True),
        sa.Column("model_used", sa.String(100), nullable=False),
        sa.Column("prompt_template", sa.Text, nullable=True),
        sa.Column("prompt_parameters", sa.Text, nullable=True),
        sa.Column("tokens_used", sa.Integer, nullable=True),
        sa.Column("credits_cost", sa.Integer, nullable=True),
        sa.Column("user_rating", sa.Integer, nullable=True),
        sa.Column("user_edited", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )

    # ── 内容模板表 ─────────────────────────────────────────
    op.create_table(
        "content_templates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("platform", sa.String(50), nullable=True),
        sa.Column("language", sa.String(20), server_default="en"),
        sa.Column("system_prompt", sa.Text, nullable=True),
        sa.Column("user_prompt_template", sa.Text, nullable=False),
        sa.Column("parameters_schema", sa.Text, nullable=True),
        sa.Column("tone", sa.String(50), nullable=True),
        sa.Column("target_audience", sa.String(255), nullable=True),
        sa.Column("is_system", sa.Boolean, server_default="false"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("usage_count", sa.Integer, server_default="0"),
        sa.Column("avg_rating", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # ── 多平台 Listing 表 ──────────────────────────────────
    op.create_table(
        "listings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("owner_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("product_id", UUID(as_uuid=True),
                  sa.ForeignKey("products.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("platform_listing_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("bullet_points", sa.Text, nullable=True),
        sa.Column("search_terms", sa.Text, nullable=True),
        sa.Column("seo_title", sa.String(500), nullable=True),
        sa.Column("seo_description", sa.Text, nullable=True),
        sa.Column("price", sa.Float, server_default="0.0"),
        sa.Column("sale_price", sa.Float, nullable=True),
        sa.Column("currency", sa.String(10), server_default="USD"),
        sa.Column("main_image_url", sa.String(1000), nullable=True),
        sa.Column("additional_image_urls", sa.Text, nullable=True),
        sa.Column("ai_generated", sa.Boolean, server_default="false"),
        sa.Column("ai_model_used", sa.String(100), nullable=True),
        sa.Column("ai_prompt_template", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── Listing 变体表（颜色/尺寸等） ──────────────────────
    op.create_table(
        "listing_variants",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("listing_id", sa.Integer,
                  sa.ForeignKey("listings.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("option1_name", sa.String(100), nullable=True),
        sa.Column("option1_value", sa.String(255), nullable=True),
        sa.Column("option2_name", sa.String(100), nullable=True),
        sa.Column("option2_value", sa.String(255), nullable=True),
        sa.Column("option3_name", sa.String(100), nullable=True),
        sa.Column("option3_value", sa.String(255), nullable=True),
        sa.Column("sku", sa.String(100), nullable=True),
        sa.Column("price", sa.Float, server_default="0.0"),
        sa.Column("stock_quantity", sa.Integer, server_default="0"),
        sa.Column("image_url", sa.String(1000), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # ── 订阅表 ─────────────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("plan_name", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), server_default="trialing"),
        sa.Column("billing_interval", sa.String(20), server_default="monthly"),
        sa.Column("amount", sa.Float, server_default="0.0"),
        sa.Column("currency", sa.String(10), server_default="USD"),
        sa.Column("creem_subscription_id", sa.String(255), nullable=True, unique=True),
        sa.Column("creem_customer_id", sa.String(255), nullable=True),
        sa.Column("creem_product_id", sa.String(255), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("credits_per_period", sa.Integer, server_default="0"),
        sa.Column("credits_used", sa.Integer, server_default="0"),
        sa.Column("features_json", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # ── 支付记录表 ─────────────────────────────────────────
    op.create_table(
        "payment_invoices",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("subscription_id", sa.Integer,
                  sa.ForeignKey("subscriptions.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("creem_invoice_id", sa.String(255), nullable=True, unique=True),
        sa.Column("creem_payment_id", sa.String(255), nullable=True),
        sa.Column("amount", sa.Float, server_default="0.0"),
        sa.Column("currency", sa.String(10), server_default="USD"),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("payment_method", sa.String(100), nullable=True),
        sa.Column("billing_reason", sa.String(100), nullable=True),
        sa.Column("plan_name", sa.String(50), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("receipt_url", sa.String(1000), nullable=True),
        sa.Column("invoice_pdf_url", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """回滚：删除所有业务表（⚠️ 会丢数据！）"""
    op.drop_table("payment_invoices")
    op.drop_table("subscriptions")
    op.drop_table("listing_variants")
    op.drop_table("listings")
    op.drop_table("content_templates")
    op.drop_table("content_generations")
    op.drop_table("batch_jobs")
    op.drop_table("shopify_channels")
    op.drop_table("personas")
    op.drop_table("system_config")
    op.drop_table("products")
