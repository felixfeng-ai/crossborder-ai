"""平台发布记录与幂等辅助服务。"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.publication import Publication


async def find_publication_by_idempotency(
    db: AsyncSession,
    user_id: UUID,
    platform: str,
    idempotency_key: str,
) -> Publication | None:
    """按用户、平台和幂等键查找已有发布记录。"""
    if not idempotency_key:
        return None
    return (
        await db.execute(
            select(Publication).where(
                Publication.user_id == user_id,
                Publication.platform == platform,
                Publication.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()


async def create_publication(
    db: AsyncSession,
    *,
    user_id: UUID,
    listing_id: UUID | None,
    platform: str,
    channel_id: str,
    idempotency_key: str,
) -> Publication:
    """创建 publishing 状态记录。"""
    publication = Publication(
        user_id=user_id,
        listing_id=listing_id,
        platform=platform,
        channel_id=channel_id,
        idempotency_key=idempotency_key or None,
        status="publishing",
    )
    db.add(publication)
    await db.flush()
    return publication


def publication_response(publication: Publication) -> dict:
    """把发布记录转成稳定的接口响应。"""
    return {
        "publication_id": str(publication.id),
        "message": "商品已发布到 Shopify（草稿状态）",
        "listing_id": str(publication.listing_id) if publication.listing_id else "",
        "shopify_product_id": (
            int(publication.external_product_id)
            if publication.external_product_id and publication.external_product_id.isdigit()
            else publication.external_product_id
        ),
        "shopify_url": publication.external_url,
    }
