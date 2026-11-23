"""在事务内执行用户注销与工作区生命周期生产演练。"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import text

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import async_session_factory, engine  # noqa: E402
from app.services.user_lifecycle import run_user_lifecycle_drill  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VeyaShip 用户生命周期演练（事务结束回滚）",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="确认在当前 DATABASE_URL 上执行隔离演练",
    )
    parser.add_argument(
        "--allow-sqlite",
        action="store_true",
        help="允许 SQLite 冒烟演练；生产正式演练必须使用 PostgreSQL",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if not args.confirm:
        raise SystemExit("必须显式传入 --confirm")
    dialect = engine.dialect.name
    if dialect != "postgresql" and not args.allow_sqlite:
        raise SystemExit("生产生命周期演练要求 PostgreSQL")

    async with async_session_factory() as db:
        if dialect == "sqlite":
            await db.execute(text("PRAGMA foreign_keys=ON"))
        result = await run_user_lifecycle_drill(db)
        await db.rollback()
    print(
        json.dumps(
            {
                "dialect": dialect,
                "rolled_back": True,
                **result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
