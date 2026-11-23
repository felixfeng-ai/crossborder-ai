"""个人账务对账命令行安全边界测试。"""

import sys
from uuid import uuid4

import pytest

from scripts import reconcile_workspace_billing as script


def test_reconciliation_script_rejects_unapproved_repair(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["reconcile", "--repair"])

    with pytest.raises(SystemExit):
        script.parse_args()


def test_reconciliation_script_requires_case_and_admin_for_repair(
    monkeypatch,
):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "reconcile",
            "--case-id",
            "00000000-0000-0000-0000-000000000001",
            "--admin-email",
            "admin@veyaship.com",
            "--note",
            "核对后修复",
        ],
    )

    args = script.parse_args()

    assert str(args.case_id) == "00000000-0000-0000-0000-000000000001"
    assert args.admin_email == "admin@veyaship.com"
    assert args.note == "核对后修复"
    assert not hasattr(args, "repair")


class _FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDb:
    def __init__(self, admin=None):
        self.admin = admin
        self.commit_count = 0

    async def execute(self, _query):
        return _FakeResult(self.admin)

    async def commit(self):
        self.commit_count += 1


class _FakeSession:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc, traceback):
        return False


@pytest.mark.asyncio
async def test_reconciliation_script_defaults_to_read_only(
    monkeypatch,
    capsys,
):
    db = _FakeDb()
    calls = []

    async def fake_reconcile(_db, **kwargs):
        calls.append(kwargs)
        return {"wallets": {"mismatched": 0}}

    monkeypatch.setattr(sys, "argv", ["reconcile"])
    monkeypatch.setattr(script, "async_session_factory", lambda: _FakeSession(db))
    monkeypatch.setattr(script, "reconcile_personal_workspace_billing", fake_reconcile)

    await script.main()

    assert calls == [{"batch_size": 500, "record_cases": False}]
    assert db.commit_count == 0
    assert '"wallets"' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_reconciliation_script_commits_recorded_cases(monkeypatch):
    db = _FakeDb()

    async def fake_reconcile(_db, **kwargs):
        assert kwargs["record_cases"] is True
        return {"cases": {"created": 1}}

    monkeypatch.setattr(sys, "argv", ["reconcile", "--record-cases"])
    monkeypatch.setattr(script, "async_session_factory", lambda: _FakeSession(db))
    monkeypatch.setattr(script, "reconcile_personal_workspace_billing", fake_reconcile)

    await script.main()

    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_reconciliation_script_approves_case_as_configured_admin(
    monkeypatch,
):
    from app.models.user import User

    admin = User(
        id=uuid4(),
        email="admin@veyaship.com",
        username="admin",
        password_hash="not-used",
    )
    db = _FakeDb(admin=admin)
    calls = []

    async def fake_approve(_db, **kwargs):
        calls.append(kwargs)
        return {"case": {"status": "resolved"}}

    case_id = "00000000-0000-0000-0000-000000000001"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "reconcile",
            "--case-id",
            case_id,
            "--admin-email",
            admin.email,
            "--note",
            "审批通过",
        ],
    )
    monkeypatch.setattr(script.settings, "ADMIN_EMAILS", [admin.email])
    monkeypatch.setattr(script, "async_session_factory", lambda: _FakeSession(db))
    monkeypatch.setattr(
        script,
        "approve_billing_reconciliation_case",
        fake_approve,
    )

    await script.main()

    assert str(calls[0]["case_id"]) == case_id
    assert calls[0]["approved_by_user_id"] == admin.id
    assert calls[0]["note"] == "审批通过"
    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_reconciliation_script_rejects_non_admin_email(monkeypatch):
    from app.models.user import User

    user = User(
        id=uuid4(),
        email="operator@example.com",
        username="operator",
        password_hash="not-used",
    )
    db = _FakeDb(admin=user)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "reconcile",
            "--case-id",
            "00000000-0000-0000-0000-000000000001",
            "--admin-email",
            user.email,
        ],
    )
    monkeypatch.setattr(script.settings, "ADMIN_EMAILS", ["admin@veyaship.com"])
    monkeypatch.setattr(script, "async_session_factory", lambda: _FakeSession(db))

    with pytest.raises(SystemExit, match="没有账务修复权限"):
        await script.main()

    assert db.commit_count == 0
