"""媒体任务工作区幂等约束迁移测试。"""

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


BACKEND_DIR = Path(__file__).resolve().parents[1]


def _unique_names(engine: sa.Engine, table_name: str) -> set[str]:
    inspector = sa.inspect(engine)
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


def test_media_idempotency_constraints_include_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "media-workspace-idempotency.db"
    sync_url = f"sqlite:///{db_path.as_posix()}"
    async_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    engine = sa.create_engine(sync_url)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", async_url)
    monkeypatch.setenv("DATABASE_URL", async_url)

    command.upgrade(config, "head")

    assert "uq_image_generation_tasks_workspace_idempotency" in _unique_names(
        engine,
        "image_generation_tasks",
    )
    assert "uq_video_tasks_workspace_idempotency" in _unique_names(
        engine,
        "video_generation_tasks",
    )
    assert "uq_marketing_video_workspace_idempotency" in _unique_names(
        engine,
        "marketing_video_projects",
    )
