"""生产 schema 漂移修复迁移测试。"""

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_migration_revision_ids_fit_alembic_version_column() -> None:
    """revision id 必须适配 VARCHAR(32)，避免 PostgreSQL 升级中断。"""

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    revisions = ScriptDirectory.from_config(config).walk_revisions()
    too_long = {
        revision.revision: len(revision.revision)
        for revision in revisions
        if len(revision.revision) > 32
    }

    assert too_long == {}


def test_workspace_automation_boolean_defaults_are_postgresql_safe() -> None:
    """布尔默认值必须用 true/false，不能被 SQLite 的 1/0 习惯带进 PostgreSQL。"""

    migration = (
        BACKEND_DIR
        / "migrations"
        / "versions"
        / "077_workspace_automation.py"
    ).read_text(encoding="utf-8")

    assert 'server_default=sa.text("1")' not in migration
    assert 'server_default=sa.text("0")' not in migration
    assert migration.count("server_default=sa.true()") == 4


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


def _column_map(engine: sa.Engine, table_name: str) -> dict[str, dict]:
    return {
        column["name"]: column
        for column in sa.inspect(engine).get_columns(table_name)
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
        "image_urls",
        "video_url",
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
    assert {
        "mode",
        "quality_tier",
        "provider",
        "reference_assets_json",
        "idempotency_key",
    } <= _column_names(engine, "image_generation_tasks")

    with engine.connect() as conn:
        version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()

    assert version == ScriptDirectory.from_config(config).get_current_head()
    assert "action_runs" in sa.inspect(engine).get_table_names()
    assert "customer_channels" in sa.inspect(engine).get_table_names()
    assert "notification_outbox" in sa.inspect(engine).get_table_names()
    assert "agent_signals" in sa.inspect(engine).get_table_names()
    assert "integration_events" in sa.inspect(engine).get_table_names()
    assert "workspace_id" in _column_names(engine, "image_assets")
    assert {
        "traffic_events",
        "feedback_tickets",
        "feedback_comments",
        "admin_audit_logs",
        "plan_versions",
        "credit_pack_versions",
    } <= set(sa.inspect(engine).get_table_names())
    assert {
        "workspaces",
        "workspace_members",
        "workspace_invitations",
        "workspace_audit_logs",
    } <= set(sa.inspect(engine).get_table_names())
    assert {"owner_user_id", "type", "status"} <= _column_names(
        engine,
        "workspaces",
    )
    assert {"role", "status", "joined_at"} <= _column_names(
        engine,
        "workspace_members",
    )
    assert {
        "agent_turns",
        "agent_turn_inputs",
        "work_items",
        "work_item_events",
        "work_item_commands",
    } <= set(sa.inspect(engine).get_table_names())
    assert {"workspace_id", "version", "requires_action"} <= _column_names(
        engine,
        "work_items",
    )
    assert "provider" in _column_names(engine, "marketing_video_projects")
    assert "workspace" in _column_names(engine, "conversations")
    assert "campaign_id" in _column_names(engine, "conversations")
    assert "user_sessions" in sa.inspect(engine).get_table_names()
    assert {
        "user_id",
        "refresh_token_hash",
        "previous_refresh_token_hash",
        "expires_at",
        "revoked_at",
    } <= _column_names(engine, "user_sessions")
    assert "marketing_campaigns" in sa.inspect(engine).get_table_names()
    assert "campaign_id" in _column_names(engine, "image_generation_tasks")
    assert "campaign_id" in _column_names(engine, "video_generation_tasks")
    assert "campaign_id" in _column_names(engine, "marketing_video_projects")
    assert {
        "generation_task_id",
        "variant_index",
    } <= _column_names(engine, "image_assets")
    assert "marketing_copy_assets" in sa.inspect(engine).get_table_names()
    assert {
        "batch_id",
        "campaign_id",
        "platform",
        "variant_key",
        "headline",
        "compliance_status",
    } <= _column_names(engine, "marketing_copy_assets")
    assert {
        "marketing_campaign_publications",
        "marketing_performance_snapshots",
    } <= set(sa.inspect(engine).get_table_names())
    assert {
        "copy_id",
        "scope_key",
    } <= _column_names(engine, "marketing_performance_snapshots")
    assert {
        "performance_status",
        "performance_metrics_json",
        "last_evaluated_at",
    } <= _column_names(engine, "marketing_copy_assets")
    assert {
        "automation_preferences",
        "automation_task_states",
    } <= set(sa.inspect(engine).get_table_names())
    assert {
        "daily_store_check",
        "daily_operations_monitor",
        "shopify_auto_sync",
        "ab_auto_pause",
    } <= _column_names(engine, "automation_preferences")
    assert {
        "ip_risk_reports",
        "ip_risk_items",
        "ip_declarations",
        "policy_sources",
        "policy_chunks",
        "policy_sync_runs",
    } <= set(sa.inspect(engine).get_table_names())
    assert {
        "input_hash",
        "ruleset_version",
        "overall_risk",
    } <= _column_names(engine, "ip_risk_reports")


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
    assert "marketing_image_suites" in inspector.get_table_names()
    assert "marketing_image_suite_items" in inspector.get_table_names()
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
        "image_urls",
        "video_url",
    } <= _column_names(engine, "products")
    with engine.connect() as conn:
        version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == ScriptDirectory.from_config(config).get_current_head()
    assert "action_runs" in inspector.get_table_names()
    assert "customer_channels" in inspector.get_table_names()
    assert "notification_outbox" in inspector.get_table_names()
    assert "agent_signals" in inspector.get_table_names()
    assert "integration_events" in inspector.get_table_names()
    assert "workspace_id" in _column_names(engine, "image_assets")
    assert {
        "traffic_events",
        "feedback_tickets",
        "feedback_comments",
        "admin_audit_logs",
        "plan_versions",
        "credit_pack_versions",
    } <= set(sa.inspect(engine).get_table_names())
    assert {
        "workspaces",
        "workspace_members",
        "workspace_invitations",
        "workspace_audit_logs",
    } <= set(inspector.get_table_names())
    assert {"owner_user_id", "type", "status"} <= _column_names(
        engine,
        "workspaces",
    )
    assert {
        "agent_turns",
        "agent_turn_inputs",
        "work_items",
        "work_item_events",
        "work_item_commands",
    } <= set(inspector.get_table_names())
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
    assert "marketing_copy_assets" in inspector.get_table_names()
    assert {
        "batch_id",
        "campaign_id",
        "platform",
        "variant_key",
        "headline",
        "compliance_status",
    } <= _column_names(engine, "marketing_copy_assets")
    assert {
        "marketing_campaign_publications",
        "marketing_performance_snapshots",
    } <= set(inspector.get_table_names())
    assert {
        "copy_id",
        "scope_key",
    } <= _column_names(engine, "marketing_performance_snapshots")
    assert {
        "performance_status",
        "performance_metrics_json",
        "last_evaluated_at",
    } <= _column_names(engine, "marketing_copy_assets")
    assert {
        "automation_preferences",
        "automation_task_states",
    } <= set(inspector.get_table_names())
    assert {
        "last_run_at",
        "status",
        "error",
    } <= _column_names(engine, "automation_task_states")
    assert {
        "ip_risk_reports",
        "ip_risk_items",
        "ip_declarations",
    } <= set(inspector.get_table_names())
    assert "credit_transactions" in inspector.get_table_names()
    assert {
        "credit_wallets",
        "user_subscriptions",
        "feature_usage_counters",
        "credit_purchases",
    } <= set(inspector.get_table_names())
    assert "voc_analyses" in inspector.get_table_names()
    user_columns = _column_map(engine, "users")
    workspace_columns = _column_map(engine, "workspaces")
    assert {"deleted_at", "deletion_reason"} <= set(user_columns)
    assert {
        "archived_at",
        "purge_after",
        "archived_by_user_id",
    } <= set(workspace_columns)
    assert workspace_columns["owner_user_id"]["nullable"] is True
    for table_name in (
        "image_generation_tasks",
        "video_generation_tasks",
        "marketing_campaigns",
        "marketing_copy_assets",
        "marketing_image_suites",
        "marketing_video_projects",
        "personas",
        "content_generations",
        "batch_jobs",
        "store_check_logs",
        "operation_alerts",
        "publications",
        "voc_analyses",
        "agent_tasks",
        "conversations",
    ):
        columns = _column_map(engine, table_name)
        assert "workspace_id" in columns
        assert columns["user_id"]["nullable"] is True
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
    assert "credit_period_start" in _column_names(
        engine,
        "workspace_credit_wallets",
    )
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


def test_personal_billing_migration_backfills_workspace_period(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """073 升级必须把存量用户的额度周期复制到个人工作区钱包。"""

    db_path = tmp_path / "personal-billing-period.db"
    sync_url = f"sqlite:///{db_path.as_posix()}"
    async_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = sa.create_engine(sync_url)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", async_url)
    monkeypatch.setenv("DATABASE_URL", async_url)

    command.upgrade(config, "072_user_workspace_lifecycle")
    user_id = "11111111111111111111111111111111"
    workspace_id = "22222222222222222222222222222222"
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO users (
                    id, email, password_hash, credits, plan,
                    credit_period_start
                )
                VALUES (
                    :user_id, :email, :password_hash, 30, 'free',
                    :credit_period_start
                )
                """
            ),
            {
                "user_id": user_id,
                "email": "period-migration@example.com",
                "password_hash": "not-used",
                "credit_period_start": "2026-11-01 08:00:00.000000",
            },
        )
        conn.execute(
            sa.text(
                """
                INSERT INTO workspaces (
                    id, name, slug, type, owner_user_id, status
                )
                VALUES (
                    :workspace_id, :name, :slug, 'personal', :user_id, 'active'
                )
                """
            ),
            {
                "workspace_id": workspace_id,
                "name": "Personal",
                "slug": "period-migration",
                "user_id": user_id,
            },
        )
        conn.execute(
            sa.text(
                """
                INSERT INTO workspace_credit_wallets (
                    workspace_id, plan_credits, purchased_credits
                )
                VALUES (:workspace_id, 30, 0)
                """
            ),
            {"workspace_id": workspace_id},
        )

    command.upgrade(config, "head")

    with engine.connect() as conn:
        period = conn.execute(
            sa.text(
                """
                SELECT credit_period_start
                FROM workspace_credit_wallets
                WHERE workspace_id = :workspace_id
                """
            ),
            {"workspace_id": workspace_id},
        ).scalar_one()

    assert str(period).startswith("2026-11-01 08:00:00")
