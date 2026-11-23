"""真实一天端到端验收证据门禁。"""

from datetime import datetime
from pathlib import Path


REQUIRED_STEPS = (
    "morning_plan",
    "product_intake",
    "listing_publish",
    "order_fulfillment",
    "price_inventory_update",
    "order_cancel_refund",
    "customer_email",
    "after_sales",
    "daily_close",
    "mobile_only",
)

REQUIRED_REFERENCES = {
    "listing_publish": ("product_id", "listing_id"),
    "order_fulfillment": (
        "order_id",
        "fulfillment_id",
        "tracking_number",
    ),
    "order_cancel_refund": (
        "order_id",
        "cancellation_id",
        "refund_id",
    ),
    "customer_email": ("message_id", "delivery_record"),
    "daily_close": ("plan_date", "close_record_id"),
}


def _issue(code: str, message: str, step: str | None = None) -> dict:
    payload = {"code": code, "message": message}
    if step is not None:
        payload["step"] = step
    return payload


def build_real_day_manifest_template() -> dict:
    """生成永不默认通过的验收模板，供真实执行人填写。"""

    steps = []
    for step_id in REQUIRED_STEPS:
        references = {
            name: ""
            for name in REQUIRED_REFERENCES.get(step_id, ())
        }
        steps.append(
            {
                "id": step_id,
                "status": "pending",
                "summary": "",
                "evidence": [],
                "references": references,
            }
        )
    return {
        "schema_version": "1",
        "workspace_id": "",
        "environment": {
            "shopify_store": "",
            "mailbox": "",
            "mobile_platform": "ios",
            "device_model": "",
        },
        "started_at": "",
        "ended_at": "",
        "steps": steps,
    }


def evaluate_real_day_evidence(
    manifest: dict,
    evidence_dir: Path,
) -> dict:
    """严格验证真实资源编号和文件证据，不做任何平台副作用。"""

    blockers: list[dict] = []
    warnings: list[dict] = []
    root = evidence_dir.resolve()
    if not root.is_dir():
        blockers.append(_issue("evidence_dir_missing", "验收目录不存在"))

    if manifest.get("schema_version") != "1":
        blockers.append(
            _issue("schema_version_invalid", "manifest schema_version 必须为 1")
        )
    if not str(manifest.get("workspace_id") or "").strip():
        blockers.append(_issue("workspace_id_missing", "缺少测试工作区 ID"))

    environment = manifest.get("environment") or {}
    for field, code, label in (
        ("shopify_store", "shopify_store_missing", "Shopify 测试店"),
        ("mailbox", "mailbox_missing", "真实邮箱"),
        ("device_model", "device_model_missing", "设备型号"),
    ):
        if not str(environment.get(field) or "").strip():
            blockers.append(_issue(code, f"缺少{label}"))
    platform = str(environment.get("mobile_platform") or "").lower()
    if platform not in {"ios", "android"}:
        blockers.append(
            _issue(
                "mobile_platform_invalid",
                "mobile_platform 必须为 ios 或 android",
            )
        )

    started_at = _parse_time(manifest.get("started_at"), "started_at", blockers)
    ended_at = _parse_time(manifest.get("ended_at"), "ended_at", blockers)
    if started_at is not None and ended_at is not None:
        if ended_at < started_at:
            blockers.append(
                _issue("time_order_invalid", "结束时间早于开始时间")
            )
        elif ended_at.date() != started_at.date():
            blockers.append(
                _issue("cross_day_invalid", "真实一天验收不能跨自然日")
            )
        elif ended_at - started_at > _hours(18):
            blockers.append(
                _issue("duration_exceeded", "验收跨度不能超过 18 小时")
            )

    raw_steps = manifest.get("steps")
    if not isinstance(raw_steps, list):
        blockers.append(_issue("steps_invalid", "steps 必须为数组"))
        raw_steps = []
    steps_by_id: dict[str, dict] = {}
    for step in raw_steps:
        step_id = str(step.get("id") or "")
        if step_id in steps_by_id:
            blockers.append(
                _issue("duplicate_step", f"步骤重复：{step_id}", step_id)
            )
        else:
            steps_by_id[step_id] = step

    for step_id in REQUIRED_STEPS:
        step = steps_by_id.get(step_id)
        if step is None:
            blockers.append(
                _issue("required_step_missing", f"缺少步骤：{step_id}", step_id)
            )
            continue
        if step.get("status") != "passed":
            blockers.append(
                _issue("step_not_passed", "步骤未通过", step_id)
            )
        evidence_items = step.get("evidence")
        if not isinstance(evidence_items, list) or not evidence_items:
            blockers.append(
                _issue("evidence_missing", "步骤没有证据文件", step_id)
            )
        else:
            for relative in evidence_items:
                _validate_evidence_file(
                    root,
                    str(relative),
                    step_id,
                    blockers,
                )
        references = step.get("references") or {}
        for reference in REQUIRED_REFERENCES.get(step_id, ()):
            if not str(references.get(reference) or "").strip():
                blockers.append(
                    _issue(
                        "reference_missing",
                        f"缺少资源编号：{reference}",
                        step_id,
                    )
                )

    mobile_step = steps_by_id.get("mobile_only") or {}
    mobile_evidence = mobile_step.get("evidence") or []
    if not any(
        str(item).lower().endswith((".mp4", ".mov"))
        for item in mobile_evidence
    ):
        blockers.append(
            _issue(
                "mobile_recording_missing",
                "mobile_only 必须包含录屏",
                "mobile_only",
            )
        )

    return {
        "passed": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "steps_checked": len(REQUIRED_STEPS),
        "evidence_root": str(root),
    }


def _parse_time(
    value,
    field: str,
    blockers: list[dict],
) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        blockers.append(_issue("time_invalid", f"{field} 不是有效时间"))
        return None
    if parsed.tzinfo is None:
        blockers.append(_issue("timezone_missing", f"{field} 必须包含时区"))
        return None
    return parsed


def _validate_evidence_file(
    root: Path,
    relative: str,
    step_id: str,
    blockers: list[dict],
) -> None:
    path = Path(relative)
    if path.is_absolute():
        blockers.append(
            _issue("evidence_path_absolute", "证据必须使用相对路径", step_id)
        )
        return
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        blockers.append(
            _issue("evidence_path_escape", "证据路径越过验收目录", step_id)
        )
        return
    if not resolved.is_file():
        blockers.append(
            _issue("evidence_file_missing", f"证据不存在：{relative}", step_id)
        )
        return
    if resolved.stat().st_size <= 0:
        blockers.append(
            _issue("evidence_file_empty", f"证据为空：{relative}", step_id)
        )


def _hours(value: int):
    from datetime import timedelta

    return timedelta(hours=value)
