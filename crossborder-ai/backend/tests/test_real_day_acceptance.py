"""真实一天端到端验收证据门禁测试。"""

import json
from pathlib import Path

from app.services.real_day_acceptance import (
    build_real_day_manifest_template,
    evaluate_real_day_evidence,
)


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


def _manifest(evidence_dir: Path) -> dict:
    references = {
        "listing_publish": {
            "product_id": "gid://shopify/Product/1",
            "listing_id": "listing-1",
        },
        "order_fulfillment": {
            "order_id": "order-1",
            "fulfillment_id": "fulfillment-1",
            "tracking_number": "TRACK123",
        },
        "order_cancel_refund": {
            "order_id": "order-2",
            "cancellation_id": "cancel-1",
            "refund_id": "refund-1",
        },
        "customer_email": {
            "message_id": "<message-1@example.com>",
            "delivery_record": "delivered",
        },
        "daily_close": {
            "plan_date": "2026-11-20",
            "close_record_id": "close-1",
        },
    }
    steps = []
    for step_id in REQUIRED_STEPS:
        suffix = "mp4" if step_id == "mobile_only" else "png"
        evidence_name = f"{step_id}.{suffix}"
        (evidence_dir / evidence_name).write_bytes(b"evidence")
        steps.append(
            {
                "id": step_id,
                "status": "passed",
                "summary": f"{step_id} completed",
                "evidence": [evidence_name],
                "references": references.get(step_id, {}),
            }
        )
    return {
        "schema_version": "1",
        "workspace_id": "workspace-e2e",
        "environment": {
            "shopify_store": "veya-test.myshopify.com",
            "mailbox": "e2e@example.com",
            "mobile_platform": "ios",
            "device_model": "iPhone 16 Pro",
        },
        "started_at": "2026-11-20T08:00:00+08:00",
        "ended_at": "2026-11-20T20:00:00+08:00",
        "steps": steps,
    }


def test_real_day_acceptance_accepts_complete_evidence(tmp_path) -> None:
    manifest = _manifest(tmp_path)
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    report = evaluate_real_day_evidence(manifest, tmp_path)

    assert report["passed"] is True
    assert report["blockers"] == []


def test_real_day_acceptance_rejects_missing_step(tmp_path) -> None:
    manifest = _manifest(tmp_path)
    manifest["steps"] = [
        step
        for step in manifest["steps"]
        if step["id"] != "order_cancel_refund"
    ]

    report = evaluate_real_day_evidence(manifest, tmp_path)

    assert report["passed"] is False
    assert "required_step_missing" in {
        item["code"] for item in report["blockers"]
    }


def test_real_day_acceptance_rejects_evidence_path_escape(tmp_path) -> None:
    manifest = _manifest(tmp_path)
    manifest["steps"][0]["evidence"] = ["../../outside.png"]

    report = evaluate_real_day_evidence(manifest, tmp_path)

    assert report["passed"] is False
    assert "evidence_path_escape" in {
        item["code"] for item in report["blockers"]
    }


def test_real_day_acceptance_requires_platform_references(tmp_path) -> None:
    manifest = _manifest(tmp_path)
    listing = next(
        step for step in manifest["steps"] if step["id"] == "listing_publish"
    )
    listing["references"] = {"product_id": "product-1"}

    report = evaluate_real_day_evidence(manifest, tmp_path)

    assert report["passed"] is False
    assert any(
        item["code"] == "reference_missing"
        and item["step"] == "listing_publish"
        for item in report["blockers"]
    )


def test_real_day_acceptance_rejects_failed_step(tmp_path) -> None:
    manifest = _manifest(tmp_path)
    manifest["steps"][0]["status"] = "failed"

    report = evaluate_real_day_evidence(manifest, tmp_path)

    assert report["passed"] is False
    assert "step_not_passed" in {
        item["code"] for item in report["blockers"]
    }


def test_real_day_acceptance_rejects_cross_day_evidence(tmp_path) -> None:
    manifest = _manifest(tmp_path)
    manifest["ended_at"] = "2026-11-21T00:00:00+08:00"

    report = evaluate_real_day_evidence(manifest, tmp_path)

    assert report["passed"] is False
    assert "cross_day_invalid" in {
        item["code"] for item in report["blockers"]
    }


def test_real_day_acceptance_requires_mobile_recording(tmp_path) -> None:
    manifest = _manifest(tmp_path)
    mobile = next(
        step for step in manifest["steps"] if step["id"] == "mobile_only"
    )
    mobile["evidence"] = ["mobile_only.png"]
    (tmp_path / "mobile_only.png").write_bytes(b"image")

    report = evaluate_real_day_evidence(manifest, tmp_path)

    assert report["passed"] is False
    assert "mobile_recording_missing" in {
        item["code"] for item in report["blockers"]
    }


def test_real_day_manifest_template_never_claims_passed() -> None:
    manifest = build_real_day_manifest_template()

    assert len(manifest["steps"]) == len(REQUIRED_STEPS)
    assert all(step["status"] == "pending" for step in manifest["steps"])
    listing = next(
        step for step in manifest["steps"] if step["id"] == "listing_publish"
    )
    assert set(listing["references"]) == {"product_id", "listing_id"}


def test_real_day_acceptance_rejects_invalid_metadata_and_absolute_path(
    tmp_path,
) -> None:
    manifest = _manifest(tmp_path)
    manifest["schema_version"] = "0"
    manifest["workspace_id"] = ""
    manifest["environment"]["shopify_store"] = ""
    manifest["environment"]["mobile_platform"] = "desktop"
    manifest["started_at"] = "2026-11-20T08:00:00"
    manifest["steps"][0]["evidence"] = [str(tmp_path / "morning_plan.png")]

    report = evaluate_real_day_evidence(manifest, tmp_path)

    codes = {item["code"] for item in report["blockers"]}
    assert {
        "schema_version_invalid",
        "workspace_id_missing",
        "shopify_store_missing",
        "mobile_platform_invalid",
        "timezone_missing",
        "evidence_path_absolute",
    } <= codes


def test_real_day_acceptance_rejects_empty_file_and_long_duration(
    tmp_path,
) -> None:
    manifest = _manifest(tmp_path)
    (tmp_path / "morning_plan.png").write_bytes(b"")
    manifest["started_at"] = "2026-11-20T00:00:00+08:00"
    manifest["ended_at"] = "2026-11-20T23:00:00+08:00"

    report = evaluate_real_day_evidence(manifest, tmp_path)

    codes = {item["code"] for item in report["blockers"]}
    assert "evidence_file_empty" in codes
    assert "duration_exceeded" in codes
