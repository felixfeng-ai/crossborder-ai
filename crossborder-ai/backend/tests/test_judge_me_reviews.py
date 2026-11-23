"""Judge.me 评价同步、公开回复与回读核验测试。"""

import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.core.crypto import encrypt_value
from app.models.agent_work import WorkItem
from app.models.action_run import ActionRun
from app.models.customer_channel import (
    CustomerChannel,
    CustomerMessage,
    CustomerThread,
    ReplyDraft,
)
from app.models.user import User
from app.services.ai.agent_orchestrator import AgentOrchestrator
from app.services.judge_me_review_service import (
    JudgeMeHTTPClient,
    JudgeMeReview,
    JudgeMeReviewActionAdapter,
    JudgeMeReplyReceipt,
    normalize_judge_me_credentials,
    sync_judge_me_reviews,
)
from app.services.workspaces import ensure_personal_workspace
from app.services.work_items import create_work_items_from_agent_result


class FakeJudgeMeClient:
    def __init__(self, reviews=None):
        self.reviews = reviews or []
        self.replies = []
        self.remote_reply = None
        self.read_calls = 0

    async def fetch_reviews(self, *, credentials, limit=50):
        assert credentials["shop_domain"] == "demo.myshopify.com"
        return self.reviews

    async def create_public_reply(
        self,
        *,
        credentials,
        review_id,
        body_text,
        send_reply_email,
        idempotency_key,
    ):
        self.replies.append(
            {
                "review_id": review_id,
                "body_text": body_text,
                "send_reply_email": send_reply_email,
                "idempotency_key": idempotency_key,
            }
        )
        self.remote_reply = body_text
        return JudgeMeReplyReceipt(
            accepted=True,
            external_id=f"judge-me-reply-{len(self.replies)}",
            response={"message": "ok"},
        )

    async def read_review(self, *, credentials, review_id):
        self.read_calls += 1
        if self.remote_reply is None:
            return {"id": int(review_id)}
        return {
            "id": int(review_id),
            "reply": {"content": self.remote_reply},
        }


async def _workspace_with_channel(db_session, email: str):
    user = User(
        email=email,
        username=email.split("@", 1)[0],
        password_hash="not-used",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    workspace = await ensure_personal_workspace(db_session, user)
    channel = CustomerChannel(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        provider="judge_me",
        external_account_id="demo.myshopify.com",
        display_name="Judge.me 评价",
        credentials_ciphertext=encrypt_value(
            json.dumps(
                {
                    "api_token": "private-token",
                    "shop_domain": "demo.myshopify.com",
                }
            )
        ),
        status="active",
    )
    db_session.add(channel)
    await db_session.commit()
    await db_session.refresh(channel)
    return user, workspace, channel


@pytest.mark.asyncio
async def test_sync_judge_me_creates_low_rating_work_item_and_deduplicates(
    db_session,
):
    _user, workspace, channel = await _workspace_with_channel(
        db_session,
        "judge-sync@example.com",
    )
    client = FakeJudgeMeClient(
        reviews=[
            JudgeMeReview(
                review_id="101",
                body="The parcel arrived damaged.",
                rating=2,
                reviewer_name="Buyer A",
                reviewer_email="buyer-a@example.com",
                review_title="Damaged item",
                product_external_id="9001",
                product_title="Travel Mug",
            ),
            JudgeMeReview(
                review_id="102",
                body="Excellent quality.",
                rating=5,
                reviewer_name="Buyer B",
                reviewer_email="buyer-b@example.com",
                review_title="Great",
                product_external_id="9001",
                product_title="Travel Mug",
            ),
        ]
    )

    first = await sync_judge_me_reviews(
        db_session,
        channel=channel,
        client=client,
    )
    await db_session.commit()
    second = await sync_judge_me_reviews(
        db_session,
        channel=channel,
        client=client,
    )
    await db_session.commit()

    assert first == {
        "messages_scanned": 2,
        "messages_created": 2,
        "duplicates_skipped": 0,
        "work_items_created": 1,
    }
    assert second["duplicates_skipped"] == 2
    assert second["work_items_created"] == 0

    threads = (
        await db_session.execute(
            select(CustomerThread).where(
                CustomerThread.workspace_id == workspace.id
            )
        )
    ).scalars().all()
    assert len(threads) == 2
    low_rating = next(
        thread
        for thread in threads
        if thread.external_thread_id == "judge-me-review:101"
    )
    assert low_rating.thread_type == "review"
    assert low_rating.status == "waiting_user"
    assert low_rating.priority == "high"
    assert low_rating.related_product_id == "9001"
    assert low_rating.customer_address_ciphertext != "buyer-a@example.com"

    items = (
        await db_session.execute(
            select(WorkItem).where(WorkItem.workspace_id == workspace.id)
        )
    ).scalars().all()
    assert len(items) == 1
    assert items[0].kind == "review_reply"
    assert items[0].requires_action == "input"
    assert "2 星评价" in items[0].title

    messages = (
        await db_session.execute(
            select(CustomerMessage).where(
                CustomerMessage.workspace_id == workspace.id
            )
        )
    ).scalars().all()
    assert len(messages) == 2
    assert {item.external_message_id for item in messages} == {
        "judge-me-review-message:101",
        "judge-me-review-message:102",
    }


@pytest.mark.asyncio
async def test_judge_me_public_reply_is_idempotent_and_read_back(db_session):
    user, workspace, channel = await _workspace_with_channel(
        db_session,
        "judge-reply@example.com",
    )
    thread = CustomerThread(
        workspace_id=workspace.id,
        channel_id=channel.id,
        external_thread_id="judge-me-review:201",
        thread_type="review",
        customer_ref="Buyer",
        related_product_id="9002",
        subject="Packaging issue",
        language="en",
        status="waiting_user",
    )
    db_session.add(thread)
    await db_session.flush()
    draft = ReplyDraft(
        workspace_id=workspace.id,
        thread_id=thread.id,
        version=1,
        language="en",
        body_text="We are sorry about the packaging issue and will review it.",
        risk_level="medium",
        status="ready",
    )
    db_session.add(draft)
    await db_session.commit()
    client = FakeJudgeMeClient()
    adapter = JudgeMeReviewActionAdapter(
        db_session,
        workspace_id=workspace.id,
        user_id=user.id,
        client=client,
    )
    input_data = {
        "channel_id": str(channel.id),
        "thread_id": str(thread.id),
        "draft_id": str(draft.id),
        "send_reply_email": False,
    }

    execution = await adapter.execute(
        action_id="reviews.reply",
        target_id=str(thread.id),
        input_data=input_data,
        idempotency_key="judge-reply-1",
    )
    verification = await adapter.verify(
        action_id="reviews.reply",
        target_id=str(thread.id),
        execution=execution,
    )
    replay = await adapter.execute(
        action_id="reviews.reply",
        target_id=str(thread.id),
        input_data=input_data,
        idempotency_key="judge-reply-1",
    )

    assert len(client.replies) == 1
    assert client.replies[0]["review_id"] == "201"
    assert client.replies[0]["send_reply_email"] is False
    assert replay.output["replayed"] is True
    assert verification.matched is True
    assert verification.details["verification_level"] == "external_readback"
    await db_session.refresh(thread)
    await db_session.refresh(draft)
    assert thread.status == "resolved"
    assert draft.status == "sent"


@pytest.mark.asyncio
async def test_agent_prepares_review_reply_and_plans_confirmable_action(db_session):
    user, workspace, channel = await _workspace_with_channel(
        db_session,
        "judge-agent-prepare@example.com",
    )
    thread = CustomerThread(
        workspace_id=workspace.id,
        channel_id=channel.id,
        external_thread_id="judge-me-review:203",
        thread_type="review",
        customer_ref="Buyer",
        related_product_id="9003",
        subject="Broken zipper",
        language="en",
        status="waiting_user",
    )
    db_session.add(thread)
    await db_session.commit()
    orchestrator = AgentOrchestrator(
        user,
        db_session,
        workspace_id=workspace.id,
    )

    result = await orchestrator._execute_step(
        "prepare_review_reply",
        {
            "thread_id": str(thread.id),
            "reply_text": "We are sorry about the zipper and will review the issue.",
            "send_reply_email": False,
        },
    )
    agent_task_id = uuid4()
    items = await create_work_items_from_agent_result(
        db_session,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        agent_task_id=agent_task_id,
        result={"steps": [result]},
    )
    await db_session.commit()

    assert result["status"] == "success"
    assert result["data"]["requires_confirmation"] is True
    assert len(items) == 1
    assert items[0].status == "waiting_user"
    assert items[0].requires_action == "confirm"
    run = (
        await db_session.execute(
            select(ActionRun).where(
                ActionRun.work_item_id == items[0].id
            )
        )
    ).scalar_one()
    assert run.action_id == "reviews.reply"
    assert run.target_id == str(thread.id)
    run_input = json.loads(run.input_json)
    assert run_input["review_id"] == "203"
    assert run_input["body_text"].startswith("We are sorry")


@pytest.mark.asyncio
async def test_judge_me_reply_verification_marks_api_acceptance_without_claiming_readback(
    db_session,
):
    user, workspace, channel = await _workspace_with_channel(
        db_session,
        "judge-accepted@example.com",
    )
    thread = CustomerThread(
        workspace_id=workspace.id,
        channel_id=channel.id,
        external_thread_id="judge-me-review:202",
        thread_type="review",
        language="en",
        status="waiting_user",
    )
    db_session.add(thread)
    await db_session.flush()
    draft = ReplyDraft(
        workspace_id=workspace.id,
        thread_id=thread.id,
        version=1,
        language="en",
        body_text="Thank you for your feedback.",
        risk_level="medium",
        status="ready",
    )
    db_session.add(draft)
    await db_session.commit()
    client = FakeJudgeMeClient()
    client.remote_reply = None

    async def read_without_reply(*, credentials, review_id):
        client.read_calls += 1
        return {"id": int(review_id)}

    client.read_review = read_without_reply
    adapter = JudgeMeReviewActionAdapter(
        db_session,
        workspace_id=workspace.id,
        user_id=user.id,
        client=client,
    )
    execution = await adapter.execute(
        action_id="reviews.reply",
        target_id=str(thread.id),
        input_data={
            "channel_id": str(channel.id),
            "thread_id": str(thread.id),
            "draft_id": str(draft.id),
        },
        idempotency_key="judge-reply-accepted",
    )
    verification = await adapter.verify(
        action_id="reviews.reply",
        target_id=str(thread.id),
        execution=execution,
    )

    assert verification.matched is True
    assert verification.details["verification_level"] == "api_accepted"
    assert verification.details["external_readback_supported"] is False


@pytest.mark.asyncio
async def test_judge_me_http_client_uses_private_header_and_exact_payload():
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["token"] = request.headers.get("X-Api-Token")
        seen["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"id": 77})

    client = JudgeMeHTTPClient(transport=httpx.MockTransport(handler))
    receipt = await client.create_public_reply(
        credentials={
            "api_token": "private-token",
            "shop_domain": "demo.myshopify.com",
        },
        review_id="123",
        body_text="Thank you for your feedback.",
        send_reply_email=False,
        idempotency_key="http-reply-1",
    )

    assert receipt.external_id == "77"
    assert seen["method"] == "POST"
    assert "shop_domain=demo.myshopify.com" in seen["url"]
    assert seen["token"] == "private-token"
    assert seen["payload"] == {
        "review_id": 123,
        "send_reply_email": False,
        "reply": {"content": "Thank you for your feedback."},
    }


def test_judge_me_credentials_reject_public_or_incomplete_values():
    with pytest.raises(ValueError, match="令牌"):
        normalize_judge_me_credentials(
            {"shop_domain": "demo.myshopify.com"}
        )
    with pytest.raises(ValueError, match="myshopify"):
        normalize_judge_me_credentials(
            {"api_token": "token", "shop_domain": "example.com"}
        )
