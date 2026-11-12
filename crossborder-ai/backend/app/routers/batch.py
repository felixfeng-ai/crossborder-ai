"""VeyaShip - 批量处理路由（F4 Batch）

功能：
1. CSV 上传解析
2. batch_jobs 表存任务
3. /api/cron/process-batch 逐条处理
"""

import csv
import io
import logging
import math
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.rate_limit import RateLimit
from app.core.access_control import check_feature_access
from app.dependencies import get_current_user
from app.models.batch_job import BatchJob
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User
from app.services.listing_service import persist_generated_listing
from app.services import provider_config
from pydantic import BaseModel

logger = logging.getLogger("veyaship")

router = APIRouter(prefix="/batch", tags=["批量处理"])

REQUIRED_HEADERS = ["title"]


@router.post("/upload")
async def upload_csv(
    file: UploadFile = File(..., description="CSV 文件，含标题头：title, url, price, description"),
    current_user: User = Depends(get_current_user),
    _ratelimit=Depends(RateLimit("batch")),
    db: AsyncSession = Depends(get_db),
):
    """上传 CSV 文件，解析后创建批量任务。

    CSV 格式：
        title,url,price,description
        商品A,https://...,29.99,描述文字
        商品B,https://...,19.99,描述文字
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="请上传 .csv 文件")

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("gbk", errors="replace")

    reader = csv.DictReader(io.StringIO(text))

    headers = [h.strip().lower() for h in (reader.fieldnames or [])]
    missing = [h for h in REQUIRED_HEADERS if h not in headers]
    if missing:
        raise HTTPException(status_code=400, detail=f"CSV 缺少必要列：{', '.join(missing)}")

    def value(row: dict, name: str) -> str:
        return str(row.get(name) or "").strip()

    def integer(row: dict, name: str) -> int | None:
        raw = value(row, name)
        if not raw:
            return None
        try:
            return max(0, int(float(raw)))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"CSV 第 {row_count} 行的 {name} 必须是数字",
            )

    # 逐行创建任务
    jobs = []
    row_count = 0
    for row in reader:
        row_count += 1
        job = BatchJob(
            user_id=current_user.id,
            source_type="csv",
            source_filename=file.filename,
            row_index=row_count,
            title=value(row, "title"),
            url=value(row, "url") or None,
            price=value(row, "cost_price") or value(row, "price") or None,
            description=value(row, "description") or None,
            origin_type=value(row, "origin_type") or (
                "1688" if "1688.com" in value(row, "url") else "own"
            ),
            main_image_url=value(row, "main_image_url") or None,
            brand_name=value(row, "brand_name") or None,
            cost_currency=(
                value(row, "cost_currency")
                or value(row, "currency")
                or "CNY"
            ).upper(),
            moq=integer(row, "moq"),
            lead_time_days=integer(row, "lead_time_days"),
            stock_quantity=integer(row, "stock_quantity"),
            sku=value(row, "sku") or None,
            status="pending",
        )
        db.add(job)
        jobs.append(job)

    if row_count == 0:
        raise HTTPException(status_code=400, detail="CSV 文件为空")

    await db.flush()

    return {
        "message": f"已导入 {row_count} 条任务",
        "total": row_count,
    }


@router.get("/jobs")
async def list_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, description="过滤状态"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查看批量任务列表"""
    query = select(BatchJob).where(BatchJob.user_id == current_user.id)
    if status_filter:
        query = query.where(BatchJob.status == status_filter)
    query = query.order_by(BatchJob.created_at.desc())

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar()
    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    jobs = result.scalars().all()

    return {
        "items": [
            {
                "id": str(j.id),
                "row_index": j.row_index,
                "title": j.title,
                "url": j.url,
                "product_id": str(j.product_id) if j.product_id else None,
                "listing_id": str(j.listing_id) if j.listing_id else None,
                "status": j.status,
                "error": j.error,
                "created_at": str(j.created_at),
                "processed_at": str(j.processed_at) if j.processed_at else None,
            }
            for j in jobs
        ],
        "total": total or 0,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, math.ceil((total or 0) / page_size)),
    }


async def _create_product_from_job(
    db: AsyncSession,
    user: User,
    job: BatchJob,
) -> Product:
    """把 CSV 任务转换为商品，并创建可选的首个 SKU。"""
    product_id = uuid4()
    try:
        price = float(job.price) if job.price else None
    except ValueError:
        raise ValueError(f"CSV 第 {job.row_index} 行的价格格式无效")
    product = Product(
        id=product_id,
        user_id=user.id,
        title=job.title or "",
        url=job.url or f"own://{product_id}",
        origin_type=job.origin_type or ("1688" if job.url else "own"),
        price=price,
        description=job.description,
        main_image_url=job.main_image_url,
        brand_name=job.brand_name,
        cost_currency=(job.cost_currency or "CNY").upper(),
        moq=job.moq,
        lead_time_days=job.lead_time_days,
    )
    db.add(product)
    await db.flush()
    if job.sku or job.stock_quantity is not None:
        db.add(
            ProductVariant(
                user_id=user.id,
                product_id=product.id,
                sku=job.sku or f"OWN-{str(product.id)[:8].upper()}",
                name=product.title,
                cost_price=price,
                stock_quantity=job.stock_quantity or 0,
                image_url=job.main_image_url,
            )
        )
        await db.flush()
    return product


@router.post("/process/{job_id}")
async def process_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """处理单条批量任务：将 CSV 行转为商品

    可从 /api/cron/process-batch 调度批量执行。
    """
    from uuid import UUID
    try:
        uid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的任务 ID")

    result = await db.execute(
        select(BatchJob).where(BatchJob.id == uid, BatchJob.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.status == "processed":
        raise HTTPException(status_code=400, detail="任务已处理")

    # 处理：创建商品
    try:
        product = await _create_product_from_job(db, current_user, job)
        job.product_id = product.id
        job.status = "processed"
        job.processed_at = datetime.now(timezone.utc)
        await db.flush()
        return {"message": "处理成功", "product_id": str(product.id)}
    except Exception:
        # 技术细节只进服务端日志；job.error 会原样展示给卖家，必须是中文
        logger.exception("批量任务处理失败 job_id=%s", job.id)
        job.status = "failed"
        job.error = "处理失败，请稍后重试"
        await db.flush()
        raise HTTPException(status_code=500, detail="处理失败，请稍后重试")


@router.post("/cron/process-batch")
async def cron_process_batch(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """批量处理所有 pending 状态的任务

    设计为可被 APScheduler 定时调用。
    """
    result = await db.execute(
        select(BatchJob).where(
            BatchJob.user_id == current_user.id,
            BatchJob.status == "pending",
        ).limit(10)
    )
    jobs = result.scalars().all()

    results = []
    for job in jobs:
        try:
            product = await _create_product_from_job(db, current_user, job)
            job.product_id = product.id
            job.status = "processed"
            job.processed_at = datetime.now(timezone.utc)
            results.append({"job_id": str(job.id), "status": "success"})
        except Exception:
            logger.exception("批量任务处理失败 job_id=%s", job.id)
            job.status = "failed"
            job.error = "处理失败，请稍后重试"
            results.append({"job_id": str(job.id), "status": "failed", "error": "处理失败，请稍后重试"})

    await db.flush()
    return {"processed": len(results), "results": results}


@router.post("/process-ai")
async def batch_process_with_ai(
    platform: str = "amazon",
    language: str = "en",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """批量 AI 处理：对 pending 状态的批量任务执行 AI 生成

    流程：
    1. 取所有 pending 任务
    2. 逐条创建商品
    3. AI 生成 Listing（标题/描述/卖点）
    4. 标记完成
    """
    if not check_feature_access(current_user, "batch_ai"):
        raise HTTPException(status_code=403, detail="批量 AI 处理仅限 Standard 及以上套餐使用")

    result = await db.execute(
        select(BatchJob)
        .where(BatchJob.user_id == current_user.id, BatchJob.status == "pending")
        .limit(20)
    )
    jobs = result.scalars().all()
    if not jobs:
        return {"message": "没有待处理的任务", "processed": 0}
    if current_user.credits < 1:
        raise HTTPException(status_code=402, detail="积分不足")

    from app.services.ai.deepseek import DeepSeekService
    from app.services.ai.compliance import check_text, merge_banned_words
    from app.services.ai.persona_kit import (
        build_persona_kit,
        fetch_persona,
        format_persona_block,
    )

    llm = DeepSeekService()
    persona = await fetch_persona(db, current_user.id)
    persona_kit = build_persona_kit(persona) if persona else None
    persona_block = format_persona_block(persona_kit) if persona_kit else ""
    banned_words = merge_banned_words(
        (persona_kit or {}).get("banned_words") or []
    )
    results = []

    for job in jobs:
        if current_user.credits < 1:
            results.append({
                "job_id": str(job.id),
                "status": "failed",
                "error": "积分不足",
            })
            continue
        try:
            async with db.begin_nested():
                product = await _create_product_from_job(db, current_user, job)

                title = await llm.generate(
                    f"You are a professional {platform} listing copywriter.",
                    (
                        f"Generate an optimized {platform} product title "
                        f"(max 200 chars) in {language}.\n"
                        f"Product: {product.title}\nSupply reference price: {product.price}"
                    ),
                    max_tokens=300,
                    persona_block=persona_block,
                )
                desc = await llm.generate_product_description(
                    product_title=product.title or "",
                    platform=platform,
                    target_language=language,
                    persona_block=persona_block,
                )
                bullets = await llm.generate_bullet_points(
                    product_title=product.title or "",
                    features=(
                        f"Supply reference price: {product.price}"
                        if product.price
                        else ""
                    ),
                    platform=platform,
                    persona_block=persona_block,
                )

                violations: list[str] = []
                for text in [title, desc, *bullets]:
                    for word in check_text(text or "", banned_words):
                        if word not in violations:
                            violations.append(word)
                blocked = bool(violations)
                draft = await persist_generated_listing(
                    db,
                    user=current_user,
                    product=product,
                    platform=platform,
                    language=language,
                    tone="professional",
                    title=title,
                    description=desc,
                    bullet_points=bullets,
                    seo_title="",
                    seo_description="",
                    violations=violations,
                    blocked=blocked,
                    ai_model_used=provider_config.get(
                        "deepseek",
                        "model",
                        settings.DEEPSEEK_MODEL,
                    ),
                )
                await current_user.deduct_credits(
                    db,
                    1,
                    feature="batch_listing",
                    reference_type="batch_job",
                    reference_id=str(job.id),
                    description="批量 AI 生成 Listing",
                )

                job.product_id = product.id
                job.listing_id = draft.id
                job.status = "processed"
                job.processed_at = datetime.now(timezone.utc)
                results.append({
                    "job_id": str(job.id),
                    "product_id": str(product.id),
                    "listing_id": str(draft.id),
                    "listing_status": draft.status,
                    "compliance_status": draft.compliance_status,
                    "title": title[:50],
                    "bullet_count": len(bullets),
                    "status": "success",
                })
        except Exception:
            logger.exception("批量任务处理失败 job_id=%s", job.id)
            job.status = "failed"
            job.error = "处理失败，请稍后重试"
            results.append({"job_id": str(job.id), "status": "failed", "error": "处理失败，请稍后重试"})

    await db.flush()
    return {"message": f"已处理 {len(results)} 条", "processed": len(results), "results": results}
