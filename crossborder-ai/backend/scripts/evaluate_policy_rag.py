"""运行 30 题平台政策 RAG 检索评测。"""

import argparse
import asyncio
import json
from pathlib import Path

from app.core.database import async_session_factory
from app.services.policy_evaluation import (
    DEFAULT_MANIFEST_PATH,
    evaluate_policy_retrieval,
    load_policy_manifest,
)


async def main(manifest_path: Path, output: Path | None) -> int:
    manifest = load_policy_manifest(manifest_path)
    async with async_session_factory() as db:
        report = await evaluate_policy_retrieval(db, manifest)
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding="utf-8")
    print(serialized)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.manifest, args.output)))
