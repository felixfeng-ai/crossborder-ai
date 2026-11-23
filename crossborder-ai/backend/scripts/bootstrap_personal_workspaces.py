"""为缺少个人工作区的用户生成所有者工作区。

脚本可重复执行。已存在的个人工作区会跳过，不重复创建。
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
from app.services.workspaces import bootstrap_personal_workspaces  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VeyaShip 个人工作区初始化",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="单批读取用户数量",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    async with async_session_factory() as db:
        result = await bootstrap_personal_workspaces(
            db,
            batch_size=args.batch_size,
        )
        await db.commit()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
