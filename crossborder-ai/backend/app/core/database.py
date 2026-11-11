"""VeyaShip - 数据库配置

【全栈学习者必读】
这个文件是后端最重要的基础设施之一，理解它就能理解：
1. 后端如何连接数据库
2. 什么是"异步数据库操作"
3. 什么是"依赖注入"和"会话管理"
4. 开发和生产环境如何切换数据库

核心概念：
- 引擎（Engine）：数据库连接池，保持多个数据库连接随时可用
- 会话（Session）：一次数据库操作的"工作单元"，用完就归还到连接池
- 依赖注入（Dependency Injection）：FastAPI 自动把会话传给路由函数
"""

import ssl
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


def _database_connect_args(
    *,
    use_sqlite: bool,
    ssl_mode: str,
    ssl_ca_path: str,
    ssl_cert_path: str,
    ssl_key_path: str,
) -> dict:
    """构造数据库连接参数，生产 PostgreSQL 可强制使用 TLS。

    verify-full 同时校验 CA 和主机名；verify-ca 只校验 CA。
    require 提供加密但不验证服务端证书，仅用于无法部署 CA 的过渡环境。
    """
    if use_sqlite:
        return {"check_same_thread": False}

    mode = (ssl_mode or "disable").strip().lower()
    if mode == "disable":
        return {}
    if mode == "require":
        return {"ssl": "require"}
    if mode not in {"verify-ca", "verify-full"}:
        raise ValueError(
            "DB_SSL_MODE 仅支持 disable、require、verify-ca、verify-full"
        )

    context = ssl.create_default_context(
        cafile=ssl_ca_path or None,
    )
    context.check_hostname = mode == "verify-full"
    context.verify_mode = ssl.CERT_REQUIRED

    if ssl_cert_path or ssl_key_path:
        if not ssl_cert_path or not ssl_key_path:
            raise ValueError("PostgreSQL 客户端证书和私钥必须同时配置")
        for path in (ssl_cert_path, ssl_key_path):
            if not Path(path).is_file():
                raise ValueError(f"PostgreSQL TLS 凭证文件不存在：{path}")
        context.load_cert_chain(ssl_cert_path, ssl_key_path)

    return {"ssl": context}


# ── 1. 创建异步数据库引擎 ───────────────────────────────────────
# create_async_engine 创建了一个异步连接池
# 异步 = 数据库查询时不会阻塞其他请求
#
# 关键参数：
#   settings.DB_URL - 连接字符串（在 config.py 中组装）
#     开发：sqlite+aiosqlite:///./crossborder_ai.db
#     生产：postgresql+asyncpg://user:pass@host:5432/db
#   echo=DEBUG - 如果开启 DEBUG，SQL 语句会打印到控制台
#   pool_pre_ping - 每次使用连接前检查是否还活着，避免用"死连接"
engine = create_async_engine(
    settings.DB_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    connect_args=_database_connect_args(
        use_sqlite=settings.USE_SQLITE,
        ssl_mode=settings.DB_SSL_MODE,
        ssl_ca_path=settings.DB_SSL_CA_PATH,
        ssl_cert_path=settings.DB_SSL_CERT_PATH,
        ssl_key_path=settings.DB_SSL_KEY_PATH,
    ),
)

# ── 2. SQLite 专有优化 ─────────────────────────────────────────
# 如果是 SQLite 开发模式，做一些优化配置
if settings.USE_SQLITE:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        """每次新连接建立时执行 SQLite 优化指令

        WAL 模式（Write-Ahead Logging）：
        - 默认 SQLite 写入时锁定整个数据库，读操作会等待
        - WAL 模式下，写入在日志文件追加，读操作读原文件
        - 写入不阻塞读取：大幅提高并发性能

        foreign_keys=ON：
        - SQLite 默认不启用外键约束（为了兼容旧数据库）
        - 手动启用，保证数据完整性
        - 比如：用户被删 → 关联的商品自动删除（CASCADE）
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")      # 写入日志模式
        cursor.execute("PRAGMA foreign_keys=ON")         # 外键约束
        cursor.close()

# ── 3. 会话工厂 ───────────────────────────────────────────────
# async_sessionmaker 可以理解为一个"会话生成器"
# 每次调用 async_session_factory() 创建一个新的数据库会话
# expire_on_commit=False 提交后，对象的属性仍然可访问
# 如果设为 True，提交后访问对象的任何属性都会触发一次新查询
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── 4. 模型基类 ──────────────────────────────────────────────
# 所有数据库模型（User、Product 等）都要继承这个 Base
# 这样 SQLAlchemy 才能自动发现哪些表需要创建
class Base(DeclarativeBase):
    """所有数据库模型的基类。

    用法：
        class User(Base):     # 继承 Base
            __tablename__ = "users"
            id = Column(...)

    Alembic 迁移工具也通过读取 Base.metadata 来知道表结构。
    """
    pass


# ── 5. 获取数据库会话（依赖注入核心） ─────────────────────────
# 【全栈学习者重点理解】
#
# 这是个 Python 生成器函数（有 yield），FastAPI 特殊处理它：
#
# 请求进来 → FastAPI 调用 get_db()
#          → 进入 with 块，创建会话
#          → yield session → 把会话传给路由函数
#          → 路由函数 await db.execute(...)
#          → 路由返回
#          → 进入 except/finally 块
#          → 成功则 commit，失败则 rollback
#          → 关闭会话
#
# 这样做的最大好处：事务自动管理！
# 路由里不需要写 try/except/rollback，get_db 全包了。
#
# 用法：
#   @router.get("/users")
#   async def get_users(db: AsyncSession = Depends(get_db)):
#       result = await db.execute(select(User))
#       return result.scalars().all()
async def get_db() -> AsyncSession:
    """FastAPI 依赖：获取一个数据库会话。

    这是依赖注入的典型例子：
    1. 路由函数声明需要 db
    2. FastAPI 自动调用 get_db() 获取会话
    3. 路由用完，自动提交/回滚/关闭

    Yields:
        AsyncSession 对象
    """
    async with async_session_factory() as session:
        try:
            yield session  # ← 路由函数执行期间，session 在这里"等待"
            await session.commit()  # 路由正常完成 → 提交事务
        except Exception:
            await session.rollback()  # 路由抛出异常 → 回滚事务
            raise  # 重新抛出异常，让 FastAPI 的全局异常处理器处理
        finally:
            await session.close()  # 归还会话到连接池


# ── 6. 自动建表（仅开发模式） ─────────────────────────────────
# init_db 在项目启动时调用（main.py 的 lifespan）
# 它会读取所有继承 Base 的模型，自动创建对应的数据库表
async def init_db():
    """启动时自动创建所有数据库表。

    开发环境（SQLite）：每次启动自动同步表结构
    生产环境（PostgreSQL）：请用 Alembic 迁移工具管理表结构

    为什么生产不用自动建表？
    - 生产环境不能轻易删表，数据宝贵
    - 需要有版本控制的迁移记录
    - 迁移需要回滚能力

    Alembic 命令：
        alembic revision --autogenerate -m "描述"
        alembic upgrade head
    """
    async with engine.begin() as conn:
        # run_sync 把异步操作转成同步，因为 create_all 是同步的
        await conn.run_sync(Base.metadata.create_all)
