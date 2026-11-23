"""回填个人工作区钱包和有效订阅。

默认 dry-run，只统计结果；确认后使用 --apply 写入。
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
from app.services.workspace_billing_backfill import (  # noqa: E402
    backfill_personal_workspace_billing,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VeyaShip 个人工作区账务回填",
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
    async with async_session_factory() as db:
        result = await backfill_personal_workspace_billing(
            db,
            batch_size=args.batch_size,
            dry_run=not args.apply,
        )
        if args.apply:
            await db.commit()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
