"""生产切换前置与后置门禁测试。"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.models.user import User
from app.models.workspace_credit_wallet import WorkspaceCreditWallet
from app.services.production_cutover import (
    collect_cutover_snapshot,
    evaluate_cutover_gate,
    run_cutover_check,
)
from app.services.workspaces import ensure_personal_workspace


def _snapshot(**overrides) -> dict:
    snapshot = {
        "dialect": "postgresql",
        "revision": "072_user_workspace_lifecycle",
        "tables": {
            "alembic_version": True,
            "users": True,
            "workspaces": True,
            "workspace_credit_wallets": True,
        },
        "columns": {
            "users": ["deleted_at", "deletion_reason"],
            "workspaces": [
                "archived_at",
                "purge_after",
                "archived_by_user_id",
            ],
            "workspace_credit_wallets": ["credit_period_start"],
        },
        "counts": {
            "users": 12,
            "personal_workspaces": 10,
            "users_missing_personal_workspace": 2,
            "duplicate_personal_workspaces": 0,
            "personal_wallets_missing_period": 0,
            "open_billing_cases": 1,
            "due_archived_workspaces": 3,
        },
        "billing": None,
    }
    snapshot.update(overrides)
    return snapshot


def test_preflight_accepts_supported_postgres_revision_and_warns() -> None:
    result = evaluate_cutover_gate("preflight", _snapshot())

    assert result["passed"] is True
    assert result["blockers"] == []
    assert {item["code"] for item in result["warnings"]} == {
        "users_missing_personal_workspace",
        "open_billing_cases",
        "due_archived_workspaces",
    }


def test_postflight_blocks_missing_period_column() -> None:
    result = evaluate_cutover_gate(
        "postflight",
        _snapshot(
            revision="073_personal_billing_source",
            columns={
                "users": ["deleted_at", "deletion_reason"],
                "workspaces": [
                    "archived_at",
                    "purge_after",
                    "archived_by_user_id",
                ],
                "workspace_credit_wallets": [],
            },
            counts={
                **_snapshot()["counts"],
                "users_missing_personal_workspace": 0,
                "open_billing_cases": 0,
                "due_archived_workspaces": 0,
            },
            billing={
                "wallets": {"mismatched": 0},
                "subscriptions": {"mismatched": 0},
                "ledger": {"requires_attention": False},
            },
        ),
    )

    assert result["passed"] is False
    assert "missing_column" in {
        item["code"] for item in result["blockers"]
    }


def test_postflight_blocks_billing_mismatch() -> None:
    base = _snapshot()
    result = evaluate_cutover_gate(
        "postflight",
        _snapshot(
            revision="073_personal_billing_source",
            counts={
                **base["counts"],
                "users_missing_personal_workspace": 0,
                "open_billing_cases": 0,
                "due_archived_workspaces": 0,
            },
            billing={
                "wallets": {"mismatched": 1},
                "subscriptions": {"mismatched": 1},
                "ledger": {"requires_attention": True},
            },
        ),
    )

    assert result["passed"] is False
    assert {
        "wallet_mismatch",
        "subscription_mismatch",
        "ledger_requires_attention",
    } <= {item["code"] for item in result["blockers"]}


def test_gate_blocks_sqlite_without_development_override() -> None:
    result = evaluate_cutover_gate(
        "preflight",
        _snapshot(dialect="sqlite"),
    )

    assert result["passed"] is False
    assert "postgresql_required" in {
        item["code"] for item in result["blockers"]
    }


def test_gate_allows_sqlite_only_with_development_override() -> None:
    result = evaluate_cutover_gate(
        "preflight",
        _snapshot(dialect="sqlite"),
        allow_sqlite=True,
    )

    assert result["passed"] is True


@pytest.mark.asyncio
async def test_collect_cutover_snapshot_reports_schema_and_counts(
    db_session,
) -> None:
    await db_session.execute(
        text(
            "CREATE TABLE alembic_version "
            "(version_num VARCHAR(32) PRIMARY KEY)"
        )
    )
    await db_session.execute(
        text(
            "INSERT INTO alembic_version(version_num) "
            "VALUES ('072_user_workspace_lifecycle')"
        )
    )
    user = User(
        email="cutover-snapshot@example.com",
        username="cutover-snapshot",
        password_hash="not-used",
        plan="professional",
        credits=40,
        credit_period_start=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    db_session.add(user)
    await db_session.flush()
    workspace = await ensure_personal_workspace(db_session, user)
    db_session.add(
        WorkspaceCreditWallet(
            workspace_id=workspace.id,
            plan_credits=30,
            purchased_credits=10,
            credit_period_start=user.credit_period_start,
        )
    )
    await db_session.commit()

    snapshot = await collect_cutover_snapshot(db_session)

    assert snapshot["dialect"] == "sqlite"
    assert snapshot["revision"] == "072_user_workspace_lifecycle"
    assert snapshot["tables"]["workspace_credit_wallets"] is True
    assert set(snapshot["columns"]["workspace_credit_wallets"]) == {
        "workspace_id",
        "plan_credits",
        "purchased_credits",
        "credit_period_start",
        "updated_at",
    }
    assert snapshot["counts"]["users"] == 1
    assert snapshot["counts"]["personal_workspaces"] == 1
    assert snapshot["counts"]["users_missing_personal_workspace"] == 0
    assert snapshot["counts"]["duplicate_personal_workspaces"] == 0
    assert snapshot["counts"]["personal_wallets_missing_period"] == 0


@pytest.mark.asyncio
async def test_postflight_check_runs_read_only_billing_reconciliation(
    db_session,
) -> None:
    await db_session.execute(
        text(
            "CREATE TABLE alembic_version "
            "(version_num VARCHAR(32) PRIMARY KEY)"
        )
    )
    await db_session.execute(
        text(
            "INSERT INTO alembic_version(version_num) "
            "VALUES ('073_personal_billing_source')"
        )
    )
    await db_session.commit()

    result = await run_cutover_check(
        db_session,
        "postflight",
        allow_sqlite=True,
    )

    assert result["passed"] is True
    assert result["snapshot"]["billing"]["wallets"]["mismatched"] == 0
    assert (
        result["snapshot"]["billing"]["subscriptions"]["mismatched"]
        == 0
    )
