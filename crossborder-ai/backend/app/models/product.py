"""VeyaShip - 商品模型

存储从 1688 抓取或手动录入的商品信息。
"""

import uuid
from datetime import datetime
from uuid import UUID as UUIDType

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Product(Base):
    """商品表 —— 存储抓取或录入的商品数据

    用户通过 1688 链接抓取或手动录入后，数据存在这里。
    后续 AI 生成 Listing 时，从这个表读取商品信息。
    """

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("user_id", "url", name="uq_products_user_url"),
    )

    # ── 主键 ──────────────────────────────────────────────────
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── 所属用户 ──────────────────────────────────────────────
    # 记录是哪个用户抓取/录入的这个商品。方便按用户统计
    # 可以为空，兼容已有的数据（尚未迁移的旧数据 user_id 为 null）
    # ForeignKey 关联到 users 表，如果用户被删除，商品也跟随删除
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )

    # ── 核心数据 ──────────────────────────────────────────────
    # 同一用户不能重复录入同一个商品；不同用户可以各自拥有相同来源 URL。
    url: Mapped[str] = mapped_column(
        String(500), index=True, nullable=False
    )
    # title 可为空，因为手动录入时可以只填链接不填标题
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 主图链接，后续 AI 生成 Listing 时可以直接引用
    main_image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # ── 供货价/销量/店铺 ──────────────────────────────────────
    # price 是 1688 来源供货参考价，不是 Shopify/Amazon 的销售价。
    # 可发布售价统一从 ProductVariant.price 读取。
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    sales_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shop_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── 描述（手动补充） ──────────────────────────────────────
    # 用户可以在抓取后手动补充商品描述，AI 生成 Listing 时会用到
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── 时间戳 ──────────────────────────────────────────────
    # created_at 在插入时自动填
    # updated_at 在更新时自动更新（onupdate）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Product {self.id}: {self.title}>"
