"""VeyaShip - 品牌档案（Persona → Brand Kit）统一构建

所有生成出口（标题/描述/五点/SEO/A+/图片 prompt/Agent/编排器）从这里读取品牌调性，
避免各处手拼逻辑漂移：
- ``fetch_persona(db, user_id)``：按用户读取 Persona 记录（无则 None）
- ``build_persona_kit(persona)``：把 Persona 归一化为 dict（缺失字段为 None/空 list）
- ``format_persona_block(kit)``：生成文案类注入的统一中文「品牌档案」块（缺失字段跳过）
- ``image_style_phrase(kit)``：图片 prompt 附加的风格串（有 image_style 用之，否则退而用 tone）
- ``strip_banned_words(text, banned_words)``：把文本中出现的品牌禁词整段移除（图片路径用）
"""

import json
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.persona import Persona

# 品牌档案块的字段顺序与中文标签（format_persona_block 用）
_BLOCK_LABELS = [
    ("brand_name", "品牌名称"),
    ("tagline", "品牌标语"),
    ("description", "品牌描述"),
    ("tone", "语气风格"),
    ("target_market", "目标市场"),
    ("product_category", "主营类目"),
    ("image_style", "视觉风格"),
]


def _field(obj: Any, key: str):
    """兼容 Persona 对象或 dict 的属性/键读取。"""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def build_persona_kit(persona: Any) -> dict:
    """把 Persona（或 dict）归一化为品牌档案 dict。

    始终包含字段：brand_name/tagline/description/tone/tone_custom/banned_words/
    target_market/product_category/image_style。缺失字段为 None（banned_words 为 []）。
    tone 已合并 tone_custom 优先。
    """
    banned_raw = _field(persona, "banned_words")
    banned_words: list[str] = []
    if isinstance(banned_raw, str):
        try:
            parsed = json.loads(banned_raw)
            banned_words = parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            banned_words = []
    elif isinstance(banned_raw, list):
        banned_words = banned_raw

    tone_custom = _field(persona, "tone_custom") or ""
    tone = _field(persona, "tone") or "professional"
    return {
        "brand_name": _field(persona, "brand_name"),
        "tagline": _field(persona, "tagline"),
        "description": _field(persona, "description"),
        "tone": tone_custom or tone,
        "tone_custom": tone_custom,
        "banned_words": [str(w) for w in banned_words if str(w).strip()],
        "target_market": _field(persona, "target_market"),
        "product_category": _field(persona, "product_category"),
        "image_style": _field(persona, "image_style"),
    }


def format_persona_block(kit: Optional[dict]) -> str:
    """把品牌档案 dict 渲染成文案类注入的统一中文块。

    缺失字段自动跳过；未配置任何字段时返回空串（不注入，AI 不感知品牌）。
    返回示例：
        【品牌档案】
        品牌名称：ABC Store
        目标市场：amazon.com
    """
    if not kit:
        return ""
    lines = []
    for key, label in _BLOCK_LABELS:
        val = kit.get(key)
        if val is not None and str(val).strip():
            lines.append(f"{label}：{str(val).strip()}")
    # 禁词单独处理：只列出配置的
    banned = kit.get("banned_words") or []
    if banned:
        lines.append(f"禁止使用的词汇：{'、'.join(banned)}")
    if not lines:
        return ""
    return "【品牌档案】\n" + "\n".join(lines)


def image_style_phrase(kit: Optional[dict]) -> str:
    """图片 prompt 要附加的风格串。

    - 配置了 image_style → 直接用（如 "clean studio lighting, soft shadows"）
    - 否则回退到语气 tone + " style"（保留旧行为）
    - 都没有 → 返回空串（不附加）
    """
    if not kit:
        return ""
    style = (kit.get("image_style") or "").strip()
    if style:
        return style
    tone = (kit.get("tone") or "").strip()
    if not tone:
        return ""
    return tone if "style" in tone.lower() else f"{tone} style"


def strip_banned_words(text: str, banned_words: list[str]) -> str:
    """把文本里出现的品牌禁词整段移除（简单 contains 替换，图片描述路径用）。

    仅做粗粒度过滤（图片不走文案合规拦截），命中即整体删除该词出现位置。
    """
    result = text
    for w in banned_words or []:
        w = str(w).strip()
        if not w:
            continue
        if w.lower() in result.lower():
            import re
            # 整段删除该词，保持上下文连贯
            result = re.sub(re.escape(w), "", result, flags=re.IGNORECASE)
    return result


async def fetch_persona(
    db: AsyncSession,
    user_id,
    workspace_id=None,
    *,
    include_legacy_workspace: bool = False,
) -> Optional[Persona]:
    """按工作区读取 Persona；未指定工作区时保留旧用户级调用兼容。"""
    query = select(Persona).where(Persona.user_id == user_id)
    if workspace_id is not None:
        scope = Persona.workspace_id == workspace_id
        if include_legacy_workspace:
            scope = or_(scope, Persona.workspace_id.is_(None))
        query = query.where(scope)
    result = await db.execute(
        query.order_by(Persona.created_at, Persona.id).limit(1)
    )
    return result.scalar_one_or_none()
