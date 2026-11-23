"""VeyaShip - 可观测性基础设施（request ID + 结构化日志 + Sentry）

最小可落地集合：
1. 每个 HTTP 请求分配唯一 X-Request-ID，注入日志与响应头
2. 日志记录自动携带 request_id，跨多步链路（如 Agent 循环）可串联
3. 配置 SENTRY_DSN 后自动接入 Sentry 错误告警；未配置/未安装则静默跳过
"""

import logging
import uuid
from contextvars import ContextVar

from app.core.config import settings

# 当前请求的 request_id（asyncio ContextVar，随异步调用自动传播，
# Agent 子任务、定时任务内部日志都能带上同一个 ID）
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_LOGGER_NAME = "veyaship"


def new_request_id() -> str:
    """生成短 request_id（12 位十六进制，足够链路唯一）。"""
    return uuid.uuid4().hex[:12]


def get_request_id() -> str | None:
    """获取当前请求的 request_id（无则 None）。"""
    return request_id_var.get()


class RequestIDFilter(logging.Filter):
    """把 request_id 注入每条日志记录，格式里可用 %(request_id)s。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


def setup_logging() -> None:
    """配置 veyaship logger：带 request_id 字段，不向 root 传播。"""
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(getattr(settings, "LOG_LEVEL", "INFO").upper())
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "[VeyaShip] %(asctime)s | %(levelname)-5s | %(request_id)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(handler)
    if not any(isinstance(f, RequestIDFilter) for f in logger.filters):
        logger.addFilter(RequestIDFilter())
    logger.propagate = False  # 避免向 root 重复输出


def init_sentry() -> None:
    """SENTRY_DSN 配置后接入 Sentry；未配置或未安装 sentry-sdk 则跳过。"""
    if not getattr(settings, "SENTRY_DSN", ""):
        return
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment="development" if getattr(settings, "DEBUG", False) else "production",
            release=getattr(settings, "APP_VERSION", "unknown"),
            traces_sample_rate=getattr(settings, "SENTRY_TRACES_SAMPLE_RATE", 0.1),
        )
        logging.getLogger(_LOGGER_NAME).info("Sentry 已启用")
    except ImportError:
        logging.getLogger(_LOGGER_NAME).warning(
            "SENTRY_DSN 已配置但未安装 sentry-sdk，跳过 Sentry"
        )


def _write_alert_log(detail: str, level: str) -> None:
    """内部日志写入点，便于测试替换而不影响全局 logging。"""

    logger = logging.getLogger(_LOGGER_NAME)
    log_method = getattr(logger, level, logger.warning)
    log_method(detail)


def emit_alert(
    message: str,
    *,
    level: str = "warning",
    context: dict | None = None,
) -> None:
    """同时写入结构化日志和 Sentry，供业务级异常告警使用。"""

    detail = (
        f"{message} | {context}"
        if context
        else message
    )
    _write_alert_log(detail, level)

    if not getattr(settings, "SENTRY_DSN", ""):
        return
    try:
        import sentry_sdk

        sentry_sdk.capture_message(detail, level=level)
    except ImportError:
        # 日志已经记录，缺少可选依赖不能影响业务任务。
        return
