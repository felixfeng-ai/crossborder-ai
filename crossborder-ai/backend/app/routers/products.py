"""VeyaShip - 商品路由

演示了数据库操作：
1. 写入新商品（INSERT）
2. 分页查询列表（SELECT + LIMIT/OFFSET）
3. 按 ID 查询详情（SELECT + WHERE）
4. 跨表查配置（SELECT SystemConfig）
5. 使用缓存装饰器减少重复查询
"""

import math
from datetime import datetime
from typing import Optional
from uuid import UUID, UUID as UUIDType

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import RateLimit
from app.core.redis import cache_clear
from app.dependencies import get_current_user
from app.models.product import Product
from app.models.listing_draft import ListingDraft
from app.models.user import User
from app.services.scraper import SERVICE_NOT_CONFIGURED_MSG, ScrapeError, scrape_1688
from app.services.listing_service import serialize_listing
from app.services import provider_config
from pydantic import BaseModel, Field

router = APIRouter(prefix="/products", tags=["Products"])


# ── Pydantic 数据校验 ──────────────────────────────────────────
# 这些不是数据库模型，而是 API 请求/响应的格式定义
# 它们和数据模型（Product）是分开的，互不影响

class ScrapeRequest(BaseModel):
    """请求体：抓取 1688 商品"""
    url: str = Field(..., description="1688 商品详情页链接")


class ManualProductRequest(BaseModel):
    """请求体：手动录入商品"""
    url: str = Field(..., description="商品链接")
    title: Optional[str] = None
    main_image_url: Optional[str] = None
    price: Optional[float] = Field(
        None,
        ge=0,
        description="1688 供货参考价，不是平台销售价",
    )
    sales_count: Optional[int] = Field(None, ge=0)
    shop_name: Optional[str] = None


class ProductResponse(BaseModel):
    """响应体：商品信息"""
    id: UUIDType  # UUID 类型，FastAPI 会自动序列化为字符串
    url: str
    title: Optional[str] = None
    main_image_url: Optional[str] = None
    price: Optional[float] = Field(
        None,
        description="1688 供货参考价，不是平台销售价",
    )
    sales_count: Optional[int] = None
    shop_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # from_attributes=True 允许从 SQLAlchemy 模型直接转换
    model_config = {"from_attributes": True}


class ProductListResponse(BaseModel):
    """响应体：分页商品列表"""
    items: list[ProductResponse]
    total: int      # 总记录数
    page: int       # 当前第几页
    page_size: int  # 每页多少条
    total_pages: int  # 总共多少页


async def _load_scrape_credentials(db: AsyncSession) -> tuple[str, str, str]:
    """读取 Just One 与 Onebound 的平台级抓取凭据。

    优先级：SystemConfig（设置页密文存储）> settings（.env 兜底）。
    Key 对卖家不可见，此处只读不暴露任何明文给前端。

    Returns:
        (justone_token, onebound_key, onebound_secret)。
    """
    await provider_config.refresh(db)
    return (
        provider_config.get("justone", "token"),
        provider_config.get("onebound", "api_key"),
        provider_config.get("onebound", "api_secret"),
    )


@router.get("/scrape/status")
async def scrape_service_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """平台级 1688 数据服务就绪探针（CAP-01）

    前端据此在 Key 未配置时禁用「自动抓取」按钮并提示联系客服，
    而不是等卖家点下去才拿到错误。
    """
    justone_token, api_key, _secret = await _load_scrape_credentials(db)
    return {
        "configured": bool(justone_token or api_key),
        "providers": {
            "justone": bool(justone_token),
            "onebound": bool(api_key),
        },
    }


@router.post("/scrape", status_code=status.HTTP_201_CREATED)
async def scrape_product(
    payload: ScrapeRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    _ratelimit=Depends(RateLimit("scrape")),
    db: AsyncSession = Depends(get_db),
):
    """抓取 1688 商品（自动，CAP-01：就绪检查 + 错误分类）

    流程：
    1. 就绪检查：平台数据服务 Key 未配置 → 400 中文「联系客服开通」，不发网络请求
    2. 查 products 表是否已抓过（防重复）
    3. 扣积分前校验余额
    4. 调用爬虫（Just One -> Onebound -> 直抓），分类错误转 HTTPException
    5. 成功扣 1 积分并 INSERT 新商品
    """
    # ── 就绪检查：平台级数据服务 Key（CAP-01 / C1）────────────
    justone_token, api_key, api_secret = await _load_scrape_credentials(db)
    if not justone_token and not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "service_not_configured", "message": SERVICE_NOT_CONFIGURED_MSG},
        )

    # ── 查重 ───────────────────────────────────────────────
    # 检查是否已抓取过这个 URL
    result = await db.execute(
        select(Product).where(
            Product.url == payload.url,
            Product.user_id == current_user.id,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="该商品已抓取过")

    # ── 积分检查 ───────────────────────────────────────────
    if current_user.credits < 1:
        raise HTTPException(status_code=402, detail="积分不足")

    # ── 调用爬虫（外部服务，不是数据库操作） ────────────────
    # ScrapeError 已分类：稳定 code + 中文 message，绝不裸抛底层异常给卖家
    try:
        data = await scrape_1688(
            payload.url,
            api_key=api_key,
            api_secret=api_secret,
            justone_token=justone_token,
        )
    except ScrapeError as e:
        raise HTTPException(
            status_code=e.http_status,
            detail={"code": e.code, "message": e.message},
        ) from e
    except (ValueError, RuntimeError) as e:
        # 防御兜底：理论已被 ScrapeError 覆盖，避免意外漏成 500
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "scrape_failed", "message": str(e) or "抓取失败，请稍后重试"},
        ) from e

    # ── 扣积分（修改已有数据） ─────────────────────────────
    await current_user.deduct_credits(db, 1)

    # ── INSERT ─────────────────────────────────────────────
    # user_id 记录是谁抓取的，用于后续按用户统计
    product = Product(
        user_id=current_user.id,  # 记录所属用户
        url=data["url"],
        title=data["title"],
        main_image_url=data["main_image_url"],
        price=data["price"],
        sales_count=data["sales_count"],
        shop_name=data["shop_name"],
    )
    db.add(product)
    await db.flush()  # 立即写入，获取 product.id

    # ── 缓存相关 ───────────────────────────────────────────
    await cache_clear(pattern="products_list")

    return {
        "message": "抓取成功",
        # 数据源标注：onebound（数据接口）/ direct（实时抓取降级），供前端提示与统计
        "data_source": data.get("data_source", "onebound"),
        "product": ProductResponse.model_validate(product).model_dump(),
    }


@router.post("/manual", status_code=status.HTTP_201_CREATED)
async def create_product_manual(
    payload: ManualProductRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """手动录入商品（兜底方案，抓取失败时用）"""
    # 查重
    result = await db.execute(
        select(Product).where(
            Product.url == payload.url,
            Product.user_id == current_user.id,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="该商品链接已存在")

    # INSERT
    product = Product(
        user_id=current_user.id,
        url=payload.url,
        title=payload.title,
        main_image_url=payload.main_image_url,
        price=payload.price,
        sales_count=payload.sales_count,
        shop_name=payload.shop_name,
    )
    db.add(product)
    await db.flush()

    return {
        "message": "创建成功",
        "product": ProductResponse.model_validate(product).model_dump(),
    }


@router.get("", response_model=ProductListResponse)
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="搜索标题"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """分页查询商品列表

    SQL：
        SELECT * FROM products
        WHERE owner_id = ?
        ORDER BY updated_at DESC
        LIMIT ? OFFSET ?
    """
    # ── 构建查询 ─────────────────────────────────────────
    # 只查当前用户自己的商品（防跨租户枚举他人商品）
    query = (
        select(Product)
        .where(Product.user_id == current_user.id)
        .order_by(Product.updated_at.desc())
    )

    # 搜索条件（WHERE title LIKE '%关键词%'）
    if search:
        query = query.where(Product.title.ilike(f"%{search}%"))

    # ── 查总数（分页需要知道总共有多少条） ────────────────
    # SELECT COUNT(*) FROM (上面的查询) AS anon_1
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # ── 分页 ─────────────────────────────────────────────
    # LIMIT page_size OFFSET (page-1)*page_size
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    products = result.scalars().all()

    return ProductListResponse(
        items=[ProductResponse.model_validate(p) for p in products],
        total=total or 0,
        page=page,
        page_size=page_size,
        total_pages=max(1, math.ceil((total or 0) / page_size)),
    )


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询单个商品详情（仅本人；他人商品按不存在处理）

    SQL：
        SELECT * FROM products WHERE id = ? AND owner_id = ?

    注：去掉 @cache —— 原缓存只按 URL 键，跨用户会串数据且与归属校验冲突。
    """
    from uuid import UUID
    try:
        uid = UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的商品 ID")

    result = await db.execute(
        select(Product).where(
            Product.id == uid,
            Product.user_id == current_user.id,
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    return ProductResponse.model_validate(product).model_dump()


@router.get("/{product_id}/listings")
async def list_product_listings(
    product_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List persisted listing drafts for one owned product."""
    try:
        pid = UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的商品 ID")

    owned = await db.execute(
        select(Product.id).where(
            Product.id == pid,
            Product.user_id == current_user.id,
        )
    )
    if owned.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="商品不存在")

    result = await db.execute(
        select(ListingDraft)
        .where(
            ListingDraft.product_id == pid,
            ListingDraft.user_id == current_user.id,
        )
        .order_by(ListingDraft.created_at.desc())
    )
    drafts = result.scalars().all()
    return {
        "items": [serialize_listing(draft) for draft in drafts],
        "total": len(drafts),
    }


@router.delete("/{product_id}", status_code=status.HTTP_200_OK)
async def delete_product(
    product_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除商品"""
    from uuid import UUID
    try:
        uid = UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的商品 ID")

    # 归属过滤：他人商品等同不存在，禁止跨租户删除
    result = await db.execute(
        select(Product).where(
            Product.id == uid,
            Product.user_id == current_user.id,
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    await db.delete(product)
    await db.flush()
    return {"message": "商品已删除"}


class BatchDeleteRequest(BaseModel):
    ids: list[str] = Field(..., description="要删除的商品 ID 列表")


@router.post("/batch-delete", status_code=status.HTTP_200_OK)
async def batch_delete_products(
    payload: BatchDeleteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """批量删除商品"""
    from uuid import UUID

    deleted = 0
    for product_id in payload.ids:
        try:
            uid = UUID(product_id)
            # 归属过滤：只删自己的商品，他人商品自动跳过
            result = await db.execute(
                select(Product).where(
                    Product.id == uid,
                    Product.user_id == current_user.id,
                )
            )
            product = result.scalar_one_or_none()
            if product:
                await db.delete(product)
                deleted += 1
        except ValueError:
            continue

    await db.flush()
    return {"message": f"已删除 {deleted} 个商品", "deleted": deleted}


@router.delete("", status_code=status.HTTP_200_OK)
async def delete_all_products(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除当前用户所有商品"""
    result = await db.execute(
        select(Product).where(Product.user_id == current_user.id)
    )
    products = result.scalars().all()
    count = len(products)
    for p in products:
        await db.delete(p)
    await db.flush()
    return {"message": f"已删除全部 {count} 个商品", "deleted": count}
