"""VeyaShip - 电商文案合规检测（普通生成路径后置校验）

把 shopify.py 里 F8 的合规能力收敛复用到这里，供普通文案生成端点使用：
- ``PLATFORM_EXTREME_WORDS``：电商平台极限词库（广告法/平台规则高频词，中文为主）
- ``merge_banned_words(user_words)``：合并用户品牌禁词 + 平台词库
- ``check_text(text, banned_words)``：正则扫出命中词（大小写不敏感、支持中文）
- ``suggest_replacements(violations)``：给出逐词修正建议
- ``ai_review_fix(...)``：可选 AI 深度改写（带 try/except，AI 不可用降级不抛 500）
"""

import json
import re
from typing import Optional

# ── 电商平台极限词库（广告法禁止的绝对化/虚假宣传用词） ──────
# 中文为主 + 常见英文。词条按短语形式收录，扫描时对纯 ASCII 单词加词边界，
# 避免 "best" 误伤 "bestseller"/"Bestwood" 之类。
PLATFORM_EXTREME_WORDS: list[str] = [
    # 绝对化极限词
    "最好", "最佳", "最强", "最大", "最高", "最优", "最便宜", "最低价", "最低", "最先进",
    "最棒", "最强", "极致", "顶级", "顶级品牌", "顶尖", "首创", "第一", "第一名", "第一品牌",
    "销量第一", "销量冠军", "全国第一", "全网第一", "全网最低", "全网最低价", "全网最便宜",
    "史上最低", "史无前例", "独一无二", "唯一", "万能", "永久", "永不", "绝对", "极品",
    "100%", "百分百", "百分之百", "零风险", "无效退款", "国家免检", "国家级", "纯天然",
    "完美", "满分", "百分百安全", "零副作用", "无任何副作用", "立刻见效", "立竿见影",
    "根治", "治愈", "彻底治愈", "医学级", "药妆级",
    # 常见英文
    "best", "cheapest", "#1", "number one", "top rated", "no.1", "100%", "zero risk",
    "guaranteed", "perfect",
]

# 常见极限词 → 合规中性替代（未被收录的词给出空 replacement，提示手动改写）
EXTREME_REPLACEMENTS: dict[str, str] = {
    "最好": "品质出众",
    "最佳": "优选",
    "最强": "表现出色",
    "最大": "容量可观",
    "最高": "领先",
    "最便宜": "价格更实惠",
    "最低价": "优惠价格",
    "全网最低": "高性价比",
    "全网最低价": "价格实惠",
    "第一": "名列前茅",
    "第一名": "头部梯队",
    "销量第一": "销量领先",
    "顶级": "高品质",
    "顶尖": "行业领先",
    "极致": "精心打磨",
    "100%": "几乎全部",
    "百分百": "几乎全部",
    "零风险": "低风险",
    "完美": "出色",
    "绝对": "明显",
    "国家级": "权威机构认可",
    "纯天然": "温和配方",
    "根治": "有助改善",
    "治愈": "有助舒缓",
    "永久": "经久耐用",
    "唯一": "特色",
    "best": "exceptional",
    "cheapest": "affordable",
    "top rated": "well-reviewed",
    "guaranteed": "designed to",
    "perfect": "excellent",
}


def _is_ascii_word(word: str) -> bool:
    """词条是否纯 ASCII 单词（首尾都是字母/数字，可用 \\b 加边界）。"""
    return bool(word) and bool(re.fullmatch(r"[A-Za-z0-9]+", word))


def _word_regex(word: str) -> re.Pattern:
    """把禁词转成正则：纯 ASCII 词加词边界，中文/带符号词用字面匹配。"""
    escaped = re.escape(word)
    if _is_ascii_word(word):
        return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)
    return re.compile(escaped, re.IGNORECASE)


def merge_banned_words(user_words: Optional[list[str]]) -> list[str]:
    """合并用户品牌禁词 + 平台极限词库（去重保序），供生成端点统一调用。"""
    merged: list[str] = []
    seen: set[str] = set()
    for w in list(user_words or []) + PLATFORM_EXTREME_WORDS:
        w = str(w).strip()
        if not w or w in seen:
            continue
        seen.add(w)
        merged.append(w)
    return merged


def check_text(text: str, banned_words: list[str]) -> list[str]:
    """正则扫描文本，返回命中的违禁词列表（空 = 通过）。

    大小写不敏感；中文与英文混合均支持。命中判定用 re.search。
    """
    if not text:
        return []
    hits: list[str] = []
    for word in banned_words or []:
        word = str(word).strip()
        if not word:
            continue
        if _word_regex(word).search(text):
            hits.append(word)
    return hits


def suggest_replacements(violations: list[str]) -> list[dict]:
    """给命中的违禁词生成修正建议 [{word, replacement}]。

    replacement 为空串表示没有预设替代词，提示卖家手动改写。
    """
    suggestions: list[dict] = []
    seen: set[str] = set()
    for w in violations or []:
        w = str(w)
        if w in seen:
            continue
        seen.add(w)
        suggestions.append({"word": w, "replacement": EXTREME_REPLACEMENTS.get(w, "")})
    return suggestions


def apply_suggested_replacements(
    text: str,
    suggestions: list[dict],
) -> tuple[str, int]:
    """按安全替换词改写文本，返回 (新文本, 替换次数)。

    没有预置 replacement 的词保持原样，由前端引导卖家手动修改。
    """
    fixed = text or ""
    total = 0
    for item in suggestions:
        word = str(item.get("word") or "").strip()
        replacement = str(item.get("replacement") or "").strip()
        if not word or not replacement:
            continue
        fixed, count = _word_regex(word).subn(replacement, fixed)
        total += count
    return fixed, total


async def ai_review_fix(
    text: str,
    banned_words: Optional[list[str]] = None,
    max_tokens: int = 600,
) -> tuple[str, bool, list[str], str]:
    """AI 深度改写违禁文案（可选增强层，正则层未启用时也可单独调用）。

    Returns:
        (fixed_text, ok, violations, message)
        - 成功：fix 可用 → ok=True，violations 为 AI 报告的问题（可能为空）
        - AI 不可用 / 解析失败 → 返回 (原文本, False, [], "合规检查暂不可用")
          绝不抛 500，保证"能用"优先。
    """
    if not text:
        return text, False, [], "文本为空"
    try:
        from app.services.ai.deepseek import DeepSeekService
        llm = DeepSeekService()
        user_words = banned_words or []
        prompt_lines = [
            "你是电商文案合规优化师。检查并改写以下商品文案：",
            "1) 去掉或替换广告法/平台极限词（最好/第一/100%/零风险 等）",
            "2) 去掉虚假宣传与绝对化用语",
            "3) 保留原意与卖点，只输出改写后的文本本身",
        ]
        if user_words:
            prompt_lines.append(f"4) 特别避开用户品牌禁词：{'、'.join(user_words)}")
        prompt_lines.append(f"\n原文：{text[:1500]}")
        fixed = await llm.generate(
            "你是一个严格的电商平台合规审核员，专注广告文案合规改写。",
            "\n".join(prompt_lines),
            max_tokens=max_tokens,
        )
        fixed = (fixed or "").strip()
        if not fixed:
            return text, False, [], "合规改写失败，请手动修改"
        return fixed, True, [], "已按合规要求改写"
    except Exception:
        # AI 服务不可用 → 降级返回原文，不阻断（不抛 500）
        return text, False, [], "合规检查暂不可用"


def check_json_block(text: str) -> list[str]:
    """向后兼容别名：仅平台词库检测（供不需合并的调用）。"""
    return check_text(text, PLATFORM_EXTREME_WORDS)
