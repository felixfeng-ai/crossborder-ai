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
from app.models.content import ContentGeneration, ContentTemplate
from app.models.listing import Listing, ListingVariant
from app.models.listing_draft import ListingDraft, ListingComplianceReport
from app.models.payment import PaymentInvoice, Subscription
from app.models.publication import Publication
from app.models.platform_connection import PlatformConnection
from app.models.product_variant import ProductVariant
from app.models.image_asset import ImageAsset
from app.models.monitor_setting import MonitorSetting
from app.models.variant_snapshot import VariantSnapshot
from app.models.operation_alert import OperationAlert
from app.models.video_generation_task import VideoGenerationTask
from app.models.marketing_video import MarketingVideoProject, MarketingVideoShot
from app.models.data_retention import DataRetentionRun
from app.models.shopify_compliance_event import ShopifyComplianceEvent
from app.models.credit_transaction import CreditTransaction
from app.models.credit_wallet import CreditWallet
from app.models.subscription import UserSubscription
from app.models.feature_usage import FeatureUsageCounter
from app.models.credit_purchase import CreditPurchase
from app.models.voc import VocAnalysis

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
    "ContentGeneration",
    "ContentTemplate",
    "Listing",
    "ListingVariant",
    "ListingDraft",
    "ListingComplianceReport",
    "PaymentInvoice",
    "Subscription",
    "Publication",
    "PlatformConnection",
    "ProductVariant",
    "ImageAsset",
    "MonitorSetting",
    "VariantSnapshot",
    "OperationAlert",
    "VideoGenerationTask",
    "MarketingVideoProject",
    "MarketingVideoShot",
    "DataRetentionRun",
    "ShopifyComplianceEvent",
    "CreditTransaction",
    "CreditWallet",
    "UserSubscription",
    "FeatureUsageCounter",
    "CreditPurchase",
    "VocAnalysis",
]
