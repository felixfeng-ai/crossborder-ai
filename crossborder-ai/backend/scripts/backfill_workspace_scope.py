"""分批回填历史业务数据的工作区归属。

默认 dry-run，只统计可回填与无法归属的记录；确认后使用 --apply 写入。
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import async_session_factory  # noqa: E402
from app.services.workspace_backfill import (  # noqa: E402
    SCOPED_MODELS,
    backfill_workspace_scope,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VeyaShip 业务表工作区字段回填",
    )
    parser.add_argument(
        "--table",
        choices=[*SCOPED_MODELS, "all"],
        default="all",
        help="指定单表或全部已接入的业务表",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="执行真实回填；未指定时仅 dry-run",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    tables = (
        tuple(SCOPED_MODELS)
        if args.table == "all"
        else (args.table,)
    )
    async with async_session_factory() as db:
        result = await backfill_workspace_scope(
            db,
            batch_size=args.batch_size,
            dry_run=not args.apply,
            tables=tables,
        )
        if args.apply:
            await db.commit()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
