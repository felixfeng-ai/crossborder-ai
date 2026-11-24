"""VeyaShip - AI Agent 编排器

【功能】
用户用自然语言下达指令，Agent 自动规划并执行多步操作。
比如 "帮我抓取这个1688商品，生成Amazon Listing" → Agent 自动完成。

【工作流程】
1. 接收用户指令
2. LLM 解析意图，规划执行步骤
3. 按顺序执行每一步（可调用抓取、生成、发布等功能）
4. 返回执行结果

【可用工具】
- scrape_1688(url) → 抓取商品
- create_product(data) → 创建商品
- generate_listing(product_id, platform) → AI 生成 Listing
- get_listing / edit_listing(listing_id) → 回查与编辑 Listing
- generate_image_asset / generate_product_video → 提交异步素材任务
- generate_product_image → 兼容旧客户端的商品图片生成工具
- create_marketing_video_plan → 生成营销方案与分镜
- generate_marketing_copy → 生成多平台 A/B 文案资产
- prepare_review_reply → 为 Judge.me 中差评创建可编辑回复并等待确认
- list_materials → 查询用户素材
- check_compliance(text) → 合规审查
- calculate_profit(params) → 净利计算
"""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import quote_plus
from uuid import UUID

from app.core.config import settings
from app.models.user import User
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.publication import Publication
from app.models.image_asset import ImageAsset
from app.models.listing_draft import ListingDraft
from app.services.ai.deepseek import DeepSeekService
from app.services.listing_service import (
    generate_and_persist_listing,
    get_current_compliance_report,
    get_owned_listing,
    serialize_listing,
    update_listing_content,
)
from app.services import agent_capability_service, marketing_copy_service, provider_config
from app.services.amazon_sp_api import AmazonSpApiService
from app.services.temu_order_read import TemuOrderReadService
from app.services.temu_product_read import TemuProductReadService
from app.services.agent_context import (
    build_system_prompt,
    compact_conversation_history,
)
from app.services.scraper import scrape_1688
from app.services.shopify_publish_service import (
    ShopifyPublishError,
    publish_shopify_product,
    serialize_shopify_publish_result,
)
from app.services.shopify_operations_sync import (
    ShopifyOperationsSyncError,
    sync_shopify_operations as run_shopify_operations_sync,
)
from app.services.store_check_service import run_store_check as execute_store_check
from app.services.ip_risk import screen_product_text
from app.services.selection_report import normalize_selection_report
from app.services.source_discovery import (
    SourceDiscoveryError,
    SourceDiscoveryInputError,
    search_1688_sources,
)
from app.services.amazon_market_data import (
    AmazonMarketDataNotConfigured,
    AmazonMarketQueryError,
    build_runtime_amazon_market_service,
)
from app.services.profit_calculation import (
    ProfitCalculationError,
    calculate_profit,
    calculate_profit_scenarios,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _extract_json(text: str) -> Optional[dict]:
    """从 LLM 输出中提取 JSON 对象（三级容错）

    1. 先剥离 ```json 代码围栏（DeepSeek 偶尔会包围栏）
    2. 贪婪匹配从第一个 { 到最后一个 }（容忍前后杂文）
    3. json.loads 解析，失败返回 None

    提取失败返回 None —— 调用方据此降级（structured=null + 原始文本兜底）。
    """
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?\s*([\s\S]*?)```", r"\1", text)
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def _amazon_search_url(query: str | None) -> str:
    """用商品名生成真实 Amazon 搜索结果链接，避免伪造具体商品 ID。"""
    value = (query or "").strip()
    return f"https://www.amazon.com/s?k={quote_plus(value)}" if value else ""


def _attach_product_links(structured: dict) -> dict:
    """为候选商品和首选方向补齐可点击的 Amazon 搜索链接。"""
    products = structured.get("products") or []
    linked_products: list[dict] = []
    for product in products:
        if not isinstance(product, dict):
            continue
        item = dict(product)
        if not item.get("url"):
            item["url"] = _amazon_search_url(item.get("name"))
        linked_products.append(item)
    structured["products"] = linked_products

    recommendation = structured.get("recommendation")
    if isinstance(recommendation, dict) and not recommendation.get("url"):
        top_pick = recommendation.get("top_pick") or ""
        matched = next(
            (
                item
                for item in linked_products
                if top_pick
                and (
                    top_pick in (item.get("name") or "")
                    or (item.get("name") or "") in top_pick
                )
            ),
            None,
        )
        recommendation["url"] = (
            matched.get("url") if matched else _amazon_search_url(top_pick)
        )
    return structured


def _render_report_markdown(structured: dict, keyword: str, mode: str = "select") -> str:
    """把结构化报告数据渲染成 Markdown（与前端卡片同源，保证一致性）

    Args:
        structured: _extract_json 解析出的报告数据
        keyword: 品类关键词
        mode: 'select' 渲染候选商品表；'category' 不渲染（品类分析通常无具体候选）
    """
    market = structured.get("market") or {}
    products = structured.get("products") or []
    rec = structured.get("recommendation") or {}

    lines = [f"## 「{keyword}」市场分析"]
    quality = structured.get("data_quality") or {}
    provider_name = quality.get("provider", "unknown")
    provider_note = (
        "Amazon 前台事实，购买量为展示范围"
        if provider_name == "justone_api"
        else "第三方销量和搜索量为估算，不是平台官方事实"
    )
    if quality:
        lines.append(
            f"> 数据来源：{provider_name}；"
            f"样本量：{quality.get('sample_size', 0)}；"
            f"完整度：{quality.get('completeness_pct', 0)}%。"
            f"{provider_note}。"
        )
        lines.append("")

    # 市场指标表格
    m_rows = [
        ("月搜索量", market.get("monthly_search_volume")),
        ("在售 Listing", market.get("active_listings")),
        ("样本数量", market.get("sample_size")),
        ("平均售价(USD)", market.get("avg_price_usd")),
        ("售价中位数(USD)", market.get("median_price_usd")),
        ("月销中位数", market.get("median_monthly_units")),
        (
            "前台购买量下限中位数",
            market.get("median_purchase_volume_min"),
        ),
        (
            "购买量展示覆盖率",
            market.get("purchase_volume_coverage_pct"),
        ),
        ("评论中位数", market.get("median_reviews")),
        ("头部集中度", market.get("head_concentration")),
        ("竞争度(1-5)", market.get("competition_level")),
        ("价格战程度(1-5)", market.get("price_war_level")),
        ("新品占比", market.get("new_product_share_pct")),
        ("用户痛点", "、".join(market.get("user_pains", []) or [])),
    ]
    lines.append("| 指标 | 数据 |")
    lines.append("|------|------|")
    for label, val in m_rows:
        if val is None or val == "":
            continue
        lines.append(f"| {label} | {val} |")

    segments = structured.get("segments") or []
    if segments:
        lines.append("")
        lines.append("## 细分方向")
        lines.append("| 方向 | 搜索词 | 结论 | 评分 | 需求信号 | 售价中位数(USD) |")
        lines.append("|------|--------|------|------|----------|-----------------|")
        for segment in segments:
            metrics = segment.get("metrics") or {}
            demand_text = (
                f"{metrics.get('monthly_units')} 件/月"
                if metrics.get("monthly_units") is not None
                else (
                    f"{metrics.get('median_purchase_volume_min')}+ 前台展示"
                    if metrics.get("median_purchase_volume_min") is not None
                    else "待验证"
                )
            )
            lines.append(
                "| {label} | {keyword} | {status} | {score} | {demand} | {price} |".format(
                    label=segment.get("label_zh") or "-",
                    keyword=segment.get("keyword") or "-",
                    status=segment.get("status") or "-",
                    score=segment.get("score", "-"),
                    demand=demand_text,
                    price=metrics.get("median_price_usd", "-"),
                )
            )

    # 候选商品表
    if mode == "select" and products:
        lines.append("")
        lines.append("## 候选商品")
        lines.append("| 商品 | 参考售价(USD) | 购买量展示 | 采购成本(CNY) | 单件净利(USD) | 净利率 | 竞争度(1-5) | 风险提示 |")
        lines.append("|------|------|------|------|------|------|------|------|")
        for p in products:
            volume = (
                f"{p.get('purchase_volume_min')}+"
                if p.get("purchase_volume_min") is not None
                else "-"
            )
            lines.append(
                "| {name} | {price} | {volume} | {cost} | {profit} | {margin}% | {comp} | {risk} |".format(
                    name=p.get("name", ""),
                    price=p.get("suggested_price_usd", "-"),
                    volume=volume,
                    cost=p.get("cost_cny", "-"),
                    profit=p.get("net_profit_usd", "-"),
                    margin=p.get("net_margin", "-"),
                    comp=p.get("competition", "-"),
                    risk="、".join(p.get("risk_tips", []) or []) or "-",
                )
            )

    # 推荐结论
    lines.append("")
    lines.append("## 推荐")
    if rec.get("top_pick"):
        lines.append(f"- 首选：**{rec['top_pick']}**")
    if rec.get("verdict"):
        lines.append(f"- 结论：{rec['verdict']}")
    if rec.get("score") is not None:
        lines.append(f"- 综合评分：{rec['score']}/10")
    for label, key in (("理由", "reasons"), ("风险", "risks")):
        for item in rec.get(key, []) or []:
            lines.append(f"- {label}：{item}")
    if rec.get("entry_advice"):
        lines.append(f"- 切入建议：{rec['entry_advice']}")

    return "\n".join(lines)


def _render_sourcing_report(structured: dict[str, Any]) -> str:
    """把 1688 货源候选渲染成不夸大相似度的可读报告。"""

    items = structured.get("items")
    if not isinstance(items, list) or not items:
        return (
            f"## 「{structured.get('keyword', '')}」1688 货源搜索\n\n"
            "暂未返回可展示的货源候选，请调整关键词或稍后重试。"
        )
    mode = "图片相似搜索" if structured.get("image_search_used") else "关键词搜索"
    lines = [
        f"## 「{structured.get('keyword', '')}」1688 货源候选",
        "",
        f"- 搜索方式：{mode}",
        f"- 数据供应商：{structured.get('provider', '')}",
        "",
        "| 商品 | 价格 | MOQ | 销量 | 店铺 |",
        "|---|---:|---:|---:|---|",
    ]
    for item in items[:10]:
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("price") or "-"),
                    str(item.get("moq") or "-"),
                    str(item.get("sale_quantity") or "-"),
                    str(item.get("shop_name") or "-"),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "> 相似标题或图片不代表同款。采购前必须进入具体 1688 商品页确认 SKU、材质、尺寸、批次和供货稳定性。",
        ]
    )
    return "\n".join(lines)


class AgentOrchestrator:
    """AI Agent 编排器 —— 基于 ReAct + Function Calling 的决策 Agent"""

    # ── 工具注册表（DeepSeek Function Calling 格式） ─────────
    TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "analyze_category",
                "description": (
                    "用真实 Amazon US 市场数据分析一个品类，"
                    "自动拆分细分方向；没有数据源时不猜测数字"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "中文或英文品类关键词，如宠物饮水机",
                        },
                        "marketplace": {
                            "type": "string",
                            "description": "默认 us，当前只支持 Amazon US",
                        },
                    },
                    "required": ["keyword"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "select_products",
                "description": (
                    "用真实 Amazon US 样本推荐细分方向和候选商品；"
                    "不生成没有来源的利润数字"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "品类关键词，如宠物饮水机",
                        },
                        "marketplace": {
                            "type": "string",
                            "description": "默认 us，当前只支持 Amazon US",
                        },
                    },
                    "required": ["keyword"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "find_1688_sources",
                "description": (
                    "根据具体商品名称、核心规格或公开主图，在 1688 搜索相似货源和供应商候选；"
                    "不自动询价、加购或下单"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": (
                                "简洁中文采购关键词，优先包含品类、材质、功能、尺寸等核心规格"
                            ),
                        },
                        "image_url": {
                            "type": "string",
                            "description": "可选商品公开主图 URL，只能使用已返回的真实图片",
                        },
                    },
                    "required": ["keyword"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "analyze_product_decision",
                "description": (
                    "分析 1688 商品链接。必须抓到采购价，并用真实 Amazon US "
                    "竞品、平台费用和卖家物流成本计算利润"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "1688 商品链接",
                        },
                        "shipping_cny": {
                            "type": "number",
                            "description": (
                                "单件头程、包装和入库人民币成本；不知道时留空，"
                                "Agent 会向卖家补充询问"
                            ),
                        },
                        "platform_fee_rate": {
                            "type": "number",
                            "description": (
                                "Amazon 类目佣金率，例如 0.15；不知道时留空，"
                                "不能由模型猜测"
                            ),
                        },
                        "fulfillment_fee_usd": {
                            "type": "number",
                            "description": (
                                "单件 FBA 或尾程配送费 USD；不知道时留空"
                            ),
                        },
                        "exchange_rate": {
                            "type": "number",
                            "description": "美元兑人民币汇率，未填时会在结果中标注假设值",
                        },
                    },
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "scrape_1688",
                "description": "抓取 1688 商品信息",
                "parameters": {
                    "type": "object",
                    "properties": {"url": {"type": "string", "description": "1688 商品链接"}},
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_product",
                "description": "把抓取到的商品保存到当前用户商品库",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "商品链接"},
                        "title": {"type": "string"},
                        "main_image_url": {"type": "string"},
                        "price": {
                            "type": "number",
                            "description": "1688 供货参考价，不是平台销售价",
                        },
                        "sales_count": {"type": "integer"},
                        "shop_name": {"type": "string"},
                    },
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_listing",
                "description": (
                    "为当前用户的商品生成完整 Listing，包含标题、描述、卖点、SEO 和合规结果。"
                    "当用户要求写 Listing、生成文案或准备上架内容时使用；返回 listing_id 和编辑链接。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "string", "description": "商品 ID"},
                        "platform": {"type": "string", "description": "目标平台"},
                        "language": {"type": "string", "description": "目标语言"},
                    },
                    "required": ["product_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_listing",
                "description": (
                    "读取当前用户的一条 Listing 详情，包含内容、版本和合规状态。"
                    "当用户询问 Listing 内容、版本或为什么不能发布时使用。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "listing_id": {"type": "string", "description": "ListingDraft ID"}
                    },
                    "required": ["listing_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "edit_listing",
                "description": (
                    "修改当前用户拥有的 Listing 内容并递增版本，修改后合规状态会重置。"
                    "当用户明确要求调整标题、描述、五点或 SEO 时使用；返回新版本和编辑链接。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "listing_id": {"type": "string", "description": "ListingDraft ID"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "bullet_points": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "seo_title": {"type": "string"},
                        "seo_description": {"type": "string"},
                    },
                    "required": ["listing_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_materials",
                "description": (
                    "查询当前用户的图片、商品图生视频和营销视频项目。"
                    "当用户询问有哪些素材、最近生成结果或素材在哪里时使用；返回计数、最近摘要和素材中心链接。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "返回最近素材数量，1-50",
                        }
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_product_image",
                "description": (
                    "兼容旧客户端的商品图片工具，禁止在新任务中主动选择。"
                    "商品主图、场景图必须优先使用 generate_image_asset，并传入真实参考素材。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "商品图片画面、场景、构图和光线描述",
                        },
                        "num_outputs": {
                            "type": "integer",
                            "description": "生成数量，1-4",
                        },
                        "confirmed": {
                            "type": "boolean",
                            "description": "用户是否已明确要求生成图片",
                        },
                    },
                    "required": ["prompt"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_image_asset",
                "description": (
                    "创建商品场景或自由创作图片任务。商品场景必须提供 1-4 张"
                    "当前用户素材 ID；自由创作默认不注入品牌人设。"
                    "只有用户明确要求生成或确认后 confirmed=true 才使用。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "完整画面描述，包括商品、场景、构图和光线",
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["free_creation", "product_scene"],
                        },
                        "reference_asset_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "商品场景参考图素材 ID，1-4 张",
                        },
                        "quality_tier": {
                            "type": "string",
                            "enum": ["fast", "standard", "hd"],
                        },
                        "aspect_ratio": {
                            "type": "string",
                            "enum": ["1:1", "4:5", "3:4", "16:9", "9:16"],
                        },
                        "negative_prompt": {"type": "string"},
                        "style_preset": {"type": "string"},
                        "use_brand_persona": {"type": "boolean"},
                        "provider": {
                            "type": "string",
                            "enum": ["auto", "seedream", "aliyun", "replicate"],
                        },
                        "num_outputs": {
                            "type": "integer",
                            "description": "生成数量，1-4",
                        },
                        "idempotency_key": {"type": "string"},
                        "confirmed": {
                            "type": "boolean",
                            "description": "用户是否已明确要求生成图片",
                        },
                    },
                    "required": ["prompt", "mode"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_product_video",
                "description": (
                    "基于已上传商品首帧提交 MiniMax 商品图生视频任务，会产生积分费用。"
                    "只有用户明确要求生成视频、且明确接受费用后才能 confirmed=true；"
                    "未确认时只返回积分估算和确认提示。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_asset_id": {
                            "type": "string",
                            "description": "素材中心中的商品首帧 ImageAsset ID",
                        },
                        "prompt": {"type": "string", "description": "镜头、场景和动作描述"},
                        "template_id": {
                            "type": "string",
                            "description": "视频模板，默认 clean_product",
                        },
                        "quality_tier": {
                            "type": "string",
                            "enum": ["draft", "standard", "cinematic"],
                        },
                        "style_preset": {
                            "type": "string",
                            "description": "视觉风格预设 ID",
                        },
                        "model": {"type": "string"},
                        "resolution": {"type": "string"},
                        "duration": {"type": "integer"},
                        "confirmed": {
                            "type": "boolean",
                            "description": "用户是否明确确认提交并接受积分消耗",
                        },
                    },
                    "required": ["source_asset_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_marketing_video_plan",
                "description": (
                    "根据商品首帧、商品名和营销想法生成营销视频项目与分镜方案。"
                    "只创建 brief_ready 方案，不自动渲染、不扣视频积分；返回项目链接供用户确认渲染。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_asset_id": {"type": "string"},
                        "product_name": {"type": "string"},
                        "idea": {"type": "string"},
                        "platform": {"type": "string"},
                        "market": {"type": "string"},
                        "language": {"type": "string"},
                        "duration": {"type": "integer"},
                        "template_id": {"type": "string"},
                        "quality_tier": {
                            "type": "string",
                            "enum": ["draft", "standard", "cinematic"],
                        },
                        "style_preset": {
                            "type": "string",
                            "description": "视觉风格预设 ID",
                        },
                    },
                    "required": ["source_asset_id", "product_name", "idea"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_marketing_copy",
                "description": (
                    "为当前营销活动生成 TikTok、Amazon 和 Shopify 文案，"
                    "每个平台包含 A/B 两个版本，并持久化为活动文案资产。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "platforms": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["tiktok", "amazon", "shopify"],
                            },
                        },
                        "language": {
                            "type": "string",
                            "description": "文案语言，如 en、zh",
                        },
                        "instructions": {
                            "type": "string",
                            "description": "本次文案的补充要求",
                        },
                    },
                    "required": ["platforms"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "push_to_shopify",
                "description": "发布一个已通过合规审查的 Listing 到 Shopify",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "listing_id": {"type": "string", "description": "ListingDraft ID"},
                        "channel_id": {"type": "string", "description": "可选，指定 Shopify 渠道"},
                    },
                    "required": ["listing_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "publish_to_amazon",
                "description": (
                    "为已通过合规检查的 Amazon Listing 准备发布动作。"
                    "只创建待确认计划，不直接提交 Amazon。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "listing_id": {"type": "string"},
                        "variant_id": {"type": "string"},
                        "marketplace_id": {"type": "string"},
                        "product_type": {"type": "string"},
                        "currency": {"type": "string"},
                        "additional_attributes": {
                            "type": "object",
                            "additionalProperties": True,
                        },
                    },
                    "required": [
                        "listing_id",
                        "product_type",
                        "marketplace_id",
                    ],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_amazon_orders",
                "description": (
                    "查询已绑定 Amazon 店铺的商户自履约订单状态。"
                    "不返回买家姓名、邮箱、地址、付款或税务信息。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "marketplace_id": {
                            "type": "string",
                            "description": "可选，多店铺时指定 Marketplace ID",
                        },
                        "days": {
                            "type": "integer",
                            "description": "查询最近更新天数，默认 7，最大 30",
                        },
                        "fulfillment_statuses": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "可选，例如 UNSHIPPED、PARTIALLY_SHIPPED、"
                                "SHIPPED、CANCELLED"
                            ),
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_temu_products",
                "description": (
                    "查询已授权 Temu 店铺的商品列表。"
                    "仅在商品读取 scope 和店铺类型匹配时可用。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "connection_id": {
                            "type": "string",
                            "description": "可选，多店铺时指定 Temu 连接 ID",
                        },
                        "page_no": {
                            "type": "integer",
                            "description": "页码，默认 1",
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "每页数量，默认 20，最大 50",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_temu_orders",
                "description": (
                    "查询已授权 Temu LOCAL/SEMI 店铺的订单状态。"
                    "仅使用 bg.order.list.v2.get，不返回买家姓名、地址、"
                    "电话或邮箱。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "connection_id": {
                            "type": "string",
                            "description": "可选，多店铺时指定 Temu 连接 ID",
                        },
                        "page_number": {
                            "type": "integer",
                            "description": "页码，默认 1",
                        },
                        "page_size": {
                            "type": "integer",
                            "description": "每页数量，默认 20，最大 100",
                        },
                        "parent_order_status": {
                            "type": "integer",
                            "description": "可选，按 Temu 父订单状态筛选",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "fulfill_temu_order",
                "description": (
                    "为 Temu LOCAL/SEMI 卖家自履约订单准备发货确认动作。"
                    "只创建待确认计划，不直接提交 Temu。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "connection_id": {
                            "type": "string",
                            "description": "可选，多店铺时指定 Temu 连接 ID",
                        },
                        "parent_order_sn": {"type": "string"},
                        "carrier_id": {
                            "type": "integer",
                            "description": "Temu 当前区域物流商 ID",
                        },
                        "tracking_number": {"type": "string"},
                        "self_shipping_warehouse_id": {
                            "type": "string",
                            "description": "卖家已配置的自发货仓库 ID，可选",
                        },
                    },
                    "required": [
                        "parent_order_sn",
                        "carrier_id",
                        "tracking_number",
                    ],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "submit_temu_listing",
                "description": (
                    "为 Temu LOCAL/SEMI 商品准备 V3 发布计划。"
                    "只创建待确认动作，不直接提交 Temu。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "listing_id": {"type": "string"},
                        "connection_id": {
                            "type": "string",
                            "description": "可选，多店铺时指定 Temu 连接 ID",
                        },
                        "asset_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "1 至 9 张当前工作区图片素材",
                        },
                        "category_name": {
                            "type": "string",
                            "description": "Temu 类目名称或类目路径",
                        },
                        "currency": {
                            "type": "string",
                            "description": "例如 USD、EUR",
                        },
                        "language": {
                            "type": "string",
                            "description": "商品内容语言，可选",
                        },
                        "attributes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": True,
                            },
                            "description": "可选商品属性",
                        },
                        "package_info": {
                            "type": "object",
                            "additionalProperties": True,
                            "description": "可选真实包装重量和长宽高",
                        },
                    },
                    "required": [
                        "listing_id",
                        "asset_ids",
                        "category_name",
                        "currency",
                    ],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_temu_inventory",
                "description": (
                    "为 Temu LOCAL/SEMI Listing 准备普通库存覆写动作。"
                    "只创建待确认计划，不直接写平台。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "listing_id": {"type": "string"},
                        "connection_id": {
                            "type": "string",
                            "description": "可选，多店铺时指定 Temu 连接 ID",
                        },
                        "variant_id": {"type": "string"},
                        "stock_target": {
                            "type": "integer",
                            "description": "普通库存目标值，范围 0 至 1000000",
                        },
                    },
                    "required": [
                        "listing_id",
                        "variant_id",
                        "stock_target",
                    ],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "submit_temu_price_change",
                "description": (
                    "为 Temu LOCAL/SEMI Listing 准备基础供货价变更。"
                    "只创建待确认计划，不直接提交平台。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "listing_id": {"type": "string"},
                        "connection_id": {
                            "type": "string",
                            "description": "可选，多店铺时指定 Temu 连接 ID",
                        },
                        "variant_id": {"type": "string"},
                        "amount": {
                            "type": "string",
                            "description": "新的基础供货价",
                        },
                        "currency": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": [
                        "listing_id",
                        "variant_id",
                        "amount",
                        "currency",
                        "reason",
                    ],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "fulfill_amazon_order",
                "description": (
                    "为 Amazon 商户自履约订单准备确认发货动作。"
                    "只创建待确认计划，不直接提交 Amazon。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "marketplace_id": {"type": "string"},
                        "carrier_code": {
                            "type": "string",
                            "description": "Amazon 承运商代码",
                        },
                        "carrier_name": {
                            "type": "string",
                            "description": "其他承运商时必填",
                        },
                        "tracking_number": {"type": "string"},
                        "shipping_method": {"type": "string"},
                        "ship_date": {
                            "type": "string",
                            "description": "ISO 8601 发货时间，可选",
                        },
                        "package_reference_id": {
                            "type": "string",
                            "description": "正整数字符串，默认 1",
                        },
                    },
                    "required": [
                        "order_id",
                        "marketplace_id",
                        "carrier_code",
                        "tracking_number",
                    ],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_amazon_inventory",
                "description": (
                    "准备 Amazon Listing 库存更新。"
                    "只创建待确认动作，不直接写平台。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "listing_id": {"type": "string"},
                        "variant_id": {"type": "string"},
                        "marketplace_id": {"type": "string"},
                        "stock_quantity": {"type": "integer"},
                    },
                    "required": [
                        "listing_id",
                        "variant_id",
                        "marketplace_id",
                        "stock_quantity",
                    ],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_amazon_price",
                "description": (
                    "准备 Amazon Listing 售价更新。"
                    "只创建待确认动作，不直接写平台。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "listing_id": {"type": "string"},
                        "variant_id": {"type": "string"},
                        "marketplace_id": {"type": "string"},
                        "price": {"type": "number"},
                        "currency": {"type": "string"},
                    },
                    "required": [
                        "listing_id",
                        "variant_id",
                        "marketplace_id",
                        "price",
                        "currency",
                    ],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_amazon_listing",
                "description": (
                    "准备 Amazon Listing 标题、描述或卖点局部更新。"
                    "只创建待确认动作，不直接写平台。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "listing_id": {"type": "string"},
                        "variant_id": {"type": "string"},
                        "marketplace_id": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "bullet_points": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": [
                        "listing_id",
                        "variant_id",
                        "marketplace_id",
                    ],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "attach_amazon_listing_images",
                "description": (
                    "准备把持久图片 URL 绑定到 Amazon Listing。"
                    "只创建待确认动作，不接受本地路径或临时签名 URL。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "listing_id": {"type": "string"},
                        "variant_id": {"type": "string"},
                        "marketplace_id": {"type": "string"},
                        "main_image_url": {"type": "string"},
                        "other_image_urls": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": [
                        "listing_id",
                        "variant_id",
                        "marketplace_id",
                    ],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "attach_amazon_listing_assets",
                "description": (
                    "准备把当前工作区素材图片显式发布并绑定到 Amazon Listing。"
                    "只创建待确认动作，不自动公开图片。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "listing_id": {"type": "string"},
                        "variant_id": {"type": "string"},
                        "marketplace_id": {"type": "string"},
                        "asset_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                            "maxItems": 9,
                        },
                    },
                    "required": [
                        "listing_id",
                        "variant_id",
                        "marketplace_id",
                        "asset_ids",
                    ],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "sync_shopify_operations",
                "description": (
                    "同步已绑定 Shopify 店铺最近订单销量和本平台已发布商品库存。"
                    "当用户询问最新销量、库存或补货数据时使用；返回扫描订单数、"
                    "销量更新数、库存更新数和未匹配 SKU。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "channel_id": {
                            "type": "string",
                            "description": "已绑定的 Shopify 渠道 ID",
                        },
                        "days": {
                            "type": "integer",
                            "description": "同步最近天数，默认 30",
                        },
                    },
                    "required": ["channel_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_shopify_price",
                "description": "为已发布到 Shopify 的 SKU 准备改价，生成待确认动作",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "variant_id": {
                            "type": "string",
                            "description": "本地 ProductVariant ID",
                        },
                        "price": {
                            "type": "number",
                            "description": "新的销售价",
                        },
                        "channel_id": {
                            "type": "string",
                            "description": "可选，指定 Shopify 渠道",
                        },
                    },
                    "required": ["variant_id", "price"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_shopify_inventory",
                "description": "为已发布到 Shopify 的 SKU 准备库存写回，生成待确认动作",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "variant_id": {
                            "type": "string",
                            "description": "本地 ProductVariant ID",
                        },
                        "stock_quantity": {
                            "type": "integer",
                            "description": "新的可用库存",
                        },
                        "channel_id": {
                            "type": "string",
                            "description": "可选，指定 Shopify 渠道",
                        },
                        "location_id": {
                            "type": "string",
                            "description": "可选，指定 Shopify 库存地点",
                        },
                    },
                    "required": ["variant_id", "stock_quantity"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_shopify_listing",
                "description": "准备修改已发布 Shopify 商品的标题、描述或上下架状态",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "listing_id": {
                            "type": "string",
                            "description": "ListingDraft ID",
                        },
                        "title": {
                            "type": "string",
                            "description": "可选，新商品标题",
                        },
                        "description": {
                            "type": "string",
                            "description": "可选，新商品描述",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["active", "draft", "archived"],
                            "description": "可选，Shopify 商品状态",
                        },
                        "channel_id": {
                            "type": "string",
                            "description": "可选，指定 Shopify 渠道",
                        },
                    },
                    "required": ["listing_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "cancel_shopify_order",
                "description": "准备取消未履约的 Shopify 订单，生成高风险待确认动作",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_id": {
                            "type": "string",
                            "description": "Shopify 订单编号",
                        },
                        "channel_id": {
                            "type": "string",
                            "description": "Shopify 渠道 ID",
                        },
                        "reason": {
                            "type": "string",
                            "enum": [
                                "customer",
                                "fraud",
                                "inventory",
                                "declined",
                                "other",
                            ],
                        },
                        "restock": {
                            "type": "boolean",
                            "description": "是否回补库存",
                        },
                        "refund": {
                            "type": "boolean",
                            "description": "是否同时退款",
                        },
                        "notify_customer": {
                            "type": "boolean",
                            "description": "是否通知买家",
                        },
                    },
                    "required": ["order_id", "channel_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "attach_shopify_listing_images",
                "description": "准备把 1 至 4 张已生成图片附加到 Shopify 商品",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "listing_id": {
                            "type": "string",
                            "description": "ListingDraft ID",
                        },
                        "asset_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "ImageAsset ID 列表，1 至 4 张",
                        },
                        "channel_id": {
                            "type": "string",
                            "description": "可选，指定 Shopify 渠道",
                        },
                    },
                    "required": ["listing_id", "asset_ids"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compliance_check",
                "description": "检查文本是否含违规内容",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string", "description": "要检查的文本"}},
                    "required": ["text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "screen_ip_risk",
                "description": (
                    "对当前用户的商品 Listing 和商品图做 IP 风险初筛。"
                    "返回风险等级、命中证据和建议动作，不做侵权或法律结论。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_id": {
                            "type": "string",
                            "description": "商品 ID",
                        },
                        "listing_id": {
                            "type": "string",
                            "description": "可选，指定 Listing；不传则使用商品最新 Listing",
                        },
                        "image_asset_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "可选，要检查的商品图素材 ID",
                        },
                        "scope": {
                            "type": "string",
                            "enum": ["text", "image", "both"],
                            "description": "检查范围，默认 text",
                        },
                    },
                    "required": ["product_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_platform_policies",
                "description": (
                    "检索 Amazon、TikTok Shop、Shopify 等平台政策原文。"
                    "用于解释认证要求、Listing 合规依据和整改动作，必须返回引用来源。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "要检索的平台政策问题",
                        },
                        "platform": {
                            "type": "string",
                            "description": "amazon、tiktok、shopify 等平台",
                        },
                        "market": {
                            "type": "string",
                            "description": "目标市场，例如 US、UK、DE",
                        },
                        "category": {
                            "type": "string",
                            "description": "可选商品类目，例如 toys、electronics",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "返回政策片段数量，默认 5",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compliance_fix",
                "description": "检查文本并自动修复违规内容",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string", "description": "要检查修复的文本"}},
                    "required": ["text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "calculate_profit",
                "description": (
                    "用确定性公式计算单件利润；采购价、汇率、运费和费率缺失时"
                    "必须拒绝，不能按 0 计算"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selling_price": {
                            "type": "number",
                            "description": "售价 USD",
                        },
                        "product_cost": {
                            "type": "number",
                            "description": "采购价 CNY，必须大于 0",
                        },
                        "platform_fee_rate": {
                            "type": "number",
                            "description": "平台佣金率，例如 0.15",
                        },
                        "shipping_cost": {
                            "type": "number",
                            "description": "头程和包装成本 CNY",
                        },
                        "fulfillment_fee": {
                            "type": "number",
                            "description": "尾程配送费 USD",
                        },
                        "other_cost": {
                            "type": "number",
                            "description": "其他单件成本 CNY",
                        },
                        "exchange_rate": {
                            "type": "number",
                            "description": "美元兑人民币汇率",
                        },
                    },
                    "required": [
                        "selling_price",
                        "product_cost",
                        "platform_fee_rate",
                        "shipping_cost",
                        "exchange_rate",
                    ],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "store_check",
                "description": (
                    "巡检店铺所有商品的资料、Listing、素材、SKU、发布和运营预警。"
                    "当用户要求检查店铺健康状态或找出待处理商品时使用。"
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "monitor_products",
                "description": "扫描 SKU 毛利、库存覆盖、补货点和未处理预警",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_operations_digest",
                "description": (
                    "读取当前待处理经营预警和优先整改动作。"
                    "用户询问今天先处理什么、有哪些风险时使用，不重新扫描。"
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "self_reflect",
                "description": "审查生成内容的质量，评分并给出改进建议",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "要审查的内容"},
                        "platform": {"type": "string", "description": "目标平台"},
                        "language": {"type": "string", "description": "语言"},
                    },
                    "required": ["content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "prepare_review_reply",
                "description": (
                    "为已同步的 Judge.me 中差评创建公开回复草稿。"
                    "只生成待确认动作，不直接发布到评价页面。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "thread_id": {
                            "type": "string",
                            "description": "客户评价线程 ID",
                        },
                        "reply_text": {
                            "type": "string",
                            "description": "准备公开发布的评价回复正文",
                        },
                        "send_reply_email": {
                            "type": "boolean",
                            "description": "是否同时让 Judge.me 邮件通知买家",
                        },
                    },
                    "required": ["thread_id", "reply_text"],
                },
            },
        },
    ]

    def __init__(
        self,
        user: User,
        db: AsyncSession,
        on_step: Optional[Callable[[list[dict]], Awaitable[None]]] = None,
        campaign_id: str | None = None,
        workspace: str = "general",
        workspace_id: UUID | None = None,
    ):
        self.llm = DeepSeekService()
        self.user = user
        self.db = db
        self.steps: list[dict] = []  # 记录执行步骤
        self.on_step = on_step  # 步骤进度回调（流式输出用），每完成一步触发
        self.campaign_id = campaign_id
        self.workspace = workspace
        self.workspace_id = workspace_id

    def _status_from_steps(self) -> str:
        failed = any(step.get("status") == "failed" for step in self.steps)
        succeeded = any(step.get("status") == "success" for step in self.steps)
        if failed and succeeded:
            return "partial"
        if failed:
            return "failed"
        return "success"

    async def _emit_step(self) -> None:
        """步骤追加后触发进度回调（流式输出用）。

        回调由执行器注入，把当前已完成的 steps 写入任务的 progress 列，
        SSE 端点轮询该列实时推送给前端，替代"跑完才出结果"。
        """
        if self.on_step:
            await self.on_step(self.steps)

    async def run_react(
        self,
        instruction: str,
        max_rounds: int = 8,
        history: list[dict] | None = None,
    ) -> dict:
        """ReAct 推理循环：思考 → 调用工具 → 观察 → 再思考

        直到模型认为任务完成（不再调用工具），或达到最大轮数。
        """
        self.steps = []
        system_prompt = build_system_prompt(self.workspace)

        # 历史只保留用户/助手文本；当前指令始终作为最后一条用户消息。
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(
            compact_conversation_history(
                history or [],
                current_instruction=instruction,
            )
        )
        messages.append({"role": "user", "content": instruction})

        for round_num in range(max_rounds):
            # 让模型思考并决定是否调用工具
            response = await self.llm.chat_with_tools(messages, tools=self.TOOLS)
            tool_calls = response.get("tool_calls", [])

            # 没有工具调用 → 模型认为任务完成，返回最终回答
            if not tool_calls:
                final_answer = response.get("content", "已完成")
                return {
                    "summary": final_answer,
                    "status": self._status_from_steps(),
                    "steps": self.steps,
                }

            # 有工具调用 → 逐个执行
            messages.append({
                "role": "assistant",
                "content": response.get("content", ""),
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                func_name = tc["function"]["name"]
                try:
                    func_args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, KeyError):
                    func_args = {}

                # 执行工具
                result = await self._execute_step(func_name, func_args)
                self.steps.append(result)
                await self._emit_step()  # 流式输出：每完成一步推送进度

                # 报告类工具只回传 summary，避免模型在最终回答里复述整份报告
                if func_name in ("select_products", "analyze_category") and result.get("status") == "success":
                    tool_content = result.get("summary", "")[:1000]
                else:
                    tool_content = json.dumps(result, ensure_ascii=False, default=str)[:2000]

                # 把工具结果返回给模型
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", str(round_num)),
                    "content": tool_content,
                })

        # 达到最大轮数
        return {
            "summary": "处理步骤较多，以下是已完成的步骤",
            "status": self._status_from_steps(),
            "steps": self.steps,
        }

    async def run(
        self,
        instruction: str,
        history: list[dict] | None = None,
    ) -> dict:
        """执行用户指令

        Args:
            instruction: 用户输入的自然语言指令
                例如："帮我抓取 https://detail.1688.com/offer/xxx.html 并生成 Amazon Listing"

        Returns:
            {
                "summary": "执行总结",
                "steps": [每步的详细结果],
                "status": "success" | "partial" | "failed"
            }
        """
        # ── ReAct 推理循环：模型自己决定调用哪些工具 ────────
        result = await self.run_react(instruction, history=history)
        if result["status"] == "success":
            return result

        # ── 降级：如果 ReAct 失败，退回 Plan-and-Execute ──
        plan = await self._create_plan(instruction)
        self.steps = []

        for step in plan.get("steps", []):
            action = step.get("action", "")
            params = step.get("params", {})
            step_result = await self._execute_step(action, params)
            self.steps.append(step_result)
            await self._emit_step()  # 流式输出：每完成一步推送进度

            if step_result["status"] == "failed" and step.get("critical", False):
                break

        # ── 汇总结果 ──────────────────────────────────────
        return self._build_summary()

    async def run_confirmed_action(
        self,
        action: str,
        params: dict[str, Any],
    ) -> dict:
        """恢复结构化待确认动作，不经过模型二次猜测。"""
        self.steps = []
        confirmed_params = {**params, "confirmed": True}
        result = await self._execute_step(action, confirmed_params)
        self.steps.append(result)
        await self._emit_step()
        status = self._status_from_steps()
        return {
            "summary": (
                result.get("summary")
                or result.get("error")
                or ("操作已完成" if status == "success" else "操作执行失败")
            ),
            "status": status,
            "steps": self.steps,
        }

    # ════════════════════════════════════════════════════════════
    # 工作流模板
    # ════════════════════════════════════════════════════════════
    WORKFLOWS = {
        "1688_to_shopify": {
            "name": "1688 → Shopify 上架",
            "steps": [
                {"action": "scrape_1688", "critical": True, "description": "抓取 1688 商品"},
                {"action": "create_product", "critical": True, "description": "创建商品"},
                {"action": "generate_listing", "critical": False, "description": "AI 生成 Listing"},
                {"action": "push_to_shopify", "critical": False, "description": "发布到 Shopify"},
            ],
        },
        "1688_to_amazon": {
            "name": "1688 → Amazon Listing 生成",
            "steps": [
                {"action": "scrape_1688", "critical": True},
                {"action": "create_product", "critical": True},
                {"action": "generate_listing", "critical": False, "params": {"platform": "amazon"}},
            ],
        },
        "scrape_and_list": {
            "name": "抓取 + 生成 Listing",
            "steps": [
                {"action": "scrape_1688", "critical": True},
                {"action": "create_product", "critical": True},
                {"action": "generate_listing", "critical": False},
            ],
        },
        "store_check": {
            "name": "整店巡检",
            "steps": [
                {"action": "store_check", "critical": True, "description": "检查所有商品状态"},
            ],
        },
        "select_products": {
            "name": "AI 选品决策",
            "steps": [
                {"action": "select_products", "critical": True, "description": "AI 推荐值得做的商品"},
            ],
        },
        "decision_and_list": {
            "name": "判断商品 + 生成 Listing",
            "steps": [
                {"action": "analyze_product_decision", "critical": True, "description": "判断这个品能不能做"},
                {"action": "scrape_1688", "critical": True},
                {"action": "create_product", "critical": True},
                {"action": "generate_listing", "critical": False, "description": "AI 生成 Listing"},
                {"action": "self_reflect", "critical": False, "description": "内容质量自检"},
            ],
        },
    }

    async def run_workflow(self, workflow_name: str, params: dict) -> dict:
        """执行预设工作流

        Args:
            workflow_name: 工作流名称（WORKFLOWS 的 key）
            params: 参数，如 {"url": "1688链接", "platform": "amazon", "language": "en"}
        """
        template = self.WORKFLOWS.get(workflow_name)
        if not template:
            return {"summary": f"未知工作流: {workflow_name}", "status": "failed", "steps": []}

        self.steps = []
        context = {}  # 步骤间传递数据

        for step_def in template["steps"]:
            action = step_def["action"]
            step_params = {**params, **step_def.get("params", {})}

            # 从上下文补充参数
            if "product_id" not in step_params and context.get("product_id"):
                step_params["product_id"] = context["product_id"]
            if "listing_id" not in step_params and context.get("listing_id"):
                step_params["listing_id"] = context["listing_id"]
            if "url" not in step_params and context.get("url"):
                step_params["url"] = context["url"]
            if "title" not in step_params and context.get("title"):
                step_params["title"] = context["title"]
            if action in ("self_reflect", "compliance_check", "compliance_fix"):
                if not step_params.get("content") and context.get("listing_content"):
                    step_params["content"] = context["listing_content"]

            # 执行
            step_result = await self._execute_step(action, step_params)
            step_result["description"] = step_def.get("description", action)
            self.steps.append(step_result)
            await self._emit_step()  # 流式输出：每完成一步推送进度

            # 传递数据到上下文
            data = step_result.get("data") or {}
            if data.get("url"): context["url"] = data["url"]
            if data.get("title"): context["title"] = data["title"]
            if data.get("product_id"): context["product_id"] = data["product_id"]
            if data.get("listing_id"): context["listing_id"] = data["listing_id"]
            if data.get("description"):
                context["listing_content"] = "\n\n".join(
                    [
                        str(data.get("title") or ""),
                        str(data.get("description") or ""),
                        *[str(item) for item in data.get("bullet_points") or []],
                    ]
                ).strip()
            if data.get("image_url"): context["image_url"] = data["image_url"]
            if step_result.get("summary"): context["last_summary"] = step_result["summary"]

            # 关键步骤失败则终止
            if step_result["status"] == "failed" and step_def.get("critical", False):
                break

        return self._build_summary()

    async def _create_plan(self, instruction: str) -> dict:
        """用 LLM 解析用户指令，生成执行计划

        让 AI 决定需要做什么、按什么顺序做。
        """
        system_prompt = """你是一个跨境电商 AI 助手，负责将用户的自然语言指令转为执行计划。

【核心规则】
- 你必须选择具体的工具来执行，不能只是回答问题
- 如果用户没有明确说要做什么，引导用户使用工具
- 用户提到分析/市场/能不能做/品类 → 用 analyze_category
- 用户提到选品/推荐/做点什么/想做XX → 用 select_products
- 用户提到 1688 货源、找同款、供应商、采购候选 → 用 find_1688_sources
- 调用 find_1688_sources 时，把 Amazon 英文标题提炼为简洁中文采购关键词；有真实主图时传 image_url
- 用户提到检查店铺/巡检/看看我的商品 → 用 store_check
- 用户提到库存/补货/毛利/预警/哪些商品要处理 → 用 monitor_products
- 用户只问当前经营风险或今天先处理什么 → 用 get_operations_digest
- 用户提到商品链接 + 能不能做/值不值得 → 用 analyze_product_decision
- 用户提到商品链接 → 用 scrape_1688
- 用户提到生成/发布/上架 → 用 generate_listing
- 用户提到查看或修改已有 Listing → 用 get_listing / edit_listing
- 用户提到商品场景图、参考图或自由创作图片 → 优先用 generate_image_asset
- 商品主图、场景图 → 优先用 generate_image_asset，必须带真实参考图
- generate_product_image 仅用于旧客户端兼容，不主动选择
- 用户明确要求生成商品视频并接受积分 → 用 generate_product_video
- 用户提到营销视频想法、分镜或方案 → 用 create_marketing_video_plan
- 用户提到广告文案、TikTok/Amazon/Shopify 文案或 A/B 测试 → 用 generate_marketing_copy
- 用户提到素材、最近图片/视频 → 用 list_materials
- 用户提到同步 Shopify 销量/库存 → 用 sync_shopify_operations
- 用户明确要求修改已发布 SKU 的价格 → 用 update_shopify_price
- 用户明确要求写回已发布 SKU 的库存 → 用 update_shopify_inventory
- 用户要求修改已上架商品的标题、描述或上下架状态 → 用 update_shopify_listing
- 用户明确要求取消未履约订单 → 用 cancel_shopify_order
- 用户要求把已生成图片采用到 Shopify 商品 → 用 attach_shopify_listing_images
- 用户提到商标、品牌授权、认证声称、Logo、水印或 IP 风险 → 用 screen_ip_risk
- 用户询问平台政策、认证要求或 Listing 合规依据 → 用 search_platform_policies
- 用户提到利润/成本/计算 → 用 calculate_profit
- 用户提到检查/审核 → 用 compliance_check
- 不要使用 "answer" 工具，永远用具体工具

可用工具：
1. analyze_category — 品类市场分析
   参数: {"keyword": "品类关键词，如蓝牙耳机"}
   输出: 真实 Amazon US 样本、细分方向、数据完整度和选品建议

2. select_products — 选品推荐
   参数: {"keyword": "品类关键词，如宠物用品"}
   输出: 真实样本支持的细分方向、候选商品和数据缺口

2b. find_1688_sources — 1688 货源与供应商候选
   参数: {"keyword": "中文采购关键词", "image_url": "可选真实商品主图"}
   输出: 价格、MOQ、销量、店铺、工厂标记、发货地和商品链接
   注意: 只能称相似货源，不能保证同款；不自动询价、下单或付款

3. analyze_product_decision — 单品决策
   参数: {"url": "1688商品链接", "shipping_cny": 可选单件物流成本}
   输出: 采购价门禁、真实竞品、固定公式利润和要不要做

4. scrape_1688 — 抓取1688商品
   参数: {"url": "1688商品链接"}
   输出: 商品标题、价格、图片

5. create_product — 创建商品到系统
   参数: {"url": "...", "title": "...", "price": 数字}
   注意: scrape_1688 后才能拿到数据

6. generate_listing — AI 生成 Listing 内容
   参数: {"product_id": "商品ID", "platform": "amazon/ebay/shopify/etsy/walmart", "language": "en/ja/es等"}
   注意: 需要先有商品

7. compliance_check — 合规审查
   参数: {"text": "要检查的文本"}

8. calculate_profit — 净利计算
   参数: {"selling_price": 售价, "product_cost": 成本, "platform_fee_rate": 费率}

9. store_check — 整店巡检
   参数: 无（检查当前用户所有商品）
   输出: 有问题的商品列表（缺标题/价格等）

10. monitor_products — 运营监控
   参数: 无
   输出: SKU 毛利、库存覆盖天数、补货点和未处理预警

11. get_operations_digest — 读取当前经营预警摘要
   参数: 无
   输出: 按优先级排序的预警、建议动作和跳转位置

11. self_reflect — 内容质量自检
   参数: {"content": "要审查的内容", "platform": "目标平台"}
   输出: 质量评分、问题、改进建议

12. get_listing — 读取 Listing
   参数: {"listing_id": "ListingDraft ID"}

13. edit_listing — 修改 Listing 并重置合规状态
   参数: {"listing_id": "...", "title": "...", "description": "...", "bullet_points": [...]}

14. list_materials — 查询素材
   参数: {"limit": 20}

15. generate_image_asset — 创建商品场景/自由创作图片任务
   参数: {"prompt": "...", "mode": "free_creation", "quality_tier": "standard", "confirmed": true}
   商品场景必须提供 reference_asset_ids（1-4 张）并选择 product_scene

16. generate_product_image — 兼容旧的商品图片任务
   参数: {"prompt": "...", "num_outputs": 1, "confirmed": true}

17. generate_product_video — 提交商品图生视频，会扣积分
   参数: {"source_asset_id": "...", "prompt": "...", "confirmed": true}
   注意: 用户未明确确认时 confirmed 必须为 false

18. create_marketing_video_plan — 创建营销视频 Brief 和分镜
   参数: {"source_asset_id": "...", "product_name": "...", "idea": "...", "duration": 15}
   注意: 只生成方案，不自动渲染

18. generate_marketing_copy — 生成多平台 A/B 文案资产
   参数: {"platforms": ["tiktok", "amazon", "shopify"], "language": "en", "instructions": "..."}
   注意: 必须在已选择营销活动时使用

19. sync_shopify_operations — 同步 Shopify 订单销量和库存
25. publish_to_amazon — 准备 Amazon Listing 发布，必须等待用户确认
   参数: {"channel_id": "Shopify 渠道 ID", "days": 30}
26. search_amazon_orders — 查询 Amazon 商户自履约订单状态
   参数: {"marketplace_id": "可选", "days": 7, "fulfillment_statuses": ["UNSHIPPED"]}
   注意: 只返回订单号、履约状态、商品数量和 SKU，不返回买家隐私
26b. search_temu_products — 查询 Temu 已授权商品列表
   参数: {"connection_id": "可选", "page_no": 1, "page_size": 20}
   注意: 只在商品读取 scope 和店铺类型都匹配时使用
27. fulfill_amazon_order — 准备 Amazon 商户自履约订单发货
   参数: {"order_id": "...", "marketplace_id": "...", "carrier_code": "UPS", "tracking_number": "1Z...", "ship_date": "可选"}
   注意: 只创建高风险待确认动作，不直接提交 Amazon
28. update_amazon_inventory — 准备 Amazon Listing 库存更新
   参数: {"listing_id": "...", "variant_id": "...", "marketplace_id": "...", "stock_quantity": 25}
   注意: 只创建待确认动作，不直接写平台

29. update_amazon_price — 准备 Amazon Listing 售价更新
   参数: {"listing_id": "...", "variant_id": "...", "marketplace_id": "...", "price": 39.9, "currency": "USD"}
   注意: 只创建高风险待确认动作，不直接写平台
30. update_amazon_listing — 准备 Amazon 标题、描述或卖点更新
   参数: {"listing_id": "...", "variant_id": "...", "marketplace_id": "...", "title": "可选", "description": "可选", "bullet_points": ["可选"]}
   注意: 至少提供一个变更字段，只创建待确认动作
31. attach_amazon_listing_images — 准备 Amazon Listing 图片绑定
   参数: {"listing_id": "...", "variant_id": "...", "marketplace_id": "...", "main_image_url": "可选", "other_image_urls": ["..."]}
   注意: 只接受持久 HTTPS 或 s3:// URL，不接受本地路径和临时签名地址
32. attach_amazon_listing_assets — 发布工作区素材并绑定 Amazon 图片
   参数: {"listing_id": "...", "variant_id": "...", "marketplace_id": "...", "asset_ids": ["素材 ID"]}
   注意: 所选图片会变成公网图片，只创建待确认动作

20. update_shopify_price — 准备 Shopify SKU 改价
    参数: {"variant_id": "本地 SKU ID", "price": 24.99, "channel_id": "可选"}
    注意: 只创建待确认动作，不直接写平台

21. update_shopify_inventory — 准备 Shopify SKU 库存写回
    参数: {"variant_id": "本地 SKU ID", "stock_quantity": 12, "channel_id": "可选"}
    注意: 只创建待确认动作，不直接写平台

22. update_shopify_listing — 准备修改已上架商品内容
    参数: {"listing_id": "ListingDraft ID", "title": "可选", "description": "可选", "status": "active/draft/archived"}
    注意: 只创建待确认动作，不直接写平台

23. cancel_shopify_order — 准备取消未履约 Shopify 订单
    参数: {"order_id": "9100", "channel_id": "...", "reason": "customer", "restock": true, "refund": false}
    注意: 只创建高风险待确认动作，不直接取消订单

24. attach_shopify_listing_images — 准备把图片附加到 Shopify 商品
    参数: {"listing_id": "...", "asset_ids": ["..."], "channel_id": "可选"}
    注意: 只创建待确认动作，不直接上传

25. search_platform_policies — 检索平台政策原文和引用
   参数: {"query": "...", "platform": "amazon", "market": "US", "category": "toys", "top_k": 5}

26. answer — 【仅当其他工具都不适用时】回答用户问题
   参数: {"message": "回答内容"}
   注意: 这是最后选项，优先用上面的工具

请分析用户的指令，返回 JSON 格式的执行计划：
{
    "summary": "对用户指令的理解",
    "steps": [
        {"action": "工具名", "params": {...}, "critical": true/false, "description": "这一步做什么"}
    ]
}

只返回 JSON，不要额外文字。"""

        result = await self.llm.generate(system_prompt, instruction, max_tokens=1000)
        # 提取 JSON
        match = re.search(r'\{.*\}', result, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {"summary": "无法理解指令", "steps": [{"action": "answer", "params": {"message": "请更具体地描述你要做什么"}, "critical": False}]}

    async def _execute_step(self, action: str, params: dict) -> dict:
        """执行单个步骤"""
        try:
            if action == "scrape_1688":
                return await self._do_scrape(params)
            elif action == "analyze_product_decision":
                return await self._do_analyze_product_decision(params)
            elif action == "select_products":
                return await self._do_select_products(params)
            elif action == "find_1688_sources":
                return await self._do_find_1688_sources(params)
            elif action == "store_check":
                return await self._do_store_check(params)
            elif action == "monitor_products":
                return await self._do_monitor_products(params)
            elif action == "get_operations_digest":
                return await self._do_get_operations_digest(params)
            elif action == "self_reflect":
                return await self._do_self_reflect(params)
            elif action == "create_product":
                return await self._do_create_product(params)
            elif action == "generate_listing":
                return await self._do_generate_listing(params)
            elif action == "get_listing":
                return await self._do_get_listing(params)
            elif action == "edit_listing":
                return await self._do_edit_listing(params)
            elif action == "list_materials":
                return await self._do_list_materials(params)
            elif action == "generate_product_image":
                return await self._do_generate_product_image(params)
            elif action == "generate_image_asset":
                return await self._do_generate_image_asset(params)
            elif action == "generate_product_video":
                return await self._do_generate_product_video(params)
            elif action == "create_marketing_video_plan":
                return await self._do_create_marketing_video_plan(params)
            elif action == "generate_marketing_copy":
                return await self._do_generate_marketing_copy(params)
            elif action == "compliance_check":
                return await self._do_compliance(params)
            elif action == "screen_ip_risk":
                return await self._do_screen_ip_risk(params)
            elif action == "search_platform_policies":
                return await self._do_search_platform_policies(params)
            elif action == "compliance_fix":
                return await self._do_compliance_fix(params)
            elif action == "push_to_shopify":
                return await self._do_push_to_shopify(params)
            elif action == "publish_to_amazon":
                return await self._do_publish_to_amazon(params)
            elif action == "search_amazon_orders":
                return await self._do_search_amazon_orders(params)
            elif action == "search_temu_products":
                return await self._do_search_temu_products(params)
            elif action == "search_temu_orders":
                return await self._do_search_temu_orders(params)
            elif action == "fulfill_temu_order":
                return await self._do_fulfill_temu_order(params)
            elif action == "submit_temu_listing":
                return await self._do_submit_temu_listing(params)
            elif action == "update_temu_inventory":
                return await self._do_update_temu_inventory(params)
            elif action == "submit_temu_price_change":
                return await self._do_submit_temu_price_change(params)
            elif action == "fulfill_amazon_order":
                return await self._do_fulfill_amazon_order(params)
            elif action == "update_amazon_inventory":
                return await self._do_update_amazon_offer(
                    params,
                    action_id="amazon.inventory.update",
                    tool_name="update_amazon_inventory",
                )
            elif action == "update_amazon_price":
                return await self._do_update_amazon_offer(
                    params,
                    action_id="amazon.pricing.update",
                    tool_name="update_amazon_price",
                )
            elif action == "update_amazon_listing":
                return await self._do_update_amazon_listing(params)
            elif action == "attach_amazon_listing_images":
                return await self._do_attach_amazon_listing_images(params)
            elif action == "attach_amazon_listing_assets":
                return await self._do_attach_amazon_listing_assets(params)
            elif action == "sync_shopify_operations":
                return await self._do_sync_shopify_operations(params)
            elif action == "update_shopify_price":
                return await self._do_update_shopify_price(params)
            elif action == "update_shopify_inventory":
                return await self._do_update_shopify_inventory(params)
            elif action == "update_shopify_listing":
                return await self._do_update_shopify_listing(params)
            elif action == "cancel_shopify_order":
                return await self._do_cancel_shopify_order(params)
            elif action == "attach_shopify_listing_images":
                return await self._do_attach_shopify_listing_images(params)
            elif action == "prepare_review_reply":
                return await self._do_prepare_review_reply(params)
            elif action == "calculate_profit":
                return await self._do_calculate_profit(params)
            elif action == "analyze_category":
                return await self._do_analyze_category(params)
            elif action == "answer":
                msg = params.get("message", "")
                return {"action": action, "status": "success", "result": msg, "summary": msg[:100]}
            else:
                return {"action": action, "status": "failed", "error": f"未知操作: {action}"}
        except Exception as e:
            return {"action": action, "status": "failed", "error": str(e)}

    async def _do_scrape(self, params: dict) -> dict:
        """执行 1688 抓取"""
        url = params.get("url", "")
        if not url:
            return {"action": "scrape_1688", "status": "failed", "error": "缺少URL"}

        await provider_config.refresh(self.db)

        data = await scrape_1688(
            url,
            justone_token=provider_config.get("justone", "token"),
            api_key=provider_config.get("onebound", "api_key"),
            api_secret=provider_config.get("onebound", "api_secret"),
        )

        # 自动创建商品
        product_data = {
            "url": data["url"],
            "title": data.get("title"),
            "main_image_url": data.get("main_image_url"),
            "price": data.get("price"),
            "sales_count": data.get("sales_count"),
            "shop_name": data.get("shop_name"),
        }

        return {
            "action": "scrape_1688",
            "status": "success",
            "data": product_data,
            "summary": f"已抓取商品：{data.get('title', '未知')}（¥{data.get('price', '?')}）",
        }

    async def _do_create_product(self, params: dict) -> dict:
        """创建商品到数据库"""
        from app.models.product import Product
        from uuid import UUID

        # 查重
        lookup = select(Product).where(
            Product.url == params.get("url", ""),
            Product.user_id == self.user.id,
        )
        if self.workspace_id is not None:
            lookup = lookup.where(Product.workspace_id == self.workspace_id)
        result = await self.db.execute(lookup)
        existing = result.scalar_one_or_none()
        if existing:
            return {
                "action": "create_product",
                "status": "success",
                "product_id": str(existing.id),
                "summary": f"商品已存在：{existing.title}",
            }

        product = Product(
            user_id=self.user.id,
            workspace_id=self.workspace_id,
            created_by_user_id=self.user.id,
            url=params.get("url", ""),
            title=params.get("title"),
            main_image_url=params.get("main_image_url"),
            price=params.get("price"),
            sales_count=params.get("sales_count"),
            shop_name=params.get("shop_name"),
        )
        self.db.add(product)
        await self.db.flush()

        return {
            "action": "create_product",
            "status": "success",
            "product_id": str(product.id),
            "summary": f"已创建商品：{product.title}",
        }

    async def _do_generate_listing(self, params: dict) -> dict:
        """AI 生成 Listing，复用网页主链路的完整事实、SEO 与合规逻辑。"""
        from app.models.product import Product

        product_id = params.get("product_id", "")
        platform = params.get("platform", "amazon")
        language = params.get("language", "en")
        tone = params.get("tone", "professional")

        try:
            product_query = select(Product).where(
                Product.id == UUID(product_id),
                Product.user_id == self.user.id,
            )
            if self.workspace_id is not None:
                product_query = product_query.where(
                    Product.workspace_id == self.workspace_id
                )
            result = await self.db.execute(product_query)
        except ValueError:
            return {"action": "generate_listing", "status": "failed", "error": "无效的商品ID"}

        product = result.scalar_one_or_none()
        if not product:
            return {"action": "generate_listing", "status": "failed", "error": "商品不存在"}

        generated = await generate_and_persist_listing(
            self.db,
            user=self.user,
            product=product,
            workspace_id=self.workspace_id,
            platform=platform,
            language=language,
            tone=tone,
        )
        draft = generated.draft
        listing_href = f"/app/products/{product.id}?listing={draft.id}"

        return {
            "action": "generate_listing",
            "status": "success",
            "data": {
                "listing_id": str(draft.id),
                "product_id": str(product.id),
                "listing_status": draft.status,
                "compliance_status": draft.compliance_status,
                "title": generated.title,
                "description": generated.description,
                "bullet_points": generated.bullet_points,
                "seo_title": generated.seo_title,
                "seo_description": generated.seo_description,
                "violations": generated.violations,
            },
            "links": [{"label": "查看 Listing", "href": listing_href}],
            "summary": f"已为 {platform} 生成 Listing：{generated.title[:50]}...",
        }

    async def _do_get_listing(self, params: dict) -> dict:
        """读取当前用户 Listing，供 Agent 回答内容、版本与发布状态。"""
        listing_id = params.get("listing_id", "")
        if not listing_id:
            return {"action": "get_listing", "status": "failed", "error": "缺少 Listing ID"}
        listing = await get_owned_listing(
            self.db,
            listing_id,
            self.user.id,
            workspace_id=self.workspace_id,
        )
        if listing is None:
            return {"action": "get_listing", "status": "failed", "error": "Listing 不存在"}
        data = serialize_listing(listing)
        return {
            "action": "get_listing",
            "status": "success",
            "data": data,
            "links": [
                {
                    "label": "编辑 Listing",
                    "href": f"/app/products/{listing.product_id}?listing={listing.id}",
                }
            ],
            "summary": f"已读取 Listing v{listing.version}，合规状态：{listing.compliance_status}",
        }

    async def _do_edit_listing(self, params: dict) -> dict:
        """修改 Listing 内容，版本递增后旧合规报告自动失效。"""
        listing_id = params.get("listing_id", "")
        if not listing_id:
            return {"action": "edit_listing", "status": "failed", "error": "缺少 Listing ID"}
        listing = await get_owned_listing(
            self.db,
            listing_id,
            self.user.id,
            workspace_id=self.workspace_id,
        )
        if listing is None:
            return {"action": "edit_listing", "status": "failed", "error": "Listing 不存在"}

        editable_fields = {
            "title",
            "description",
            "bullet_points",
            "seo_title",
            "seo_description",
        }
        updates = {
            key: value
            for key, value in params.items()
            if key in editable_fields and value is not None
        }
        if not updates:
            return {"action": "edit_listing", "status": "failed", "error": "没有可修改的 Listing 字段"}
        if "title" in updates and not str(updates["title"]).strip():
            return {"action": "edit_listing", "status": "failed", "error": "Listing 标题不能为空"}

        update_listing_content(listing, **updates)
        await self.db.flush()
        await self.db.refresh(listing)
        data = serialize_listing(listing)
        return {
            "action": "edit_listing",
            "status": "success",
            "data": data,
            "links": [
                {
                    "label": "查看 Listing",
                    "href": f"/app/products/{listing.product_id}?listing={listing.id}",
                }
            ],
            "summary": f"Listing 已更新到 v{listing.version}，请重新执行合规审查",
        }

    async def _do_list_materials(self, params: dict) -> dict:
        """汇总当前用户图片、商品视频与营销项目。"""
        data = await agent_capability_service.list_user_materials(
            self.db,
            self.user,
            workspace_id=self.workspace_id,
            limit=int(params.get("limit") or 20),
        )
        counts = data["counts"]
        return {
            "action": "list_materials",
            "status": "success",
            "data": data,
            "links": [{"label": "打开素材中心", "href": "/app/assets"}],
            "summary": (
                f"素材中心现有 {counts['images']} 个图片来源、"
                f"{counts['product_videos']} 个商品视频、"
                f"{counts['marketing_projects']} 个营销视频项目"
            ),
        }

    async def _do_prepare_review_reply(self, params: dict) -> dict:
        """为 Judge.me 评价创建版本化草稿，真实发布仍走确认动作。"""

        from app.models.customer_channel import CustomerChannel, CustomerThread
        from app.services.customer_reply_adapter import create_reply_draft

        if self.workspace_id is None:
            return {
                "action": "prepare_review_reply",
                "status": "failed",
                "error": "当前会话缺少工作区，无法准备评价回复",
            }
        reply_text = str(params.get("reply_text") or "").strip()
        if not reply_text:
            return {
                "action": "prepare_review_reply",
                "status": "failed",
                "error": "评价回复正文不能为空",
            }
        try:
            thread_id = UUID(str(params.get("thread_id") or ""))
        except (TypeError, ValueError):
            return {
                "action": "prepare_review_reply",
                "status": "failed",
                "error": "评价线程编号无效",
            }
        thread = (
            await self.db.execute(
                select(CustomerThread).where(
                    CustomerThread.id == thread_id,
                    CustomerThread.workspace_id == self.workspace_id,
                    CustomerThread.thread_type == "review",
                )
            )
        ).scalar_one_or_none()
        if thread is None:
            return {
                "action": "prepare_review_reply",
                "status": "failed",
                "error": "评价线程不存在或不属于当前工作区",
            }
        channel = await self.db.get(CustomerChannel, thread.channel_id)
        if (
            channel is None
            or channel.workspace_id != self.workspace_id
            or channel.provider != "judge_me"
            or channel.status != "active"
        ):
            return {
                "action": "prepare_review_reply",
                "status": "failed",
                "error": "Judge.me 评价渠道未连接或已失效",
            }
        review_id = thread.external_thread_id.removeprefix(
            "judge-me-review:"
        )
        if not review_id.isdigit():
            return {
                "action": "prepare_review_reply",
                "status": "failed",
                "error": "评价线程缺少 Judge.me 编号",
            }
        draft = await create_reply_draft(
            self.db,
            workspace_id=self.workspace_id,
            thread_id=thread.id,
            body_text=reply_text,
            language=thread.language,
            risk_level="medium",
        )
        return {
            "action": "prepare_review_reply",
            "status": "success",
            "data": {
                "thread_id": str(thread.id),
                "draft_id": str(draft.id),
                "draft_version": draft.version,
                "requires_confirmation": True,
                "pending_action": {
                    "action": "reviews.reply",
                    "params": {
                        "channel_id": str(channel.id),
                        "thread_id": str(thread.id),
                        "draft_id": str(draft.id),
                        "review_id": review_id,
                        "product_title": thread.subject,
                        "body_text": reply_text,
                        "send_reply_email": bool(
                            params.get("send_reply_email", False)
                        ),
                    },
                },
            },
            "summary": "评价回复草稿已准备，确认后公开发布",
        }

    async def _do_generate_product_image(self, params: dict) -> dict:
        """创建商品图片任务；未确认时只返回下一步提示。"""
        prompt = str(params.get("prompt") or "").strip()
        if len(prompt) < 5:
            return {
                "action": "generate_product_image",
                "status": "failed",
                "error": "图片描述至少需要 5 个字符",
            }
        if not params.get("confirmed", False):
            return {
                "action": "generate_product_image",
                "status": "success",
                "data": {
                    "requires_confirmation": True,
                    "pending_action": {
                        "action": "generate_product_image",
                        "params": {
                            "prompt": prompt,
                            "num_outputs": int(params.get("num_outputs") or 1),
                        },
                    },
                },
                "summary": "已准备图片生成方案，请确认后开始生成",
            }
        try:
            task = await agent_capability_service.schedule_product_image_task(
                self.db,
                self.user,
                workspace_id=self.workspace_id,
                prompt=prompt,
                num_outputs=int(params.get("num_outputs") or 1),
                campaign_id=self.campaign_id,
            )
        except PermissionError as exc:
            return {
                "action": "generate_product_image",
                "status": "failed",
                "error": str(exc),
            }
        return {
            "action": "generate_product_image",
            "status": "success",
            "data": {
                "task_id": str(task.id),
                "status": task.status,
                "num_outputs": task.num_outputs,
            },
            "links": [{"label": "查看图片任务", "href": "/app/images"}],
            "summary": "图片生成任务已进入队列，完成后可在图片工作台查看",
        }

    async def _do_generate_image_asset(self, params: dict) -> dict:
        """创建三模式图片任务，并把参数真实落库供调度器执行。"""
        prompt = str(params.get("prompt") or "").strip()
        mode = str(params.get("mode") or "free_creation")
        quality_tier = str(params.get("quality_tier") or "standard")
        if len(prompt) < 5:
            return {
                "action": "generate_image_asset",
                "status": "failed",
                "error": "图片描述至少需要 5 个字符",
            }
        from app.services.image_quality import image_generation_credits

        try:
            credits = image_generation_credits(
                mode,
                quality_tier,
                int(params.get("num_outputs") or 1),
            )
        except ValueError as exc:
            return {
                "action": "generate_image_asset",
                "status": "failed",
                "error": str(exc),
            }
        if not params.get("confirmed", False):
            return {
                "action": "generate_image_asset",
                "status": "success",
                "data": {
                    "requires_confirmation": True,
                    "mode": mode,
                    "quality_tier": quality_tier,
                    "estimated_credits": credits,
                    "pending_action": {
                        "action": "generate_image_asset",
                        "params": {
                            "prompt": prompt,
                            "mode": mode,
                            "quality_tier": quality_tier,
                            "aspect_ratio": str(params.get("aspect_ratio") or "1:1"),
                            "negative_prompt": str(params.get("negative_prompt") or ""),
                            "style_preset": params.get("style_preset"),
                            "use_brand_persona": params.get("use_brand_persona"),
                            "provider": str(params.get("provider") or "auto"),
                            "reference_asset_ids": [
                                str(item)
                                for item in params.get("reference_asset_ids") or []
                            ],
                            "num_outputs": int(params.get("num_outputs") or 1),
                            "idempotency_key": params.get("idempotency_key"),
                        },
                        "estimated_credits": credits,
                    },
                },
                "summary": f"预计消耗 {credits} 积分，确认后开始生成图片",
            }

        try:
            task = await agent_capability_service.schedule_product_image_task(
                self.db,
                self.user,
                workspace_id=self.workspace_id,
                prompt=prompt,
                num_outputs=int(params.get("num_outputs") or 1),
                campaign_id=self.campaign_id,
                mode=mode,
                quality_tier=quality_tier,
                aspect_ratio=str(params.get("aspect_ratio") or "1:1"),
                negative_prompt=str(params.get("negative_prompt") or ""),
                style_preset=params.get("style_preset"),
                use_brand_persona=params.get("use_brand_persona"),
                provider=str(params.get("provider") or "auto"),
                reference_asset_ids=[
                    str(item)
                    for item in params.get("reference_asset_ids") or []
                ],
                idempotency_key=params.get("idempotency_key"),
            )
        except (PermissionError, ValueError) as exc:
            return {
                "action": "generate_image_asset",
                "status": "failed",
                "error": str(exc),
            }
        return {
            "action": "generate_image_asset",
            "status": "success",
            "data": {
                "task_id": str(task.id),
                "status": task.status,
                "mode": task.mode,
                "quality_tier": task.quality_tier,
                "credits_cost": task.credits_cost,
                "num_outputs": task.num_outputs,
            },
            "links": [{"label": "打开图片工作台", "href": "/app/images"}],
            "summary": (
                f"{mode} 图片任务已进入队列，预计消耗 {task.credits_cost} 积分"
            ),
        }

    async def _do_generate_product_video(self, params: dict) -> dict:
        """提交商品图生视频；未显式确认时不得扣积分。"""
        source_asset_id = str(params.get("source_asset_id") or "").strip()
        if not source_asset_id:
            return {
                "action": "generate_product_video",
                "status": "failed",
                "error": "缺少商品首帧素材 ID",
            }
        quality_tier = str(params.get("quality_tier") or "draft")
        style_preset = str(params.get("style_preset") or "commerce_showcase")
        duration = int(params.get("duration") or 4)
        if not params.get("confirmed", False):
            from app.services.video_quality import estimate_quality_credits

            try:
                estimated_credits = estimate_quality_credits(
                    quality_tier,
                    duration,
                )
            except ValueError as exc:
                return {
                    "action": "generate_product_video",
                    "status": "failed",
                    "error": str(exc),
                }
            return {
                "action": "generate_product_video",
                "status": "success",
                "data": {
                    "requires_confirmation": True,
                    "estimated_credits": estimated_credits,
                    "source_asset_id": source_asset_id,
                    "pending_action": {
                        "action": "generate_product_video",
                        "params": {
                            "source_asset_id": source_asset_id,
                            "prompt": str(params.get("prompt") or ""),
                            "template_id": str(params.get("template_id") or "clean_product"),
                            "quality_tier": quality_tier,
                            "style_preset": style_preset,
                            "duration": duration,
                            "ratio": str(params.get("ratio") or "9:16"),
                        },
                        "estimated_credits": estimated_credits,
                    },
                },
                "summary": f"预计消耗 {estimated_credits} 积分，请明确确认后生成视频",
            }

        try:
            task = await agent_capability_service.create_product_video_task(
                self.db,
                self.user,
                workspace_id=self.workspace_id,
                source_asset_id=source_asset_id,
                prompt=str(params.get("prompt") or ""),
                template_id=str(params.get("template_id") or "clean_product"),
                quality_tier=quality_tier,
                style_preset=style_preset,
                duration=duration,
                ratio=str(params.get("ratio") or "9:16"),
                reserve_credits=1,
                campaign_id=self.campaign_id,
            )
        except (PermissionError, ValueError) as exc:
            return {
                "action": "generate_product_video",
                "status": "failed",
                "error": str(exc),
            }
        return {
            "action": "generate_product_video",
            "status": "success",
            "data": {
                "task_id": str(task.id),
                "status": task.status,
                "credits_cost": task.credits_cost,
                "model": task.model,
                "quality_tier": task.quality_tier,
                "style_preset": task.style_preset,
                "duration": task.duration,
            },
            "links": [
                {
                    "label": "查看商品视频",
                    "href": "/app/videos?tab=single",
                }
            ],
            "summary": f"商品图生视频任务已提交，消耗 {task.credits_cost} 积分",
        }

    async def _do_create_marketing_video_plan(self, params: dict) -> dict:
        """创建营销视频 Brief 与分镜，明确不启动供应商渲染。"""
        try:
            project, credits = await agent_capability_service.create_marketing_plan_project(
                self.db,
                self.user,
                workspace_id=self.workspace_id,
                source_asset_id=str(params.get("source_asset_id") or ""),
                product_name=str(params.get("product_name") or "").strip(),
                idea=str(params.get("idea") or "").strip(),
                platform=str(params.get("platform") or "tiktok"),
                market=str(params.get("market") or "US"),
                language=str(params.get("language") or "en"),
                duration=int(params.get("duration") or 15),
                template_id=str(params.get("template_id") or "presenter_demo"),
                quality_tier=str(params.get("quality_tier") or "draft"),
                style_preset=str(params.get("style_preset") or "premium_luxury"),
                campaign_id=self.campaign_id,
            )
        except (PermissionError, ValueError) as exc:
            return {
                "action": "create_marketing_video_plan",
                "status": "failed",
                "error": str(exc),
            }
        return {
            "action": "create_marketing_video_plan",
            "status": "success",
            "data": {
                "project_id": str(project.id),
                "status": project.status,
                "title": project.title,
                "duration": project.duration,
                "estimated_credits": credits,
                "render_started": False,
            },
            "links": [
                {
                    "label": "查看营销方案",
                    "href": f"/app/videos?tab=marketing&project={project.id}",
                }
            ],
            "summary": f"营销方案已生成，预计渲染消耗 {credits} 积分，尚未开始渲染",
        }

    async def _do_generate_marketing_copy(self, params: dict) -> dict:
        """生成多平台 A/B 文案并保存到当前活动。"""
        if not self.campaign_id:
            return {
                "action": "generate_marketing_copy",
                "status": "failed",
                "error": "请先选择营销活动",
            }
        platforms = params.get("platforms") or [
            "tiktok",
            "amazon",
            "shopify",
        ]
        if not isinstance(platforms, list):
            return {
                "action": "generate_marketing_copy",
                "status": "failed",
                "error": "平台参数必须是数组",
            }
        try:
            assets = await marketing_copy_service.generate_marketing_copy_batch(
                self.db,
                self.user,
                campaign_id=UUID(str(self.campaign_id)),
                platforms=[str(item) for item in platforms],
                language=str(params.get("language") or "en"),
                instructions=str(params.get("instructions") or ""),
            )
        except (ValueError, PermissionError) as exc:
            return {
                "action": "generate_marketing_copy",
                "status": "failed",
                "error": str(exc),
            }
        return {
            "action": "generate_marketing_copy",
            "status": "success",
            "data": {
                "batch_id": str(assets[0].batch_id),
                "count": len(assets),
                "platforms": sorted({asset.platform for asset in assets}),
                "variants": sorted({asset.variant_key for asset in assets}),
                "blocked": sum(
                    1 for asset in assets if asset.compliance_status == "block"
                ),
            },
            "links": [
                {
                    "label": "查看活动文案",
                    "href": f"/app/marketing-agent?campaign={self.campaign_id}",
                }
            ],
            "summary": (
                f"已生成 {len(assets)} 条多平台 A/B 文案，"
                "可在活动文案素材板查看和编辑"
            ),
        }

    async def _do_select_products(self, params: dict) -> dict:
        """选品决策：用真实 Amazon US 样本返回细分方向和参考商品。"""
        marketplace = str(params.get("marketplace") or "us").strip().lower()
        if marketplace != "us":
            return {
                "action": "select_products",
                "status": "failed",
                "error": "当前真实市场数据只支持 Amazon US（marketplace=us）",
            }
        keyword = params.get("keyword") or params.get("category") or params.get("query", "")
        if not keyword:
            return {"action": "select_products", "status": "failed", "error": "缺少品类关键词"}
        try:
            await provider_config.refresh(self.db)
            service = build_runtime_amazon_market_service()
            structured = await service.analyze(
                str(keyword).strip(),
                include_products=True,
            )
            structured = normalize_selection_report(
                structured,
                include_products=True,
            )
            structured = _attach_product_links(structured)
            summary = (
                f"已完成「{keyword}」Amazon US 选品分析，"
                f"优先方向：{structured.get('recommendation', {}).get('top_pick', '待补充')}"
            )
            return {
                "action": "select_products",
                "status": "success",
                "data": {
                    "keyword": keyword,
                    "structured": structured,
                    "report": _render_report_markdown(
                        structured,
                        str(keyword),
                        mode="select",
                    ),
                },
                "summary": summary,
            }
        except (AmazonMarketDataNotConfigured, AmazonMarketQueryError) as exc:
            return {
                "action": "select_products",
                "status": "failed",
                "error": str(exc),
            }
        except Exception as exc:
            return {
                "action": "select_products",
                "status": "failed",
                "error": f"Amazon 市场数据分析失败：{exc}",
            }

    async def _do_find_1688_sources(self, params: dict) -> dict:
        """在 1688 查找与 Amazon 候选商品相似的货源和供应商。"""

        keyword = str(
            params.get("keyword")
            or params.get("query")
            or params.get("product_name")
            or ""
        ).strip()
        if not keyword:
            return {
                "action": "find_1688_sources",
                "status": "failed",
                "error": "缺少 1688 货源搜索关键词",
            }
        image_url = str(params.get("image_url") or "").strip() or None
        try:
            await provider_config.refresh(self.db)
            structured = await search_1688_sources(
                keyword,
                image_url=image_url,
                justone_token=provider_config.get("justone", "token"),
                onebound_api_key=provider_config.get("onebound", "api_key"),
                onebound_api_secret=provider_config.get(
                    "onebound",
                    "api_secret",
                ),
                limit=10,
            )
            items = structured.get("items")
            count = len(items) if isinstance(items, list) else 0
            search_mode = (
                "图片相似搜索"
                if structured.get("image_search_used")
                else "关键词搜索"
            )
            summary = (
                f"已在 1688 完成「{keyword}」{search_mode}，"
                f"返回 {count} 个货源候选"
            )
            return {
                "action": "find_1688_sources",
                "status": "success",
                "data": {
                    "keyword": keyword,
                    "structured": structured,
                    "report": _render_sourcing_report(structured),
                },
                "summary": summary,
            }
        except SourceDiscoveryInputError as exc:
            return {
                "action": "find_1688_sources",
                "status": "failed",
                "error": str(exc),
            }
        except SourceDiscoveryError as exc:
            return {
                "action": "find_1688_sources",
                "status": "failed",
                "error": str(exc),
            }
        except Exception:
            return {
                "action": "find_1688_sources",
                "status": "failed",
                "error": "1688 货源搜索失败，请稍后重试",
            }

    async def _do_analyze_category(self, params: dict) -> dict:
        """品类分析：只用真实 Amazon US 样本，不调用模型编造数字。"""
        marketplace = str(params.get("marketplace") or "us").strip().lower()
        if marketplace != "us":
            return {
                "action": "analyze_category",
                "status": "failed",
                "error": "当前真实市场数据只支持 Amazon US（marketplace=us）",
            }
        keyword = params.get("keyword") or params.get("category") or params.get("query", "")
        if not keyword:
            return {"action": "analyze_category", "status": "failed", "error": "缺少品类关键词"}
        try:
            await provider_config.refresh(self.db)
            service = build_runtime_amazon_market_service()
            structured = await service.analyze_category(str(keyword).strip())
            structured = normalize_selection_report(
                structured,
                include_products=False,
            )
            structured = _attach_product_links(structured)
            summary = (
                f"「{keyword}」Amazon US 市场分析完成，"
                f"首选方向：{structured.get('recommendation', {}).get('top_pick', '待补充')}"
            )
            return {
                "action": "analyze_category",
                "status": "success",
                "data": {
                    "keyword": keyword,
                    "structured": structured,
                    "report": _render_report_markdown(
                        structured,
                        str(keyword),
                        mode="category",
                    ),
                },
                "summary": summary,
            }
        except (AmazonMarketDataNotConfigured, AmazonMarketQueryError) as exc:
            return {
                "action": "analyze_category",
                "status": "failed",
                "error": str(exc),
            }
        except Exception as exc:
            return {
                "action": "analyze_category",
                "status": "failed",
                "error": f"Amazon 市场数据分析失败：{exc}",
            }

    async def _do_self_reflect(self, params: dict) -> dict:
        """自我反思：审查生成的内容质量，给出评分和改进建议

        用于 Listing 生成后的质量把关：
        1. 检查内容完整性（标题/描述/卖点是否齐全）
        2. 检查平台适配度
        3. 检查 SEO 质量
        4. 检查合规性
        5. 输出评分 + 改进建议
        """
        from app.services.ai.deepseek import DeepSeekService

        content = params.get("content", "") or params.get("title", "")
        platform = params.get("platform", "amazon")
        language = params.get("language", "en")

        if not content:
            return {"action": "self_reflect", "status": "failed", "error": "缺少要审查的内容"}

        llm = DeepSeekService()
        try:
            result = await llm.generate(
                "你是电商内容质量评审员。严格评审内容质量，只返回JSON。",
                f"评审以下 {platform} Listing 内容（语言：{language}）：\n"
                f"内容：{content[:1500]}\n\n"
                f"评分标准（1-10）：\n"
                f"1. completeness：内容是否完整（标题、描述、卖点）\n"
                f"2. platform_fit：是否适配 {platform} 平台规则\n"
                f"3. seo_quality：SEO 关键词是否优化\n"
                f"4. conversion：转化说服力\n"
                f"5. compliance：是否含违规内容\n\n"
                f"返回 JSON：\n"
                f"{{\"scores\": {{\"completeness\": 8, \"platform_fit\": 7, \"seo_quality\": 6, \"conversion\": 7, \"compliance\": 9}}, \"overall\": 7, \"issues\": [\"问题1\", \"问题2\"], \"suggestions\": [\"建议1\", \"建议2\"]}}",
                max_tokens=500,
            )
            import json as _json
            import re as _re
            match = _re.search(r'\{.*\}', result, _re.DOTALL)
            if match:
                data = _json.loads(match.group())
                overall = data.get("overall", 5)
                issues = data.get("issues", [])
                suggestions = data.get("suggestions", [])

                quality = "良好" if overall >= 7 else ("一般" if overall >= 5 else "较差")
                need_improve = overall < 7

                summary = f"内容自检评分：{overall}/10（{quality}）"
                if need_improve:
                    summary += f"，建议改进：{'、'.join(suggestions[:2])}"

                return {
                    "action": "self_reflect",
                    "status": "success",
                    "data": {
                        "overall": overall,
                        "scores": data.get("scores", {}),
                        "issues": issues,
                        "suggestions": suggestions,
                        "need_improve": need_improve,
                    },
                    "summary": summary,
                }
        except Exception:
            pass

        return {"action": "self_reflect", "status": "success", "data": {"overall": 7, "need_improve": False}, "summary": "内容自检完成"}

    async def _do_screen_ip_risk(self, params: dict) -> dict:
        """执行可解释 IP 初筛，并复用当前 Listing 版本报告。"""
        product_id = str(params.get("product_id") or "").strip()
        if not product_id:
            return {
                "action": "screen_ip_risk",
                "status": "failed",
                "error": "缺少商品 ID",
            }
        try:
            product = await self.db.get(Product, UUID(product_id))
        except (ValueError, TypeError):
            product = None
        if (
            product is None
            or product.user_id != self.user.id
            or (
                self.workspace_id is not None
                and product.workspace_id != self.workspace_id
            )
        ):
            return {
                "action": "screen_ip_risk",
                "status": "failed",
                "error": "商品不存在",
            }

        listing = None
        listing_id = str(params.get("listing_id") or "").strip()
        if listing_id:
            listing = await get_owned_listing(
                self.db,
                listing_id,
                self.user.id,
                workspace_id=self.workspace_id,
            )
            if listing is None:
                return {
                    "action": "screen_ip_risk",
                    "status": "failed",
                    "error": "Listing 不存在",
                }
        else:
            listing = (
                await self.db.execute(
                    select(ListingDraft)
                    .where(
                        ListingDraft.product_id == product.id,
                        ListingDraft.user_id == self.user.id,
                        *(
                            [ListingDraft.workspace_id == self.workspace_id]
                            if self.workspace_id is not None
                            else []
                        ),
                    )
                    .order_by(ListingDraft.updated_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

        scope = str(params.get("scope") or "text").lower()
        if scope not in {"text", "image", "both"}:
            scope = "text"
        report = await screen_product_text(
            self.db,
            user=self.user,
            product=product,
            listing=listing,
            platform=listing.platform if listing else "amazon",
            trigger="agent",
            scope=scope,
        )
        return {
            "action": "screen_ip_risk",
            "status": "success",
            "data": report,
            "summary": (
                f"IP 初筛完成：{report['overall_risk']}，"
                f"{len(report['risks'])} 条风险"
            ),
            "links": [
                {
                    "label": "查看 Listing",
                    "href": (
                        f"/app/products/{product.id}?listing={listing.id}"
                        if listing
                        else f"/app/products/{product.id}"
                    ),
                }
            ],
        }

    async def _do_search_platform_policies(self, params: dict) -> dict:
        """检索平台政策原文；没有依据时明确拒绝推断。"""
        from app.services.policy_knowledge import search_policy_knowledge

        query = str(params.get("query") or "").strip()
        if len(query) < 2:
            return {
                "action": "search_platform_policies",
                "status": "failed",
                "error": "缺少要检索的平台政策问题",
            }
        result = await search_policy_knowledge(
            self.db,
            query=query,
            platform=str(params.get("platform") or "").strip() or None,
            market=str(params.get("market") or "").strip() or None,
            category=str(params.get("category") or "").strip() or None,
            top_k=int(params.get("top_k") or 5),
        )
        if not result["has_evidence"]:
            return {
                "action": "search_platform_policies",
                "status": "success",
                "data": result,
                "summary": "未检索到足够可靠的平台政策依据，请补充平台、市场或类目后重试。",
                "links": [{"label": "查看平台政策库", "href": "/app/operations"}],
            }
        links = []
        seen_urls = set()
        for item in result["items"][:3]:
            url = item.get("source_url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            links.append(
                {
                    "label": f"政策来源：{item.get('title') or '平台政策'}",
                    "href": url,
                }
            )
        return {
            "action": "search_platform_policies",
            "status": "success",
            "data": result,
            "summary": (
                f"检索到 {len(result['items'])} 条政策依据"
                f"（{result['retrieval_mode']}）"
            ),
            "links": links,
        }

    async def _do_compliance(self, params: dict) -> dict:
        """合规审查（正则 + AI 双重检测）"""
        from app.routers.shopify import compliance_check
        from app.services.ai.deepseek import DeepSeekService

        text = params.get("text", "")
        if not text:
            return {"action": "compliance_check", "status": "failed", "error": "缺少要检查的文本"}

        violations = []

        # 第一层：广告法违禁词正则
        regex_violations = compliance_check(text)
        violations.extend(regex_violations)

        # 第二层：AI 检测不当用语（侮辱、攻击、虚假宣传等）
        try:
            llm = DeepSeekService()
            ai_result = await llm.generate(
                "你是电商内容合规审核员。判断以下文本是否存在问题，只返回JSON。",
                f"检查文本是否包含：1)侮辱/攻击性用语 2)虚假宣传 3)绝对化用语 4)其他违规内容。\n文本：{text}\n返回 JSON: {{\"has_issue\": true/false, \"issue_type\": \"类型\", \"reason\": \"原因\"}}",
                max_tokens=300,
            )
            import json as _json
            import re as _re
            match = _re.search(r'\{.*\}', ai_result, _re.DOTALL)
            if match:
                data = _json.loads(match.group())
                if data.get("has_issue"):
                    issue = data.get("reason", data.get("issue_type", "内容不当"))
                    violations.append(issue)
        except Exception:
            pass  # AI 检测失败则只依赖正则

        passed = len(violations) == 0
        return {
            "action": "compliance_check",
            "status": "success",
            "data": {"passed": passed, "violations": violations},
            "summary": "合规审查通过" if passed else f"发现违规内容：{'、'.join(violations)}",
        }

    async def _do_store_check(self, params: dict) -> dict:
        """整店巡检：复用页面与定时任务共用的完整检查服务。"""
        result = await execute_store_check(
            self.db,
            self.user,
            workspace_id=self.workspace_id,
        )
        return {
            "action": "store_check",
            "status": "success",
            "data": result,
            "links": [{"label": "查看巡检详情", "href": "/app/dashboard"}],
            "summary": result["summary"],
        }

    async def _do_monitor_products(self, params: dict) -> dict:
        """执行 SKU 运营扫描，返回补货计划和预警摘要。"""
        from app.services.operations_monitor import run_monitor_scan

        result = await run_monitor_scan(
            self.db,
            self.user,
            workspace_id=self.workspace_id,
        )
        summary = (
            f"运营扫描完成：{result['sku_count']} 个 SKU，"
            f"{result['reorder_count']} 个需补货，"
            f"{result['open_alerts']} 个待处理预警。"
            f"{result['digest']['headline']}"
        )
        return {
            "action": "monitor_products",
            "status": "success",
            "data": result,
            "summary": summary,
            "links": [{"label": "查看运营预警", "href": "/app/operations"}],
        }

    async def _do_get_operations_digest(self, params: dict) -> dict:
        """只读取当前预警摘要，不触发新一轮扫描。"""
        from app.services.operation_digest import get_operation_digest

        digest = await get_operation_digest(
            self.db,
            user_id=self.user.id,
            workspace_id=self.workspace_id,
        )
        return {
            "action": "get_operations_digest",
            "status": "success",
            "data": digest,
            "summary": digest["headline"],
            "links": [{"label": "查看运营预警", "href": "/app/operations"}],
        }

    async def _do_analyze_product_decision(self, params: dict) -> dict:
        """单品决策：真实竞品、固定公式利润和缺失成本门禁。"""
        url = params.get("url", "")
        if not url:
            return {"action": "analyze_product_decision", "status": "failed", "error": "缺少商品链接"}

        try:
            await provider_config.refresh(self.db)
            data = await scrape_1688(
                url,
                justone_token=provider_config.get("justone", "token"),
                api_key=provider_config.get("onebound", "api_key"),
                api_secret=provider_config.get("onebound", "api_secret"),
            )
        except Exception as e:
            return {"action": "analyze_product_decision", "status": "failed", "error": f"抓取失败：{str(e)}"}

        title = data.get("title", "")
        price = data.get("price")
        sales = data.get("sales_count")
        shop = data.get("shop_name")

        if not title:
            return {"action": "analyze_product_decision", "status": "failed", "error": "无法获取商品标题"}

        # 采购价是利润计算的硬输入。缺失时必须让卖家补充，不能用 0 冒充。
        try:
            product_cost_cny = (
                float(price) if price not in (None, "") else None
            )
        except (TypeError, ValueError):
            product_cost_cny = None
        if product_cost_cny is None or product_cost_cny <= 0:
            return {
                "action": "analyze_product_decision",
                "status": "needs_input",
                "data": {
                    "url": url,
                    "title": title,
                    "sales_count": sales,
                    "shop_name": shop,
                    "missing_fields": ["purchase_price_cny"],
                    "reason": "1688 采购价缺失或无效，不能继续计算利润",
                },
                "summary": "已抓到商品，但缺少有效采购价。请补充 1688 采购价后再判断能不能做。",
            }

        shipping_value = params.get("shipping_cny")
        try:
            shipping_cny = (
                float(shipping_value)
                if shipping_value not in (None, "")
                else None
            )
        except (TypeError, ValueError):
            shipping_cny = None

        try:
            service = build_runtime_amazon_market_service()
            structured = await service.analyze_product_link_facts(
                title=title,
                keyword=params.get("keyword"),
            )
            market = structured.get("market", {})
            if shipping_cny is None or shipping_cny < 0:
                return {
                    "action": "analyze_product_decision",
                    "status": "needs_input",
                    "data": {
                        "url": url,
                        "title": title,
                        "cost_cny": round(product_cost_cny, 2),
                        "market": market,
                        "structured": structured,
                        "missing_fields": ["shipping_cost_cny"],
                        "reason": (
                            "真实 Amazon 竞品已读取，但单件头程、包装和入库成本"
                            "尚未提供，不能输出利润结论"
                        ),
                    },
                    "summary": (
                        "Amazon 竞品数据已读取。请补充单件头程、包装和入库成本"
                        "（人民币），再计算真实利润。"
                    ),
                }

            referral_rate = (
                params.get("platform_fee_rate")
                if params.get("platform_fee_rate") not in (None, "")
                else market.get("referral_fee_rate")
            )
            fulfillment_fee = (
                params.get("fulfillment_fee_usd")
                if params.get("fulfillment_fee_usd") not in (None, "")
                else market.get("fulfillment_fee_usd")
            )
            median_price = market.get("median_price_usd")
            conservative_price = market.get("price_p25_usd")
            aggressive_price = market.get("price_p75_usd")
            if (
                referral_rate is None
                or fulfillment_fee is None
                or median_price is None
                or conservative_price is None
                or aggressive_price is None
            ):
                missing_fields = [
                    field
                    for field, value in (
                        ("platform_fee_rate", referral_rate),
                        ("fulfillment_fee_usd", fulfillment_fee),
                        ("median_price_usd", median_price),
                        ("price_p25_usd", conservative_price),
                        ("price_p75_usd", aggressive_price),
                    )
                    if value in (None, "")
                ]
                return {
                    "action": "analyze_product_decision",
                    "status": "needs_input",
                    "data": {
                        "url": url,
                        "title": title,
                        "cost_cny": round(product_cost_cny, 2),
                        "shipping_cny": round(shipping_cny, 2),
                        "market": market,
                        "structured": structured,
                        "missing_fields": missing_fields,
                        "reason": (
                            "Amazon 竞品样本已读取，但平台佣金率或尾程配送费"
                            "尚未确认，不能输出可审计利润"
                        ),
                    },
                    "summary": (
                        "Amazon 竞品样本已读取。请确认平台佣金率和单件尾程"
                        "配送费后再计算利润。"
                    ),
                }

            exchange_value = params.get("exchange_rate")
            exchange_rate = (
                float(exchange_value)
                if exchange_value not in (None, "")
                else 7.2
            )
            scenarios = calculate_profit_scenarios(
                selling_prices_usd={
                    "conservative": conservative_price,
                    "base": median_price,
                    "aggressive": aggressive_price,
                },
                exchange_rate_cny_per_usd=exchange_rate,
                product_cost_cny=product_cost_cny,
                shipping_cost_cny=shipping_cny,
                platform_fee_rate=referral_rate,
                fulfillment_fee_usd=fulfillment_fee,
            )
            base_profit = scenarios["base"]
            market_status = structured.get("recommendation", {}).get(
                "verdict",
                "数据不足",
            )
            if base_profit["net_margin_pct"] < 0:
                decision_status = "谨慎"
            elif base_profit["net_margin_pct"] < 20:
                decision_status = "有机会但需验证"
            else:
                decision_status = market_status
            structured["recommendation"]["verdict"] = decision_status
            return {
                "action": "analyze_product_decision",
                "status": "success",
                "data": {
                    "url": url,
                    "title": title,
                    "cost_cny": round(product_cost_cny, 2),
                    "shipping_cny": round(shipping_cny, 2),
                    "exchange_rate_cny_per_usd": round(exchange_rate, 4),
                    "exchange_rate_type": (
                        "user_input"
                        if exchange_value not in (None, "")
                        else "user_assumption"
                    ),
                    "structured": structured,
                    "profit_scenarios": scenarios,
                    "decision_status": decision_status,
                    "analysis": self._render_product_decision_text(
                        title=title,
                        decision_status=decision_status,
                        base_profit=base_profit,
                        market=market,
                    ),
                },
                "summary": (
                    f"「{title[:30]}」Amazon US 决策：{decision_status}；"
                    f"基准净利率 {base_profit['net_margin_pct']:.2f}%"
                ),
            }
        except (AmazonMarketDataNotConfigured, AmazonMarketQueryError) as exc:
            return {
                "action": "analyze_product_decision",
                "status": "failed",
                "error": str(exc),
            }
        except ProfitCalculationError as exc:
            return {
                "action": "analyze_product_decision",
                "status": "failed",
                "error": f"利润输入不完整：{exc}",
            }
        except Exception as exc:
            return {
                "action": "analyze_product_decision",
                "status": "failed",
                "error": f"Amazon 市场数据分析失败：{exc}",
            }

    @staticmethod
    def _render_product_decision_text(
        *,
        title: str,
        decision_status: str,
        base_profit: dict,
        market: dict,
    ) -> str:
        """只解释确定性结果，不追加模型数字。"""
        return (
            f"「{title}」在 Amazon US 的基准判断为{decision_status}。"
            f"样本售价中位数 US${market.get('median_price_usd'):.2f}，"
            f"基准净利 ¥{base_profit['net_profit_cny']:.2f}，"
            f"净利率 {base_profit['net_margin_pct']:.2f}%。"
            "成本包含采购、头程包装、平台佣金和尾程配送。"
        )

    async def _do_compliance_fix(self, params: dict) -> dict:
        """合规自动修复：检查文本，发现违禁词自动改写"""
        from app.routers.shopify import compliance_check
        from app.services.ai.deepseek import DeepSeekService

        text = params.get("text", "")
        if not text:
            return {"action": "compliance_fix", "status": "failed", "error": "缺少文本"}

        # 第一层：正则检查
        regex_violations = compliance_check(text)

        # 第二层：AI 检查
        ai_issue = ""
        try:
            llm = DeepSeekService()
            result = await llm.generate(
                "你是电商合规审核员。检查文本是否有问题，只返回JSON。",
                f"检查文本：{text}\n是否存在：侮辱性用语、虚假宣传、绝对化用语。\n返回 JSON: {{\"has_issue\": true/false, \"reason\": \"\"}}",
                max_tokens=200,
            )
            import json as _json
            import re as _re
            match = _re.search(r'\{.*\}', result, _re.DOTALL)
            if match:
                data = _json.loads(match.group())
                if data.get("has_issue"):
                    ai_issue = data.get("reason", "内容不当")
        except Exception:
            pass

        violations = list(regex_violations) + ([ai_issue] if ai_issue else [])

        if not violations:
            return {
                "action": "compliance_fix",
                "status": "success",
                "data": {"passed": True, "fixed": False, "text": text},
                "summary": "合规审查通过，无需修改",
            }

        # 发现违规 → AI 改写
        try:
            llm = DeepSeekService()
            fixed_text = await llm.generate(
                "你是电商文案合规优化师。重写文本，去掉违规内容，保留原意，输出优化后的文本。",
                f"原文：{text}\n违规原因：{'、'.join(violations)}\n请输出合规的改写版本，只输出文本本身。",
                max_tokens=1000,
            )
            return {
                "action": "compliance_fix",
                "status": "success",
                "data": {"passed": False, "fixed": True, "text": fixed_text.strip(), "violations": violations},
                "summary": f"发现违规内容（{'、'.join(violations)}），已自动改写",
            }
        except Exception as e:
            return {
                "action": "compliance_fix",
                "status": "success",
                "data": {"passed": False, "fixed": False, "text": text, "violations": violations},
                "summary": f"发现违规内容：{'、'.join(violations)}，请手动修改",
            }

    async def _do_publish_to_amazon(self, params: dict) -> dict:
        """准备 Amazon Listing 发布计划；真实提交由动作运行时完成。"""

        from uuid import UUID as UUIDValue

        from app.models.listing_draft import ListingDraft
        from app.models.platform_connection import PlatformConnection
        from app.models.product_variant import ProductVariant
        from app.models.workspace import Workspace

        if self.workspace_id is None:
            return {
                "action": "publish_to_amazon",
                "status": "failed",
                "error": "当前会话缺少工作区",
            }
        try:
            listing_id = UUIDValue(str(params.get("listing_id") or ""))
        except (TypeError, ValueError):
            return {
                "action": "publish_to_amazon",
                "status": "failed",
                "error": "Amazon Listing 编号无效",
            }
        listing = (
            await self.db.execute(
                select(ListingDraft).where(
                    ListingDraft.id == listing_id,
                    ListingDraft.workspace_id == self.workspace_id,
                    ListingDraft.platform == "amazon",
                )
            )
        ).scalar_one_or_none()
        if listing is None:
            return {
                "action": "publish_to_amazon",
                "status": "failed",
                "error": "Amazon Listing 不存在",
            }
        if listing.compliance_status != "passed":
            return {
                "action": "publish_to_amazon",
                "status": "failed",
                "error": "Amazon Listing 当前版本尚未通过合规检查",
            }
        product = (
            await self.db.execute(
                select(Product).where(
                    Product.id == listing.product_id,
                    Product.workspace_id == self.workspace_id,
                )
            )
        ).scalar_one_or_none()
        if product is None:
            return {
                "action": "publish_to_amazon",
                "status": "failed",
                "error": "Amazon Listing 关联商品不存在",
            }
        variant_query = select(ProductVariant).where(
            ProductVariant.product_id == product.id,
            ProductVariant.workspace_id == self.workspace_id,
            ProductVariant.is_active.is_(True),
        )
        if params.get("variant_id"):
            try:
                variant_query = variant_query.where(
                    ProductVariant.id
                    == UUIDValue(str(params["variant_id"]))
                )
            except (TypeError, ValueError):
                return {
                    "action": "publish_to_amazon",
                    "status": "failed",
                    "error": "Amazon 变体编号无效",
                }
        variant = (
            await self.db.execute(
                variant_query.order_by(ProductVariant.created_at).limit(1)
            )
        ).scalar_one_or_none()
        if variant is None or variant.price is None or variant.price <= 0:
            return {
                "action": "publish_to_amazon",
                "status": "failed",
                "error": "Amazon SKU 缺少有效销售价",
            }
        marketplace_id = str(
            params.get("marketplace_id") or ""
        ).strip()
        workspace = await self.db.get(Workspace, self.workspace_id)
        if workspace is None:
            return {
                "action": "publish_to_amazon",
                "status": "failed",
                "error": "工作区不存在",
            }
        connections = (
            await self.db.execute(
                select(PlatformConnection).where(
                    PlatformConnection.user_id.in_(
                        {self.user.id, workspace.owner_user_id}
                    ),
                    PlatformConnection.platform == "amazon",
                    PlatformConnection.status == "active",
                )
            )
        ).scalars().all()
        connection = next(
            (
                item
                for item in connections
                if item.marketplace_id == marketplace_id
            ),
            None,
        )
        if connection is None:
            return {
                "action": "publish_to_amazon",
                "status": "failed",
                "error": "Amazon Marketplace 尚未绑定",
            }
        additional_attributes = params.get("additional_attributes")
        pending_params = {
            "listing_id": str(listing.id),
            "variant_id": str(variant.id),
            "marketplace_id": marketplace_id,
            "product_type": str(params.get("product_type") or "").strip(),
            "currency": str(params.get("currency") or "USD"),
            "title": listing.title,
            "sku": variant.sku,
            "additional_attributes": (
                additional_attributes
                if isinstance(additional_attributes, dict)
                else {}
            ),
        }
        return {
            "action": "publish_to_amazon",
            "status": "success",
            "data": {
                "requires_confirmation": True,
                "pending_action": {
                    "action": "amazon.listings.publish",
                    "params": pending_params,
                },
            },
            "summary": "Amazon 发布计划已准备，确认后提交 Listings Items",
        }

    async def _do_search_amazon_orders(self, params: dict) -> dict:
        """读取 Amazon FBM 订单的非敏感履约字段。"""

        from app.core.crypto import decrypt_value
        from app.models.platform_connection import PlatformConnection
        from app.models.workspace import Workspace
        from app.services.amazon_orders import AmazonOrdersService

        if self.workspace_id is None:
            return {
                "action": "search_amazon_orders",
                "status": "failed",
                "error": "当前会话缺少工作区",
            }
        workspace = await self.db.get(Workspace, self.workspace_id)
        if workspace is None:
            return {
                "action": "search_amazon_orders",
                "status": "failed",
                "error": "工作区不存在",
            }
        connections = (
            await self.db.execute(
                select(PlatformConnection).where(
                    PlatformConnection.user_id.in_(
                        {self.user.id, workspace.owner_user_id}
                    ),
                    PlatformConnection.platform == "amazon",
                    PlatformConnection.status == "active",
                )
            )
        ).scalars().all()
        marketplace_id = str(
            params.get("marketplace_id") or ""
        ).strip()
        if marketplace_id:
            connection = next(
                (
                    item
                    for item in connections
                    if item.marketplace_id == marketplace_id
                ),
                None,
            )
        else:
            connection = connections[0] if len(connections) == 1 else None
        if connection is None:
            if len(connections) > 1:
                return {
                    "action": "search_amazon_orders",
                    "status": "needs_input",
                    "data": {
                        "marketplaces": [
                            {
                                "connection_id": str(item.id),
                                "marketplace_id": item.marketplace_id,
                                "account_name": item.account_name,
                            }
                            for item in connections
                        ],
                    },
                    "summary": "请指定要查询的 Amazon Marketplace",
                }
            return {
                "action": "search_amazon_orders",
                "status": "failed",
                "error": "当前工作区没有可用的 Amazon 店铺授权",
            }

        try:
            credentials = json.loads(
                decrypt_value(connection.credentials)
            )
            refresh_token = str(
                credentials.get("refresh_token") or ""
            ).strip()
            if not refresh_token:
                raise ValueError("Amazon 店铺授权缺少 Refresh Token")
            access_token = await AmazonSpApiService().refresh_access_token(
                refresh_token
            )
            days = max(1, min(int(params.get("days") or 7), 30))
            statuses = params.get("fulfillment_statuses")
            body = await AmazonOrdersService().search_orders(
                access_token=access_token,
                marketplace_id=str(connection.marketplace_id),
                last_updated_after=(
                    datetime.now(timezone.utc) - timedelta(days=days)
                ).isoformat(),
                fulfillment_statuses=(
                    [str(item) for item in statuses]
                    if isinstance(statuses, list)
                    else None
                ),
            )
        except Exception as exc:
            return {
                "action": "search_amazon_orders",
                "status": "failed",
                "error": str(exc)[:300],
            }

        orders = []
        for order in body.get("orders") or []:
            if not isinstance(order, dict):
                continue
            fulfillment = order.get("fulfillment") or {}
            item_count = sum(
                max(0, int(item.get("quantityOrdered") or 0))
                for item in order.get("orderItems") or []
                if isinstance(item, dict)
            )
            skus = [
                str((item.get("product") or {}).get("sellerSku") or "")
                for item in order.get("orderItems") or []
                if isinstance(item, dict)
                and (item.get("product") or {}).get("sellerSku")
            ]
            created_time = str(order.get("createdTime") or "")
            age_hours = 0
            try:
                created_at = datetime.fromisoformat(
                    created_time.replace("Z", "+00:00")
                )
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                age_hours = max(
                    0,
                    int(
                        (
                            datetime.now(timezone.utc) - created_at
                        ).total_seconds()
                        // 3600
                    ),
                )
            except (TypeError, ValueError):
                pass
            orders.append(
                {
                    "order_id": str(order.get("orderId") or ""),
                    "marketplace_id": str(
                        (order.get("salesChannel") or {}).get(
                            "marketplaceId"
                        )
                        or connection.marketplace_id
                    ),
                    "fulfillment_status": str(
                        fulfillment.get("fulfillmentStatus") or ""
                    ),
                    "fulfilled_by": str(
                        fulfillment.get("fulfilledBy") or ""
                    ),
                    "created_time": created_time,
                    "last_updated_time": str(
                        order.get("lastUpdatedTime") or ""
                    ),
                    "age_hours": age_hours,
                    "item_count": item_count,
                    "skus": skus[:20],
                }
            )
        return {
            "action": "search_amazon_orders",
            "status": "success",
            "data": {
                "marketplace_id": connection.marketplace_id,
                "orders": orders,
                "count": len(orders),
            },
            "summary": f"已读取 {len(orders)} 笔 Amazon 商户自履约订单",
        }

    async def _do_search_temu_products(self, params: dict) -> dict:
        """查询当前用户已授权 Temu 店铺的商品列表。"""

        from uuid import UUID as UUIDValue

        from app.models.platform_connection import PlatformConnection

        connections = (
            await self.db.execute(
                select(PlatformConnection).where(
                    PlatformConnection.user_id == self.user.id,
                    PlatformConnection.platform == "temu",
                    PlatformConnection.status == "active",
                )
            )
        ).scalars().all()
        connection_id = str(params.get("connection_id") or "").strip()
        if connection_id:
            try:
                parsed_id = UUIDValue(connection_id)
            except (TypeError, ValueError):
                return {
                    "action": "search_temu_products",
                    "status": "failed",
                    "error": "Temu 店铺连接 ID 格式不正确",
                }
            connection = next(
                (item for item in connections if item.id == parsed_id),
                None,
            )
        else:
            connection = connections[0] if len(connections) == 1 else None
        if connection is None:
            if len(connections) > 1:
                return {
                    "action": "search_temu_products",
                    "status": "needs_input",
                    "data": {
                        "connections": [
                            {
                                "connection_id": str(item.id),
                                "account_name": item.account_name,
                                "region": item.marketplace_id,
                            }
                            for item in connections
                        ]
                    },
                    "summary": "请指定要查询的 Temu 店铺",
                }
            return {
                "action": "search_temu_products",
                "status": "failed",
                "error": "当前没有可用的 Temu 店铺授权",
            }
        try:
            data = await TemuProductReadService(
                self.db,
                user_id=self.user.id,
            ).list_products(
                connection_id=connection.id,
                page_no=max(1, int(params.get("page_no") or 1)),
                page_size=max(
                    1,
                    min(int(params.get("page_size") or 20), 50),
                ),
            )
        except Exception as exc:
            return {
                "action": "search_temu_products",
                "status": "failed",
                "error": str(exc)[:300],
            }
        return {
            "action": "search_temu_products",
            "status": "success",
            "data": data,
            "summary": f"已读取 {len(data.get('items') or [])} 个 Temu 商品",
        }

    async def _do_search_temu_orders(self, params: dict) -> dict:
        """查询当前用户 LOCAL/SEMI Temu 店铺的非敏感订单字段。"""

        from uuid import UUID as UUIDValue

        from app.models.platform_connection import PlatformConnection

        connections = (
            await self.db.execute(
                select(PlatformConnection).where(
                    PlatformConnection.user_id == self.user.id,
                    PlatformConnection.platform == "temu",
                    PlatformConnection.status == "active",
                )
            )
        ).scalars().all()
        connection_id = str(params.get("connection_id") or "").strip()
        if connection_id:
            try:
                parsed_id = UUIDValue(connection_id)
            except (TypeError, ValueError):
                return {
                    "action": "search_temu_orders",
                    "status": "failed",
                    "error": "Temu 店铺连接 ID 格式不正确",
                }
            connection = next(
                (item for item in connections if item.id == parsed_id),
                None,
            )
            if connection is None:
                return {
                    "action": "search_temu_orders",
                    "status": "failed",
                    "error": "指定的 Temu 店铺不存在或授权不可用",
                }
        elif len(connections) == 1:
            connection = connections[0]
        elif len(connections) > 1:
            return {
                "action": "search_temu_orders",
                "status": "needs_input",
                "data": {
                    "connections": [
                        {
                            "connection_id": str(item.id),
                            "account_name": item.account_name,
                            "region": item.marketplace_id,
                        }
                        for item in connections
                    ]
                },
                "summary": "请指定要查询订单的 Temu 店铺",
            }
        else:
            return {
                "action": "search_temu_orders",
                "status": "failed",
                "error": "当前没有可用的 Temu 店铺授权",
            }

        try:
            status_value = params.get("parent_order_status")
            parent_order_status = (
                int(status_value)
                if status_value not in (None, "")
                else None
            )
            data = await TemuOrderReadService(
                self.db,
                user_id=self.user.id,
            ).list_orders(
                connection_id=connection.id,
                page_number=max(1, int(params.get("page_number") or 1)),
                page_size=max(
                    1,
                    min(int(params.get("page_size") or 20), 100),
                ),
                parent_order_status=parent_order_status,
            )
        except (TypeError, ValueError) as exc:
            return {
                "action": "search_temu_orders",
                "status": "failed",
                "error": str(exc)[:300],
            }
        except Exception as exc:
            return {
                "action": "search_temu_orders",
                "status": "failed",
                "error": str(exc)[:300],
            }
        return {
            "action": "search_temu_orders",
            "status": "success",
            "data": data,
            "summary": f"已读取 {len(data.get('items') or [])} 笔 Temu 订单",
        }

    async def _do_fulfill_temu_order(self, params: dict) -> dict:
        """为 LOCAL/SEMI Temu 订单准备自发货确认动作。"""

        from app.models.platform_connection import PlatformConnection
        from app.services.temu_fulfillment_adapter import (
            TemuOrderFulfillmentActionAdapter,
        )

        if self.workspace_id is None:
            return {
                "action": "fulfill_temu_order",
                "status": "failed",
                "error": "当前会话缺少工作区",
            }
        connections = (
            await self.db.execute(
                select(PlatformConnection).where(
                    PlatformConnection.user_id == self.user.id,
                    PlatformConnection.platform == "temu",
                    PlatformConnection.status == "active",
                )
            )
        ).scalars().all()
        connection_id = str(params.get("connection_id") or "").strip()
        if connection_id:
            try:
                parsed_id = UUID(connection_id)
            except (TypeError, ValueError):
                return {
                    "action": "fulfill_temu_order",
                    "status": "failed",
                    "error": "Temu 店铺连接 ID 格式不正确",
                }
            connection = next(
                (item for item in connections if item.id == parsed_id),
                None,
            )
            if connection is None:
                return {
                    "action": "fulfill_temu_order",
                    "status": "failed",
                    "error": "指定的 Temu 店铺不存在或授权不可用",
                }
        elif len(connections) == 1:
            connection = connections[0]
        elif len(connections) > 1:
            return {
                "action": "fulfill_temu_order",
                "status": "needs_input",
                "data": {
                    "connections": [
                        {
                            "connection_id": str(item.id),
                            "account_name": item.account_name,
                            "region": item.marketplace_id,
                        }
                        for item in connections
                    ]
                },
                "summary": "请指定要发货的 Temu 店铺",
            }
        else:
            return {
                "action": "fulfill_temu_order",
                "status": "failed",
                "error": "当前没有可用的 Temu 店铺授权",
            }

        parent_order_sn = str(
            params.get("parent_order_sn") or ""
        ).strip()
        pending_input = {
            "connection_id": str(connection.id),
            "parent_order_sn": parent_order_sn,
            "carrier_id": params.get("carrier_id"),
            "tracking_number": str(
                params.get("tracking_number") or ""
            ).strip(),
            "self_shipping_warehouse_id": str(
                params.get("self_shipping_warehouse_id") or ""
            ).strip(),
        }
        adapter = TemuOrderFulfillmentActionAdapter(
            self.db,
            user_id=self.user.id,
            workspace_id=self.workspace_id,
        )
        try:
            snapshot = await adapter.preflight(
                action_id="temu.orders.fulfill",
                target_id=parent_order_sn,
                input_data=pending_input,
            )
        except Exception as exc:
            return {
                "action": "fulfill_temu_order",
                "status": "failed",
                "error": str(exc)[:300],
            }
        pending_input.update(
            {
                "carrier_id": snapshot["carrier_id"],
                "carrier_name": snapshot["carrier_name"],
                "tracking_number": snapshot["tracking_number"],
                "item_count": snapshot["item_count"],
            }
        )
        return {
            "action": "fulfill_temu_order",
            "status": "success",
            "data": {
                "requires_confirmation": True,
                "requires_input": False,
                "pending_action": {
                    "action": "temu.orders.fulfill",
                    "params": pending_input,
                },
            },
            "summary": (
                f"Temu 发货计划已准备：{parent_order_sn}，"
                f"物流单号 {pending_input['tracking_number']}"
            ),
        }

    async def _do_submit_temu_listing(self, params: dict) -> dict:
        """为 Temu Listing 准备 V3 提交动作，不直接发布。"""

        from app.models.platform_connection import PlatformConnection
        from app.services.temu_listing_publish_adapter import (
            TemuListingPublishActionAdapter,
        )

        if self.workspace_id is None:
            return {
                "action": "submit_temu_listing",
                "status": "failed",
                "error": "当前会话缺少工作区",
            }
        connections = (
            await self.db.execute(
                select(PlatformConnection).where(
                    PlatformConnection.user_id == self.user.id,
                    PlatformConnection.platform == "temu",
                    PlatformConnection.status == "active",
                )
            )
        ).scalars().all()
        connection_id = str(params.get("connection_id") or "").strip()
        if connection_id:
            try:
                parsed_id = UUID(connection_id)
            except (TypeError, ValueError):
                return {
                    "action": "submit_temu_listing",
                    "status": "failed",
                    "error": "Temu 店铺连接 ID 格式不正确",
                }
            connection = next(
                (item for item in connections if item.id == parsed_id),
                None,
            )
            if connection is None:
                return {
                    "action": "submit_temu_listing",
                    "status": "failed",
                    "error": "指定的 Temu 店铺不存在或授权不可用",
                }
        elif len(connections) == 1:
            connection = connections[0]
        elif len(connections) > 1:
            return {
                "action": "submit_temu_listing",
                "status": "needs_input",
                "data": {
                    "connections": [
                        {
                            "connection_id": str(item.id),
                            "account_name": item.account_name,
                            "region": item.marketplace_id,
                        }
                        for item in connections
                    ]
                },
                "summary": "请指定要发布商品的 Temu 店铺",
            }
        else:
            return {
                "action": "submit_temu_listing",
                "status": "failed",
                "error": "当前没有可用的 Temu 店铺授权",
            }
        listing_id = str(params.get("listing_id") or "").strip()
        asset_ids = params.get("asset_ids")
        pending_input = {
            "listing_id": listing_id,
            "connection_id": str(connection.id),
            "asset_ids": (
                [str(item) for item in asset_ids]
                if isinstance(asset_ids, list)
                else []
            ),
            "category_name": str(
                params.get("category_name") or ""
            ).strip(),
            "currency": str(params.get("currency") or "").strip().upper(),
            "language": str(params.get("language") or "").strip(),
            "attributes": (
                params.get("attributes")
                if isinstance(params.get("attributes"), list)
                else []
            ),
            "package_info": (
                params.get("package_info")
                if isinstance(params.get("package_info"), dict)
                else None
            ),
        }
        adapter = TemuListingPublishActionAdapter(
            self.db,
            user_id=self.user.id,
            workspace_id=self.workspace_id,
        )
        try:
            snapshot = await adapter.preflight(
                action_id="temu.listings.submit",
                target_id=listing_id,
                input_data=pending_input,
            )
        except Exception as exc:
            return {
                "action": "submit_temu_listing",
                "status": "failed",
                "error": str(exc)[:300],
            }
        pending_input.update(
            {
                "asset_ids": snapshot["asset_ids"],
                "asset_count": snapshot["asset_count"],
                "sku_count": snapshot["sku_count"],
                "item_count": snapshot["item_count"],
            }
        )
        return {
            "action": "submit_temu_listing",
            "status": "success",
            "data": {
                "requires_confirmation": True,
                "pending_action": {
                    "action": "temu.listings.submit",
                    "params": pending_input,
                },
            },
            "summary": (
                f"Temu 商品提交计划已准备：{snapshot['sku_count']} 个 SKU，"
                f"{snapshot['asset_count']} 张图片"
            ),
        }

    async def _do_update_temu_inventory(self, params: dict) -> dict:
        """为 Temu Listing 准备库存覆写计划。"""

        from app.models.platform_connection import PlatformConnection
        from app.services.temu_inventory_adapter import (
            TemuInventoryUpdateActionAdapter,
        )

        if self.workspace_id is None:
            return {
                "action": "update_temu_inventory",
                "status": "failed",
                "error": "当前会话缺少工作区",
            }
        connections = (
            await self.db.execute(
                select(PlatformConnection).where(
                    PlatformConnection.user_id == self.user.id,
                    PlatformConnection.platform == "temu",
                    PlatformConnection.status == "active",
                )
            )
        ).scalars().all()
        connection_id = str(params.get("connection_id") or "").strip()
        if connection_id:
            try:
                parsed_id = UUID(connection_id)
            except (TypeError, ValueError):
                return {
                    "action": "update_temu_inventory",
                    "status": "failed",
                    "error": "Temu 店铺连接 ID 格式不正确",
                }
            connection = next(
                (item for item in connections if item.id == parsed_id),
                None,
            )
            if connection is None:
                return {
                    "action": "update_temu_inventory",
                    "status": "failed",
                    "error": "指定的 Temu 店铺不存在或授权不可用",
                }
        elif len(connections) == 1:
            connection = connections[0]
        elif len(connections) > 1:
            return {
                "action": "update_temu_inventory",
                "status": "needs_input",
                "data": {
                    "connections": [
                        {
                            "connection_id": str(item.id),
                            "account_name": item.account_name,
                            "region": item.marketplace_id,
                        }
                        for item in connections
                    ]
                },
                "summary": "请指定要更新库存的 Temu 店铺",
            }
        else:
            return {
                "action": "update_temu_inventory",
                "status": "failed",
                "error": "当前没有可用的 Temu 店铺授权",
            }
        listing_id = str(params.get("listing_id") or "").strip()
        variant_id = str(params.get("variant_id") or "").strip()
        pending_input = {
            "listing_id": listing_id,
            "connection_id": str(connection.id),
            "variant_id": variant_id,
            "stock_target": params.get("stock_target"),
        }
        adapter = TemuInventoryUpdateActionAdapter(
            self.db,
            user_id=self.user.id,
            workspace_id=self.workspace_id,
        )
        try:
            snapshot = await adapter.preflight(
                action_id="temu.inventory.update",
                target_id=listing_id,
                input_data=pending_input,
            )
        except Exception as exc:
            return {
                "action": "update_temu_inventory",
                "status": "failed",
                "error": str(exc)[:300],
            }
        pending_input.update(snapshot)
        return {
            "action": "update_temu_inventory",
            "status": "success",
            "data": {
                "requires_confirmation": True,
                "pending_action": {
                    "action": "temu.inventory.update",
                    "params": pending_input,
                },
            },
            "summary": (
                f"Temu 库存计划已准备：{snapshot['sku']}，"
                f"{snapshot['current_stock']} → {snapshot['stock_target']} 件"
            ),
        }

    async def _do_submit_temu_price_change(self, params: dict) -> dict:
        """为 Temu Listing 准备基础供货价提交计划。"""

        from app.models.platform_connection import PlatformConnection
        from app.services.temu_price_adapter import (
            TemuPriceUpdateActionAdapter,
        )

        if self.workspace_id is None:
            return {
                "action": "submit_temu_price_change",
                "status": "failed",
                "error": "当前会话缺少工作区",
            }
        connections = (
            await self.db.execute(
                select(PlatformConnection).where(
                    PlatformConnection.user_id == self.user.id,
                    PlatformConnection.platform == "temu",
                    PlatformConnection.status == "active",
                )
            )
        ).scalars().all()
        connection_id = str(params.get("connection_id") or "").strip()
        if connection_id:
            try:
                parsed_id = UUID(connection_id)
            except (TypeError, ValueError):
                return {
                    "action": "submit_temu_price_change",
                    "status": "failed",
                    "error": "Temu 店铺连接 ID 格式不正确",
                }
            connection = next(
                (item for item in connections if item.id == parsed_id),
                None,
            )
            if connection is None:
                return {
                    "action": "submit_temu_price_change",
                    "status": "failed",
                    "error": "指定的 Temu 店铺不存在或授权不可用",
                }
        elif len(connections) == 1:
            connection = connections[0]
        elif len(connections) > 1:
            return {
                "action": "submit_temu_price_change",
                "status": "needs_input",
                "data": {
                    "connections": [
                        {
                            "connection_id": str(item.id),
                            "account_name": item.account_name,
                            "region": item.marketplace_id,
                        }
                        for item in connections
                    ]
                },
                "summary": "请指定要调整价格的 Temu 店铺",
            }
        else:
            return {
                "action": "submit_temu_price_change",
                "status": "failed",
                "error": "当前没有可用的 Temu 店铺授权",
            }
        listing_id = str(params.get("listing_id") or "").strip()
        pending_input = {
            "listing_id": listing_id,
            "connection_id": str(connection.id),
            "variant_id": str(params.get("variant_id") or "").strip(),
            "amount": str(params.get("amount") or "").strip(),
            "currency": str(params.get("currency") or "").strip().upper(),
            "reason": str(params.get("reason") or "").strip(),
        }
        adapter = TemuPriceUpdateActionAdapter(
            self.db,
            user_id=self.user.id,
            workspace_id=self.workspace_id,
        )
        try:
            snapshot = await adapter.preflight(
                action_id="temu.pricing.submit",
                target_id=listing_id,
                input_data=pending_input,
            )
        except Exception as exc:
            return {
                "action": "submit_temu_price_change",
                "status": "failed",
                "error": str(exc)[:300],
            }
        pending_input.update(snapshot)
        return {
            "action": "submit_temu_price_change",
            "status": "success",
            "data": {
                "requires_confirmation": True,
                "pending_action": {
                    "action": "temu.pricing.submit",
                    "params": pending_input,
                },
            },
            "summary": (
                f"Temu 价格变更计划已准备：{snapshot['sku']}，"
                f"{snapshot['currency']} {snapshot['amount']}"
            ),
        }

    async def _do_fulfill_amazon_order(self, params: dict) -> dict:
        """准备 Amazon FBM 发货动作，只返回待确认计划。"""

        from app.services.amazon_fulfillment_adapter import (
            AmazonOrderFulfillmentActionAdapter,
        )

        if self.workspace_id is None:
            return {
                "action": "fulfill_amazon_order",
                "status": "failed",
                "error": "当前会话缺少工作区",
            }
        adapter = AmazonOrderFulfillmentActionAdapter(
            self.db,
            user_id=self.user.id,
            workspace_id=self.workspace_id,
        )
        pending_input = {
            "marketplace_id": str(
                params.get("marketplace_id") or ""
            ).strip(),
            "carrier_code": str(
                params.get("carrier_code") or ""
            ).strip(),
            "carrier_name": str(
                params.get("carrier_name") or ""
            ).strip(),
            "tracking_number": str(
                params.get("tracking_number") or ""
            ).strip(),
            "shipping_method": str(
                params.get("shipping_method") or ""
            ).strip(),
            "ship_date": params.get("ship_date"),
            "package_reference_id": str(
                params.get("package_reference_id") or "1"
            ).strip(),
        }
        order_id = str(params.get("order_id") or "").strip()
        try:
            snapshot = await adapter.preflight(
                action_id="amazon.orders.fulfill",
                target_id=order_id,
                input_data=pending_input,
            )
        except Exception as exc:
            return {
                "action": "fulfill_amazon_order",
                "status": "failed",
                "error": str(exc)[:300],
            }
        pending_input.update(
            {
                "order_id": order_id,
                "ship_date": snapshot["ship_date"],
                "item_count": snapshot["item_count"],
            }
        )
        return {
            "action": "fulfill_amazon_order",
            "status": "success",
            "data": {
                "requires_confirmation": True,
                "pending_action": {
                    "action": "amazon.orders.fulfill",
                    "params": pending_input,
                },
            },
            "summary": (
                f"Amazon 发货计划已准备：{order_id}，"
                f"物流单号 {pending_input['tracking_number']}"
            ),
        }

    async def _do_update_amazon_offer(
        self,
        params: dict,
        *,
        action_id: str,
        tool_name: str,
    ) -> dict:
        """准备 Amazon 库存或售价 PATCH 动作。"""

        from app.services.amazon_offer_adapter import AmazonOfferUpdateAdapter

        if self.workspace_id is None:
            return {
                "action": tool_name,
                "status": "failed",
                "error": "当前会话缺少工作区",
            }
        listing_id = str(params.get("listing_id") or "").strip()
        variant_id = str(params.get("variant_id") or "").strip()
        marketplace_id = str(
            params.get("marketplace_id") or ""
        ).strip()
        input_data = {
            "listing_id": listing_id,
            "variant_id": variant_id,
            "marketplace_id": marketplace_id,
        }
        if action_id == "amazon.inventory.update":
            input_data["stock_quantity"] = params.get("stock_quantity")
        else:
            input_data["price"] = params.get("price")
            input_data["currency"] = params.get("currency")
        try:
            adapter = AmazonOfferUpdateAdapter(
                self.db,
                user_id=self.user.id,
                workspace_id=self.workspace_id,
            )
            snapshot = await adapter.preflight(
                action_id=action_id,
                target_id=listing_id,
                input_data=input_data,
            )
        except Exception as exc:
            return {
                "action": tool_name,
                "status": "failed",
                "error": str(exc)[:300],
            }
        input_data.update(
            {
                "sku": snapshot["sku"],
                "before_value": snapshot["before_value"],
                "after_value": snapshot["after_value"],
                "product_type": snapshot["product_type"],
            }
        )
        return {
            "action": tool_name,
            "status": "success",
            "data": {
                "requires_confirmation": True,
                "pending_action": {
                    "action": action_id,
                    "params": input_data,
                },
            },
            "summary": (
                f"Amazon {snapshot['sku']} 将从 "
                f"{snapshot['before_value']} 更新为 "
                f"{snapshot['after_value']}"
            ),
        }

    async def _do_update_amazon_listing(self, params: dict) -> dict:
        """准备 Amazon Listing 标题、描述和卖点更新。"""

        from app.services.amazon_listing_content_adapter import (
            AmazonListingContentUpdateAdapter,
        )

        if self.workspace_id is None:
            return {
                "action": "update_amazon_listing",
                "status": "failed",
                "error": "当前会话缺少工作区",
            }
        input_data = {
            "listing_id": str(params.get("listing_id") or "").strip(),
            "variant_id": str(params.get("variant_id") or "").strip(),
            "marketplace_id": str(
                params.get("marketplace_id") or ""
            ).strip(),
            "title": params.get("title"),
            "description": params.get("description"),
            "bullet_points": params.get("bullet_points"),
        }
        try:
            adapter = AmazonListingContentUpdateAdapter(
                self.db,
                user_id=self.user.id,
                workspace_id=self.workspace_id,
            )
            snapshot = await adapter.preflight(
                action_id="amazon.listings.update",
                target_id=input_data["listing_id"],
                input_data=input_data,
            )
        except Exception as exc:
            return {
                "action": "update_amazon_listing",
                "status": "failed",
                "error": str(exc)[:300],
            }
        input_data.update(
            {
                "sku": snapshot["sku"],
                "product_type": snapshot["product_type"],
                "changed_fields": snapshot["changed_fields"],
            }
        )
        return {
            "action": "update_amazon_listing",
            "status": "success",
            "data": {
                "requires_confirmation": True,
                "pending_action": {
                    "action": "amazon.listings.update",
                    "params": input_data,
                },
            },
            "summary": (
                f"Amazon {snapshot['sku']} 将更新 "
                f"{'、'.join(snapshot['changed_fields'])}"
            ),
        }

    async def _do_attach_amazon_listing_images(self, params: dict) -> dict:
        """准备 Amazon Listing 持久图片 URL 绑定。"""

        from app.services.amazon_listing_media_adapter import (
            AmazonListingMediaAttachAdapter,
        )

        if self.workspace_id is None:
            return {
                "action": "attach_amazon_listing_images",
                "status": "failed",
                "error": "当前会话缺少工作区",
            }
        input_data = {
            "listing_id": str(params.get("listing_id") or "").strip(),
            "variant_id": str(params.get("variant_id") or "").strip(),
            "marketplace_id": str(
                params.get("marketplace_id") or ""
            ).strip(),
            "main_image_url": str(
                params.get("main_image_url") or ""
            ).strip(),
            "other_image_urls": params.get("other_image_urls") or [],
        }
        try:
            adapter = AmazonListingMediaAttachAdapter(
                self.db,
                user_id=self.user.id,
                workspace_id=self.workspace_id,
            )
            snapshot = await adapter.preflight(
                action_id="amazon.listing.media.attach",
                target_id=input_data["listing_id"],
                input_data=input_data,
            )
        except Exception as exc:
            return {
                "action": "attach_amazon_listing_images",
                "status": "failed",
                "error": str(exc)[:300],
            }
        input_data.update(
            {
                "sku": snapshot["sku"],
                "product_type": snapshot["product_type"],
                "image_count": snapshot["image_count"],
            }
        )
        return {
            "action": "attach_amazon_listing_images",
            "status": "success",
            "data": {
                "requires_confirmation": True,
                "pending_action": {
                    "action": "amazon.listing.media.attach",
                    "params": input_data,
                },
            },
            "summary": (
                f"Amazon {snapshot['sku']} 将绑定 "
                f"{snapshot['image_count']} 张图片"
            ),
        }

    async def _do_attach_amazon_listing_assets(self, params: dict) -> dict:
        """准备工作区图片公共发布并绑定 Amazon Listing。"""

        from app.services.amazon_listing_asset_media_adapter import (
            AmazonListingAssetMediaAdapter,
        )

        if self.workspace_id is None:
            return {
                "action": "attach_amazon_listing_assets",
                "status": "failed",
                "error": "当前会话缺少工作区",
            }
        input_data = {
            "listing_id": str(params.get("listing_id") or "").strip(),
            "variant_id": str(params.get("variant_id") or "").strip(),
            "marketplace_id": str(
                params.get("marketplace_id") or ""
            ).strip(),
            "asset_ids": params.get("asset_ids") or [],
        }
        try:
            adapter = AmazonListingAssetMediaAdapter(
                self.db,
                user_id=self.user.id,
                workspace_id=self.workspace_id,
            )
            snapshot = await adapter.preflight(
                action_id="amazon.listing.media.attach_assets",
                target_id=input_data["listing_id"],
                input_data=input_data,
            )
        except Exception as exc:
            return {
                "action": "attach_amazon_listing_assets",
                "status": "failed",
                "error": str(exc)[:300],
            }
        input_data.update(
            {
                "asset_count": snapshot["asset_count"],
                "public_visibility": True,
            }
        )
        return {
            "action": "attach_amazon_listing_assets",
            "status": "success",
            "data": {
                "requires_confirmation": True,
                "pending_action": {
                    "action": "amazon.listing.media.attach_assets",
                    "params": input_data,
                },
            },
            "summary": (
                f"将发布 {snapshot['asset_count']} 张工作区图片并绑定到 Amazon"
            ),
        }

    async def _do_push_to_shopify(self, params: dict) -> dict:
        """Publish an owned, compliance-approved listing to Shopify."""
        listing_id = params.get("listing_id")
        if not listing_id:
            return {"action": "push_to_shopify", "status": "failed", "error": "缺少 Listing ID"}

        listing = await get_owned_listing(
            self.db,
            listing_id,
            self.user.id,
            workspace_id=self.workspace_id,
        )
        if listing is None:
            return {"action": "push_to_shopify", "status": "failed", "error": "Listing 不存在"}
        if listing.status != "ready" or listing.compliance_status != "pass":
            return {
                "action": "push_to_shopify",
                "status": "failed",
                "error": "Listing 未通过合规审查，无法发布",
            }
        report = await get_current_compliance_report(self.db, listing)
        if report is None or report.status != "pass":
            return {
                "action": "push_to_shopify",
                "status": "failed",
                "error": "Listing 合规报告已失效，请重新检查",
            }

        # 获取用户已绑定的 Shopify 店铺
        from app.models.shopify_channel import ShopifyChannel
        channel_id = params.get("channel_id", "")
        channel_query = select(ShopifyChannel).where(
            ShopifyChannel.user_id == self.user.id,
            ShopifyChannel.is_active == True,
        )
        if self.workspace_id is not None:
            channel_query = channel_query.where(
                ShopifyChannel.workspace_id == self.workspace_id
            )
        if channel_id:
            try:
                channel_query = channel_query.where(
                    ShopifyChannel.id == UUID(channel_id)
                )
            except ValueError:
                return {
                    "action": "push_to_shopify",
                    "status": "failed",
                    "error": "无效的 Shopify 渠道 ID",
                }
        result = await self.db.execute(
            channel_query
        )
        channels = result.scalars().all()
        if not channels:
            return {"action": "push_to_shopify", "status": "failed", "error": "未绑定 Shopify 店铺，请先在 Shopify 页面绑定"}

        from app.models.product import Product

        product_query = select(Product).where(
            Product.id == listing.product_id,
            Product.user_id == self.user.id,
        )
        if self.workspace_id is not None:
            product_query = product_query.where(
                Product.workspace_id == self.workspace_id
            )
        prod_result = await self.db.execute(product_query)
        product = prod_result.scalar_one_or_none()
        if not product:
            return {"action": "push_to_shopify", "status": "failed", "error": "商品不存在"}

        channel = channels[0]
        try:
            publish_result = await publish_shopify_product(
                self.db,
                user=self.user,
                product=product,
                listing=listing,
                channel=channel,
                idempotency_key=str(params.get("idempotency_key") or ""),
            )
        except ShopifyPublishError as exc:
            return {
                "action": "push_to_shopify",
                "status": "failed",
                "error": str(exc),
            }
        data = serialize_shopify_publish_result(publish_result)
        data["listing_id"] = str(listing.id)
        return {
            "action": "push_to_shopify",
            "status": "success",
            "data": data,
            "links": [
                {
                    "label": "打开 Shopify 商品",
                    "href": data.get("shopify_url") or "https://admin.shopify.com",
                }
            ],
            "summary": f"已完整发布到 {channel.shop_name}（草稿状态）",
        }

    async def _do_sync_shopify_operations(self, params: dict) -> dict:
        """把 Shopify 最新销量和库存同步到本地 SKU 运营模型。"""
        channel_id = str(params.get("channel_id") or "").strip()
        if not channel_id:
            return {
                "action": "sync_shopify_operations",
                "status": "failed",
                "error": "缺少 Shopify 渠道 ID",
            }
        try:
            parsed_channel_id = UUID(channel_id)
        except ValueError:
            return {
                "action": "sync_shopify_operations",
                "status": "failed",
                "error": "无效的 Shopify 渠道 ID",
            }

        from app.models.shopify_channel import ShopifyChannel

        channel = (
            await self.db.execute(
                select(ShopifyChannel).where(
                    ShopifyChannel.id == parsed_channel_id,
                    ShopifyChannel.user_id == self.user.id,
                    ShopifyChannel.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if channel is None:
            return {
                "action": "sync_shopify_operations",
                "status": "failed",
                "error": "Shopify 渠道不存在或未启用",
            }
        try:
            data = await run_shopify_operations_sync(
                self.db,
                user=self.user,
                channel=channel,
                days=int(params.get("days") or 30),
            )
        except ShopifyOperationsSyncError as exc:
            return {
                "action": "sync_shopify_operations",
                "status": "failed",
                "error": str(exc),
            }
        return {
            "action": "sync_shopify_operations",
            "status": "success",
            "data": data,
            "links": [
                {
                    "label": "查看运营监控",
                    "href": "/app/operations",
                }
            ],
            "summary": (
                f"Shopify 同步完成：{data['orders_scanned']} 个订单，"
                f"{data['sales_rate_updates']} 个销量更新，"
                f"{data['stock_updates']} 个库存更新"
            ),
        }

    async def _owned_variant_for_update(
        self,
        params: dict,
    ) -> tuple[ProductVariant | None, dict | None]:
        try:
            variant_id = UUID(str(params.get("variant_id") or ""))
        except (TypeError, ValueError):
            return None, {
                "action": "update_shopify_variant",
                "status": "failed",
                "error": "缺少有效的 SKU 编号",
            }
        query = select(ProductVariant).where(
            ProductVariant.id == variant_id,
            ProductVariant.user_id == self.user.id,
        )
        if self.workspace_id is not None:
            query = query.where(ProductVariant.workspace_id == self.workspace_id)
        variant = (await self.db.execute(query)).scalar_one_or_none()
        if variant is None:
            return None, {
                "action": "update_shopify_variant",
                "status": "failed",
                "error": "SKU 不存在或不属于当前工作区",
            }
        publication_query = (
            select(Publication.id)
            .join(
                ListingDraft,
                Publication.listing_id == ListingDraft.id,
            )
            .where(
                Publication.user_id == self.user.id,
                Publication.platform == "shopify",
                Publication.status == "completed",
                Publication.external_product_id.is_not(None),
                ListingDraft.product_id == variant.product_id,
            )
        )
        if self.workspace_id is not None:
            publication_query = publication_query.where(
                ListingDraft.workspace_id == self.workspace_id
            )
        channel_id = str(params.get("channel_id") or "").strip()
        if channel_id:
            publication_query = publication_query.where(
                Publication.channel_id == channel_id
            )
        publication_id = (
            await self.db.execute(publication_query.limit(1))
        ).scalar_one_or_none()
        if publication_id is None:
            return None, {
                "action": "update_shopify_variant",
                "status": "failed",
                "error": "SKU 尚未完成 Shopify 发布，不能远程写回",
            }
        return variant, None

    async def _do_update_shopify_price(self, params: dict) -> dict:
        """创建改价待确认动作，不在聊天线程直接写 Shopify。"""

        variant, error = await self._owned_variant_for_update(params)
        if error is not None:
            return error
        try:
            price = round(float(params.get("price")), 2)
        except (TypeError, ValueError):
            return {
                "action": "update_shopify_price",
                "status": "failed",
                "error": "销售价格式不正确",
            }
        if price <= 0:
            return {
                "action": "update_shopify_price",
                "status": "failed",
                "error": "销售价必须大于 0",
            }
        pending_params = {
            "variant_id": str(variant.id),
            "sku": variant.sku,
            "price": f"{price:.2f}",
        }
        if variant.cost_price is not None:
            pending_params["cost_price"] = float(variant.cost_price)
            pending_params["below_cost"] = price < float(variant.cost_price)
        channel_id = str(params.get("channel_id") or "").strip()
        if channel_id:
            pending_params["channel_id"] = channel_id
        return {
            "action": "update_shopify_price",
            "status": "success",
            "data": {
                "requires_confirmation": True,
                "pending_action": {
                    "action": "pricing.update",
                    "params": pending_params,
                },
            },
            "summary": f"已准备将 SKU {variant.sku} 售价改为 {price:.2f}。",
        }

    async def _do_update_shopify_inventory(self, params: dict) -> dict:
        """创建库存写回待确认动作。"""

        variant, error = await self._owned_variant_for_update(params)
        if error is not None:
            return {
                **error,
                "action": "update_shopify_inventory",
            }
        try:
            stock_quantity = int(params.get("stock_quantity"))
        except (TypeError, ValueError):
            return {
                "action": "update_shopify_inventory",
                "status": "failed",
                "error": "库存数量格式不正确",
            }
        if stock_quantity < 0:
            return {
                "action": "update_shopify_inventory",
                "status": "failed",
                "error": "库存数量不能小于 0",
            }
        pending_params = {
            "variant_id": str(variant.id),
            "sku": variant.sku,
            "stock_quantity": stock_quantity,
        }
        channel_id = str(params.get("channel_id") or "").strip()
        location_id = str(params.get("location_id") or "").strip()
        if channel_id:
            pending_params["channel_id"] = channel_id
        if location_id:
            pending_params["location_id"] = location_id
        return {
            "action": "update_shopify_inventory",
            "status": "success",
            "data": {
                "requires_confirmation": True,
                "pending_action": {
                    "action": "inventory.update",
                    "params": pending_params,
                },
            },
            "summary": f"已准备将 SKU {variant.sku} 库存更新为 {stock_quantity} 件。",
        }

    async def _do_update_shopify_listing(self, params: dict) -> dict:
        """创建已上架商品内容更新的待确认动作。"""

        try:
            listing_id = UUID(str(params.get("listing_id") or ""))
        except (TypeError, ValueError):
            return {
                "action": "update_shopify_listing",
                "status": "failed",
                "error": "缺少有效的 Listing 编号",
            }
        query = select(ListingDraft).where(
            ListingDraft.id == listing_id,
            ListingDraft.user_id == self.user.id,
        )
        if self.workspace_id is not None:
            query = query.where(ListingDraft.workspace_id == self.workspace_id)
        listing = (await self.db.execute(query)).scalar_one_or_none()
        if listing is None:
            return {
                "action": "update_shopify_listing",
                "status": "failed",
                "error": "Listing 不存在或不属于当前工作区",
            }
        publication_query = select(Publication.id).where(
            Publication.user_id == self.user.id,
            Publication.listing_id == listing.id,
            Publication.platform == "shopify",
            Publication.status == "completed",
            Publication.external_product_id.is_not(None),
        )
        channel_id = str(params.get("channel_id") or "").strip()
        if channel_id:
            publication_query = publication_query.where(
                Publication.channel_id == channel_id
            )
        publication_id = (
            await self.db.execute(publication_query.limit(1))
        ).scalar_one_or_none()
        if publication_id is None:
            return {
                "action": "update_shopify_listing",
                "status": "failed",
                "error": "Listing 尚未完成 Shopify 发布",
            }

        pending_params: dict[str, object] = {
            "listing_id": str(listing.id),
            "product_id": str(listing.product_id),
        }
        if "title" in params:
            title = str(params.get("title") or "").strip()
            if not title or len(title) > 500:
                return {
                    "action": "update_shopify_listing",
                    "status": "failed",
                    "error": "商品标题必须为 1 至 500 个字符",
                }
            pending_params["title"] = title
        if "description" in params:
            description = str(params.get("description") or "")
            if len(description) > 100_000:
                return {
                    "action": "update_shopify_listing",
                    "status": "failed",
                    "error": "商品描述过长",
                }
            pending_params["description"] = description
        if "status" in params:
            status = str(params.get("status") or "").strip().lower()
            if status not in {"active", "draft", "archived"}:
                return {
                    "action": "update_shopify_listing",
                    "status": "failed",
                    "error": "商品状态只支持 active、draft 或 archived",
                }
            pending_params["status"] = status
        if channel_id:
            pending_params["channel_id"] = channel_id
        if not {"title", "description", "status"} & set(pending_params):
            return {
                "action": "update_shopify_listing",
                "status": "failed",
                "error": "至少修改标题、描述或状态中的一项",
            }
        return {
            "action": "update_shopify_listing",
            "status": "success",
            "data": {
                "requires_confirmation": True,
                "pending_action": {
                    "action": "listings.update",
                    "params": pending_params,
                },
            },
            "summary": f"已准备更新 Listing「{listing.title}」。",
        }

    async def _do_cancel_shopify_order(self, params: dict) -> dict:
        """创建订单取消高风险待确认动作。"""

        order_id = str(params.get("order_id") or "").strip().rsplit("/", 1)[-1]
        if not order_id.isdigit():
            return {
                "action": "cancel_shopify_order",
                "status": "failed",
                "error": "缺少有效的 Shopify 订单编号",
            }
        channel_id = str(params.get("channel_id") or "").strip()
        try:
            parsed_channel_id = UUID(channel_id)
        except (TypeError, ValueError):
            return {
                "action": "cancel_shopify_order",
                "status": "failed",
                "error": "缺少有效的 Shopify 店铺",
            }
        from app.models.shopify_channel import ShopifyChannel

        query = select(ShopifyChannel).where(
            ShopifyChannel.id == parsed_channel_id,
            ShopifyChannel.user_id == self.user.id,
            ShopifyChannel.is_active.is_(True),
        )
        if self.workspace_id is not None:
            query = query.where(
                ShopifyChannel.workspace_id == self.workspace_id
            )
        channel = (await self.db.execute(query)).scalar_one_or_none()
        if channel is None:
            return {
                "action": "cancel_shopify_order",
                "status": "failed",
                "error": "Shopify 店铺不存在或未启用",
            }
        reason = str(params.get("reason") or "customer").strip().lower()
        if reason not in {"customer", "fraud", "inventory", "declined", "other"}:
            return {
                "action": "cancel_shopify_order",
                "status": "failed",
                "error": "不支持的订单取消原因",
            }
        pending_params = {
            "order_id": order_id,
            "channel_id": channel_id,
            "reason": reason,
            "restock": bool(params.get("restock", True)),
            "refund": bool(params.get("refund", False)),
            "notify_customer": bool(params.get("notify_customer", True)),
        }
        return {
            "action": "cancel_shopify_order",
            "status": "success",
            "data": {
                "requires_confirmation": True,
                "pending_action": {
                    "action": "orders.cancel",
                    "params": pending_params,
                },
            },
            "summary": f"已准备取消订单 #{order_id}。",
        }

    async def _do_attach_shopify_listing_images(self, params: dict) -> dict:
        """创建商品图片采用待确认动作。"""

        try:
            listing_id = UUID(str(params.get("listing_id") or ""))
            asset_ids = list(
                dict.fromkeys(
                    UUID(str(value))
                    for value in params.get("asset_ids") or []
                )
            )
        except (TypeError, ValueError):
            return {
                "action": "attach_shopify_listing_images",
                "status": "failed",
                "error": "Listing 或图片素材编号格式不正确",
            }
        if not asset_ids or len(asset_ids) > 4:
            return {
                "action": "attach_shopify_listing_images",
                "status": "failed",
                "error": "每次必须选择 1 至 4 张图片",
            }
        listing_query = select(ListingDraft).where(
            ListingDraft.id == listing_id,
            ListingDraft.user_id == self.user.id,
        )
        if self.workspace_id is not None:
            listing_query = listing_query.where(
                ListingDraft.workspace_id == self.workspace_id
            )
        listing = (await self.db.execute(listing_query)).scalar_one_or_none()
        if listing is None:
            return {
                "action": "attach_shopify_listing_images",
                "status": "failed",
                "error": "Listing 不存在或不属于当前工作区",
            }
        publication_query = select(Publication.id).where(
            Publication.user_id == self.user.id,
            Publication.listing_id == listing.id,
            Publication.platform == "shopify",
            Publication.status == "completed",
            Publication.external_product_id.is_not(None),
        )
        channel_id = str(params.get("channel_id") or "").strip()
        if channel_id:
            publication_query = publication_query.where(
                Publication.channel_id == channel_id
            )
        if (
            await self.db.execute(publication_query.limit(1))
        ).scalar_one_or_none() is None:
            return {
                "action": "attach_shopify_listing_images",
                "status": "failed",
                "error": "Listing 尚未完成 Shopify 发布",
            }
        assets = (
            await self.db.execute(
                select(ImageAsset).where(
                    ImageAsset.id.in_(asset_ids),
                    ImageAsset.user_id == self.user.id,
                    ImageAsset.workspace_id == self.workspace_id,
                )
            )
        ).scalars().all()
        asset_by_id = {asset.id: asset for asset in assets}
        if len(asset_by_id) != len(asset_ids):
            return {
                "action": "attach_shopify_listing_images",
                "status": "failed",
                "error": "图片素材不存在或不属于当前工作区",
            }
        root = Path(settings.IMAGE_STORAGE_DIR).resolve()
        for asset_id in asset_ids:
            asset = asset_by_id[asset_id]
            target = (root / asset.storage_key).resolve()
            if (
                target != root
                and root not in target.parents
            ) or not target.is_file():
                return {
                    "action": "attach_shopify_listing_images",
                    "status": "failed",
                    "error": "图片素材文件不存在或路径非法",
                }
        pending_params = {
            "listing_id": str(listing.id),
            "product_id": str(listing.product_id),
            "asset_ids": [str(asset_id) for asset_id in asset_ids],
        }
        if channel_id:
            pending_params["channel_id"] = channel_id
        return {
            "action": "attach_shopify_listing_images",
            "status": "success",
            "data": {
                "requires_confirmation": True,
                "pending_action": {
                    "action": "listing.media.attach",
                    "params": pending_params,
                },
            },
            "summary": f"已准备把 {len(asset_ids)} 张图片附加到商品。",
        }

    async def _do_calculate_profit(self, params: dict) -> dict:
        """用共享的确定性利润服务计算成本明细。"""
        try:
            result = calculate_profit(
                selling_price_usd=params.get("selling_price"),
                exchange_rate_cny_per_usd=params.get("exchange_rate"),
                product_cost_cny=params.get("product_cost"),
                shipping_cost_cny=params.get("shipping_cost"),
                platform_fee_rate=params.get("platform_fee_rate"),
                fulfillment_fee_usd=params.get("fulfillment_fee", 0),
                other_cost_cny=params.get("other_cost", 0),
            )
        except ProfitCalculationError as exc:
            return {
                "action": "calculate_profit",
                "status": "failed",
                "error": str(exc),
            }
        return {
            "action": "calculate_profit",
            "status": "success",
            "data": result,
            "summary": (
                f"净利 ¥{result['net_profit_cny']:.2f}，"
                f"净利率 {result['net_margin_pct']:.2f}%"
            ),
        }

    def _build_summary(self) -> dict:
        """汇总执行结果"""
        success_steps = [s for s in self.steps if s["status"] == "success"]
        failed_steps = [s for s in self.steps if s["status"] == "failed"]

        if not failed_steps:
            status = "success"
            summary = "全部完成！" + " ".join(s.get("summary", "") for s in success_steps)
        elif success_steps:
            status = "partial"
            summary = "部分完成。成功：" + str(len(success_steps)) + "步，失败：" + str(len(failed_steps)) + "步"
        else:
            status = "failed"
            summary = failed_steps[0].get("error", "执行失败")

        return {
            "summary": summary,
            "status": status,
            "steps": self.steps,
        }
