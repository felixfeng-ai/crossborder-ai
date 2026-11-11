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
        conn.execute(sa.text("CREATE TABLE products (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36), url VARCHAR(500) NOT NULL)"))
        conn.execute(sa.text("CREATE TABLE listing_drafts (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(sa.text("CREATE TABLE batch_jobs (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36) NOT NULL)"))
        conn.execute(sa.text("CREATE TABLE image_generation_tasks (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36) NOT NULL)"))
        conn.execute(sa.text("CREATE TABLE product_variants (id VARCHAR(36) PRIMARY KEY, user_id VARCHAR(36) NOT NULL, sku VARCHAR(100) NOT NULL)"))
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
    assert {"ix_batch_jobs_listing_id", "ix_batch_jobs_product_id"} <= _index_names(
        engine,
        "batch_jobs",
    )
    assert "uq_products_user_url" in _index_names(engine, "products")

    with engine.connect() as conn:
        version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()

    assert version == "023_data_retention_runs"


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
    with engine.connect() as conn:
        version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "023_data_retention_runs"
