"""Agent 结果状态判断。"""

from typing import Any


def result_needs_user_input(result: dict[str, Any] | None) -> bool:
    """判断 Agent 是否在等待用户补充，而不是真正完成。"""

    if not isinstance(result, dict):
        return False
    return any(
        isinstance(step, dict) and step.get("status") == "needs_input"
        for step in result.get("steps") or []
    )
