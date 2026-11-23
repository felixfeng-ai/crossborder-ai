"""清理已过保留期的归档工作区。"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.core.database import async_session_factory  # noqa: E402
from app.services.user_lifecycle import (  # noqa: E402
    purge_expired_workspaces,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VeyaShip 归档工作区到期清理",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=settings.DATA_RETENTION_BATCH_SIZE,
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    async with async_session_factory() as db:
        result = await purge_expired_workspaces(
            db,
            batch_size=args.batch_size,
        )
        await db.commit()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
