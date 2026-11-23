"""校验真实一天 E2E 证据并输出 JSON 报告。"""

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.real_day_acceptance import (  # noqa: E402
    build_real_day_manifest_template,
    evaluate_real_day_evidence,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VeyaShip 真实一天端到端验收证据门禁",
    )
    parser.add_argument(
        "--directory",
        type=Path,
        required=True,
        help="包含 manifest.json 和证据文件的目录",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="可选 JSON 报告路径",
    )
    parser.add_argument(
        "--init-template",
        action="store_true",
        help="生成不会默认通过的 manifest 模板",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="模板已存在时允许覆盖",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest_path = args.directory / "manifest.json"
    if args.init_template:
        args.directory.mkdir(parents=True, exist_ok=True)
        if manifest_path.exists() and not args.force:
            raise SystemExit("manifest.json 已存在；使用 --force 才可覆盖")
        manifest_path.write_text(
            json.dumps(
                build_real_day_manifest_template(),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Created {manifest_path}")
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"manifest.json 无法解析：{exc}") from exc
    if not isinstance(manifest, dict):
        raise SystemExit("manifest.json 必须是 JSON 对象")

    report = evaluate_real_day_evidence(manifest, args.directory)
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    if not report["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
