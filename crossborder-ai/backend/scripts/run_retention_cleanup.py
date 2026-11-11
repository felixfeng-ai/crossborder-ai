"""手动执行数据保留清理。

默认 dry-run，只统计待删除数量；确认后再加 --apply 执行真实删除。
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
from app.services.data_retention import run_retention_cleanup  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VeyaShip 数据保留清理")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="执行真实删除；未指定时仅 dry-run",
    )
    parser.add_argument("--days", type=int, default=None, help="临时记录保留天数")
    parser.add_argument(
        "--store-check-days",
        type=int,
        default=None,
        help="巡检日志保留天数",
    )
    parser.add_argument("--batch-size", type=int, default=None, help="单批删除数量")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    async with async_session_factory() as db:
        result = await run_retention_cleanup(
            db,
            retention_days=args.days,
            store_check_retention_days=args.store_check_days,
            dry_run=not args.apply,
            batch_size=args.batch_size,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
