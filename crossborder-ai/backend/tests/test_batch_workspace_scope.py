"""批量任务上传、列表与处理的工作区隔离测试。"""

import pytest
from sqlalchemy import select

from app.models.batch_job import BatchJob
from app.models.product import Product
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services.workspaces import ensure_personal_workspace


async def _workspace_pair(db_session):
    user = (
        await db_session.execute(
            select(User).where(User.email == "test@example.com")
        )
    ).scalar_one()
    personal = await ensure_personal_workspace(db_session, user)
    team = Workspace(
        name="Batch Team",
        slug="batch-team",
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


@pytest.mark.asyncio
async def test_batch_upload_records_workspace_and_list_is_scoped(
    client,
    auth_headers,
    db_session,
):
    _user, personal, team = await _workspace_pair(db_session)
    team_headers = {
        **auth_headers,
        "X-Workspace-Id": str(team.id),
    }

    uploaded = await client.post(
        "/api/v1/batch/upload",
        files={
            "file": (
                "team-products.csv",
                "title,url,price\nTeam product,https://example.com/team,12.5\n",
                "text/csv",
            )
        },
        headers=team_headers,
    )
    assert uploaded.status_code == 200, uploaded.text
    job = (
        await db_session.execute(
            select(BatchJob).where(BatchJob.user_id == _user.id)
        )
    ).scalar_one()
    assert job.workspace_id == team.id

    team_list = await client.get(
        "/api/v1/batch/jobs",
        headers=team_headers,
    )
    personal_list = await client.get(
        "/api/v1/batch/jobs",
        headers={
            **auth_headers,
            "X-Workspace-Id": str(personal.id),
        },
    )

    assert [item["id"] for item in team_list.json()["items"]] == [
        str(job.id)
    ]
    assert personal_list.json()["items"] == []


@pytest.mark.asyncio
async def test_batch_job_rejects_other_workspace_and_product_uses_job_workspace(
    client,
    auth_headers,
    db_session,
):
    user, personal, team = await _workspace_pair(db_session)
    job = BatchJob(
        user_id=user.id,
        workspace_id=team.id,
        source_type="csv",
        source_filename="team.csv",
        row_index=1,
        title="Team batch product",
        url="https://example.com/team-batch-product",
        price="19.9",
        status="pending",
    )
    db_session.add(job)
    await db_session.commit()

    hidden = await client.post(
        f"/api/v1/batch/process/{job.id}",
        headers={
            **auth_headers,
            "X-Workspace-Id": str(personal.id),
        },
    )
    processed = await client.post(
        f"/api/v1/batch/process/{job.id}",
        headers={
            **auth_headers,
            "X-Workspace-Id": str(team.id),
        },
    )

    assert hidden.status_code == 404
    assert processed.status_code == 200, processed.text
    await db_session.refresh(job)
    product = await db_session.get(Product, job.product_id)
    assert product is not None
    assert product.workspace_id == team.id
