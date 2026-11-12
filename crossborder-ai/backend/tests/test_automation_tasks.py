"""调度任务遵守用户自动化开关的测试。"""

import uuid

import pytest
from sqlalchemy import select

from app.models.automation_preference import (
    AutomationPreference,
    AutomationTaskState,
)
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User
from app.services.automation_settings import effective_automation_enabled
from app.services.automation_tasks import (
    run_scheduled_operations_monitors,
    run_scheduled_store_checks,
)


async def _user_with_product(db_session, label: str, *, plan="professional"):
    user = User(
        email=f"{label}-{uuid.uuid4().hex[:8]}@test.com",
        username=label,
        password_hash="x",
        plan=plan,
    )
    db_session.add(user)
    await db_session.flush()
    product = Product(
        user_id=user.id,
        url=f"https://detail.1688.com/offer/{uuid.uuid4().hex}.html",
        title=f"{label} product",
    )
    db_session.add(product)
    await db_session.flush()
    db_session.add(
        ProductVariant(
            user_id=user.id,
            product_id=product.id,
            sku=f"{label.upper()}-SKU",
            price=20,
            cost_price=8,
            stock_quantity=5,
            is_active=True,
        )
    )
    await db_session.commit()
    return user.id


def test_effective_automation_requires_paid_plan():
    class Preference:
        daily_store_check = True

    class User:
        plan = "free"

    assert (
        effective_automation_enabled(
            User(),
            Preference(),
            "store_check",
        )
        is False
    )


@pytest.mark.asyncio
async def test_scheduled_store_checks_skip_disabled_and_record_state(
    db_session,
    monkeypatch,
):
    enabled_user_id = await _user_with_product(db_session, "store-enabled")
    disabled_user_id = await _user_with_product(db_session, "store-disabled")
    db_session.add(
        AutomationPreference(
            user_id=disabled_user_id,
            daily_store_check=False,
        )
    )
    await db_session.commit()
    called: list[uuid.UUID] = []

    async def fake_run_store_check(db, user):
        called.append(user.id)
        return {"status": "ok"}

    monkeypatch.setattr(
        "app.services.automation_tasks.run_store_check",
        fake_run_store_check,
    )

    result = await run_scheduled_store_checks(db_session)

    assert called == [enabled_user_id]
    assert result == {"scanned": 2, "succeeded": 1, "failed": 0, "skipped": 1}
    state = (
        await db_session.execute(
            select(AutomationTaskState).where(
                AutomationTaskState.user_id == enabled_user_id,
                AutomationTaskState.task == "store_check",
            )
        )
    ).scalar_one()
    assert state.status == "success"


@pytest.mark.asyncio
async def test_scheduled_operations_monitor_skips_disabled(
    db_session,
    monkeypatch,
):
    enabled_user_id = await _user_with_product(db_session, "monitor-enabled")
    disabled_user_id = await _user_with_product(db_session, "monitor-disabled")
    db_session.add(
        AutomationPreference(
            user_id=disabled_user_id,
            daily_operations_monitor=False,
        )
    )
    await db_session.commit()
    called: list[uuid.UUID] = []

    async def fake_run_monitor_scan(db, user):
        called.append(user.id)
        return {"sku_count": 1}

    monkeypatch.setattr(
        "app.services.automation_tasks.run_monitor_scan",
        fake_run_monitor_scan,
    )

    result = await run_scheduled_operations_monitors(db_session)

    assert called == [enabled_user_id]
    assert result["skipped"] == 1
