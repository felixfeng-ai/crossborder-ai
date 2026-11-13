"""导入 VeyaShip 正式平台政策语料。"""

import argparse
import asyncio
import json
from pathlib import Path

from app.core.database import async_session_factory
from app.services.policy_evaluation import (
    DEFAULT_MANIFEST_PATH,
    ingest_policy_manifest,
    load_policy_manifest,
)


async def main(manifest_path: Path) -> None:
    manifest = load_policy_manifest(manifest_path)
    async with async_session_factory() as db:
        result = await ingest_policy_manifest(db, manifest)
        await db.commit()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
    )
    args = parser.parse_args()
    asyncio.run(main(args.manifest))
