"""执行 Temu 自发货只读验收诊断，不提交任何发货请求。"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import async_session_factory  # noqa: E402
from app.models.platform_connection import PlatformConnection  # noqa: E402
from app.models.workspace import Workspace  # noqa: E402
from app.services.temu_fulfillment_readiness import (  # noqa: E402
    build_temu_fulfillment_readiness_report,
    readiness_exit_code,
    run_temu_fulfillment_readiness,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Temu LOCAL/SEMI 自发货只读验收诊断",
    )
    parser.add_argument(
        "--connection-id",
        type=UUID,
        required=True,
        help="Temu PlatformConnection ID",
    )
    parser.add_argument(
        "--parent-order-sn",
        required=True,
        help="Temu 父订单号",
    )
    parser.add_argument(
        "--carrier-id",
        type=int,
        required=True,
        help="当前区域 Temu 物流商 ID",
    )
    parser.add_argument(
        "--tracking-number",
        required=True,
        help="拟用于验收的物流单号",
    )
    parser.add_argument(
        "--self-shipping-warehouse-id",
        default="",
        help="卖家已配置的自发货仓库 ID，可选",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="可选 JSON 报告输出路径",
    )
    return parser.parse_args()


async def execute(args: argparse.Namespace) -> dict:
    async with async_session_factory() as db:
        connection = (
            await db.execute(
                select(PlatformConnection).where(
                    PlatformConnection.id == args.connection_id,
                    PlatformConnection.platform == "temu",
                    PlatformConnection.status == "active",
                )
            )
        ).scalar_one_or_none()
        if connection is None:
            return build_temu_fulfillment_readiness_report(
                error="Temu 店铺连接不存在或授权不可用",
                connection_id=str(args.connection_id),
                parent_order_sn=args.parent_order_sn,
            )
        workspace = (
            await db.execute(
                select(Workspace)
                .where(
                    Workspace.owner_user_id == connection.user_id,
                    Workspace.type == "personal",
                    Workspace.status == "active",
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if workspace is None:
            return build_temu_fulfillment_readiness_report(
                error="Temu 店铺没有可用个人工作区",
                connection_id=str(args.connection_id),
                parent_order_sn=args.parent_order_sn,
            )
        return await run_temu_fulfillment_readiness(
            db,
            user_id=connection.user_id,
            workspace_id=workspace.id,
            connection_id=connection.id,
            parent_order_sn=args.parent_order_sn,
            carrier_id=args.carrier_id,
            tracking_number=args.tracking_number,
            self_shipping_warehouse_id=(
                args.self_shipping_warehouse_id
            ),
        )


def main() -> None:
    args = parse_args()
    try:
        report = asyncio.run(execute(args))
    except Exception as exc:
        report = build_temu_fulfillment_readiness_report(
            error=str(exc),
            connection_id=str(args.connection_id),
            parent_order_sn=args.parent_order_sn,
        )
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    raise SystemExit(readiness_exit_code(report))


if __name__ == "__main__":
    main()
