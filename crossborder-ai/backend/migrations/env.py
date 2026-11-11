"""VeyaShip - Alembic 迁移环境配置

【全栈学习者必读】
Alembic 是 SQLAlchemy 的数据库迁移工具，类似于 Git 但管的是数据库表结构。
- 开发时改了模型（加了字段等）→ 生成迁移文件 → 应用到数据库
- 版本控制：可以升/降级（upgrade/downgrade）
- 生产环境：绝不能用 create_all，必须用迁移管理

工作流程：
1. 改 models/ 下的某个文件（比如给 Product 加了个字段）
2. 运行：alembic revision --autogenerate -m "add xxx field to Product"
3. 检查生成的迁移文件是否正确
4. 运行：alembic upgrade head

首次部署用：
    alembic stamp head    # 标记当前数据库为最新（不做任何 DDL）
    alembic upgrade head   # 执行所有未应用的迁移

首次部署也可以用 app 自带的 init_db()（会自动 create_all），
然后用 alembic stamp head 标记为已迁移。

注意：
    async 环境下，Alembic 的离线迁移（--autogenerate）需要同步连接。
    所以这里用 sync 的数据库 URL（postgresql:// 而不是 postgresql+asyncpg://）。
"""

from logging.config import fileConfig
import asyncio
import sys
import os
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# 把 backend/ 加到 Python 路径，让 Alembic 能找到 app 包
sys.path.insert(0, str(Path(__file__).parent.parent))

# Alembic 的配置文件（alembic.ini）
config = context.config

# 设置日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── 数据库 URL 优先级 ──────────────────────────────────────
# 按顺序使用：
# 1. 环境变量 DATABASE_URL（Docker 部署用）
# 2. app settings 中的 DB_URL（从 .env 读取）
# 3. alembic.ini 中的 sqlalchemy.url（本地开发备用）
#
# Alembic 与运行时共用 asyncpg / aiosqlite，避免再依赖第二套同步驱动。
db_url = os.environ.get("DATABASE_URL") or ""
if not db_url:
    try:
        from app.core.config import settings
        db_url = settings.DB_URL
    except Exception:
        pass

if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

# ── 导入所有模型（让 Alembic 能检测到表结构变化） ──────────
from app.core.database import Base
from app.models.user import User          # noqa: F401
from app.models.product import Product    # noqa: F401
from app.models.system_config import SystemConfig  # noqa: F401
from app.models.persona import Persona    # noqa: F401
from app.models.shopify_channel import ShopifyChannel  # noqa: F401
from app.models.batch_job import BatchJob  # noqa: F401
from app.models.content import ContentGeneration, ContentTemplate  # noqa: F401
from app.models.listing import Listing, ListingVariant  # noqa: F401
from app.models.listing_draft import ListingDraft, ListingComplianceReport  # noqa: F401
from app.models.publication import Publication  # noqa: F401
from app.models.platform_connection import PlatformConnection  # noqa: F401
from app.models.product_variant import ProductVariant  # noqa: F401
from app.models.payment import Subscription, PaymentInvoice  # noqa: F401
from app.models.conversation import Conversation, ConversationMessage  # noqa: F401
from app.models.store_check_log import StoreCheckLog  # noqa: F401
from app.models.data_retention import DataRetentionRun  # noqa: F401
from app.models.shopify_compliance_event import ShopifyComplianceEvent  # noqa: F401
from app.models.credit_transaction import CreditTransaction  # noqa: F401
from app.models.credit_wallet import CreditWallet  # noqa: F401
from app.models.subscription import UserSubscription  # noqa: F401
from app.models.feature_usage import FeatureUsageCounter  # noqa: F401
from app.models.credit_purchase import CreditPurchase  # noqa: F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """在异步连接上执行同步 Alembic 迁移上下文。"""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """使用应用同一套异步驱动完成迁移。"""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
