"""营销活动与文案的跨工作区隔离测试。"""

import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.image_asset import ImageAsset
from app.models.marketing_campaign import MarketingCampaign
from app.models.marketing_copy import MarketingCopyAsset
from app.models.marketing_video import MarketingVideoProject
from app.models.product import Product
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import provider_config
from app.services.workspaces import ensure_personal_workspace


async def _workspace_pair(db_session):
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    personal = await ensure_personal_workspace(db_session, user)
    team = Workspace(
        name="Marketing Scope Team",
        slug="marketing-scope-team",
        type="team",
        owner_user_id=user.id,
        status="active",
    )
    db_session.add(team)
    await db_session.flush()
    db_session.add(
        WorkspaceMember(
            workspace_id=team.id,
            user_id=user.id,
            role="owner",
            status="active",
        )
    )
    await db_session.flush()
    return user, personal, team


def _campaign(user_id, workspace_id, title: str) -> MarketingCampaign:
    return MarketingCampaign(
        user_id=user_id,
        workspace_id=workspace_id,
        title=title,
    )


def _marketing_video_project(
    user_id,
    workspace_id,
    title: str,
) -> MarketingVideoProject:
    return MarketingVideoProject(
        user_id=user_id,
        workspace_id=workspace_id,
        title=title,
        product_name=title,
        idea="show the product",
        platform="tiktok",
        market="US",
        language="en",
        duration=15,
        template_id="presenter_demo",
        mode="creative",
        quality_tier="draft",
        style_preset="premium_luxury",
        provider="minimax",
        credits_per_second=4,
        model="MiniMax-H3-Lite",
        resolution="480P",
        status="brief_ready",
        brief_json="{}",
        continuity_json="{}",
    )


@pytest.mark.asyncio
async def test_marketing_campaign_rejects_other_workspace(
    client,
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    campaign = _campaign(user.id, team.id, "team campaign")
    db_session.add(campaign)
    await db_session.commit()

    response = await client.get(
        f"/api/v1/marketing-campaigns/{campaign.id}",
        headers={
            **auth_headers,
            "X-Workspace-Id": str(personal.id),
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_marketing_campaign_list_is_scoped(
    client,
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    db_session.add_all(
        [
            _campaign(user.id, personal.id, "personal campaign"),
            _campaign(user.id, team.id, "team campaign"),
        ]
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/marketing-campaigns",
        headers={
            **auth_headers,
            "X-Workspace-Id": str(team.id),
        },
    )

    assert response.status_code == 200
    assert [item["title"] for item in response.json()["items"]] == [
        "team campaign"
    ]


@pytest.mark.asyncio
async def test_marketing_copy_rejects_other_workspace_campaign(
    client,
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    campaign = _campaign(user.id, team.id, "team campaign")
    db_session.add(campaign)
    await db_session.flush()
    asset = MarketingCopyAsset(
        batch_id=campaign.id,
        user_id=user.id,
        workspace_id=team.id,
        campaign_id=campaign.id,
        platform="tiktok",
        variant_key="A",
        language="en",
        headline="Team headline",
        body="Team body",
        cta="Shop now",
    )
    db_session.add(asset)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/marketing-campaigns/{campaign.id}/copy/{asset.id}",
        json={"headline": "Changed"},
        headers={
            **auth_headers,
            "X-Workspace-Id": str(personal.id),
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_marketing_campaign_rejects_product_from_other_workspace(
    client,
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    product = Product(
        user_id=user.id,
        workspace_id=team.id,
        title="Team product",
        url="https://example.com/team-product",
    )
    db_session.add(product)
    await db_session.commit()

    response = await client.post(
        "/api/v1/marketing-campaigns",
        json={
            "title": "Cross workspace campaign",
            "product_id": str(product.id),
        },
        headers={
            **auth_headers,
            "X-Workspace-Id": str(personal.id),
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_marketing_video_project_list_and_detail_are_workspace_scoped(
    client,
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    personal_project = _marketing_video_project(
        user.id,
        personal.id,
        "personal video",
    )
    team_project = _marketing_video_project(
        user.id,
        team.id,
        "team video",
    )
    db_session.add_all([personal_project, team_project])
    await db_session.commit()

    listed = await client.get(
        "/api/v1/marketing-videos/projects",
        headers={
            **auth_headers,
            "X-Workspace-Id": str(team.id),
        },
    )
    hidden = await client.get(
        f"/api/v1/marketing-videos/projects/{team_project.id}",
        headers={
            **auth_headers,
            "X-Workspace-Id": str(personal.id),
        },
    )

    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [str(team_project.id)]
    assert hidden.status_code == 404


@pytest.mark.asyncio
async def test_create_marketing_video_project_records_workspace(
    client,
    auth_headers,
    db_session,
    monkeypatch,
):
    user, _personal, team = await _workspace_pair(db_session)
    user.plan = "professional"
    user.credits = 50
    asset = ImageAsset(
        user_id=user.id,
        workspace_id=team.id,
        name="team product",
        kind="upload",
        storage_key=f"{uuid.uuid4()}.png",
        content_type="image/png",
        width=800,
        height=800,
        file_size=128,
    )
    db_session.add(asset)
    await db_session.flush()
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    provider_config.clear_cache()

    async def fake_plan(**kwargs):
        return {
            "title": "Team marketing video",
            "audience": "US buyers",
            "angle": "easy to use",
            "hook": "A faster routine",
            "script": "Show the product in use",
            "cta": "Shop now",
            "shots": [
                {
                    "position": 1,
                    "title": "Hook",
                    "purpose": "hook",
                    "prompt": "product hero shot",
                    "duration": 5,
                },
                {
                    "position": 2,
                    "title": "Demo",
                    "purpose": "demo",
                    "prompt": "presenter uses product",
                    "duration": 5,
                },
                {
                    "position": 3,
                    "title": "CTA",
                    "purpose": "cta",
                    "prompt": "clean product end frame",
                    "duration": 5,
                },
            ],
        }

    monkeypatch.setattr(
        "app.routers.marketing_videos.generate_marketing_plan",
        fake_plan,
    )

    response = await client.post(
        "/api/v1/marketing-videos/projects",
        json={
            "source_asset_id": str(asset.id),
            "idea": "show a faster routine",
            "product_name": "Team Product",
        },
        headers={
            **auth_headers,
            "X-Workspace-Id": str(team.id),
        },
    )

    assert response.status_code == 201, response.text
    project = await db_session.get(
        MarketingVideoProject,
        uuid.UUID(response.json()["id"]),
    )
    assert project is not None
    assert project.workspace_id == team.id


@pytest.mark.asyncio
async def test_create_marketing_video_rejects_other_workspace_asset(
    client,
    auth_headers,
    db_session,
    monkeypatch,
):
    user, personal, team = await _workspace_pair(db_session)
    user.plan = "professional"
    user.credits = 50
    asset = ImageAsset(
        user_id=user.id,
        workspace_id=team.id,
        name="team product",
        kind="upload",
        storage_key=f"{uuid.uuid4()}.png",
        content_type="image/png",
        width=800,
        height=800,
        file_size=128,
    )
    db_session.add(asset)
    monkeypatch.setattr(settings, "MINIMAX_API_KEY", "video-key")
    provider_config.clear_cache()
    await db_session.commit()

    response = await client.post(
        "/api/v1/marketing-videos/projects",
        json={
            "source_asset_id": str(asset.id),
            "idea": "show the product",
            "product_name": "Team Product",
        },
        headers={
            **auth_headers,
            "X-Workspace-Id": str(personal.id),
        },
    )

    assert response.status_code == 404
