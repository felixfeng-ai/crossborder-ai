"""用户资料、头像和账户相关 HTTP 路由。

VeyaShip - User Management Routes.

Credits query and deduction endpoints."""

from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.credit_transaction import CreditTransaction
from app.schemas.user import UserResponse
from app.services.credit_service import apply_monthly_allowance
from app.services.user_avatars import (
    avatar_path,
    delete_avatar_file,
    normalize_avatar_image,
    save_avatar_bytes,
)
from app.services.user_profiles import build_user_response
from app.services.workspace_billing_reconciliation import (
    BillingSpendingBlockedError,
)
from pydantic import BaseModel, Field

router = APIRouter(prefix="/users", tags=["Users"])


class DeductCreditsRequest(BaseModel):
    amount: int = Field(..., ge=1, description="扣减积分数")


@router.get("/me/avatar")
async def get_my_avatar(
    current_user: User = Depends(get_current_user),
):
    """头像只通过带登录态的文件响应读取，不暴露公共直链。"""

    if not current_user.avatar_storage_key:
        raise HTTPException(status_code=404, detail="尚未设置头像")
    try:
        target = avatar_path(current_user.avatar_storage_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="头像不存在") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="头像不存在")
    return FileResponse(
        target,
        media_type="image/webp",
        headers={"Cache-Control": "private, no-store"},
    )


@router.put("/me/avatar", response_model=UserResponse)
async def update_my_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传后统一裁成 512px WebP；旧文件只在数据库提交成功后删除。"""

    raw = await file.read(settings.MAX_IMAGE_UPLOAD_BYTES + 1)
    if len(raw) > settings.MAX_IMAGE_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="头像文件过大",
        )
    try:
        normalized = await run_in_threadpool(
            normalize_avatar_image,
            raw,
            max_bytes=settings.MAX_IMAGE_UPLOAD_BYTES,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    previous_key = current_user.avatar_storage_key
    next_key = await save_avatar_bytes(current_user.id, normalized)
    current_user.avatar_storage_key = next_key
    current_user.avatar_updated_at = datetime.now(timezone.utc)
    try:
        await db.commit()
        await db.refresh(current_user)
    except Exception:
        await delete_avatar_file(next_key)
        raise
    await delete_avatar_file(previous_key)
    return build_user_response(current_user)


@router.delete("/me/avatar", status_code=status.HTTP_204_NO_CONTENT)
async def remove_my_avatar(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    previous_key = current_user.avatar_storage_key
    current_user.avatar_storage_key = None
    current_user.avatar_updated_at = None
    await db.commit()
    await delete_avatar_file(previous_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/credits")
async def get_credits(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current user's credit balance."""
    applied = await apply_monthly_allowance(db, current_user)
    if applied is not None:
        await db.commit()
        await db.refresh(current_user)
    return {
        "credits": current_user.credits,
    }


@router.get("/credits/transactions")
async def list_credit_transactions(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回当前用户的积分流水，最新在前。"""
    safe_limit = max(1, min(limit, 200))
    result = await db.execute(
        select(CreditTransaction)
        .where(CreditTransaction.user_id == current_user.id)
        .order_by(desc(CreditTransaction.created_at))
        .limit(safe_limit)
    )
    return {
        "items": [
            {
                "id": str(item.id),
                "delta": item.delta,
                "balance_after": item.balance_after,
                "feature": item.feature,
                "reference_type": item.reference_type,
                "reference_id": item.reference_id,
                "description": item.description,
                "created_at": str(item.created_at),
            }
            for item in result.scalars().all()
        ]
    }


@router.post("/credits/deduct")
async def deduct_credits(
    payload: DeductCreditsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deduct credits atomically.

    Uses row-level locking to prevent race conditions.
    Returns 400 if credits are insufficient.
    """
    try:
        remaining = await current_user.deduct_credits(
            db,
            payload.amount,
            feature="manual_deduct",
            description="手动扣减积分",
        )
        await db.commit()
        return {
            "success": True,
            "credits_deducted": payload.amount,
            "credits_remaining": remaining,
        }
    except BillingSpendingBlockedError:
        # 账务差异止付必须交由全局处理器返回 423。
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
