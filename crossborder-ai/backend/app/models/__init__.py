"""VeyaShip - 数据模型入口

所有模型集中导出，方便 Alembic 迁移检测和外部导入。
每新增一个模型，都要在这里注册。

Alembic 通过 from app.models import * 自动发现所有表结构变更。
"""

from app.models.user import User
from app.models.product import Product
from app.models.system_config import SystemConfig
from app.models.persona import Persona
from app.models.shopify_channel import ShopifyChannel
from app.models.batch_job import BatchJob
from app.models.conversation import Conversation, ConversationMessage
from app.models.store_check_log import StoreCheckLog
from app.models.rate_limit import RateLimitWindow
from app.models.agent_task import AgentTask
from app.models.plan_upgrade import PlanUpgradeRequest
from app.models.image_generation_task import ImageGenerationTask
from app.models.listing_draft import ListingDraft, ListingComplianceReport
from app.models.publication import Publication
from app.models.platform_connection import PlatformConnection
from app.models.product_variant import ProductVariant

__all__ = [
    "User",
    "Product",
    "SystemConfig",
    "Persona",
    "ShopifyChannel",
    "BatchJob",
    "Conversation",
    "ConversationMessage",
    "StoreCheckLog",
    "RateLimitWindow",
    "AgentTask",
    "PlanUpgradeRequest",
    "ImageGenerationTask",
    "ListingDraft",
    "ListingComplianceReport",
    "Publication",
    "PlatformConnection",
    "ProductVariant",
]
