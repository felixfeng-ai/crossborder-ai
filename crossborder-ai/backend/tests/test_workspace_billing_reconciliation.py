"""个人工作区账务对账测试。"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.dependencies import get_current_user, require_admin
from app.main import app
from app.models.billing_reconciliation_case import BillingReconciliationCase
from app.models.credit_transaction import CreditTransaction
from app.models.credit_wallet import CreditWallet
from app.models.subscription import UserSubscription
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_credit_wallet import WorkspaceCreditWallet
from app.models.workspace_subscription import WorkspaceSubscription
from app.services.workspace_billing_reconciliation import (
    reconcile_personal_workspace_billing,
)
from app.services.plan_service import add_purchased_credits
from app.services import workspace_billing_reconciliation as billing_reconciliation
from app.services.workspaces import ensure_personal_workspace


async def _billing_pair(db_session, email: str):
    now = datetime.now(timezone.utc)
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used",
        plan="standard",
        credits=820,
    )
    db_session.add(user)
    await db_session.flush()
    workspace = await ensure_personal_workspace(db_session, user)
    db_session.add(
        CreditWallet(
            user_id=user.id,
            plan_credits=800,
            purchased_credits=20,
        )
    )
    legacy_subscription = UserSubscription(
        user_id=user.id,
        plan="standard",
        status="active",
        starts_at=now,
        expires_at=now + timedelta(days=30),
    )
    db_session.add(legacy_subscription)
    return user, workspace, legacy_subscription, now


@pytest.mark.asyncio
async def test_reconciliation_reports_mismatch_without_changes(db_session):
    _user, workspace, _subscription, now = await _billing_pair(
        db_session,
        "billing-reconcile-report@example.com",
    )
    db_session.add(
        WorkspaceCreditWallet(
            workspace_id=workspace.id,
            plan_credits=1,
            purchased_credits=2,
        )
    )
    db_session.add(
        WorkspaceSubscription(
            workspace_id=workspace.id,
            plan="professional",
            status="active",
            starts_at=now,
            expires_at=now + timedelta(days=60),
            payer_user_id=workspace.owner_user_id,
        )
    )
    await db_session.commit()

    report = await reconcile_personal_workspace_billing(
        db_session,
        now=now,
    )
    wallet = await db_session.get(WorkspaceCreditWallet, workspace.id)
    subscription = (
        await db_session.execute(
            select(WorkspaceSubscription).where(
                WorkspaceSubscription.workspace_id == workspace.id,
                WorkspaceSubscription.status == "active",
            )
        )
    ).scalar_one()

    assert report["wallets"]["mismatched"] == 1
    assert report["subscriptions"]["mismatched"] == 1
    assert report["summary"]["workspace_count"] >= 1
    assert report["summary"]["wallet_mismatches"] == 1
    assert report["summary"]["subscription_mismatches"] == 1
    assert wallet.plan_credits == 1
    assert subscription.plan == "professional"


@pytest.mark.asyncio
async def test_reconciliation_repair_mirrors_workspace_ledger(db_session):
    user, workspace, legacy_subscription, now = await _billing_pair(
        db_session,
        "billing-reconcile-repair@example.com",
    )
    db_session.add(
        WorkspaceCreditWallet(
            workspace_id=workspace.id,
            plan_credits=1,
            purchased_credits=2,
        )
    )
    await db_session.commit()

    report = await reconcile_personal_workspace_billing(
        db_session,
        repair=True,
        now=now,
    )
    wallet = await db_session.get(WorkspaceCreditWallet, workspace.id)
    subscription = (
        await db_session.execute(
            select(WorkspaceSubscription).where(
                WorkspaceSubscription.workspace_id == workspace.id,
                WorkspaceSubscription.status == "active",
            )
        )
    ).scalar_one()

    assert report["wallets"]["repaired"] == 1
    assert report["subscriptions"]["repaired"] == 1
    assert wallet.plan_credits == 1
    assert wallet.purchased_credits == 2
    legacy_wallet = await db_session.get(CreditWallet, user.id)
    assert legacy_wallet.plan_credits == 1
    assert legacy_wallet.purchased_credits == 2
    assert subscription.plan == legacy_subscription.plan
    assert subscription.expires_at.replace(
        tzinfo=timezone.utc
    ) == legacy_subscription.expires_at
    assert user.credits == 3


@pytest.mark.asyncio
async def test_reconciliation_marks_matched_data(db_session):
    user, workspace, legacy_subscription, now = await _billing_pair(
        db_session,
        "billing-reconcile-match@example.com",
    )
    db_session.add(
        WorkspaceCreditWallet(
            workspace_id=workspace.id,
            plan_credits=800,
            purchased_credits=20,
        )
    )
    db_session.add(
        WorkspaceSubscription(
            workspace_id=workspace.id,
            plan=legacy_subscription.plan,
            status="active",
            starts_at=legacy_subscription.starts_at,
            expires_at=legacy_subscription.expires_at,
            payer_user_id=user.id,
        )
    )
    await db_session.commit()

    report = await reconcile_personal_workspace_billing(
        db_session,
        now=now,
    )

    assert report["wallets"]["matched"] == 1
    assert report["wallets"]["mismatched"] == 0
    assert report["subscriptions"]["matched"] == 1
    assert report["subscriptions"]["mismatched"] == 0
    assert report["ledger"]["requires_attention"] is False


@pytest.mark.asyncio
async def test_reconciliation_detects_and_repairs_period_mismatch(
    db_session,
):
    user, workspace, _subscription, now = await _billing_pair(
        db_session,
        "billing-reconcile-period@example.com",
    )
    user.credit_period_start = now - timedelta(days=40)
    db_session.add(
        WorkspaceCreditWallet(
            workspace_id=workspace.id,
            plan_credits=800,
            purchased_credits=20,
            credit_period_start=now,
        )
    )
    await db_session.commit()

    detected = await reconcile_personal_workspace_billing(
        db_session,
        now=now,
    )
    assert detected["wallets"]["mismatched"] == 1

    repaired = await reconcile_personal_workspace_billing(
        db_session,
        repair=True,
        now=now,
    )

    assert repaired["wallets"]["repaired"] == 1
    assert user.credit_period_start.replace(
        tzinfo=timezone.utc
    ) == now


@pytest.mark.asyncio
async def test_reconciliation_ledger_reads_wallet_balances_not_transaction_tail(
    db_session,
):
    user, workspace, _subscription, now = await _billing_pair(
        db_session,
        "billing-reconcile-wallet-source@example.com",
    )
    db_session.add(
        WorkspaceCreditWallet(
            workspace_id=workspace.id,
            plan_credits=700,
            purchased_credits=10,
        )
    )
    db_session.add(
        CreditTransaction(
            user_id=user.id,
            workspace_id=workspace.id,
            actor_user_id=user.id,
            delta=-1,
            balance_after=999,
            feature="not-a-wallet-source",
        )
    )
    await db_session.commit()

    report = await reconcile_personal_workspace_billing(
        db_session,
        now=now,
    )

    assert report["ledger"]["legacy_plan_credits"] == 800
    assert report["ledger"]["legacy_purchased_credits"] == 20
    assert report["ledger"]["workspace_plan_credits"] == 700
    assert report["ledger"]["workspace_purchased_credits"] == 10
    assert report["ledger"]["plan_credit_delta"] == 100
    assert report["ledger"]["purchased_credit_delta"] == 10
    assert report["ledger"]["total_credit_delta"] == 110
    assert report["ledger"]["requires_attention"] is True


@pytest.mark.asyncio
async def test_reconciliation_ledger_keeps_all_user_workspace_assignments(
    db_session,
):
    """旧用户视角的全部流水也要覆盖同一用户在其他工作区执行的操作。"""
    user, workspace, _subscription, now = await _billing_pair(
        db_session,
        "billing-reconcile-team-ledger@example.com",
    )
    db_session.add(
        WorkspaceCreditWallet(
            workspace_id=workspace.id,
            plan_credits=800,
            purchased_credits=20,
        )
    )
    team_workspace = Workspace(
        name="团队工作区",
        slug="billing-reconcile-team",
        type="team",
        owner_user_id=user.id,
    )
    db_session.add(team_workspace)
    await db_session.flush()
    db_session.add(
        CreditTransaction(
            user_id=user.id,
            workspace_id=team_workspace.id,
            actor_user_id=user.id,
            delta=-7,
            balance_after=793,
            feature="team_workspace_deduction",
        )
    )
    await db_session.commit()

    report = await reconcile_personal_workspace_billing(
        db_session,
        now=now,
    )

    assert report["ledger"]["legacy_transaction_count"] == 1
    assert report["ledger"]["workspace_transaction_count"] == 1
    assert report["ledger"]["unassigned_transaction_count"] == 0
    assert report["ledger"]["legacy_delta"] == -7
    assert report["ledger"]["workspace_delta"] == -7
    assert report["ledger"]["unassigned_delta"] == 0
    assert report["ledger"]["requires_attention"] is False


@pytest.mark.asyncio
async def test_reconciliation_reports_ledger_totals_without_duplicate_counting(
    db_session,
):
    user, workspace, _subscription, now = await _billing_pair(
        db_session,
        "billing-reconcile-ledger@example.com",
    )
    db_session.add(
        WorkspaceCreditWallet(
            workspace_id=workspace.id,
            plan_credits=800,
            purchased_credits=20,
        )
    )
    db_session.add_all(
        [
            CreditTransaction(
                user_id=user.id,
                workspace_id=workspace.id,
                actor_user_id=user.id,
                delta=50,
                balance_after=870,
                feature="assigned_purchase",
                wallet_type="purchased",
            ),
            CreditTransaction(
                user_id=user.id,
                workspace_id=None,
                actor_user_id=user.id,
                delta=-20,
                balance_after=850,
                feature="legacy_deduction",
                wallet_type="plan",
            ),
        ]
    )
    await db_session.commit()

    report = await reconcile_personal_workspace_billing(
        db_session,
        now=now,
    )

    assert report["ledger"]["legacy_transaction_count"] == 2
    assert report["ledger"]["workspace_transaction_count"] == 1
    assert report["ledger"]["unassigned_transaction_count"] == 1
    assert report["ledger"]["legacy_delta"] == 30
    assert report["ledger"]["workspace_delta"] == 50
    assert report["ledger"]["unassigned_delta"] == -20
    assert report["ledger"]["legacy_plan_credits"] == 800
    assert report["ledger"]["legacy_purchased_credits"] == 20
    assert report["ledger"]["workspace_plan_credits"] == 800
    assert report["ledger"]["workspace_purchased_credits"] == 20
    assert report["ledger"]["plan_credit_delta"] == 0
    assert report["ledger"]["purchased_credit_delta"] == 0
    assert report["ledger"]["requires_attention"] is True


@pytest.mark.asyncio
async def test_reconciliation_records_wallet_case_only_when_requested(
    db_session,
):
    _user, workspace, _subscription, now = await _billing_pair(
        db_session,
        "billing-reconcile-case@example.com",
    )
    db_session.add(
        WorkspaceCreditWallet(
            workspace_id=workspace.id,
            plan_credits=1,
            purchased_credits=2,
        )
    )
    await db_session.commit()

    report_only = await reconcile_personal_workspace_billing(
        db_session,
        now=now,
    )
    recorded = await reconcile_personal_workspace_billing(
        db_session,
        record_cases=True,
        now=now,
    )
    repeated = await reconcile_personal_workspace_billing(
        db_session,
        record_cases=True,
        now=now,
    )

    assert report_only["cases"]["created"] == 0
    assert recorded["cases"]["created"] == 1
    assert recorded["cases"]["reused"] == 0
    assert repeated["cases"]["created"] == 0
    assert repeated["cases"]["reused"] == 1


@pytest.mark.asyncio
async def test_open_reconciliation_case_blocks_personal_credit_spending(
    db_session,
):
    user, workspace, _subscription, now = await _billing_pair(
        db_session,
        "billing-reconcile-stop-payment@example.com",
    )
    db_session.add(
        WorkspaceCreditWallet(
            workspace_id=workspace.id,
            plan_credits=1,
            purchased_credits=2,
        )
    )
    await db_session.commit()
    await reconcile_personal_workspace_billing(
        db_session,
        record_cases=True,
        now=now,
    )

    with pytest.raises(ValueError, match="账务差异待人工修复"):
        await user.deduct_credits(
            db_session,
            5,
            feature="blocked_spend",
        )

    await db_session.refresh(user)
    assert user.credits == 820


@pytest.mark.asyncio
async def test_approved_repair_only_changes_target_workspace_and_unblocks(
    db_session,
):
    first_user, first_workspace, _first_subscription, now = await _billing_pair(
        db_session,
        "billing-reconcile-approve-first@example.com",
    )
    second_user, second_workspace, _second_subscription, _now2 = (
        await _billing_pair(
            db_session,
            "billing-reconcile-approve-second@example.com",
        )
    )
    db_session.add_all(
        [
            WorkspaceCreditWallet(
                workspace_id=first_workspace.id,
                plan_credits=10,
                purchased_credits=2,
            ),
            WorkspaceCreditWallet(
                workspace_id=second_workspace.id,
                plan_credits=3,
                purchased_credits=4,
            ),
        ]
    )
    await db_session.commit()
    await reconcile_personal_workspace_billing(
        db_session,
        record_cases=True,
        now=now,
    )
    first_case = (
        await db_session.execute(
            select(BillingReconciliationCase).where(
                BillingReconciliationCase.workspace_id == first_workspace.id,
                BillingReconciliationCase.status == "open",
            )
        )
    ).scalar_one()

    result = await billing_reconciliation.approve_billing_reconciliation_case(
        db_session,
        case_id=first_case.id,
        approved_by_user_id=first_user.id,
        note="核对后按用户账本修复",
        now=now,
    )
    await db_session.flush()

    first_wallet = await db_session.get(
        WorkspaceCreditWallet,
        first_workspace.id,
    )
    second_wallet = await db_session.get(
        WorkspaceCreditWallet,
        second_workspace.id,
    )
    await db_session.refresh(first_case)
    repaired_plan_credits = first_wallet.plan_credits
    repaired_purchased_credits = first_wallet.purchased_credits
    remaining = await first_user.deduct_credits(
        db_session,
        5,
        feature="after_repair_spend",
    )
    with pytest.raises(ValueError, match="账务差异待人工修复"):
        await second_user.deduct_credits(
            db_session,
            5,
            feature="still_blocked_spend",
        )

    assert result["repaired"] is True
    assert first_case.status == "resolved"
    assert first_case.approved_by_user_id == first_user.id
    assert repaired_plan_credits == 10
    assert repaired_purchased_credits == 2
    assert second_wallet.plan_credits == 3
    assert second_wallet.purchased_credits == 4
    assert remaining == 7


@pytest.mark.asyncio
async def test_admin_reconciliation_case_api_lists_and_approves_once(
    client,
    db_session,
):
    user, workspace, _subscription, now = await _billing_pair(
        db_session,
        "billing-reconcile-admin-api@example.com",
    )
    admin = User(
        email="billing-reconcile-admin@example.com",
        username="billing-reconcile-admin",
        password_hash="not-used",
        plan="free",
    )
    db_session.add_all(
        [
            WorkspaceCreditWallet(
                workspace_id=workspace.id,
                plan_credits=1,
                purchased_credits=2,
            ),
            admin,
        ]
    )
    await db_session.commit()
    await reconcile_personal_workspace_billing(
        db_session,
        record_cases=True,
        now=now,
    )

    app.dependency_overrides[require_admin] = lambda: admin
    try:
        listed = await client.get(
            "/api/v1/billing/admin/reconciliation/cases?status=open"
        )
        assert listed.status_code == 200, listed.text
        item = listed.json()["items"][0]
        case_id = item["id"]
        assert item["workspace_id"] == str(workspace.id)
        assert item["snapshot"]["legacy"]["plan_credits"] == 800

        approved = await client.post(
            f"/api/v1/billing/admin/reconciliation/cases/{case_id}/approve",
            json={"note": "核对钱包后批准"},
        )
        repeated = await client.post(
            f"/api/v1/billing/admin/reconciliation/cases/{case_id}/approve",
            json={"note": "重复提交"},
        )
        open_cases = await client.get(
            "/api/v1/billing/admin/reconciliation/cases?status=open"
        )
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert approved.status_code == 200, approved.text
    assert approved.json()["result"]["repaired"] is True
    assert approved.json()["result"]["case"]["status"] == "resolved"
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["result"]["already_resolved"] is True
    assert open_cases.json()["items"] == []


@pytest.mark.asyncio
async def test_blocked_credit_deduction_api_returns_locked(
    client,
    db_session,
):
    user, workspace, _subscription, now = await _billing_pair(
        db_session,
        "billing-reconcile-locked-api@example.com",
    )
    db_session.add(
        WorkspaceCreditWallet(
            workspace_id=workspace.id,
            plan_credits=1,
            purchased_credits=2,
        )
    )
    await db_session.commit()
    await reconcile_personal_workspace_billing(
        db_session,
        record_cases=True,
        now=now,
    )

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        response = await client.post(
            "/api/v1/users/credits/deduct",
            json={"amount": 5},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 423, response.text
    assert "账务差异待人工修复" in response.json()["detail"]


@pytest.mark.asyncio
async def test_open_reconciliation_case_does_not_block_credit_grants(
    db_session,
):
    user, workspace, _subscription, now = await _billing_pair(
        db_session,
        "billing-reconcile-grant@example.com",
    )
    db_session.add(
        WorkspaceCreditWallet(
            workspace_id=workspace.id,
            plan_credits=1,
            purchased_credits=2,
        )
    )
    await db_session.commit()
    await reconcile_personal_workspace_billing(
        db_session,
        record_cases=True,
        now=now,
    )

    total = await add_purchased_credits(
        db_session,
        user,
        10,
        feature="manual_bonus",
        reference_type="manual",
        reference_id="bonus-during-block",
    )
    mirrored_wallet = await db_session.get(
        WorkspaceCreditWallet,
        workspace.id,
    )

    assert total == 13
    assert user.credits == 13
    assert mirrored_wallet.plan_credits == 1
    assert mirrored_wallet.purchased_credits == 12


@pytest.mark.asyncio
async def test_approval_resolves_case_without_repair_when_balances_match(
    db_session,
):
    user, workspace, _subscription, now = await _billing_pair(
        db_session,
        "billing-reconcile-approve-match@example.com",
    )
    workspace_wallet = WorkspaceCreditWallet(
        workspace_id=workspace.id,
        plan_credits=1,
        purchased_credits=2,
    )
    db_session.add(workspace_wallet)
    await db_session.commit()
    await reconcile_personal_workspace_billing(
        db_session,
        record_cases=True,
        now=now,
    )
    case = (
        await db_session.execute(
            select(BillingReconciliationCase).where(
                BillingReconciliationCase.workspace_id == workspace.id,
                BillingReconciliationCase.status == "open",
            )
        )
    ).scalar_one()
    workspace_wallet.plan_credits = 800
    workspace_wallet.purchased_credits = 20
    await db_session.flush()

    result = await billing_reconciliation.approve_billing_reconciliation_case(
        db_session,
        case_id=case.id,
        approved_by_user_id=user.id,
        note="同步任务已修复，确认结案",
        now=now,
    )

    assert result["repaired"] is False
    assert result["case"]["status"] == "resolved"


@pytest.mark.asyncio
async def test_approval_rebuilds_missing_legacy_wallet_from_workspace(
    db_session,
):
    user = User(
        email="billing-reconcile-missing-legacy@example.com",
        username="billing-reconcile-missing-legacy",
        password_hash="not-used",
        plan="standard",
        credits=3,
    )
    db_session.add(user)
    await db_session.flush()
    workspace = await ensure_personal_workspace(db_session, user)
    workspace_wallet = WorkspaceCreditWallet(
        workspace_id=workspace.id,
        plan_credits=1,
        purchased_credits=2,
    )
    db_session.add(workspace_wallet)
    await db_session.commit()
    await reconcile_personal_workspace_billing(
        db_session,
        record_cases=True,
    )
    case = (
        await db_session.execute(
            select(BillingReconciliationCase).where(
                BillingReconciliationCase.workspace_id == workspace.id,
                BillingReconciliationCase.status == "open",
            )
        )
    ).scalar_one()

    result = await billing_reconciliation.approve_billing_reconciliation_case(
        db_session,
        case_id=case.id,
        approved_by_user_id=user.id,
        note="按工作区权威余额重建旧镜像",
    )

    await db_session.refresh(workspace_wallet)
    await db_session.refresh(case)
    legacy_wallet = await db_session.get(CreditWallet, user.id)
    assert workspace_wallet.plan_credits == 1
    assert workspace_wallet.purchased_credits == 2
    assert legacy_wallet.plan_credits == 1
    assert legacy_wallet.purchased_credits == 2
    assert user.credits == 3
    assert case.status == "resolved"
    assert result["repaired"] is True
