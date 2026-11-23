"""历史工作区归属回填迁移测试。"""

import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_history_workspace_backfill_migration_is_idempotent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "workspace-history-backfill.db"
    sync_url = f"sqlite:///{db_path.as_posix()}"
    async_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = sa.create_engine(sync_url)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", async_url)
    monkeypatch.setenv("DATABASE_URL", async_url)

    command.upgrade(config, "074_agent_workspace_idem")

    user_id = str(uuid.uuid4())
    workspace_id = str(uuid.uuid4())
    orphan_user_id = str(uuid.uuid4())
    rows = {
        "conversation": str(uuid.uuid4()),
        "agent_task": str(uuid.uuid4()),
        "persona": str(uuid.uuid4()),
        "batch_job": str(uuid.uuid4()),
        "marketing_video": str(uuid.uuid4()),
        "orphan_conversation": str(uuid.uuid4()),
    }
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO users (id, email, password_hash) "
                "VALUES (:id, :email, 'x')"
            ),
            {"id": user_id, "email": "history@example.com"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO users (id, email, password_hash) "
                "VALUES (:id, :email, 'x')"
            ),
            {"id": orphan_user_id, "email": "orphan@example.com"},
        )
        conn.execute(
            sa.text(
                "INSERT INTO workspaces "
                "(id, name, slug, type, owner_user_id, status) "
                "VALUES (:id, 'Personal', :slug, 'personal', :owner, 'active')"
            ),
            {
                "id": workspace_id,
                "slug": f"personal-{workspace_id[:8]}",
                "owner": user_id,
            },
        )
        conn.execute(
            sa.text(
                "INSERT INTO conversations (id, user_id, title) "
                "VALUES (:id, :user_id, 'history conversation')"
            ),
            {"id": rows["conversation"], "user_id": user_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO agent_tasks "
                "(id, user_id, task_type, status, input) "
                "VALUES (:id, :user_id, 'agent_run', 'pending', '{}')"
            ),
            {"id": rows["agent_task"], "user_id": user_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO personas (id, user_id, brand_name) "
                "VALUES (:id, :user_id, 'History Brand')"
            ),
            {"id": rows["persona"], "user_id": user_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO batch_jobs "
                "(id, user_id, source_type, title, status) "
                "VALUES (:id, :user_id, 'csv', 'History Job', 'pending')"
            ),
            {"id": rows["batch_job"], "user_id": user_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO marketing_video_projects "
                "(id, user_id, title, product_name, idea, platform, "
                "duration, template_id, model, resolution, brief_json) "
                "VALUES (:id, :user_id, 'History Video', 'Product', "
                "'idea', 'tiktok', 15, 'presenter_demo', "
                "'MiniMax-H3-Lite', '480P', '{}')"
            ),
            {"id": rows["marketing_video"], "user_id": user_id},
        )
        conn.execute(
            sa.text(
                "INSERT INTO conversations (id, user_id, title) "
                "VALUES (:id, :user_id, 'unresolved conversation')"
            ),
            {
                "id": rows["orphan_conversation"],
                "user_id": orphan_user_id,
            },
        )

    command.upgrade(config, "head")

    with engine.connect() as conn:
        for table_name, row_id in (
            ("conversations", rows["conversation"]),
            ("agent_tasks", rows["agent_task"]),
            ("personas", rows["persona"]),
            ("batch_jobs", rows["batch_job"]),
            ("marketing_video_projects", rows["marketing_video"]),
        ):
            value = conn.execute(
                sa.text(
                    f"SELECT workspace_id FROM {table_name} WHERE id = :id"
                ),
                {"id": row_id},
            ).scalar_one()
            assert value == workspace_id

        unresolved = conn.execute(
            sa.text(
                "SELECT workspace_id FROM conversations WHERE id = :id"
            ),
            {"id": rows["orphan_conversation"]},
        ).scalar_one()
        assert unresolved is None
        version = conn.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one()

    assert version == ScriptDirectory.from_config(config).get_current_head()
