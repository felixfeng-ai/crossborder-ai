"""生产切换只读门禁：输出 preflight/postflight JSON 证据。"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import async_session_factory  # noqa: E402
from app.services.production_cutover import run_cutover_check  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VeyaShip 生产切换前置/后置只读门禁",
    )
    parser.add_argument(
        "phase",
        choices=("preflight", "postflight"),
        help="迁移前或迁移后检查",
    )
    parser.add_argument(
        "--allow-sqlite",
        action="store_true",
        help="仅限本地开发使用 SQLite 验证脚本",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument(
        "--output",
        type=Path,
        help="可选 JSON 报告输出路径",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    async with async_session_factory() as db:
        result = await run_cutover_check(
            db,
            args.phase,
            allow_sqlite=args.allow_sqlite,
            batch_size=args.batch_size,
        )
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    if not result["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    asyncio.run(main())
