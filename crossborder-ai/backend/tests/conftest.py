"""VeyaShip - 测试配置

【全栈学习者必读】
pytest 是 Python 最流行的测试框架。
conftest.py 是 pytest 的"全局配置"——定义所有测试共享的 fixtures。

什么是 fixture？
- 有点类似 FastAPI 的"依赖注入"
- fixture 是"测试需要的东西"的工厂
- pytest 自动管理创建和销毁

本文件定义的 fixtures：
- db_session: 测试专用的数据库会话（每条测试独立，互不干扰）
- client: 模拟 HTTP 请求的测试客户端
- sample_user_data: 测试用的用户数据
"""

import asyncio
import os
from typing import AsyncGenerator

# 测试默认走 SQLite 模式：config 的 validate_secrets 校验依赖此开关
# （生产 PG 模式要求 JWT_SECRET_KEY 非空，测试无 .env 需跳过该校验）
os.environ.setdefault("USE_SQLITE", "true")
os.environ.setdefault("SECRET_KEY", "test-only-app-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.config import settings
from app.core import rate_limit as rate_limit_module
import app.models  # noqa: F401  # 建立完整 metadata，避免单测导入顺序导致外键缺表
from app.main import app

# ── 测试数据库 URL ────────────────────────────────────────────
# 开发环境用 SQLite 内存数据库（速度快，不需额外安装）
# 生产环境测试用 PostgreSQL（需要配置，目前被注释掉）
# 优先用环境变量 CROSSBORNER_TEST_DB_URL，方便 CI 配置
TEST_DATABASE_URL = os.environ.get(
    "CROSSBORDER_TEST_DB_URL",
    "sqlite+aiosqlite://",  # 内存 SQLite，每条测试独立
)
# 如果要用 PostgreSQL 测试，取消下面注释并配置
# TEST_DATABASE_URL = "postgresql+asyncpg://crossborder:change_this_password@localhost:5432/crossborder_ai_test"

# ── SQLite 内存模式 ───────────────────────────────────────────
# 用 ":memory:" SQLite 时，必须用同一个 engine 保证数据一致
# 这是因为 SQLite 的内存模式是"每个连接一个独立数据库"
_use_sqlite = TEST_DATABASE_URL.startswith("sqlite")


@pytest.fixture(scope="session")
def event_loop():
    """创建测试用的事件循环

    pytest-asyncio 需要这个 fixture 来管理事件循环的生命周期。
    scope="session" 表示整个测试会话只创建一个事件循环。
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_engine():
    """创建测试数据库引擎

    scope="function"：每个测试一个全新的内存库，天然隔离。

    历史教训（2026-09-07 收口）：之前是 session 级共享引擎，而
    auth_token 用固定邮箱 test@example.com 注册。一旦某个测试触发了
    会显式 commit 的端点（新增的 images/persona/compliance 路由），
    同会话里 pending 的注册用户会一起落库 → 之后所有测试的 auth_token
    都撞 409（全量回归连环 error，21 个）。改成每测试独立引擎后，
    无论端点是否 commit，数据都随测试结束的引擎销毁，无需依赖
    「路由不 commit」这一隐性前提。

    SQLite 内存模式：
    - StaticPool 强制单连接，保证 create_all 与后续查询看到同一个库
    - 连接随 dispose 释放，内存库自动销毁
    """
    engine_kwargs: dict = {"echo": False}
    if _use_sqlite:
        engine_kwargs["poolclass"] = StaticPool
        # connect_args: SQLite 内存模式不需要 check_same_thread
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_async_engine(TEST_DATABASE_URL, **engine_kwargs)

    # 创建所有表（读取 Base 的所有继承类）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """创建测试用数据库会话

    每个测试用例获取一个独立会话。
    测试结束后自动回滚，不会影响其他测试。

    这模拟了 FastAPI 的 get_db 依赖，但使用测试数据库。
    """
    session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session
        # 不回滚，让 commit 真实写入（这样测试更接近真实场景）
        # 但因为是内存 SQLite，测试结束自动丢弃


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """创建模拟 HTTP 客户端

    这个客户端直接调用 FastAPI 的路由，不需要启动服务器。
    有点"前端发请求到后端"的模拟版。

    关键操作：
    - override 了 get_db 依赖，让测试使用测试数据库
    - 测试结束后恢复原始依赖
    """
    # 覆盖 FastAPI 的 get_db 依赖
    # 这样路由里 Depends(get_db) 获取的是我们的测试会话
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # ASGITransport 让 httpx 可以直接调用 FastAPI ASGI 应用
    # 不需要启动 uvicorn 服务器，测试更快
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # 测试结束，恢复原始依赖
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(autouse=True)
async def disable_rate_limit():
    """自动禁用所有限流（每个测试函数自动生效）

    原理：设置 rate_limit 模块的 RATE_LIMIT_DISABLED = True，
    RateLimit 函数会跳过检查。

    autouse=True 表示所有测试自动使用这个 fixture，不需要显式声明。
    """
    rate_limit_module.RATE_LIMIT_DISABLED = True
    yield
    rate_limit_module.RATE_LIMIT_DISABLED = False


@pytest_asyncio.fixture
async def sample_user_data() -> dict:
    """提供测试用的用户注册数据

    这是一个"数据 fixture"——不涉及数据库操作，只是返回一个字典。
    pytest 会缓存这个 fixture 的返回值（scope="function" 默认）。
    """
    return {
        "email": "test@example.com",
        "username": "testuser",
        "password": "testpass123",
    }


@pytest_asyncio.fixture
async def auth_token(client: AsyncClient, sample_user_data: dict) -> str:
    """注册一个测试用户并返回 JWT token

    这是一个"复合 fixture"——依赖其他 fixture（client + sample_user_data）。
    pytest 自动管理依赖链。

    用途：需要认证的测试可以直接用这个 fixture 获取 token。
    """
    response = await client.post("/api/v1/auth/register", json=sample_user_data)
    assert response.status_code == 201
    return response.json()["access_token"]


@pytest_asyncio.fixture
async def auth_headers(auth_token: str) -> dict:
    """返回包含认证信息的 HTTP Header

    这个 fixture 依赖于 auth_token，
    返回可以直接传入 httpx 客户端的 headers 字典。

    用法：
        response = await client.get("/api/v1/me", headers=auth_headers)
    """
    return {"Authorization": f"Bearer {auth_token}"}
