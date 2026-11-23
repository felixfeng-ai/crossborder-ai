"""生产切换只读门禁：检查数据库状态，不执行迁移或修复。"""

from typing import Literal

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession


PRE_CUTOVER_REVISIONS = {
    "071_customer_order_links",
    "072_user_workspace_lifecycle",
}
POST_CUTOVER_REVISION = "073_personal_billing_source"


def _issue(code: str, message: str) -> dict:
    return {"code": code, "message": message}


async def _count(db: AsyncSession, statement: str) -> int:
    return int((await db.execute(text(statement))).scalar_one() or 0)


async def collect_cutover_snapshot(db: AsyncSession) -> dict:
    """读取 schema 和关键计数；所有查询均为只读。"""

    schema = await db.run_sync(_read_schema)
    tables = schema["tables"]
    columns = schema["columns"]
    counts = {
        "users": 0,
        "personal_workspaces": 0,
        "users_missing_personal_workspace": 0,
        "duplicate_personal_workspaces": 0,
        "personal_wallets_missing_period": None,
        "open_billing_cases": 0,
        "due_archived_workspaces": 0,
    }
    revision = None
    if tables.get("alembic_version"):
        revision = (
            await db.execute(
                text(
                    "SELECT version_num FROM alembic_version "
                    "ORDER BY version_num LIMIT 1"
                )
            )
        ).scalar_one_or_none()

    if tables.get("users"):
        counts["users"] = await _count(db, "SELECT COUNT(*) FROM users")
    if tables.get("workspaces"):
        counts["personal_workspaces"] = await _count(
            db,
            """
            SELECT COUNT(*)
            FROM workspaces
            WHERE type = 'personal' AND status = 'active'
            """,
        )
    if tables.get("users") and tables.get("workspaces"):
        active_user_filter = (
            "u.deleted_at IS NULL"
            if "deleted_at" in columns.get("users", [])
            else "1 = 1"
        )
        counts["users_missing_personal_workspace"] = await _count(
            db,
            f"""
            SELECT COUNT(*)
            FROM users u
            LEFT JOIN workspaces w
              ON w.owner_user_id = u.id
             AND w.type = 'personal'
             AND w.status = 'active'
            WHERE {active_user_filter}
              AND w.id IS NULL
            """,
        )
        counts["duplicate_personal_workspaces"] = await _count(
            db,
            """
            SELECT COUNT(*)
            FROM (
                SELECT owner_user_id
                FROM workspaces
                WHERE type = 'personal'
                  AND owner_user_id IS NOT NULL
                GROUP BY owner_user_id
                HAVING COUNT(*) > 1
            ) duplicate_owners
            """,
        )
    if (
        tables.get("workspace_credit_wallets")
        and "credit_period_start"
        in columns.get("workspace_credit_wallets", [])
    ):
        counts["personal_wallets_missing_period"] = await _count(
            db,
            """
            SELECT COUNT(*)
            FROM workspace_credit_wallets wcw
            JOIN workspaces w ON w.id = wcw.workspace_id
            WHERE w.type = 'personal'
              AND w.status = 'active'
              AND wcw.credit_period_start IS NULL
            """,
        )
    if tables.get("billing_reconciliation_cases"):
        counts["open_billing_cases"] = await _count(
            db,
            """
            SELECT COUNT(*)
            FROM billing_reconciliation_cases
            WHERE status = 'open'
            """,
        )
    if (
        tables.get("workspaces")
        and {"status", "purge_after"}
        <= set(columns.get("workspaces") or [])
    ):
        counts["due_archived_workspaces"] = await _count(
            db,
            """
            SELECT COUNT(*)
            FROM workspaces
            WHERE status = 'archived'
              AND purge_after IS NOT NULL
              AND purge_after <= CURRENT_TIMESTAMP
            """,
        )

    return {
        "dialect": schema["dialect"],
        "revision": revision,
        "tables": tables,
        "columns": columns,
        "counts": counts,
        "billing": None,
    }


async def run_cutover_check(
    db: AsyncSession,
    phase: Literal["preflight", "postflight"],
    *,
    allow_sqlite: bool = False,
    batch_size: int = 500,
) -> dict:
    """收集快照并执行门禁；postflight 额外运行只读账务对账。"""

    snapshot = await collect_cutover_snapshot(db)
    if phase == "postflight" and _postflight_schema_ready(snapshot):
        try:
            from app.services.workspace_billing_reconciliation import (
                reconcile_personal_workspace_billing,
            )

            snapshot["billing"] = (
                await reconcile_personal_workspace_billing(
                    db,
                    batch_size=batch_size,
                    repair=False,
                    record_cases=False,
                )
            )
        except Exception as exc:  # pragma: no cover - CLI 边界
            snapshot["billing_error"] = str(exc)
    return evaluate_cutover_gate(
        phase,
        snapshot,
        allow_sqlite=allow_sqlite,
    )


def _postflight_schema_ready(snapshot: dict) -> bool:
    tables = snapshot.get("tables") or {}
    columns = snapshot.get("columns") or {}
    return (
        bool(tables.get("workspace_credit_wallets"))
        and "credit_period_start"
        in (columns.get("workspace_credit_wallets") or [])
        and bool(tables.get("billing_reconciliation_cases"))
    )


def _read_schema(session) -> dict:
    """同步反射 schema；仅读取表名和列名。"""

    connection = session.connection()
    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    tracked_tables = (
        "alembic_version",
        "users",
        "workspaces",
        "workspace_credit_wallets",
        "billing_reconciliation_cases",
    )
    tables = {
        table_name: table_name in table_names
        for table_name in tracked_tables
    }
    columns = {}
    for table_name in tracked_tables:
        if tables[table_name]:
            columns[table_name] = [
                column["name"]
                for column in inspector.get_columns(table_name)
            ]
    return {
        "dialect": connection.dialect.name,
        "tables": tables,
        "columns": columns,
    }


def evaluate_cutover_gate(
    phase: Literal["preflight", "postflight"],
    snapshot: dict,
    *,
    allow_sqlite: bool = False,
) -> dict:
    """评估只读快照；blocker 会阻断发布，warning 需要人工确认。"""

    if phase not in {"preflight", "postflight"}:
        raise ValueError("phase 只能是 preflight 或 postflight")

    blockers: list[dict] = []
    warnings: list[dict] = []
    dialect = snapshot.get("dialect")
    revision = snapshot.get("revision")
    tables = snapshot.get("tables") or {}
    columns = snapshot.get("columns") or {}
    counts = snapshot.get("counts") or {}
    billing = snapshot.get("billing")

    if dialect != "postgresql" and not (
        allow_sqlite and dialect == "sqlite"
    ):
        blockers.append(
            _issue(
                "postgresql_required",
                "生产切换门禁要求 PostgreSQL",
            )
        )
    expected_revisions = (
        PRE_CUTOVER_REVISIONS
        if phase == "preflight"
        else {POST_CUTOVER_REVISION}
    )
    if revision not in expected_revisions:
        blockers.append(
            _issue(
                "unexpected_revision",
                f"当前 revision {revision} 不在允许范围",
            )
        )
    required_tables = {"alembic_version", "users", "workspaces"}
    if phase == "postflight":
        required_tables.add("workspace_credit_wallets")
    for table_name in sorted(required_tables):
        if not tables.get(table_name):
            blockers.append(
                _issue(
                    "missing_table",
                    f"缺少基础表 {table_name}",
                )
            )
    if int(counts.get("duplicate_personal_workspaces") or 0) > 0:
        blockers.append(
            _issue(
                "duplicate_personal_workspaces",
                "存在同一用户多个个人工作区",
            )
        )

    if phase == "preflight":
        warning_counts = (
            (
                "users_missing_personal_workspace",
                "仍有用户缺少个人工作区",
            ),
            (
                "open_billing_cases",
                "仍有未结案账务案件",
            ),
            (
                "due_archived_workspaces",
                "仍有到期归档工作区待清理",
            ),
        )
        for code, message in warning_counts:
            if int(counts.get(code) or 0) > 0:
                warnings.append(_issue(code, message))
    else:
        required_columns = {
            "users": {"deleted_at", "deletion_reason"},
            "workspaces": {
                "archived_at",
                "purge_after",
                "archived_by_user_id",
            },
            "workspace_credit_wallets": {"credit_period_start"},
        }
        for table_name, expected_columns in required_columns.items():
            actual_columns = set(columns.get(table_name) or [])
            for column_name in sorted(expected_columns - actual_columns):
                blockers.append(
                    _issue(
                        "missing_column",
                        f"{table_name}.{column_name} 缺失",
                    )
                )
        if int(
            counts.get("users_missing_personal_workspace") or 0
        ) > 0:
            blockers.append(
                _issue(
                    "users_missing_personal_workspace",
                    "仍有有效用户缺少个人工作区",
                )
            )
        if int(counts.get("open_billing_cases") or 0) > 0:
            blockers.append(
                _issue(
                    "open_billing_cases",
                    "仍有未结案账务案件",
                )
            )
        if snapshot.get("billing_error"):
            blockers.append(
                _issue(
                    "billing_check_failed",
                    f"账务对账执行失败：{snapshot['billing_error']}",
                )
            )
        elif billing is None:
            blockers.append(
                _issue(
                    "billing_report_missing",
                    "缺少后置账务对账报告",
                )
            )
        else:
            if int(
                (billing.get("wallets") or {}).get("mismatched") or 0
            ) > 0:
                blockers.append(
                    _issue(
                        "wallet_mismatch",
                        "工作区钱包与旧镜像存在差异",
                    )
                )
            if int(
                (billing.get("subscriptions") or {}).get(
                    "mismatched"
                )
                or 0
            ) > 0:
                blockers.append(
                    _issue(
                        "subscription_mismatch",
                        "工作区订阅与旧镜像存在差异",
                    )
                )
            if bool(
                (billing.get("ledger") or {}).get(
                    "requires_attention"
                )
            ):
                blockers.append(
                    _issue(
                        "ledger_requires_attention",
                        "账本存在未归属或余额关注项",
                    )
                )
        if int(
            counts.get("personal_wallets_missing_period") or 0
        ) > 0:
            warnings.append(
                _issue(
                    "personal_wallets_missing_period",
                    "仍有个人工作区钱包额度周期为空",
                )
            )
        if int(counts.get("due_archived_workspaces") or 0) > 0:
            warnings.append(
                _issue(
                    "due_archived_workspaces",
                    "仍有到期归档工作区待清理",
                )
            )

    return {
        "phase": phase,
        "passed": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "snapshot": snapshot,
    }
