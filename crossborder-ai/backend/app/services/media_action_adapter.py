"""图片与视频生成动作适配器。"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image_generation_task import ImageGenerationTask
from app.models.user import User
from app.models.video_generation_task import VideoGenerationTask
from app.services.action_runtime import ActionExecution, ActionVerification
from app.services.agent_capability_service import (
    create_product_video_task,
    schedule_product_image_task,
)


class MediaGenerationActionAdapter:
    """把媒体生成动作接到现有持久任务队列，不直接在动作线程生成媒体。"""

    def __init__(self, db: AsyncSession, *, user_id: UUID):
        self.db = db
        self.user_id = user_id

    async def preflight(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
    ) -> dict:
        if action_id not in {"media.generate_image", "media.generate_video"}:
            raise ValueError("适配器不支持该动作")
        if action_id == "media.generate_image":
            prompt = str(input_data.get("prompt") or "").strip()
            if len(prompt) < 5:
                raise ValueError("图片描述至少需要 5 个字符")
            return {
                "media_type": "image",
                "prompt": prompt,
                "estimated_credits": input_data.get("estimated_credits"),
            }
        if not str(input_data.get("source_asset_id") or "").strip():
            raise ValueError("视频生成需要商品首帧素材")
        return {
            "media_type": "video",
            "source_asset_id": str(input_data["source_asset_id"]),
            "duration": int(input_data.get("duration") or 4),
        }

    async def execute(
        self,
        *,
        action_id: str,
        target_id: str,
        input_data: dict,
        idempotency_key: str,
    ) -> ActionExecution:
        await self.preflight(
            action_id=action_id,
            target_id=target_id,
            input_data=input_data,
        )
        user = await self._load_user()
        if action_id == "media.generate_image":
            task = await self._submit_image(
                user,
                input_data,
                idempotency_key,
            )
            return ActionExecution(
                external_id=str(task.id),
                output={
                    "media_type": "image",
                    "task_status": task.status,
                    "mode": task.mode,
                    "quality_tier": task.quality_tier,
                    "credits_cost": task.credits_cost,
                },
            )
        task = await self._submit_video(
            user,
            input_data,
            idempotency_key,
        )
        return ActionExecution(
            external_id=str(task.id),
            output={
                "media_type": "video",
                "task_status": task.status,
                "quality_tier": task.quality_tier,
                "credits_per_second": task.credits_per_second,
            },
        )

    async def _load_user(self):
        user = await self.db.get(User, self.user_id)
        if user is None:
            raise ValueError("用户不存在")
        return user

    async def _submit_image(self, user, input_data: dict, idempotency_key: str):
        return await schedule_product_image_task(
            self.db,
            user,
            prompt=str(input_data.get("prompt") or "").strip(),
            num_outputs=int(input_data.get("num_outputs") or 1),
            mode=str(input_data.get("mode") or "free_creation"),
            quality_tier=input_data.get("quality_tier"),
            aspect_ratio=str(input_data.get("aspect_ratio") or "1:1"),
            negative_prompt=str(input_data.get("negative_prompt") or ""),
            style_preset=input_data.get("style_preset"),
            use_brand_persona=input_data.get("use_brand_persona"),
            provider=str(input_data.get("provider") or "auto"),
            reference_asset_ids=input_data.get("reference_asset_ids") or [],
            idempotency_key=idempotency_key,
        )

    async def _submit_video(self, user, input_data: dict, idempotency_key: str):
        # 视频队列以 source_asset_id 和模板参数做业务幂等，动作键由 ActionRun 保存。
        return await create_product_video_task(
            self.db,
            user,
            source_asset_id=str(input_data["source_asset_id"]),
            prompt=str(input_data.get("prompt") or ""),
            template_id=str(input_data.get("template_id") or "clean_product"),
            quality_tier=str(input_data.get("quality_tier") or "draft"),
            style_preset=str(input_data.get("style_preset") or "commerce_showcase"),
            duration=int(input_data.get("duration") or 4),
            ratio=str(input_data.get("ratio") or "9:16"),
            reserve_credits=0,
        )

    async def _task_status(
        self,
        action_id: str,
        task_id: UUID,
    ) -> dict:
        model = (
            ImageGenerationTask
            if action_id == "media.generate_image"
            else VideoGenerationTask
        )
        task = await self.db.get(model, task_id)
        if task is None:
            return {}
        return {
            "status": task.status,
            "user_id": str(task.user_id),
            "task_id": str(task.id),
        }

    async def verify(
        self,
        *,
        action_id: str,
        target_id: str,
        execution: ActionExecution,
    ) -> ActionVerification:
        if not execution.external_id:
            return ActionVerification(
                matched=False,
                details={"error": "缺少媒体任务编号"},
            )
        try:
            task_id = UUID(execution.external_id)
        except ValueError:
            return ActionVerification(
                matched=False,
                details={"error": "媒体任务编号无效"},
            )
        snapshot = await self._task_status(action_id, task_id)
        matched = (
            bool(snapshot)
            and snapshot.get("user_id") == str(self.user_id)
            and snapshot.get("task_id") == str(task_id)
            and snapshot.get("status") != "failed"
        )
        return ActionVerification(
            matched=matched,
            snapshot=snapshot,
            details={
                "media_type": (
                    "image"
                    if action_id == "media.generate_image"
                    else "video"
                ),
                "mismatches": [] if matched else ["task_owner_or_id"],
            },
            terminal=snapshot.get("status")
            in {"completed", "succeeded", "failed", "canceled"},
        )
