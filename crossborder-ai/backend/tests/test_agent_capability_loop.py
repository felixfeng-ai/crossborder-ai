"""AI Agent 与平台能力的闭环测试。"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.image_asset import ImageAsset
from app.models.image_generation_task import ImageGenerationTask
from app.models.listing_draft import ListingDraft
from app.models.marketing_video import MarketingVideoProject, MarketingVideoShot
from app.models.product import Product
from app.models.user import User
from app.models.video_generation_task import VideoGenerationTask
from app.services import agent_capability_service, provider_config
from app.services.ai.agent_orchestrator import AgentOrchestrator
from app.services.ai.deepseek import DeepSeekService
from app.services.listing_service import persist_generated_listing
from app.services.minimax_video import estimate_video_credits


async def _make_user(
    db_session,
    *,
    email: str,
    plan: str = "professional",
    credits: int = 200,
) -> User:
    user = User(
        email=email,
        username=email.split("@")[0],
        password_hash="x",
        plan=plan,
        credits=credits,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_asset(db_session, user: User, tmp_path, monkeypatch) -> ImageAsset:
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(tmp_path))
    asset_id = uuid.uuid4()
    storage_key = f"{user.id}/{asset_id}.png"
    path = tmp_path / storage_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\nagent-capability-test")
    asset = ImageAsset(
        id=asset_id,
        user_id=user.id,
        name="商品首帧",
        kind="upload",
        storage_key=storage_key,
        content_type="image/png",
        width=800,
        height=800,
        file_size=path.stat().st_size,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(asset)
    await db_session.flush()
    return asset


def test_agent_tools_cover_creation_and_material_loop():
    """工具注册表必须能覆盖生成、回查、编辑和素材查询。"""
    names = {tool["function"]["name"] for tool in AgentOrchestrator.TOOLS}

    assert {
        "list_materials",
        "generate_product_image",
        "generate_product_video",
        "create_marketing_video_plan",
        "get_listing",
        "edit_listing",
        "sync_shopify_operations",
    } <= names


@pytest.mark.asyncio
async def test_agent_can_read_and_edit_owned_listing(db_session):
    user = await _make_user(db_session, email="agent-loop-listing@test.com")
    product = Product(
        user_id=user.id,
        url="https://detail.1688.com/offer/agent-loop.html",
        title="可编辑商品",
        price=29.9,
    )
    db_session.add(product)
    await db_session.flush()
    draft = await persist_generated_listing(
        db_session,
        user=user,
        product=product,
        platform="amazon",
        language="en",
        tone="professional",
        title="Original title",
        description="Original description",
        bullet_points=["Original bullet"],
        seo_title="Original SEO",
        seo_description="Original SEO description",
        violations=[],
        blocked=False,
        ai_model_used="test-model",
    )
    orchestrator = AgentOrchestrator(user=user, db=db_session)

    read_result = await orchestrator._execute_step(
        "get_listing",
        {"listing_id": str(draft.id)},
    )
    edit_result = await orchestrator._execute_step(
        "edit_listing",
        {
            "listing_id": str(draft.id),
            "title": "Edited title",
            "bullet_points": ["Edited bullet one", "Edited bullet two"],
        },
    )

    assert read_result["status"] == "success"
    assert read_result["data"]["title"] == "Original title"
    assert edit_result["status"] == "success"
    assert edit_result["data"]["version"] == 2
    assert edit_result["data"]["compliance_status"] == "unknown"
    assert edit_result["links"][0]["href"].endswith(
        f"/app/products/{product.id}?listing={draft.id}"
    )


@pytest.mark.asyncio
async def test_agent_material_list_is_user_scoped(db_session):
    owner = await _make_user(db_session, email="agent-loop-materials@test.com")
    other = await _make_user(db_session, email="agent-loop-other@test.com")
    owner_task = ImageGenerationTask(
        user_id=owner.id,
        prompt="owner image",
        num_outputs=1,
        status="completed",
        image_urls='["https://example.com/owner.png"]',
    )
    other_task = ImageGenerationTask(
        user_id=other.id,
        prompt="other image",
        num_outputs=1,
        status="completed",
        image_urls='["https://example.com/other.png"]',
    )
    owner_video = VideoGenerationTask(
        user_id=owner.id,
        provider="minimax",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        prompt="owner video",
        status="succeeded",
        storage_key="owner/video.mp4",
    )
    other_video = VideoGenerationTask(
        user_id=other.id,
        provider="minimax",
        model="MiniMax-H3-Lite",
        resolution="480P",
        duration=4,
        ratio="9:16",
        prompt="other video",
        status="succeeded",
        storage_key="other/video.mp4",
    )
    db_session.add_all([owner_task, other_task, owner_video, other_video])
    await db_session.flush()
    orchestrator = AgentOrchestrator(user=owner, db=db_session)

    result = await orchestrator._execute_step("list_materials", {})

    assert result["status"] == "success"
    assert result["data"]["counts"]["images"] == 1
    assert result["data"]["counts"]["product_videos"] == 1
    assert all("other" not in str(item) for item in result["data"]["items"])
    assert result["links"][0]["href"] == "/app/assets"


@pytest.mark.asyncio
async def test_material_list_handles_corrupt_image_json(db_session):
    user = await _make_user(db_session, email="agent-loop-corrupt-material@test.com")
    task = ImageGenerationTask(
        user_id=user.id,
        prompt="corrupt image task",
        num_outputs=1,
        status="completed",
        image_urls="{not-json",
    )
    db_session.add(task)
    await db_session.flush()

    result = await agent_capability_service.list_user_materials(
        db_session,
        user,
    )

    image_item = next(
        item for item in result["items"] if item["id"] == str(task.id)
    )
    assert image_item["urls"] == []


@pytest.mark.asyncio
async def test_image_asset_lookup_rejects_invalid_and_foreign_ids(
    db_session,
    tmp_path,
    monkeypatch,
):
    owner = await _make_user(db_session, email="agent-loop-asset-owner@test.com")
    other = await _make_user(db_session, email="agent-loop-asset-other@test.com")
    asset = await _make_asset(db_session, owner, tmp_path, monkeypatch)

    invalid = await agent_capability_service.get_owned_image_asset(
        db_session,
        owner.id,
        "not-a-uuid",
    )
    foreign = await agent_capability_service.get_owned_image_asset(
        db_session,
        other.id,
        str(asset.id),
    )

    assert invalid is None
    assert foreign is None


@pytest.mark.asyncio
async def test_agent_can_schedule_product_image_task(
    db_session,
    monkeypatch,
):
    user = await _make_user(db_session, email="agent-loop-image@test.com")
    monkeypatch.setattr(
        provider_config,
        "get",
        lambda provider, key, default="": "test-key" if provider == "aliyun" else default,
    )
    orchestrator = AgentOrchestrator(user=user, db=db_session)

    rejected = await orchestrator._execute_step(
        "generate_product_image",
        {"prompt": "white background product hero", "confirmed": False},
    )
    created = await orchestrator._execute_step(
        "generate_product_image",
        {"prompt": "white background product hero", "confirmed": True},
    )

    assert rejected["data"]["requires_confirmation"] is True
    assert created["status"] == "success"
    task = (
        await db_session.execute(
            select(ImageGenerationTask).where(
                ImageGenerationTask.id == uuid.UUID(created["data"]["task_id"])
            )
        )
    ).scalar_one()
    assert task.user_id == user.id
    assert task.status == "pending"
    assert created["links"][0]["href"] == "/app/images"


@pytest.mark.asyncio
async def test_agent_video_requires_confirmation_and_submits_after_confirmation(
    db_session,
    tmp_path,
    monkeypatch,
):
    user = await _make_user(db_session, email="agent-loop-video@test.com")
    asset = await _make_asset(db_session, user, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    provider_config.clear_cache()
    submitted: list[str] = []

    async def fake_submit(db, task):
        submitted.append(str(task.id))
        task.provider_task_id = "provider-agent-video"
        task.status = "running"
        await db.flush()
        return "provider-agent-video"

    monkeypatch.setattr(
        "app.services.video_task_executor.submit_video_task",
        fake_submit,
    )
    orchestrator = AgentOrchestrator(user=user, db=db_session)
    base_params = {
        "source_asset_id": str(asset.id),
        "prompt": "slow premium product camera movement",
        "template_id": "clean_product",
    }

    rejected = await orchestrator._execute_step(
        "generate_product_video",
        {**base_params, "confirmed": False},
    )
    created = await orchestrator._execute_step(
        "generate_product_video",
        {**base_params, "confirmed": True},
    )

    assert rejected["data"]["requires_confirmation"] is True
    assert created["status"] == "success"
    assert submitted == [created["data"]["task_id"]]
    task = (
        await db_session.execute(
            select(VideoGenerationTask).where(
                VideoGenerationTask.id == uuid.UUID(created["data"]["task_id"])
            )
        )
    ).scalar_one()
    assert task.provider_task_id == "provider-agent-video"
    assert task.provider == "minimax"
    await db_session.refresh(user)
    assert user.credits == 200 - task.credits_cost
    assert created["links"][0]["href"] == "/app/videos?tab=single"


@pytest.mark.asyncio
async def test_agent_video_reserves_credit_for_agent_task_settlement(
    db_session,
    tmp_path,
    monkeypatch,
):
    video_cost = estimate_video_credits("MiniMax-H3-Lite", "480P", 4)
    user = await _make_user(
        db_session,
        email="agent-loop-video-reserve@test.com",
        credits=video_cost,
    )
    asset = await _make_asset(db_session, user, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    provider_config.clear_cache()
    provider_called = False

    async def fake_submit(db, task):
        nonlocal provider_called
        provider_called = True
        return "should-not-run"

    monkeypatch.setattr(
        "app.services.video_task_executor.submit_video_task",
        fake_submit,
    )
    orchestrator = AgentOrchestrator(user=user, db=db_session)

    result = await orchestrator._execute_step(
        "generate_product_video",
        {
            "source_asset_id": str(asset.id),
            "prompt": "premium product movement",
            "confirmed": True,
        },
    )

    assert result["status"] == "failed"
    assert "预留" in result["error"] or "积分不足" in result["error"]
    assert provider_called is False


@pytest.mark.asyncio
async def test_agent_video_provider_failure_marks_task_failed_without_charging(
    db_session,
    tmp_path,
    monkeypatch,
):
    user = await _make_user(db_session, email="agent-loop-video-failed@test.com")
    asset = await _make_asset(db_session, user, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    provider_config.clear_cache()

    async def fake_submit(db, task):
        raise ValueError("供应商拒绝任务")

    monkeypatch.setattr(
        "app.services.video_task_executor.submit_video_task",
        fake_submit,
    )
    orchestrator = AgentOrchestrator(user=user, db=db_session)

    result = await orchestrator._execute_step(
        "generate_product_video",
        {
            "source_asset_id": str(asset.id),
            "prompt": "premium product movement",
            "confirmed": True,
        },
    )

    assert result["status"] == "failed"
    assert "供应商拒绝任务" in result["error"]
    task = (
        await db_session.execute(
            select(VideoGenerationTask).where(VideoGenerationTask.user_id == user.id)
        )
    ).scalar_one()
    assert task.status == "failed"
    await db_session.refresh(user)
    assert user.credits == 200


@pytest.mark.asyncio
async def test_agent_marketing_plan_creates_brief_without_rendering(
    db_session,
    tmp_path,
    monkeypatch,
):
    user = await _make_user(db_session, email="agent-loop-marketing@test.com")
    asset = await _make_asset(db_session, user, tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    provider_config.clear_cache()

    async def fake_plan(**kwargs):
        return {
            "title": "夏日收纳营销片",
            "audience": "美国小户型用户",
            "angle": "一物多用",
            "hook": "房间瞬间变整齐",
            "script": "展示收纳前后变化",
            "cta": "Discover more",
            "shots": [
                {
                    "position": 1,
                    "title": "收纳前",
                    "purpose": "hook",
                    "prompt": "Messy room before using the product",
                    "duration": 5,
                },
                {
                    "position": 2,
                    "title": "使用产品",
                    "purpose": "demo",
                    "prompt": "Presenter uses the product naturally",
                    "duration": 5,
                },
                {
                    "position": 3,
                    "title": "收纳后",
                    "purpose": "cta",
                    "prompt": "Clean room with product centered",
                    "duration": 5,
                },
            ],
        }

    monkeypatch.setattr(
        "app.services.agent_capability_service.generate_marketing_plan",
        fake_plan,
    )
    orchestrator = AgentOrchestrator(user=user, db=db_session)

    result = await orchestrator._execute_step(
        "create_marketing_video_plan",
        {
            "source_asset_id": str(asset.id),
            "product_name": "折叠收纳箱",
            "idea": "让美国小户型用户看到一物多用",
            "platform": "tiktok",
            "market": "US",
            "language": "en",
            "duration": 15,
            "template_id": "presenter_demo",
        },
    )

    assert result["status"] == "success"
    project = (
        await db_session.execute(
            select(MarketingVideoProject).where(
                MarketingVideoProject.id == uuid.UUID(result["data"]["project_id"])
            )
        )
    ).scalar_one()
    shots = (
        await db_session.execute(
            select(MarketingVideoShot).where(
                MarketingVideoShot.project_id == project.id
            )
        )
    ).scalars().all()
    tasks = (
        await db_session.execute(
            select(VideoGenerationTask).where(VideoGenerationTask.user_id == user.id)
        )
    ).scalars().all()
    assert project.status == "brief_ready"
    assert len(shots) == 3
    assert tasks == []
    assert result["links"][0]["href"].endswith(
        f"/app/videos?tab=marketing&project={project.id}"
    )


@pytest.mark.asyncio
async def test_agent_listing_generation_uses_full_facts_and_seo(
    db_session,
    monkeypatch,
):
    user = await _make_user(
        db_session,
        email="agent-loop-listing-seo@test.com",
        plan="standard",
    )
    product = Product(
        user_id=user.id,
        url="https://detail.1688.com/offer/agent-facts.html",
        title="Foldable storage box",
        description="Oversized foldable storage box with reinforced handles",
        price=36.5,
        shop_name="Yiwu Source Factory",
        sales_count=8800,
    )
    db_session.add(product)
    await db_session.flush()
    captured: dict[str, str] = {}

    async def fake_generate(self, system_prompt, user_prompt, **kwargs):
        if "title" in system_prompt.lower():
            return "Foldable Storage Box with Reinforced Handles"
        return "Generated content"

    async def fake_description(self, **kwargs):
        captured["description_features"] = kwargs.get("product_features", "")
        return "A durable foldable storage solution for small homes."

    async def fake_bullets(self, **kwargs):
        captured["bullet_features"] = kwargs.get("features", "")
        return ["Reinforced handles", "Folds flat", "Large capacity"]

    async def fake_seo(self, **kwargs):
        return {
            "seo_title": "Foldable Storage Box | Reinforced Handles",
            "seo_description": "Shop a foldable storage box with reinforced handles.",
        }

    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)
    monkeypatch.setattr(DeepSeekService, "generate_product_description", fake_description)
    monkeypatch.setattr(DeepSeekService, "generate_bullet_points", fake_bullets)
    monkeypatch.setattr(DeepSeekService, "optimize_seo", fake_seo)
    orchestrator = AgentOrchestrator(user=user, db=db_session)

    result = await orchestrator._execute_step(
        "generate_listing",
        {
            "product_id": str(product.id),
            "platform": "amazon",
            "language": "en",
        },
    )

    assert result["status"] == "success"
    assert "Oversized foldable storage box" in captured["description_features"]
    assert "Yiwu Source Factory" in captured["bullet_features"]
    assert "8800" in captured["bullet_features"]
    draft = (
        await db_session.execute(
            select(ListingDraft).where(
                ListingDraft.id == uuid.UUID(result["data"]["listing_id"])
            )
        )
    ).scalar_one()
    assert draft.seo_title
    assert draft.seo_description
    assert result["links"][0]["href"].startswith(f"/app/products/{product.id}?listing=")
