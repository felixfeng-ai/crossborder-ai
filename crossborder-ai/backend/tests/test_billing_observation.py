"""首个账期账务观察门禁测试。"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.models.credit_transaction import CreditTransaction
from app.models.user import User
from app.services.billing_observation import (
    collect_billing_observation,
    count_duplicate_monthly_allowances,
    evaluate_billing_observation,
    persist_billing_observation,
    read_observation_files,
    summarize_observation_history,
)
from app.services.workspaces import ensure_personal_workspace


def _gate(*, passed: bool = True, missing_period: int = 0) -> dict:
    return {
        "phase": "postflight",
        "passed": passed,
        "blockers": (
            []
            if passed
            else [{"code": "wallet_mismatch", "message": "钱包差异"}]
        ),
        "warnings": [],
        "snapshot": {
            "revision": "073_personal_billing_source",
            "counts": {
                "users": 10,
                "personal_workspaces": 10,
                "personal_wallets_missing_period": missing_period,
                "open_billing_cases": 0,
                "due_archived_workspaces": 0,
            },
            "billing": {
                "summary": {
                    "wallet_mismatches": 0,
                    "subscription_mismatches": 0,
                    "ledger_requires_attention": False,
                }
            },
        },
    }


def test_observation_fails_on_duplicate_same_plan_period() -> None:
    result = evaluate_billing_observation(
        gate=_gate(),
        previous=None,
        duplicate_monthly_allowances=1,
        observed_at=datetime(2026, 11, 20, 8, tzinfo=timezone.utc),
        since=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )

    assert result["status"] == "failed"
    assert "duplicate_monthly_allowance" in {
        issue["code"] for issue in result["issues"]
    }
    assert result["snapshot"]["duplicate_monthly_allowances"] == 1


def test_observation_fails_when_missing_period_grows() -> None:
    previous = evaluate_billing_observation(
        gate=_gate(missing_period=2),
        previous=None,
        duplicate_monthly_allowances=0,
        observed_at=datetime(2026, 11, 19, 8, tzinfo=timezone.utc),
        since=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )

    result = evaluate_billing_observation(
        gate=_gate(missing_period=3),
        previous=previous,
        duplicate_monthly_allowances=0,
        observed_at=datetime(2026, 11, 20, 8, tzinfo=timezone.utc),
        since=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )

    assert result["status"] == "failed"
    issue = next(
        item
        for item in result["issues"]
        if item["code"] == "missing_period_increased"
    )
    assert issue["increase"] == 1


def test_observation_history_requires_seven_consecutive_days() -> None:
    observations = [
        {
            "status": "passed",
            "observed_at": f"2026-11-{day:02d}T08:00:00+00:00",
        }
        for day in range(13, 20)
    ]

    summary = summarize_observation_history(observations)

    assert summary["consecutive_passed_days"] == 7
    assert summary["gate_passed"] is True


def test_observation_history_resets_after_failed_day() -> None:
    observations = [
        {"status": "passed", "observed_at": "2026-11-15T08:00:00+00:00"},
        {"status": "passed", "observed_at": "2026-11-16T08:00:00+00:00"},
        {"status": "failed", "observed_at": "2026-11-17T08:00:00+00:00"},
        {"status": "passed", "observed_at": "2026-11-18T08:00:00+00:00"},
    ]

    summary = summarize_observation_history(observations)

    assert summary["consecutive_passed_days"] == 1
    assert summary["gate_passed"] is False


@pytest.mark.asyncio
async def test_duplicate_allowance_query_groups_workspace_plan_and_month(
    db_session,
) -> None:
    user = User(
        email="allowance-observation@example.com",
        username="allowance-observation",
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.flush()
    workspace = await ensure_personal_workspace(db_session, user)
    observed = datetime(2026, 11, 20, 8, tzinfo=timezone.utc)
    db_session.add_all(
        [
            CreditTransaction(
                user_id=user.id,
                workspace_id=workspace.id,
                delta=3000,
                balance_after=3000,
                feature="monthly_allowance",
                reference_id="professional",
                created_at=datetime(
                    2026,
                    11,
                    1,
                    0,
                    tzinfo=timezone.utc,
                ),
            ),
            CreditTransaction(
                user_id=user.id,
                workspace_id=workspace.id,
                delta=3000,
                balance_after=6000,
                feature="monthly_allowance",
                reference_id="professional",
                created_at=datetime(
                    2026,
                    11,
                    2,
                    0,
                    tzinfo=timezone.utc,
                ),
            ),
            CreditTransaction(
                user_id=user.id,
                workspace_id=workspace.id,
                delta=1000,
                balance_after=7000,
                feature="monthly_allowance",
                reference_id="standard",
                created_at=datetime(
                    2026,
                    11,
                    3,
                    tzinfo=timezone.utc,
                ),
            ),
            CreditTransaction(
                user_id=user.id,
                workspace_id=workspace.id,
                delta=3000,
                balance_after=10000,
                feature="monthly_allowance",
                reference_id="professional",
                created_at=datetime(
                    2026,
                    10,
                    1,
                    tzinfo=timezone.utc,
                ),
            ),
        ]
    )
    await db_session.commit()

    duplicates = await count_duplicate_monthly_allowances(
        db_session,
        since=observed - timedelta(days=20),
    )

    assert duplicates == 1


@pytest.mark.asyncio
async def test_collect_billing_observation_runs_read_only_gate(
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
    observed_at = datetime(2026, 11, 20, 8, tzinfo=timezone.utc)

    observation = await collect_billing_observation(
        db_session,
        observed_at=observed_at,
        since=datetime(2026, 11, 1, tzinfo=timezone.utc),
        allow_sqlite=True,
    )

    assert observation["status"] == "passed"
    assert observation["snapshot"]["revision"] == (
        "073_personal_billing_source"
    )
    assert observation["snapshot"]["duplicate_monthly_allowances"] == 0


def test_observation_history_rejects_malformed_file(tmp_path) -> None:
    (tmp_path / "observation-good.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "observed_at": "2026-11-20T08:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "observation-bad.json").write_text(
        "{broken",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="observation-bad.json"):
        read_observation_files(tmp_path)


def test_persist_observation_updates_continuous_summary(tmp_path) -> None:
    first = {
        "status": "passed",
        "observed_at": "2026-11-19T08:00:00+00:00",
        "snapshot": {"counts": {}},
    }
    second = {
        "status": "passed",
        "observed_at": "2026-11-20T08:00:00+00:00",
        "snapshot": {"counts": {}},
    }

    persist_billing_observation(tmp_path, first)
    result = persist_billing_observation(tmp_path, second)

    assert result["history"]["consecutive_passed_days"] == 2
    summary = json.loads(
        (tmp_path / "billing-observation-summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["consecutive_passed_days"] == 2
