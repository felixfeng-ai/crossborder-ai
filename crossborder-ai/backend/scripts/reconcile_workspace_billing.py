"""对账个人用户账务与个人工作区账务。

默认只报告；修复必须按案件由配置内管理员批准，禁止整库直接覆盖。
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import async_session_factory  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.workspace_billing_reconciliation import (  # noqa: E402
    BillingReconciliationRepairError,
    approve_billing_reconciliation_case,
    reconcile_personal_workspace_billing,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VeyaShip 个人工作区账务对账",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument(
        "--record-cases",
        action="store_true",
        help="把钱包差异记录为待审批止付案件",
    )
    parser.add_argument(
        "--case-id",
        type=UUID,
        help="管理员批准的账务差异案件 ID",
    )
    parser.add_argument(
        "--admin-email",
        help="执行批准的管理员邮箱，必须在 ADMIN_EMAILS 内",
    )
    parser.add_argument(
        "--note",
        default="",
        help="管理员修复依据",
    )
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="发现任何账务差异时返回非零退出码",
    )
    args = parser.parse_args()
    if bool(args.case_id) != bool(args.admin_email):
        parser.error("--case-id 与 --admin-email 必须同时提供")
    if args.case_id and args.record_cases:
        parser.error("案件审批不能与 --record-cases 同时执行")
    return args


async def main() -> None:
    args = parse_args()
    async with async_session_factory() as db:
        if args.case_id is not None:
            admin = (
                await db.execute(
                    select(User).where(
                        func.lower(User.email) == args.admin_email.lower()
                    )
                )
            ).scalar_one_or_none()
            admin_emails = {
                email.lower() for email in settings.ADMIN_EMAILS
            }
            if (
                admin is None
                or admin.email.lower() not in admin_emails
            ):
                raise SystemExit("管理员不存在或没有账务修复权限")
            try:
                result = await approve_billing_reconciliation_case(
                    db,
                    case_id=args.case_id,
                    approved_by_user_id=admin.id,
                    note=args.note,
                )
            except BillingReconciliationRepairError as exc:
                raise SystemExit(str(exc)) from exc
            await db.commit()
        else:
            result = await reconcile_personal_workspace_billing(
                db,
                batch_size=args.batch_size,
                record_cases=args.record_cases,
            )
            if args.record_cases:
                await db.commit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.fail_on_mismatch and (
        result["wallets"]["mismatched"]
        or result["subscriptions"]["mismatched"]
        or result["ledger"]["requires_attention"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
