"""生成首个账期每日只读账务观察快照。"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import async_session_factory  # noqa: E402
from app.services.billing_observation import (  # noqa: E402
    collect_billing_observation,
    latest_observation_before,
    persist_billing_observation,
    read_observation_files,
)


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("时间必须为 ISO 8601") from exc
    return (
        parsed.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is None
        else parsed.astimezone(timezone.utc)
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VeyaShip 首个账期每日只读观察",
    )
    parser.add_argument(
        "--directory",
        type=Path,
        required=True,
        help="观察 JSON 证据目录",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument(
        "--observed-at",
        type=_parse_datetime,
        help="观测时间，默认当前 UTC 时间",
    )
    parser.add_argument(
        "--since",
        type=_parse_datetime,
        help="重复额度检查起点，默认观测月第一天",
    )
    parser.add_argument(
        "--allow-sqlite",
        action="store_true",
        help="仅限本地开发使用 SQLite 验证脚本",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    if args.batch_size < 1:
        raise SystemExit("--batch-size 必须大于 0")
    observed_at = args.observed_at or datetime.now(timezone.utc)
    since = args.since or observed_at.replace(
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    if since > observed_at:
        raise SystemExit("--since 不能晚于 --observed-at")

    args.directory.mkdir(parents=True, exist_ok=True)
    try:
        existing = read_observation_files(args.directory)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    async with async_session_factory() as db:
        observation = await collect_billing_observation(
            db,
            observed_at=observed_at,
            since=since,
            previous=latest_observation_before(existing, observed_at),
            allow_sqlite=args.allow_sqlite,
            batch_size=args.batch_size,
        )

    stored = persist_billing_observation(args.directory, observation)
    print(
        json.dumps(
            stored["observation"],
            ensure_ascii=False,
            indent=2,
        )
    )
    if stored["observation"]["status"] != "passed":
        raise SystemExit(2)


if __name__ == "__main__":
    asyncio.run(main())
