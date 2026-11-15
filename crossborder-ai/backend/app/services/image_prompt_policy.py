"""Agent 图片提示词的确定性文字安全策略。"""


_COPY_SPACE_PHRASES = (
    "留左上角文案空间",
    "预留左上角文案空间",
    "留文案空间",
    "预留文案区域",
    "为文案留白",
    "文案区域留白",
)

_NO_NEW_TEXT = (
    "画面不得新增任何文字、汉字、字母、数字、水印、字幕、标签、UI 或叠加文案"
)
_CLEAN_SPACE = "需要留白时保持干净留白，留白区域不得出现任何文字或符号"
_PRESERVE_PRODUCT_TEXT = (
    "商品自身已有的 Logo、包装文字、型号和容量严格以参考图为准，"
    "不自行创造、改写或补全文字"
)

_NEGATIVE_TEXT_RULES = (
    "新增文字",
    "中文标题",
    "错误汉字",
    "重复文字",
    "乱码",
    "水印",
    "字幕",
    "标签",
    "UI",
    "叠加文案",
)


def merge_agent_negative_prompt(negative_prompt: str = "") -> str:
    """合并文字安全负向词，保留原有内容并去重。"""
    parts = [
        item.strip()
        for item in str(negative_prompt or "").split("，")
        if item.strip()
    ]
    for rule in _NEGATIVE_TEXT_RULES:
        if rule not in parts:
            parts.append(rule)
    return "，".join(parts)


def prepare_agent_image_prompt(
    prompt: str,
    *,
    mode: str,
    negative_prompt: str = "",
) -> tuple[str, str]:
    """阻止生成模型自由排版文案，文字应由前端或图像模板后处理。"""
    enhanced = str(prompt or "").strip()
    for phrase in _COPY_SPACE_PHRASES:
        enhanced = enhanced.replace(phrase, "干净留白")

    if "不得新增任何文字" not in enhanced:
        enhanced = f"{enhanced}，{_NO_NEW_TEXT}" if enhanced else _NO_NEW_TEXT
    if "干净留白" in enhanced and "留白区域不得出现任何文字" not in enhanced:
        enhanced = f"{enhanced}，{_CLEAN_SPACE}"
    if mode == "product_scene" and "严格以参考图为准" not in enhanced:
        enhanced = f"{enhanced}，{_PRESERVE_PRODUCT_TEXT}"

    return enhanced, merge_agent_negative_prompt(negative_prompt)
