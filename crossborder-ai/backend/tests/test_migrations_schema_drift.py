"""生产 schema 漂移修复迁移测试。"""

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


BACKEND_DIR = Path(__file__).resolve().parents[1]


def _column_names(engine: sa.Engine, table_name: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(engine).get_columns(table_name)
    }


def _index_names(engine: sa.Engine, table_name: str) -> set[str]:
    return {
        index["name"]
        for index in sa.inspect(engine).get_indexes(table_name)
    }


def test_repair_migration_restores_stamped_schema_drift(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """数据库已标记 021 时仍应补齐被跳过的历史列和索引。"""

    db_path = tmp_path / "schema-drift.db"
    sync_url = f"sqlite:///{db_path.as_posix()}"
    async_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = sa.create_engine(sync_url)

    with engine.begin() as conn:
        conn.execute(sa.text(
            "CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, credits INTEGER NOT NULL DEFAULT 30, plan VARCHAR(32) NOT NULL DEFAULT 'free')"
        ))
        conn.execute(sa.text("CREATE TABLE products (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36), url VARCHAR(500) NOT NULL)"))
        conn.execute(sa.text("CREATE TABLE listing_drafts (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(sa.text("CREATE TABLE batch_jobs (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36) NOT NULL)"))
        conn.execute(sa.text("CREATE TABLE image_generation_tasks (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36) NOT NULL)"))
        conn.execute(sa.text(
            "CREATE TABLE image_assets ("
            "id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36) NOT NULL, "
            "name VARCHAR(255) NOT NULL, kind VARCHAR(20) NOT NULL, "
            "storage_key VARCHAR(500) NOT NULL UNIQUE, "
            "content_type VARCHAR(100) NOT NULL, width INTEGER NOT NULL, "
            "height INTEGER NOT NULL, file_size INTEGER NOT NULL, "
            "preset_id VARCHAR(50), platform VARCHAR(50), "
            "background_mode VARCHAR(20), source_asset_id VARCHAR(36), "
            "created_at DATETIME, updated_at DATETIME)"
        ))
        conn.execute(sa.text("CREATE TABLE product_variants (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36) NOT NULL, sku VARCHAR(100) NOT NULL)"))
        conn.execute(sa.text("CREATE TABLE video_generation_tasks (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36) NOT NULL)"))
        conn.execute(sa.text("CREATE TABLE marketing_video_projects (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36) NOT NULL)"))
        conn.execute(sa.text(
            "CREATE TABLE marketing_video_shots ("
            "id VARCHAR(36) PRIMARY KEY, project_id VARCHAR(36) NOT NULL, "
            "position INTEGER NOT NULL, title VARCHAR(255) NOT NULL, "
            "purpose VARCHAR(100) NOT NULL, prompt TEXT NOT NULL, "
            "duration INTEGER NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'planned', "
            "video_task_id VARCHAR(36), error TEXT, created_at DATETIME)"
        ))
        conn.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        conn.execute(sa.text("INSERT INTO alembic_version (version_num) VALUES ('021_marketing_video_projects')"))

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", async_url)
    monkeypatch.setenv("DATABASE_URL", async_url)

    command.upgrade(config, "head")

    assert {"listing_id", "product_id"} <= _column_names(engine, "batch_jobs")
    assert {
        "attempts",
        "finished_at",
        "num_outputs",
        "started_at",
    } <= _column_names(engine, "image_generation_tasks")
    assert "daily_sales_rate" in _column_names(engine, "product_variants")
    assert "reference_assets_json" in _column_names(
        engine,
        "marketing_video_projects",
    )
    assert "reference_assets_json" in _column_names(
        engine,
        "video_generation_tasks",
    )
    assert {
        "quality_tier",
        "style_preset",
        "credits_per_second",
    } <= _column_names(engine, "marketing_video_projects")
    assert {
        "quality_tier",
        "style_preset",
        "credits_per_second",
    } <= _column_names(engine, "video_generation_tasks")
    assert {
        "origin_type",
        "brand_name",
        "cost_currency",
        "moq",
        "lead_time_days",
    } <= _column_names(engine, "products")
    assert {
        "origin_type",
        "main_image_url",
        "stock_quantity",
        "sku",
    } <= _column_names(engine, "batch_jobs")
    assert {"ix_batch_jobs_listing_id", "ix_batch_jobs_product_id"} <= _index_names(
        engine,
        "batch_jobs",
    )
    assert "uq_products_user_url" in _index_names(engine, "products")

    with engine.connect() as conn:
        version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()

    assert version == "039_generated_image_assets"
    assert "provider" in _column_names(engine, "marketing_video_projects")
    assert "workspace" in _column_names(engine, "conversations")
    assert "campaign_id" in _column_names(engine, "conversations")
    assert "marketing_campaigns" in sa.inspect(engine).get_table_names()
    assert "campaign_id" in _column_names(engine, "image_generation_tasks")
    assert "campaign_id" in _column_names(engine, "video_generation_tasks")
    assert "campaign_id" in _column_names(engine, "marketing_video_projects")
    assert {
        "generation_task_id",
        "variant_index",
    } <= _column_names(engine, "image_assets")


def test_full_sqlite_upgrade_from_empty_database(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """全新 SQLite 也必须能一次性升级到包含数据保留审计表的 head。"""
    db_path = tmp_path / "fresh-upgrade.db"
    sync_url = f"sqlite:///{db_path.as_posix()}"
    async_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = sa.create_engine(sync_url)

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", async_url)
    monkeypatch.setenv("DATABASE_URL", async_url)

    command.upgrade(config, "head")

    inspector = sa.inspect(engine)
    assert "data_retention_runs" in inspector.get_table_names()
    assert "reference_assets_json" in _column_names(
        engine,
        "marketing_video_projects",
    )
    assert "reference_assets_json" in _column_names(
        engine,
        "video_generation_tasks",
    )
    assert {
        "quality_tier",
        "style_preset",
        "credits_per_second",
    } <= _column_names(engine, "marketing_video_projects")
    assert {
        "quality_tier",
        "style_preset",
        "credits_per_second",
    } <= _column_names(engine, "video_generation_tasks")
    assert {
        "origin_type",
        "brand_name",
        "cost_currency",
        "moq",
        "lead_time_days",
    } <= _column_names(engine, "products")
    with engine.connect() as conn:
        version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "039_generated_image_assets"
    assert "provider" in _column_names(engine, "marketing_video_projects")
    assert "workspace" in _column_names(engine, "conversations")
    assert "campaign_id" in _column_names(engine, "conversations")
    assert "marketing_campaigns" in sa.inspect(engine).get_table_names()
    assert "campaign_id" in _column_names(engine, "image_generation_tasks")
    assert "campaign_id" in _column_names(engine, "video_generation_tasks")
    assert "campaign_id" in _column_names(engine, "marketing_video_projects")
    assert {
        "generation_task_id",
        "variant_index",
    } <= _column_names(engine, "image_assets")
    assert "credit_transactions" in inspector.get_table_names()
    assert {
        "credit_wallets",
        "user_subscriptions",
        "feature_usage_counters",
        "credit_purchases",
    } <= set(inspector.get_table_names())
    assert "voc_analyses" in inspector.get_table_names()
    assert "subtitles_burned_in" in _column_names(
        engine,
        "marketing_video_projects",
    )
    assert {"mode", "script_text", "continuity_json"} <= _column_names(
        engine,
        "marketing_video_projects",
    )
    assert "source_text" in _column_names(engine, "marketing_video_shots")
    assert "credit_period_start" in _column_names(engine, "users")
    assert {"credits_cost", "credits_charged"} <= _column_names(
        engine, "image_generation_tasks"
    )
    assert {"credits_charged", "credits_refunded"} <= _column_names(
        engine, "video_generation_tasks"
    )
    assert {
        "billing_cycle",
        "promotion_code",
        "original_amount",
        "bonus_credits",
        "duration_days",
    } <= _column_names(engine, "plan_upgrade_requests")
