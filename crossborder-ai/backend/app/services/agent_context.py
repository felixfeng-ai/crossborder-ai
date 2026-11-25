"""Agent 会话上下文、确认语句和待执行动作的纯函数。"""

from dataclasses import dataclass
import json
import re
from typing import Any


HISTORY_MESSAGE_LIMIT = 12
HISTORY_MESSAGE_CHAR_LIMIT = 1800
HISTORY_TOTAL_CHAR_LIMIT = 12000

CONFIRMABLE_ACTIONS = {
    "generate_product_image",
    "generate_image_asset",
    "generate_product_video",
}


@dataclass(frozen=True)
class PendingAction:
    action: str
    params: dict[str, Any]
    estimated_credits: int | None = None


def compact_conversation_history(
    messages: list[dict[str, Any]],
    *,
    current_instruction: str = "",
) -> list[dict[str, str]]:
    """保留最近有限条用户/助手消息，并剔除已单独传入的当前用户消息。"""
    compacted: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role") or "")
        if role not in {"user", "assistant"}:
            continue
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        compacted.append(
            {
                "role": role,
                "content": content[:HISTORY_MESSAGE_CHAR_LIMIT],
            }
        )

    if current_instruction:
        for index in range(len(compacted) - 1, -1, -1):
            message = compacted[index]
            if (
                message["role"] == "user"
                and message["content"].strip() == current_instruction.strip()
            ):
                compacted.pop(index)
                break

    compacted = compacted[-HISTORY_MESSAGE_LIMIT:]
    total = 0
    bounded: list[dict[str, str]] = []
    for message in reversed(compacted):
        length = len(message["content"])
        if total + length > HISTORY_TOTAL_CHAR_LIMIT:
            break
        bounded.append(message)
        total += length
    bounded.reverse()
    return bounded


def is_confirmation(instruction: str) -> bool:
    """只接受短而明确的确认，问题、否定和补充修改继续交给模型理解。"""
    normalized = re.sub(r"\s+", "", str(instruction or "")).strip()
    if not normalized:
        return False
    if any(word in normalized for word in ("不要", "不用", "取消", "先别", "别执行", "不可以")):
        return False
    return bool(
        re.fullmatch(
            r"(?:可以|好的?|行|确认|继续|按这个来|就这个|没问题|开始吧|执行吧)"
            r"(?:[,，。.!！]?(?:开始|继续|执行|生成|按这个来)?吧?)?[。.!！]?",
            normalized,
        )
    )


def _parse_steps(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def extract_pending_action(messages: list[dict[str, Any]]) -> PendingAction | None:
    """从最近一条带结构化步骤的助手消息中提取待确认动作。"""
    for message in reversed(messages):
        if str(message.get("role") or "") != "assistant":
            continue
        steps = _parse_steps(message.get("steps"))
        for step in reversed(steps):
            data = step.get("data")
            if not isinstance(data, dict):
                continue
            pending = data.get("pending_action")
            if not isinstance(pending, dict):
                continue
            action = str(pending.get("action") or "").strip()
            params = pending.get("params")
            if action not in CONFIRMABLE_ACTIONS or not isinstance(params, dict):
                continue
            credits = pending.get("estimated_credits")
            return PendingAction(
                action=action,
                params=dict(params),
                estimated_credits=(
                    int(credits)
                    if isinstance(credits, (int, float, str)) and str(credits).isdigit()
                    else None
                ),
            )
    return None


def build_system_prompt(workspace: str) -> str:
    """按工作区构造角色提示，共享安全规则和工具使用边界。"""
    base_rules = (
        "规则：\n"
        "1. 必须结合会话历史理解确认、继续、指代和参数补充\n"
        "2. 需要业务数据或执行操作时调用相应工具\n"
        "3. 不要编造工具没有返回的数据\n"
        "4. 最终回答使用简短中文，不重复完整报告\n"
        "5. 会扣积分的操作必须先调用工具并传 confirmed=false，生成结构化待确认任务\n"
        "6. 用户确认后优先恢复待确认动作，不重新猜测任务\n"
        "7. 生成图片或视频后只报告任务状态，不声称素材已经完成\n"
        "8. 商品图和广告图默认不生成任何文字、数字、水印或字幕\n"
        "9. 标题、卖点、价格和 CTA 使用前端模板后处理，不交给生图模型排版\n"
        "10. 商品主图优先使用带参考图的 generate_image_asset\n"
        "11. 用户要求找 1688 货源、找同款或供应商时，生成简洁中文采购关键词并调用 "
        "find_1688_sources；有真实商品主图时可传 image_url\n"
        "12. 1688 搜索结果只能称为相似货源，不能宣称同款，不得自动询价、加购、下单或付款\n"
        "13. 泛化的同品类推荐只调用一次 select_products，使用最贴近当前商品的关键词；"
        "不得自行扩展多个近义关键词连续查询\n"
        "14. 最终回答先列本次任务结果；如需引用更早对话，必须明确标注历史结果，"
        "不得把历史结果写成累计执行次数\n"
    )
    if workspace == "marketing":
        role = (
            "你是 VeyaShip 营销 Agent，服务跨境电商卖家的营销活动。\n"
            "优先围绕当前活动、商品、目标市场、预算和素材，完成营销方案、营销图片、"
            "商品视频、广告文案和效果数据任务。\n"
            "15. 用户要求营销方案、活动方案或投放方案时，必须调用 "
            "create_marketing_campaign_plan；有明确商品名即可开始，不要求视频首帧。\n"
            "16. 只有用户明确要求选品、市场分析、竞争分析或商品判断时，才可使用 "
            "select_products、analyze_category、analyze_product_decision；"
            "生成营销方案时不得调用 select_products。\n"
        )
    else:
        role = (
            "你是跨境电商 AI 决策助手。\n"
            "负责选品、商品判断、Listing、供应链分析、店铺巡检、素材生成和合规检查。\n"
        )
    return role + base_rules
