"""图片/视频生成动作适配器测试。"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.action_runtime import ActionExecution
from app.services.media_action_adapter import MediaGenerationActionAdapter


class FakeMediaAdapter(MediaGenerationActionAdapter):
    def __init__(self):
        super().__init__(None, user_id=uuid4())
        self.task_id = uuid4()
        self.submitted = None
        self.status = "pending"

    async def _submit_image(self, user, input_data, idempotency_key):
        self.submitted = (input_data, idempotency_key)
        return SimpleNamespace(
            id=self.task_id,
            status=self.status,
            mode="free_creation",
            quality_tier="standard",
            credits_cost=8,
        )

    async def _load_user(self):
        return SimpleNamespace(id=self.user_id, credits=999)

    async def _submit_video(self, user, input_data, idempotency_key):
        self.submitted = (input_data, idempotency_key)
        return SimpleNamespace(
            id=self.task_id,
            status=self.status,
            quality_tier="draft",
            credits_per_second=15,
        )

    async def _task_status(self, action_id, task_id):
        return {
            "status": self.status,
            "user_id": str(self.user_id),
            "task_id": str(task_id),
        }


@pytest.mark.asyncio
async def test_image_generation_action_submits_and_verifies_pending_task():
    adapter = FakeMediaAdapter()
    input_data = {
        "prompt": "白色背景商品图",
        "num_outputs": 1,
        "mode": "free_creation",
        "quality_tier": "standard",
    }

    snapshot = await adapter.preflight(
        action_id="media.generate_image",
        target_id="new",
        input_data=input_data,
    )
    execution = await adapter.execute(
        action_id="media.generate_image",
        target_id="new",
        input_data=input_data,
        idempotency_key="image-action-1",
    )
    verification = await adapter.verify(
        action_id="media.generate_image",
        target_id="new",
        execution=execution,
    )

    assert snapshot["media_type"] == "image"
    assert execution.external_id == str(adapter.task_id)
    assert execution.output["credits_cost"] == 8
    assert adapter.submitted[1] == "image-action-1"
    assert verification.matched is True
    assert verification.snapshot["status"] == "pending"


@pytest.mark.asyncio
async def test_video_generation_requires_source_asset():
    adapter = FakeMediaAdapter()
    with pytest.raises(ValueError, match="首帧"):
        await adapter.preflight(
            action_id="media.generate_video",
            target_id="new",
            input_data={"prompt": "镜头推进"},
        )


@pytest.mark.asyncio
async def test_media_verification_rejects_foreign_task():
    class ForeignAdapter(FakeMediaAdapter):
        async def _task_status(self, action_id, task_id):
            return {
                "status": "pending",
                "user_id": str(uuid4()),
                "task_id": str(task_id),
            }

    adapter = ForeignAdapter()
    execution = ActionExecution(external_id=str(adapter.task_id))

    verification = await adapter.verify(
        action_id="media.generate_image",
        target_id="new",
        execution=execution,
    )
    assert verification.matched is False
