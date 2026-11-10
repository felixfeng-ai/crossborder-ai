"""Production gates that require a real PostgreSQL database."""

import asyncio
import os
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import models  # noqa: F401 - register all models
from app.core.database import Base
from app.models.agent_task import AgentTask
from app.models.image_generation_task import ImageGenerationTask
from app.models.listing_draft import ListingDraft
from app.models.product import Product
from app.models.user import InsufficientCreditsError, User
from app.services import scheduler as scheduler_module


POSTGRES_TEST_URL = os.environ.get("POSTGRES_TEST_URL", "")

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not POSTGRES_TEST_URL,
        reason="POSTGRES_TEST_URL is required for PostgreSQL gates",
    ),
]


@pytest_asyncio.fixture
async def pg_engine():
    engine = create_async_engine(POSTGRES_TEST_URL, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_postgres(pg_engine):
    table_names = [
        table.name
        for table in reversed(Base.metadata.sorted_tables)
        if table.name != "alembic_version"
    ]
    if table_names:
        quoted = ", ".join(f'"{name}"' for name in table_names)
        async with pg_engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE TABLE {quoted} CASCADE"))
    yield


@pytest.mark.asyncio
async def test_postgres_schema_uses_uuid_and_tenant_url_constraint(pg_engine):
    async with pg_engine.connect() as conn:
        product_columns = await conn.run_sync(
            lambda sync_conn: {
                col["name"]: col
                for col in sa.inspect(sync_conn).get_columns("products")
            }
        )
        listing_columns = await conn.run_sync(
            lambda sync_conn: {
                col["name"]: col
                for col in sa.inspect(sync_conn).get_columns("listing_drafts")
            }
        )
        unique_constraints = await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_unique_constraints("products")
        )

    assert isinstance(product_columns["id"]["type"], PG_UUID)
    assert isinstance(product_columns["user_id"]["type"], PG_UUID)
    assert isinstance(listing_columns["id"]["type"], PG_UUID)
    assert isinstance(listing_columns["user_id"]["type"], PG_UUID)
    assert isinstance(listing_columns["product_id"]["type"], PG_UUID)
    assert any(
        set(item.get("column_names") or []) == {"user_id", "url"}
        for item in unique_constraints
    )


@pytest.mark.asyncio
async def test_concurrent_credit_deduction_never_goes_negative(pg_engine):
    factory = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        user = User(
            email="pg-credit@test.com",
            username="pg-credit",
            password_hash="x",
            credits=1,
        )
        db.add(user)
        await db.commit()
        user_id = user.id

    ready = asyncio.Event()
    arrived = 0
    arrival_lock = asyncio.Lock()

    async def worker() -> bool:
        nonlocal arrived
        async with factory() as db:
            user = (
                await db.execute(sa.select(User).where(User.id == user_id))
            ).scalar_one()
            async with arrival_lock:
                arrived += 1
                if arrived == 2:
                    ready.set()
            await ready.wait()
            try:
                await user.deduct_credits(db, 1)
                await db.commit()
                return True
            except InsufficientCreditsError:
                await db.rollback()
                return False

    results = await asyncio.gather(worker(), worker())
    assert results.count(True) == 1
    assert results.count(False) == 1

    async with factory() as db:
        user = (
            await db.execute(sa.select(User).where(User.id == user_id))
        ).scalar_one()
        assert user.credits == 0


@pytest.mark.asyncio
async def test_scheduler_claim_is_not_duplicated_on_postgres(
    pg_engine,
    monkeypatch: pytest.MonkeyPatch,
):
    factory = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(scheduler_module, "async_session_factory", factory)

    async with factory() as db:
        user = User(
            email="pg-claim@test.com",
            username="pg-claim",
            password_hash="x",
            credits=30,
        )
        db.add(user)
        await db.flush()
        agent = AgentTask(
            user_id=user.id,
            task_type="agent_run",
            status="pending",
            input='{"instruction":"hi"}',
            cost=1,
        )
        image = ImageGenerationTask(
            user_id=user.id,
            prompt="pg image task",
            status="pending",
            num_outputs=1,
            image_urls="[]",
        )
        db.add_all([agent, image])
        await db.commit()

    scheduler = scheduler_module.SchedulerService()
    first_agents = await scheduler._claim_agent_tasks()
    first_images = await scheduler._claim_image_tasks()
    second_agents = await scheduler._claim_agent_tasks()
    second_images = await scheduler._claim_image_tasks()

    assert len(first_agents) == 1
    assert len(first_images) == 1
    assert second_agents == []
    assert second_images == []


@pytest.mark.asyncio
async def test_tenant_isolation_on_postgres(pg_engine):
    factory = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)
    shared_url = f"https://detail.1688.com/offer/pg-{uuid.uuid4().hex}.html"

    async with factory() as db:
        owner_a = User(email="pg-owner-a@test.com", username="a", password_hash="x")
        owner_b = User(email="pg-owner-b@test.com", username="b", password_hash="x")
        db.add_all([owner_a, owner_b])
        await db.flush()
        product_a = Product(user_id=owner_a.id, url=shared_url, title="A product")
        product_b = Product(user_id=owner_b.id, url=shared_url, title="B product")
        db.add_all([product_a, product_b])
        await db.flush()
        db.add_all([
            ListingDraft(
                user_id=owner_a.id,
                product_id=product_a.id,
                platform="amazon",
                title="A listing",
                content_hash="a" * 64,
                compliance_status="pass",
                compliance_violations="[]",
            ),
            ListingDraft(
                user_id=owner_b.id,
                product_id=product_b.id,
                platform="amazon",
                title="B listing",
                content_hash="b" * 64,
                compliance_status="pass",
                compliance_violations="[]",
            ),
        ])
        await db.commit()
        owner_a_id = owner_a.id

    async with factory() as db:
        products = (
            await db.execute(sa.select(Product).where(Product.user_id == owner_a_id))
        ).scalars().all()
        listings = (
            await db.execute(
                sa.select(ListingDraft).where(ListingDraft.user_id == owner_a_id)
            )
        ).scalars().all()

    assert [item.title for item in products] == ["A product"]
    assert [item.title for item in listings] == ["A listing"]
