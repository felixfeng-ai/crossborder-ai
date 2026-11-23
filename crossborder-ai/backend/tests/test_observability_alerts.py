"""可观测性告警桥接测试。"""

import sys
import types

from app.core import observability
from app.core.config import settings


def test_emit_alert_writes_log_and_sentry(monkeypatch):
    captured = {}
    log_messages = []

    class FakeSentry:
        @staticmethod
        def capture_message(message, level):
            captured["message"] = message
            captured["level"] = level

    monkeypatch.setattr(settings, "SENTRY_DSN", "https://example.invalid/1")
    monkeypatch.setitem(sys.modules, "sentry_sdk", FakeSentry)
    monkeypatch.setattr(
        observability,
        "_write_alert_log",
        lambda detail, level: log_messages.append(detail),
    )

    observability.emit_alert(
        "账务对账发现差异",
        context={"wallets": 2},
    )

    assert captured["message"] == "账务对账发现差异 | {'wallets': 2}"
    assert captured["level"] == "warning"
    assert "账务对账发现差异" in log_messages[0]


def test_emit_alert_works_without_sentry(monkeypatch):
    monkeypatch.setattr(settings, "SENTRY_DSN", "")
    monkeypatch.setitem(
        sys.modules,
        "sentry_sdk",
        types.SimpleNamespace(
            capture_message=lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("未配置 Sentry 时不应调用")
            )
        ),
    )
    log_messages = []
    monkeypatch.setattr(
        observability,
        "_write_alert_log",
        lambda detail, level: log_messages.append(detail),
    )

    observability.emit_alert("普通告警")

    assert "普通告警" in log_messages[0]
