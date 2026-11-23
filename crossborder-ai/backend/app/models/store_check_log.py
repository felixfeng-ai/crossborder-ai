"""VeyaShip AI - 整店巡检记录模型

存储定时巡检结果，供用户查看历史记录。
"""

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StoreCheckLog(Base):
    """整店巡检记录表"""

    __tablename__ = "store_check_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    total: Mapped[int] = mapped_column(Integer, default=0)          # 商品总数
    healthy: Mapped[int] = mapped_column(Integer, default=0)        # 正常商品数
    issue_count: Mapped[int] = mapped_column(Integer, default=0)    # 有问题商品数
    issues_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 问题列表 JSON
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
