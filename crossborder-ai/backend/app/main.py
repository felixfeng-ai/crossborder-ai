"""VeyaShip - Main Application Entry Point."""

import traceback
import time
import logging

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Scope, Receive, Send
from sqlalchemy.exc import DataError, IntegrityError

from app.core.config import settings
from app.core.database import init_db
from app.core.observability import (
    init_sentry,
    new_request_id,
    request_id_var,
    setup_logging,
)
from app.models.user import InsufficientCreditsError
from app.routers import auth, users, products, content, images, billing, shopify, batch, radar, ledger, analytics, agent, listings, platforms, product_variants, catalog, operations
from app.routers import settings as settings_router

# ── 日志配置（可观测性：所有日志自动携带 request_id）──────────
setup_logging()
logger = logging.getLogger("veyaship")


# ── 请求日志中间件 ────────────────────────────────────────────
class RequestLogMiddleware:
    """记录每个 HTTP 请求的方法、路径、状态码、耗时，并分配 X-Request-ID。

    request_id 写入 asyncio ContextVar，随异步调用自动传播——
    Agent 循环、定时任务等内部日志都能带上同一 ID，跨步骤可串联。
    响应头带 X-Request-ID，用户/客服反馈时可用它定位日志。
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = new_request_id()
        request_id_var.set(request_id)
        start = time.time()
        method = scope.get("method", "?")
        path = scope.get("path", "?")

        async def _send(message):
            if message["type"] == "http.response.start":
                # 响应头带上 request_id（ASGI headers 是二元组列表）
                headers = list(message.get("headers", []))
                headers.append((b"X-Request-ID", request_id.encode()))
                message["headers"] = headers

                status = message["status"]
                elapsed = time.time() - start
                logger.info("%s %s → %d (%.0fms)", method, path, status, elapsed * 1000)
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception as exc:
            elapsed = time.time() - start
            logger.error("%s %s → ERROR (%dms): %s", method, path, elapsed * 1000, str(exc))
            raise
        finally:
            request_id_var.set(None)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    print(f"[VeyaShip] v{settings.APP_VERSION} starting...")

    # 配置了 SENTRY_DSN 则接入错误告警（幂等，未配置直接跳过）
    init_sentry()

    # 启动时检查密钥是否已配置
    if not settings.SECRET_KEY:
        print("[VeyaShip] WARNING: SECRET_KEY 未设置！请在 .env 中配置")
    if not settings.JWT_SECRET_KEY:
        print("[VeyaShip] WARNING: JWT_SECRET_KEY 未设置！请在 .env 中配置")

    await init_db()
    from app.services import provider_config
    from app.core.database import async_session_factory
    async with async_session_factory() as db:
        await provider_config.refresh(db)
    print(f"[VeyaShip] Database ready ({'SQLite' if settings.USE_SQLITE else 'PostgreSQL'})")

    # 启动定时任务
    from app.services.scheduler import SchedulerService
    scheduler = SchedulerService()
    try:
        await scheduler.start()
    except Exception as e:
        print(f"[VeyaShip] WARNING: Scheduler 启动失败：{e}")

    yield
    try:
        await scheduler.stop()
    except Exception:
        pass
    print("[VeyaShip] shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DOCS_ENABLED else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
    lifespan=lifespan,
)


# ── 全局异常处理器 ────────────────────────────────────────────
@app.exception_handler(InsufficientCreditsError)
async def insufficient_credits_handler(request: Request, exc: InsufficientCreditsError) -> JSONResponse:
    """积分不足 → 402。行级锁下并发扣分触发的 ValueError 不再变 500。"""
    logger.info("Insufficient credits on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        content={"detail": str(exc)},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """捕获所有未处理的异常，返回安全错误响应。

    生产环境不暴露内部错误细节，DEBUG 模式下显示详细错误。
    """
    # HTTPException 是已知的业务错误，直接返回给用户
    if isinstance(exc, HTTPException):
        raise exc

    # SQLAlchemy DataError（如字段超长、类型不匹配）→ 用户输入问题
    if isinstance(exc, DataError):
        logger.warning("DataError on %s %s: %s", request.method, request.url.path, str(exc))
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "输入数据格式有误，请检查后重试"},
        )

    # SQLAlchemy IntegrityError（如违反唯一约束）
    if isinstance(exc, IntegrityError):
        logger.warning("IntegrityError on %s %s: %s", request.method, request.url.path, str(exc))
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "数据冲突，请检查是否已存在相同记录"},
        )

    # 未预期的内部错误
    logger.error("Unhandled exception on %s %s: %s\n%s",
                 request.method, request.url.path, str(exc), traceback.format_exc())

    if settings.DEBUG:
        detail = f"{type(exc).__name__}: {str(exc)}"
    else:
        detail = "服务器内部错误，请稍后重试"

    return JSONResponse(
        status_code=500,
        content={"detail": detail},
    )


# 请求日志中间件（最外层，记录所有请求）
app.add_middleware(RequestLogMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routes ---
API_PREFIX = settings.API_V1_PREFIX
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(products.router, prefix=API_PREFIX)
app.include_router(settings_router.router, prefix=API_PREFIX)
app.include_router(content.router, prefix=API_PREFIX)
app.include_router(images.router, prefix=API_PREFIX)
app.include_router(billing.router, prefix=API_PREFIX)
app.include_router(shopify.router, prefix=API_PREFIX)
app.include_router(batch.router, prefix=API_PREFIX)
app.include_router(radar.router, prefix=API_PREFIX)
app.include_router(ledger.router, prefix=API_PREFIX)
app.include_router(analytics.router, prefix=API_PREFIX)
app.include_router(agent.router, prefix=API_PREFIX)
app.include_router(listings.router, prefix=API_PREFIX)
app.include_router(platforms.router, prefix=API_PREFIX)
app.include_router(product_variants.router, prefix=API_PREFIX)
app.include_router(catalog.router, prefix=API_PREFIX)
app.include_router(operations.router, prefix=API_PREFIX)


# --- Health Check ---
@app.get("/health", tags=["System"])
async def health_check():
    """健康检查：返回服务状态、版本、数据库连接状态。"""
    db_ok = False
    try:
        from app.core.database import async_session_factory
        async with async_session_factory() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "healthy" if db_ok else "degraded",
        "version": settings.APP_VERSION,
        "database": "connected" if db_ok else "disconnected",
        "debug": settings.DEBUG,
    }
