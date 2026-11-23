"""VeyaShip - 定时任务跨进程锁测试

背景：生产是 uvicorn 4 worker，每个 worker 各跑一份 APScheduler。
若不加锁，整店巡检（写 StoreCheckLog）会在 4 个 worker 各执行一遍。

覆盖：
1. SQLite 开发模式（单进程）下 _run_with_lock 直接执行 job
2. 两个写数据 job 的包装方法确实带正确的锁 key
"""

import pytest


@pytest.mark.asyncio
async def test_run_with_lock_sqlite_executes_job():
    """SQLite 模式单进程，无需锁，job 正常执行。"""
    from app.services.scheduler import SchedulerService

    svc = SchedulerService()
    calls = []

    async def fake_job():
        calls.append(1)

    await svc._run_with_lock("test_key", fake_job)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_run_with_lock_no_op_job_runs():
    """job 抛异常前正常执行，锁包层不吞错误。"""
    from app.services.scheduler import SchedulerService

    svc = SchedulerService()

    async def returns_value():
        return "done"

    # 不应抛异常（SQLite 路径直接透传）
    await svc._run_with_lock("test_key2", returns_value)


@pytest.mark.asyncio
async def test_locked_wrappers_use_correct_lock_key(monkeypatch):
    """写数据 job 的包装方法都经过 _run_with_lock，且锁 key 唯一。

    注：订阅过期任务已在 scheduler 重构中随 Subscription 模型移除，
    当前写数据包装为「定时整店巡检」与「Agent 任务分发」两个。
    """
    from app.services.scheduler import SchedulerService

    svc = SchedulerService()
    captured = []

    async def fake_lock(lock_key, job):
        captured.append(lock_key)

    monkeypatch.setattr(svc, "_run_with_lock", fake_lock)

    await svc._run_store_checks_locked()
    await svc._dispatch_agent_tasks()

    assert captured == ["store_check_daily", "dispatch_agent_tasks"]
    # 两个 job 用不同的锁 key，互不阻塞
    assert len(set(captured)) == 2


@pytest.mark.asyncio
async def test_billing_reconciliation_uses_dedicated_lock(monkeypatch):
    """账务对账必须经过独立跨进程锁，避免多 Worker 重复扫描。"""
    from app.services.scheduler import SchedulerService

    svc = SchedulerService()
    captured = []

    async def fake_lock(lock_key, job):
        captured.append(lock_key)

    monkeypatch.setattr(svc, "_run_with_lock", fake_lock)
    await svc._reconcile_workspace_billing_locked()

    assert captured == ["reconcile_workspace_billing"]


@pytest.mark.asyncio
async def test_billing_observation_uses_dedicated_lock(monkeypatch):
    """每日账务观察必须独立加锁，避免多 Worker 重复写同一天快照。"""
    from app.services.scheduler import SchedulerService

    svc = SchedulerService()
    captured = []

    async def fake_lock(lock_key, job):
        captured.append(lock_key)

    monkeypatch.setattr(svc, "_run_with_lock", fake_lock)
    await svc._record_billing_observation_locked()

    assert captured == ["record_billing_observation"]


@pytest.mark.asyncio
async def test_billing_observation_skips_when_disabled(monkeypatch):
    import app.services.scheduler as scheduler_module
    from app.services.scheduler import SchedulerService

    monkeypatch.setattr(
        scheduler_module.settings,
        "BILLING_OBSERVATION_ENABLED",
        False,
    )

    def unexpected_session():
        raise AssertionError("disabled observation must not open DB")

    monkeypatch.setattr(
        scheduler_module,
        "async_session_factory",
        unexpected_session,
    )

    await SchedulerService()._record_billing_observation()


@pytest.mark.asyncio
async def test_billing_observation_alerts_and_raises_on_bad_file(
    tmp_path,
    monkeypatch,
):
    import app.services.scheduler as scheduler_module
    from app.core import observability
    from app.services.scheduler import SchedulerService

    monkeypatch.setattr(
        scheduler_module.settings,
        "BILLING_OBSERVATION_ENABLED",
        True,
    )
    monkeypatch.setattr(
        scheduler_module.settings,
        "BILLING_OBSERVATION_DIR",
        str(tmp_path),
    )
    (tmp_path / "observation-bad.json").write_text(
        "{broken",
        encoding="utf-8",
    )
    alerts = []
    monkeypatch.setattr(
        observability,
        "emit_alert",
        lambda message, *, context: alerts.append((message, context)),
    )

    with pytest.raises(ValueError, match="observation-bad.json"):
        await SchedulerService()._record_billing_observation()

    assert alerts
    assert alerts[0][0] == "首个账期账务观察执行失败"


@pytest.mark.asyncio
async def test_billing_observation_alerts_when_snapshot_fails(
    tmp_path,
    monkeypatch,
):
    import app.services.scheduler as scheduler_module
    from app.core import observability
    from app.services import billing_observation
    from app.services.scheduler import SchedulerService

    class FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    async def fake_collect(*args, **kwargs):
        return {
            "status": "failed",
            "observed_at": "2026-11-20T08:00:00+00:00",
            "issues": [{"code": "wallet_mismatch", "message": "差异"}],
            "snapshot": {"counts": {"open_billing_cases": 1}},
        }

    monkeypatch.setattr(
        scheduler_module.settings,
        "BILLING_OBSERVATION_ENABLED",
        True,
    )
    monkeypatch.setattr(
        scheduler_module.settings,
        "BILLING_OBSERVATION_DIR",
        str(tmp_path),
    )
    monkeypatch.setattr(
        scheduler_module,
        "async_session_factory",
        lambda: FakeSession(),
    )
    monkeypatch.setattr(
        billing_observation,
        "read_observation_files",
        lambda _directory: [],
    )
    monkeypatch.setattr(
        billing_observation,
        "collect_billing_observation",
        fake_collect,
    )
    monkeypatch.setattr(
        billing_observation,
        "persist_billing_observation",
        lambda _directory, _observation: {
            "path": tmp_path / "observation.json",
            "history": {"consecutive_passed_days": 0},
        },
    )
    alerts = []
    monkeypatch.setattr(
        observability,
        "emit_alert",
        lambda message, *, context: alerts.append((message, context)),
    )

    await SchedulerService()._record_billing_observation()

    assert alerts[0][0] == "首个账期账务观察失败"
    assert alerts[0][1]["issues"][0]["code"] == "wallet_mismatch"


@pytest.mark.asyncio
async def test_workspace_purge_uses_dedicated_lock(monkeypatch):
    """归档工作区清理必须使用独立锁，避免重复物理删除。"""
    from app.services.scheduler import SchedulerService

    svc = SchedulerService()
    captured = []

    async def fake_lock(lock_key, job):
        captured.append(lock_key)

    monkeypatch.setattr(svc, "_run_with_lock", fake_lock)
    await svc._purge_archived_workspaces_locked()

    assert captured == ["purge_archived_workspaces"]


@pytest.mark.asyncio
async def test_customer_reply_enqueue_uses_dedicated_lock(monkeypatch):
    from app.services.scheduler import SchedulerService

    svc = SchedulerService()
    captured = []

    async def fake_lock(lock_key, job):
        captured.append(lock_key)

    monkeypatch.setattr(svc, "_run_with_lock", fake_lock)
    await svc._enqueue_customer_reply_tasks()

    assert captured == ["enqueue_customer_reply_tasks"]


@pytest.mark.asyncio
async def test_scheduler_registers_customer_reply_enqueue_job():
    from app.services.scheduler import SchedulerService

    service = SchedulerService()
    job_ids = []

    class FakeScheduler:
        running = False

        def add_job(self, func, trigger, *, id, replace_existing):
            job_ids.append(id)

        def start(self):
            self.running = True

    service.scheduler = FakeScheduler()
    await service.start()

    assert "enqueue_customer_reply_tasks" in job_ids


@pytest.mark.asyncio
async def test_scheduler_registers_daily_billing_observation_job():
    from app.services.scheduler import SchedulerService

    service = SchedulerService()
    job_ids = []

    class FakeScheduler:
        running = False

        def add_job(self, func, trigger, *, id, replace_existing):
            job_ids.append(id)

        def start(self):
            self.running = True

    service.scheduler = FakeScheduler()
    await service.start()

    assert "record_billing_observation_daily" in job_ids


@pytest.mark.asyncio
async def test_billing_reconciliation_alerts_on_unassigned_ledger(monkeypatch):
    """钱包和订阅一致时，未归属流水仍必须触发账务告警。"""
    import app.services.scheduler as scheduler_module
    from app.core import observability
    from app.services import workspace_billing_reconciliation
    from app.services.scheduler import SchedulerService

    class FakeDb:
        async def commit(self):
            return None

    class FakeSession:
        async def __aenter__(self):
            return FakeDb()

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    reconciliation_calls = []

    async def fake_reconcile(_db, **kwargs):
        reconciliation_calls.append(kwargs)
        return {
            "wallets": {"mismatched": 0},
            "subscriptions": {"mismatched": 0},
            "ledger": {
                "requires_attention": True,
                "unassigned_transaction_count": 3,
                "unassigned_delta": -12,
                "plan_credit_delta": 0,
                "purchased_credit_delta": 0,
                "total_credit_delta": 0,
            },
            "summary": {
                "wallet_mismatches": 0,
                "subscription_mismatches": 0,
                "workspace_count": 1,
            },
        }

    alerts = []
    monkeypatch.setattr(
        scheduler_module,
        "async_session_factory",
        lambda: FakeSession(),
    )
    monkeypatch.setattr(
        workspace_billing_reconciliation,
        "reconcile_personal_workspace_billing",
        fake_reconcile,
    )
    monkeypatch.setattr(
        observability,
        "emit_alert",
        lambda message, *, context: alerts.append((message, context)),
    )

    await SchedulerService()._reconcile_workspace_billing()

    assert len(alerts) == 1
    assert alerts[0][1]["unassigned_transaction_count"] == 3
    assert alerts[0][1]["unassigned_delta"] == -12
    assert reconciliation_calls == [{"record_cases": True}]
