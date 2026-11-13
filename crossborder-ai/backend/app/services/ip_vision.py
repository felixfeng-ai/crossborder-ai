"""Qwen3-VL 商品图 IP 风险视觉初筛。"""

import base64
import json
import mimetypes
import re
from pathlib import Path

import httpx

from app.core.config import settings
from app.models.image_asset import ImageAsset
from app.services import provider_config


def get_vision_config() -> tuple[str, str, str] | None:
    """读取平台级视觉模型配置；缺失时返回 None。"""
    api_key = provider_config.get(
        "aliyun",
        "api_key",
        settings.ALIYUN_DASHSCOPE_API_KEY or "",
    )
    if not api_key:
        return None
    return (
        api_key,
        provider_config.get(
            "aliyun",
            "vision_model",
            settings.IP_VISION_MODEL,
        ),
        settings.IP_VISION_BASE_URL.rstrip("/"),
    )


def _asset_path(asset: ImageAsset) -> Path:
    base = Path(settings.IMAGE_STORAGE_DIR).resolve()
    target = (base / asset.storage_key).resolve()
    if base not in target.parents:
        raise ValueError("图片路径无效")
    return target


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return {}
    try:
        value = json.loads(match.group())
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


async def analyze_image_asset(asset: ImageAsset) -> list[dict]:
    """调用视觉模型识别 Logo、水印、商标文字和 IP 形象。"""
    config = get_vision_config()
    if config is None:
        raise ValueError("视觉模型未配置")
    api_key, model, base_url = config
    path = _asset_path(asset)
    if not path.is_file():
        raise ValueError("图片文件不存在")
    mime_type = asset.content_type or mimetypes.guess_type(path.name)[0] or "image/webp"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    prompt = (
        "你是商品图视觉识别器，不是法律审核器。"
        "只识别图中可见的商标文字、品牌 Logo、水印、影视或卡通 IP 形象。"
        "不要判断是否侵权。返回严格 JSON："
        '{"items":[{"type":"logo|watermark|character|trademark_text",'
        '"label":"可见品牌或形象名","confidence":0.0,'
        '"bbox":[x1,y1,x2,y2],"reason":"可见依据"}]}。'
        "bbox 使用 0-1000 归一化坐标；无法定位区域时 bbox=null。"
    )
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{encoded}"
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                "temperature": 0,
                "max_tokens": 800,
            },
        )
        response.raise_for_status()
    payload = response.json()
    content = (
        payload.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    parsed = _extract_json(str(content))
    items = parsed.get("items")
    return items if isinstance(items, list) else []


def _valid_bbox(value) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        bbox = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    if any(item < 0 or item > 1000 for item in bbox):
        return None
    return bbox


def visual_items_to_risks(
    items: list[dict],
    *,
    asset_id: str,
    authorized_brands: set[str] | None = None,
) -> list[dict]:
    """把视觉识别结果转换成统一风险项，不伪造 bbox 或法律结论。"""
    authorized = {
        str(item).strip().lower()
        for item in (authorized_brands or set())
        if str(item).strip()
    }
    risks = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").lower()
        label = str(item.get("label") or "").strip()
        try:
            confidence = float(item.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0
        bbox = _valid_bbox(item.get("bbox"))
        evidence = {
            "type": "image",
            "asset_id": asset_id,
            "text": label or None,
            "bbox": bbox,
            "bbox_format": "normalized_1000" if bbox else None,
        }
        is_authorized = bool(label) and label.lower() in authorized
        if item_type in {"logo", "trademark_text"}:
            code = "IMAGE_TRADEMARK_SUSPECTED"
            category = "trademark"
            severity = "info" if is_authorized else (
                "high" if confidence >= 0.75 else "medium"
            )
            suggestion = (
                "视觉识别到疑似商标标识，请人工核对品牌授权范围"
                if not is_authorized
                else "已提供该品牌授权依据，请人工核验图片使用范围"
            )
        elif item_type == "watermark":
            code = "IMAGE_WATERMARK_SUSPECTED"
            category = "watermark"
            severity = "medium"
            suggestion = "建议移除来源不明水印，或补充合法使用权说明"
        elif item_type == "character":
            code = "IMAGE_CHARACTER_SUSPECTED"
            category = "character_ip"
            severity = "medium"
            suggestion = "疑似影视/卡通 IP 形象，请人工核实角色授权后再发布"
        else:
            continue
        if bbox is None:
            code = "VISION_REGION_UNVERIFIED"
            severity = "medium"
            suggestion = "视觉结果缺少可靠区域坐标，请人工复核整张图片"
        risks.append(
            {
                "code": code,
                "category": category,
                "severity": severity,
                "evidence": evidence,
                "suggestion": suggestion,
                "source": "vision_model",
            }
        )
    return risks
