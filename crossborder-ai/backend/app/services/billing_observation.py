"""首个账期只读观察快照与连续天数评估。"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.production_cutover import run_cutover_check


def _issue(code: str, message: str, **details) -> dict:
    return {
        "code": code,
        "message": message,
        **details,
    }


async def count_duplicate_monthly_allowances(
    db: AsyncSession,
    *,
    since: datetime,
) -> int:
    """统计同工作区、同套餐、同月份重复发放的月度额度分组。"""

    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        period_expression = (
            "to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM')"
        )
    elif dialect == "sqlite":
        period_expression = "strftime('%Y-%m', created_at)"
    else:
        raise ValueError("重复月度额度检查只支持 PostgreSQL 和 SQLite")

    statement = text(
        f"""
        SELECT COUNT(*)
        FROM (
            SELECT
                workspace_id,
                reference_id,
                period_key,
                COUNT(*) AS allowance_count
            FROM (
                SELECT
                    workspace_id,
                    reference_id,
                    {period_expression} AS period_key
                FROM credit_transactions
                WHERE feature = 'monthly_allowance'
                  AND workspace_id IS NOT NULL
                  AND created_at >= :since
            ) allowances
            GROUP BY workspace_id, reference_id, period_key
            HAVING COUNT(*) > 1
        ) duplicate_groups
        """
    )
    return int(
        (
            await db.execute(
                statement,
                {"since": since},
            )
        ).scalar_one()
        or 0
    )


async def collect_billing_observation(
    db: AsyncSession,
    *,
    observed_at: datetime,
    since: datetime,
    previous: dict | None = None,
    allow_sqlite: bool = False,
    batch_size: int = 500,
) -> dict:
    """执行只读后置门禁、重复额度检查并生成单日观察。"""

    gate = await run_cutover_check(
        db,
        "postflight",
        allow_sqlite=allow_sqlite,
        batch_size=batch_size,
    )
    duplicates = await count_duplicate_monthly_allowances(
        db,
        since=since,
    )
    return evaluate_billing_observation(
        gate=gate,
        previous=previous,
        duplicate_monthly_allowances=duplicates,
        observed_at=observed_at,
        since=since,
    )


def evaluate_billing_observation(
    *,
    gate: dict,
    previous: dict | None,
    duplicate_monthly_allowances: int,
    observed_at: datetime,
    since: datetime,
) -> dict:
    """把生产门禁和重复额度结果收敛为单日观察结论。"""

    issues: list[dict] = [
        _issue(
            item["code"],
            item["message"],
        )
        for item in gate.get("blockers", [])
    ]
    if duplicate_monthly_allowances > 0:
        issues.append(
            _issue(
                "duplicate_monthly_allowance",
                "同一工作区、套餐和月份存在重复月度额度",
                count=duplicate_monthly_allowances,
            )
        )

    current_counts = (gate.get("snapshot") or {}).get("counts") or {}
    current_missing_period = int(
        current_counts.get("personal_wallets_missing_period") or 0
    )
    if previous is not None:
        previous_counts = (
            (previous.get("snapshot") or {}).get("counts") or {}
        )
        previous_missing_period = int(
            previous_counts.get("personal_wallets_missing_period") or 0
        )
        increase = current_missing_period - previous_missing_period
        if increase > 0:
            issues.append(
                _issue(
                    "missing_period_increased",
                    "个人工作区钱包额度周期空值数量增加",
                    increase=increase,
                )
            )

    return {
        "status": "failed" if issues else "passed",
        "observed_at": observed_at.isoformat(),
        "since": since.isoformat(),
        "issues": issues,
        "warnings": gate.get("warnings", []),
        "snapshot": {
            "revision": (gate.get("snapshot") or {}).get("revision"),
            "counts": {
                **current_counts,
                "personal_wallets_missing_period": current_missing_period,
            },
            "billing_summary": (
                ((gate.get("snapshot") or {}).get("billing") or {}).get(
                    "summary"
                )
                or {}
            ),
            "duplicate_monthly_allowances": duplicate_monthly_allowances,
        },
    }


def summarize_observation_history(observations: list[dict]) -> dict:
    """按自然日保留最新快照，并计算末尾连续通过天数。"""

    latest_by_day: dict[str, tuple[datetime, dict]] = {}
    for observation in observations:
        try:
            observed_at = datetime.fromisoformat(
                str(observation["observed_at"])
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("观察快照时间格式无效") from exc
        day = observed_at.date().isoformat()
        existing = latest_by_day.get(day)
        if existing is None or observed_at > existing[0]:
            latest_by_day[day] = (observed_at, observation)

    ordered = [
        item[1]
        for _, item in sorted(
            latest_by_day.items(),
            key=lambda pair: pair[1][0],
        )
    ]
    streak = 0
    for observation in reversed(ordered):
        if observation.get("status") != "passed":
            break
        streak += 1
    return {
        "consecutive_passed_days": streak,
        "gate_passed": streak >= 7,
        "latest_status": (
            ordered[-1].get("status") if ordered else None
        ),
        "latest_observed_at": (
            ordered[-1].get("observed_at") if ordered else None
        ),
        "observation_days": len(ordered),
    }


def read_observation_files(directory: Path) -> list[dict]:
    """严格读取观察 JSON；损坏文件不能被静默跳过。"""

    observations: list[dict] = []
    for path in sorted(directory.glob("observation-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"观察快照无法解析：{path.name}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"观察快照不是 JSON 对象：{path.name}")
        observations.append(payload)
    return observations


def latest_observation_before(
    observations: list[dict],
    observed_at: datetime,
) -> dict | None:
    """只返回严格早于当前观测的历史快照，便于同日重跑。"""

    candidates: list[tuple[datetime, dict]] = []
    for observation in observations:
        try:
            item_time = datetime.fromisoformat(
                str(observation["observed_at"])
            )
        except (KeyError, TypeError, ValueError):
            continue
        if item_time.tzinfo is None:
            item_time = item_time.replace(tzinfo=observed_at.tzinfo)
        if item_time < observed_at:
            candidates.append((item_time, observation))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def persist_billing_observation(
    directory: Path,
    observation: dict[str, Any],
) -> dict:
    """写入单日快照和汇总，返回带连续天数的最新观察。"""

    try:
        observed_at = datetime.fromisoformat(
            str(observation["observed_at"])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("观察快照时间格式无效") from exc

    directory.mkdir(parents=True, exist_ok=True)
    existing = read_observation_files(directory)
    history = summarize_observation_history([*existing, observation])
    stored = {**observation, "history": history}
    observation_path = directory / (
        f"observation-{observed_at:%Y%m%dT%H%M%SZ}.json"
    )
    observation_path.write_text(
        json.dumps(stored, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = {
        **history,
        "latest_file": observation_path.name,
        "updated_at": observed_at.isoformat(),
    }
    (directory / "billing-observation-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "observation": stored,
        "history": history,
        "summary": summary,
        "path": observation_path,
    }
