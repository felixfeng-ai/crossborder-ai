"""Agent 受控动作运行时的核心行为测试。"""

from dataclasses import dataclass
from uuid import uuid4

import pytest

from app.models.agent_work import WorkItem
from app.models.user import User
from app.services.action_runtime import (
    ActionExecution,
    ActionRunStateError,
    ActionVerification,
    confirm_action_run,
    execute_action_run,
    get_action_run,
    plan_action_run,
    retry_action_run,
)
from app.services.action_dispatcher import dispatch_queued_action_runs
from app.services import action_dispatcher
from app.services.workspaces import ensure_personal_workspace


@dataclass
class FakeActionAdapter:
    """只用于验证运行时状态机的确定性适配器。"""

    matched: bool = True
    terminal: bool = True
    error: Exception | None = None
    execute_calls: int = 0

    async def preflight(self, *, action_id, target_id, input_data):
        return {
            "action_id": action_id,
            "target_id": target_id,
            "input": input_data,
        }

    async def execute(self, *, action_id, target_id, input_data, idempotency_key):
        self.execute_calls += 1
        if self.error is not None:
            raise self.error
        return ActionExecution(
            external_id=f"external-{action_id}",
            output={"target_id": target_id, "idempotency_key": idempotency_key},
        )

    async def verify(self, *, action_id, target_id, execution):
        return ActionVerification(
            matched=self.matched,
            snapshot={
                "target_id": target_id,
                "external_id": execution.external_id,
            },
            details={"reason": "verified" if self.matched else "state_mismatch"},
            terminal=self.terminal,
        )


async def _user_workspace_item(db_session, email: str) -> tuple[User, object, WorkItem]:
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    workspace = await ensure_personal_workspace(db_session, user)
    item = WorkItem(
        workspace_id=workspace.id,
        kind="listing_action",
        source="agent",
        title="发布新品",
        summary="准备执行受控动作",
        status="running",
        requires_action="none",
        current_step="准备执行",
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return user, workspace, item


@pytest.mark.asyncio
async def test_auto_action_executes_preflight_and_verification_once(db_session):
    user, workspace, item = await _user_workspace_item(
        db_session,
        "action-auto@example.com",
    )
    adapter = FakeActionAdapter()

    run = await plan_action_run(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        work_item_id=item.id,
        action_id="operations.scan",
        platform="internal",
        target_type="workspace",
        target_id=str(workspace.id),
        input_data={"scope": "today"},
        idempotency_key="action-auto-1",
    )
    await db_session.commit()

    assert run.status == "queued"
    completed = await execute_action_run(
        db_session,
        workspace_id=workspace.id,
        action_run_id=run.id,
        adapter=adapter,
    )
    first_finished_at = completed.finished_at
    await db_session.commit()
    await db_session.refresh(item)

    assert completed.status == "succeeded"
    assert completed.attempt == 1
    assert completed.external_id == "external-operations.scan"
    assert completed.before_snapshot_json is not None
    assert completed.after_snapshot_json is not None
    assert completed.verification_json is not None
    assert first_finished_at is not None
    assert item.status == "succeeded"
    assert item.current_step == "动作已完成并核验"
    assert adapter.execute_calls == 1

    replayed = await execute_action_run(
        db_session,
        workspace_id=workspace.id,
        action_run_id=run.id,
        adapter=adapter,
    )
    await db_session.commit()

    assert replayed.id == completed.id
    assert replayed.finished_at == first_finished_at
    assert adapter.execute_calls == 1


@pytest.mark.asyncio
async def test_confirmation_is_required_before_publish_executes(db_session):
    user, workspace, item = await _user_workspace_item(
        db_session,
        "action-confirm@example.com",
    )
    adapter = FakeActionAdapter()

    run = await plan_action_run(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        work_item_id=item.id,
        action_id="listings.publish",
        platform="shopify",
        target_type="product",
        target_id="product-1",
        input_data={"shopify_product_id": "gid://shopify/Product/1"},
        idempotency_key="action-confirm-1",
    )
    await db_session.commit()

    assert run.status == "awaiting_confirmation"
    with pytest.raises(ActionRunStateError):
        await execute_action_run(
            db_session,
            workspace_id=workspace.id,
            action_run_id=run.id,
            adapter=adapter,
        )

    confirmed = await confirm_action_run(
        db_session,
        workspace_id=workspace.id,
        action_run_id=run.id,
        actor_user_id=user.id,
    )
    await db_session.commit()
    assert confirmed.status == "queued"

    completed = await execute_action_run(
        db_session,
        workspace_id=workspace.id,
        action_run_id=run.id,
        adapter=adapter,
    )
    await db_session.commit()

    assert completed.status == "succeeded"
    assert adapter.execute_calls == 1


@pytest.mark.asyncio
async def test_action_plan_is_idempotent_and_workspace_scoped(db_session):
    user, workspace, item = await _user_workspace_item(
        db_session,
        "action-idempotent@example.com",
    )
    first = await plan_action_run(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        work_item_id=item.id,
        action_id="inventory.update",
        platform="shopify",
        target_type="inventory_item",
        target_id="inventory-1",
        input_data={"available": 9},
        idempotency_key="action-idempotent-1",
    )
    await db_session.commit()
    repeated = await plan_action_run(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        work_item_id=item.id,
        action_id="inventory.update",
        platform="shopify",
        target_type="inventory_item",
        target_id="inventory-1",
        input_data={"available": 9},
        idempotency_key="action-idempotent-1",
    )
    await db_session.commit()

    assert repeated.id == first.id
    assert await get_action_run(
        db_session,
        workspace_id=uuid4(),
        action_run_id=first.id,
    ) is None


@pytest.mark.asyncio
async def test_verification_mismatch_blocks_with_retry_action(db_session):
    user, workspace, item = await _user_workspace_item(
        db_session,
        "action-mismatch@example.com",
    )
    adapter = FakeActionAdapter(matched=False)
    run = await plan_action_run(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        work_item_id=item.id,
        action_id="orders.fulfill",
        platform="shopify",
        target_type="fulfillment_order",
        target_id="fulfillment-1",
        input_data={"tracking_number": "TRACK-1"},
        idempotency_key="action-mismatch-1",
        autonomy_level="auto",
    )
    await db_session.commit()

    completed = await execute_action_run(
        db_session,
        workspace_id=workspace.id,
        action_run_id=run.id,
        adapter=adapter,
    )
    await db_session.commit()
    await db_session.refresh(item)

    assert completed.status == "blocked"
    assert completed.error_code == "verification_mismatch"
    assert item.status == "waiting_user"
    assert item.requires_action == "retry"
    assert "回读" in item.current_step


@pytest.mark.asyncio
async def test_dispatcher_executes_resolved_queued_action(db_session, monkeypatch):
    user, workspace, item = await _user_workspace_item(
        db_session,
        "action-dispatcher@example.com",
    )
    adapter = FakeActionAdapter()
    run = await plan_action_run(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        work_item_id=item.id,
        action_id="listings.publish",
        platform="shopify",
        target_type="product",
        target_id="product-1",
        input_data={"product_id": "product-1"},
        idempotency_key="action-dispatcher-1",
        autonomy_level="auto",
    )
    await db_session.commit()

    async def fake_resolve(_db, _run):
        return adapter

    monkeypatch.setattr(
        action_dispatcher,
        "resolve_action_adapter",
        fake_resolve,
    )

    executed = await dispatch_queued_action_runs(db_session, limit=1)
    await db_session.refresh(run)

    assert executed == 1
    assert run.status == "succeeded"
    assert adapter.execute_calls == 1


@pytest.mark.asyncio
async def test_non_terminal_verification_waits_for_external_result(db_session):
    user, workspace, item = await _user_workspace_item(
        db_session,
        "action-pending-result@example.com",
    )
    adapter = FakeActionAdapter(terminal=False)
    run = await plan_action_run(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        work_item_id=item.id,
        action_id="media.generate_image",
        platform="internal",
        target_type="media_task",
        target_id="media-1",
        input_data={"prompt": "商品图"},
        idempotency_key="media-pending-result-1",
        autonomy_level="auto",
    )
    await db_session.commit()

    completed = await execute_action_run(
        db_session,
        workspace_id=workspace.id,
        action_run_id=run.id,
        adapter=adapter,
    )
    await db_session.commit()
    await db_session.refresh(item)

    assert completed.status == "verifying"
    assert item.status == "running"
    assert item.requires_action == "none"
    assert "等待结果" in item.current_step


@pytest.mark.asyncio
async def test_media_retry_uses_new_idempotency_key(db_session):
    user, workspace, item = await _user_workspace_item(
        db_session,
        "media-retry-key@example.com",
    )
    adapter = FakeActionAdapter(error=RuntimeError("provider failed"))
    run = await plan_action_run(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        work_item_id=item.id,
        action_id="media.generate_image",
        platform="internal",
        target_type="media_task",
        target_id="media-retry",
        input_data={"prompt": "商品图"},
        idempotency_key="media-retry-original",
        autonomy_level="auto",
    )
    await db_session.commit()

    with pytest.raises(RuntimeError):
        await execute_action_run(
            db_session,
            workspace_id=workspace.id,
            action_run_id=run.id,
            adapter=adapter,
        )
    await db_session.commit()
    await db_session.refresh(run)
    assert run.status == "retryable_failed"

    retried = await retry_action_run(
        db_session,
        workspace_id=workspace.id,
        action_run_id=run.id,
        actor_user_id=user.id,
    )
    await db_session.commit()

    assert retried.status == "queued"
    assert retried.idempotency_key.startswith("media-retry-original:retry:")
    assert retried.external_id is None
