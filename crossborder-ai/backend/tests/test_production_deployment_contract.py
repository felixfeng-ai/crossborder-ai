"""生产部署脚本与镜像契约测试。"""

from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent


def test_production_deploy_migrates_before_starting_backend() -> None:
    script = (PROJECT_DIR / "deploy.sh").read_text(encoding="utf-8")

    assert "alembic stamp head" not in script
    assert "init_db() 自动调用 create_all" not in script
    database_start = script.index(
        "docker compose -f docker-compose.prod.yml up -d postgres qdrant"
    )
    migration = script.index(
        "backend alembic upgrade head"
    )
    full_start = script.index(
        "docker compose -f docker-compose.prod.yml up -d\n"
    )
    assert database_start < migration < full_start


def test_backend_image_contains_alembic_configuration() -> None:
    dockerfile = (BACKEND_DIR / "Dockerfile").read_text(encoding="utf-8")

    assert "COPY ./alembic.ini /app/alembic.ini" in dockerfile
