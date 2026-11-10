"""VeyaShip - AI 图片生成路由

生产级设计：异步任务模式 + 任务落库（CAP-07）。
用户提交生成请求 → 立即返回 task_id → 调度器从数据库队列消费 →
前端轮询结果。任务不依赖当前进程存活。

接口契约：
- POST /api/v1/images/generate  → 建库记录（pending）+ 后台执行，返回 TaskResponse
- GET  /api/v1/images/status/{task_id} → 从库读任务状态（不存在返回 404 中文）
- GET  /api/v1/images/history        → 当前用户最近 N 条记录（画廊/仪表盘，顶层路径固定）
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.rate_limit import RateLimit
from app.dependencies import get_current_user
from app.models.user import User
from app.models.image_generation_task import ImageGenerationTask
from app.services.image_task_executor import (
    execute_image_generation_task,
    run_image_generation,
)
from app.services import provider_config
from app.services.ai.persona_kit import (
    fetch_persona,
    build_persona_kit,
    image_style_phrase,
    strip_banned_words,
)
from app.core.access_control import check_feature_access
from pydantic import BaseModel, Field

router = APIRouter(prefix="/images", tags=["AI 图片生成"])


class GenerateImageRequest(BaseModel):
    prompt: str = Field(..., min_length=5, description="图片描述词")
    num_outputs: int = Field(default=1, ge=1, le=4)


class TaskResponse(BaseModel):
    task_id: str
    status: str  # pending / processing / completed / failed
    image_urls: list[str] = []
    model_used: str = ""
    error: Optional[str] = None


class ImageHistoryItem(BaseModel):
    """画廊/仪表盘展示用的单条图片生成记录"""
    task_id: str
    prompt: str
    image_urls: list[str]
    model_used: str
    status: str
    created_at: str


def _parse_urls(raw: Optional[str]) -> list[str]:
    """把 DB 里 image_urls JSON 文本解析为列表（空/损坏返回 []）。"""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


async def _run_generation_impl(db: AsyncSession, task_id: str, prompt: str, num_outputs: int) -> None:
    """Backward-compatible wrapper around the durable executor."""
    await run_image_generation(db, task_id, prompt, num_outputs)


async def _run_generation(task_id: str, prompt: str, num_outputs: int, db: Optional[AsyncSession] = None) -> None:
    """执行图片生成并写库。

    传入 db 时（测试/同会话调用）用该会话；否则自建会话（生产后台任务跨请求生命周期）。
    """
    if db is not None:
        await _run_generation_impl(db, task_id, prompt, num_outputs)
        return
    async with async_session_factory() as session:
        await _run_generation_impl(session, task_id, prompt, num_outputs)


async def _execute_image_task(task_id: str, prompt: str, num_outputs: int) -> None:
    """Compatibility entrypoint for code that still calls the old helper."""
    from uuid import UUID
    try:
        tid = UUID(task_id)
    except ValueError:
        return
    await execute_image_generation_task(tid)


async def schedule_image_task(db: AsyncSession, user_id, prompt: str, num_outputs: int = 1) -> str:
    """建 pending 记录并后台调度生成；返回 task_id（供 POST /generate 与 content 主图复用）。"""
    task = ImageGenerationTask(
        user_id=user_id,
        prompt=prompt,
        num_outputs=num_outputs,
        status="pending",
        attempts=0,
        image_urls="[]",
        model_used="",
        error=None,
    )
    db.add(task)
    await db.flush()
    return str(task.id)


@router.post("/generate", response_model=TaskResponse)
async def generate_image(
    payload: GenerateImageRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    _ratelimit=Depends(RateLimit("ai_generate")),
    db: AsyncSession = Depends(get_db),
):
    """提交图片生成任务（异步落库，立即返回 task_id）

    前端通过 GET /api/v1/images/status/{task_id} 轮询结果。
    图片路径不做文案合规拦截；品牌禁词仅做描述级简单移除，附品牌视觉风格（CAP-04）。
    """
    if not check_feature_access(current_user, "ai_image"):
        raise HTTPException(status_code=403, detail="图片生成功能仅限专业版套餐使用，请升级套餐")

    aliyun_key = provider_config.get("aliyun", "api_key", settings.ALIYUN_DASHSCOPE_API_KEY or "")
    replicate_key = provider_config.get("replicate", "api_key", settings.REPLICATE_API_KEY or "")
    if not aliyun_key and not replicate_key:
        raise HTTPException(status_code=400, detail="图片生成功能暂未配置")

    # 拼接品牌调性：image_style 优先，否则 tone + style；补 brand identity；去品牌禁词
    persona = await fetch_persona(db, current_user.id)
    enhanced_prompt = payload.prompt
    if persona:
        kit = build_persona_kit(persona)
        enhanced_prompt = strip_banned_words(enhanced_prompt, kit.get("banned_words") or [])
        style_phrase = image_style_phrase(kit)
        if style_phrase:
            enhanced_prompt = f"{enhanced_prompt}, {style_phrase}"
        if kit.get("brand_name"):
            enhanced_prompt = f"{enhanced_prompt}, {kit['brand_name']} brand identity"

    task_id = await schedule_image_task(db, current_user.id, enhanced_prompt, payload.num_outputs)
    return TaskResponse(task_id=task_id, status="pending")


@router.get("/status/{task_id}", response_model=TaskResponse)
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询当前用户图片生成任务状态（从库读，不存在/非本人 → 404 中文）"""
    from uuid import UUID
    try:
        tid = UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 只允许本人读自己的任务：他人/匿名一律 404，不暴露任务是否存在（防跨用户读图）
    result = await db.execute(
        select(ImageGenerationTask).where(
            ImageGenerationTask.id == tid,
            ImageGenerationTask.user_id == current_user.id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return TaskResponse(
        task_id=str(task.id),
        status=task.status,
        image_urls=_parse_urls(task.image_urls),
        model_used=task.model_used or "",
        error=task.error,
    )


@router.get("/history", response_model=list[ImageHistoryItem])
async def list_history(
    limit: int = Query(20, ge=1, le=100, description="返回条数，默认 20"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户最近 N 条图片生成记录（时间倒序），供画廊/仪表盘展示"""
    result = await db.execute(
        select(ImageGenerationTask)
        .where(ImageGenerationTask.user_id == current_user.id)
        .order_by(desc(ImageGenerationTask.created_at), desc(ImageGenerationTask.id))
        .limit(limit)
    )
    tasks = result.scalars().all()
    return [
        ImageHistoryItem(
            task_id=str(t.id),
            prompt=t.prompt,
            image_urls=_parse_urls(t.image_urls),
            model_used=t.model_used or "",
            status=t.status,
            created_at=str(t.created_at),
        )
        for t in tasks
    ]
