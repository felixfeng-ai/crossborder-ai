"""平台政策语料校验、批量入库与检索评测。"""

import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.policy_knowledge import (
    ingest_policy_text,
    search_policy_knowledge,
)


DEFAULT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "policy_corpus"
    / "policy_manifest.json"
)


def load_policy_manifest(
    path: str | Path = DEFAULT_MANIFEST_PATH,
) -> dict[str, Any]:
    """加载并校验正式政策语料与评测问题。"""
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_policy_manifest(manifest)
    return manifest


def validate_policy_manifest(manifest: dict[str, Any]) -> None:
    sources = manifest.get("sources")
    cases = manifest.get("cases")
    if not isinstance(sources, list) or not isinstance(cases, list):
        raise ValueError("政策清单必须包含 sources 和 cases")
    if not sources:
        raise ValueError("政策清单不能为空")
    source_ids = [str(item.get("id") or "") for item in sources]
    if any(not item for item in source_ids):
        raise ValueError("政策来源缺少 id")
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("政策来源 id 重复")
    source_identities = [
        (
            str(item.get("platform") or "").lower(),
            str(item.get("market") or "").upper(),
            str(item.get("category") or "").lower(),
            str(item.get("document_type") or ""),
            str(item.get("source_url") or ""),
            str(item.get("version") or ""),
        )
        for item in sources
    ]
    if len(source_identities) != len(set(source_identities)):
        raise ValueError("政策来源身份字段重复")
    case_ids = [str(item.get("id") or "") for item in cases]
    if any(not item for item in case_ids):
        raise ValueError("评测问题缺少 id")
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("评测问题 id 重复")
    allowed_platforms = {"amazon", "tiktok", "shopify"}
    for source in sources:
        required = {
            "title",
            "platform",
            "market",
            "document_type",
            "source_url",
            "version",
            "content_text",
        }
        missing = required - set(source)
        if missing:
            raise ValueError(
                f"政策来源 {source.get('id')} 缺少字段：{sorted(missing)}"
            )
        if str(source["platform"]).lower() not in allowed_platforms:
            raise ValueError(f"不支持的政策平台：{source['platform']}")
        if len(str(source["content_text"]).strip()) < 20:
            raise ValueError(f"政策来源 {source['id']} 内容过短")
    for case in cases:
        required = {
            "query",
            "platform",
            "market",
            "expect_evidence",
            "expected_source_urls",
        }
        missing = required - set(case)
        if missing:
            raise ValueError(
                f"评测问题 {case.get('id')} 缺少字段：{sorted(missing)}"
            )
        if case["expect_evidence"] and not case["expected_source_urls"]:
            raise ValueError(f"评测问题 {case['id']} 缺少预期来源")


async def ingest_policy_manifest(
    db: AsyncSession,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """按正式语料清单顺序导入政策。"""
    results = []
    for source in manifest["sources"]:
        result = await ingest_policy_text(
            db,
            title=source["title"],
            platform=source["platform"],
            market=source["market"],
            category=source.get("category"),
            document_type=source["document_type"],
            source_url=source["source_url"],
            version=source["version"],
            effective_at=(
                datetime.fromisoformat(
                    str(source["effective_at"]).replace("Z", "+00:00")
                )
                if source.get("effective_at")
                else None
            ),
            content_text=source["content_text"],
        )
        results.append({**result, "id": source["id"]})
    return {
        "total": len(results),
        "changed": sum(item["changed"] for item in results),
        "degraded": sum(
            item["vector_status"] == "degraded" for item in results
        ),
        "items": results,
    }


def _percentile(values: list[float], percentile: float) -> float:
    """按 nearest-rank 计算分位数，避免小样本遗漏尾部延迟。"""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(
        len(ordered) - 1,
        max(0, math.ceil(len(ordered) * percentile) - 1),
    )
    return round(ordered[index], 2)


async def evaluate_policy_retrieval(
    db: AsyncSession,
    manifest: dict[str, Any],
    *,
    search_fn: Callable[..., Awaitable[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """评测 Recall@5、首条引用正确率和无依据识别率。"""
    search = search_fn or search_policy_knowledge
    results = []
    evidence_cases = 0
    recall_hits = 0
    citation_hits = 0
    no_evidence_cases = 0
    no_evidence_hits = 0
    latencies: list[float] = []

    for case in manifest["cases"]:
        started = time.perf_counter()
        response = await search(
            db,
            query=case["query"],
            platform=case["platform"],
            market=case["market"],
            category=case.get("category"),
            top_k=5,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        latencies.append(latency_ms)
        items = response.get("items") or []
        returned_urls = [
            str(item.get("source_url") or "") for item in items
        ]
        expected = set(case["expected_source_urls"])
        if case["expect_evidence"]:
            evidence_cases += 1
            recalled = bool(expected.intersection(returned_urls))
            cited = bool(returned_urls and returned_urls[0] in expected)
            recall_hits += recalled
            citation_hits += cited
            passed = recalled and cited
        else:
            no_evidence_cases += 1
            passed = response.get("has_evidence") is False
            no_evidence_hits += passed
        results.append(
            {
                "id": case["id"],
                "query": case["query"],
                "passed": passed,
                "has_evidence": bool(response.get("has_evidence")),
                "retrieval_mode": response.get("retrieval_mode"),
                "expected_source_urls": sorted(expected),
                "returned_source_urls": returned_urls,
                "latency_ms": round(latency_ms, 2),
            }
        )

    metrics = {
        "recall_at_5": round(
            recall_hits / evidence_cases if evidence_cases else 0.0,
            4,
        ),
        "citation_accuracy": round(
            citation_hits / evidence_cases if evidence_cases else 0.0,
            4,
        ),
        "no_evidence_accuracy": round(
            no_evidence_hits / no_evidence_cases
            if no_evidence_cases
            else 1.0,
            4,
        ),
        "p95_latency_ms": _percentile(latencies, 0.95),
        "max_latency_ms": round(max(latencies) if latencies else 0.0, 2),
        "average_latency_ms": round(
            statistics.mean(latencies) if latencies else 0.0,
            2,
        ),
    }
    passed = (
        metrics["recall_at_5"] >= 0.8
        and metrics["citation_accuracy"] >= 0.95
        and metrics["no_evidence_accuracy"] >= 0.9
        and metrics["p95_latency_ms"] <= 800
        # 小样本冷启动可能落在 p95 之外，最大值也必须受门禁约束。
        and metrics["max_latency_ms"] <= 800
    )
    return {
        "manifest_version": manifest.get("version"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_count": len(manifest["sources"]),
        "case_count": len(manifest["cases"]),
        "metrics": metrics,
        "passed": passed,
        "results": results,
    }
