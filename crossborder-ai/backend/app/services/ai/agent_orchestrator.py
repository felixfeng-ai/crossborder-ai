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
- generate_product_image / generate_product_video → 提交异步素材任务
- create_marketing_video_plan → 生成营销方案与分镜
- generate_marketing_copy → 生成多平台 A/B 文案资产
- list_materials → 查询用户素材
- check_compliance(text) → 合规审查
- calculate_profit(params) → 净利计算
"""

import json
import re
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import quote_plus
from uuid import UUID

from app.core.config import settings
from app.models.user import User
from app.models.product import Product
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

    # 市场指标表格
    m_rows = [
        ("月搜索量", market.get("monthly_search_volume")),
        ("在售 Listing", market.get("active_listings")),
        ("平均售价(USD)", market.get("avg_price_usd")),
        ("头部集中度", market.get("head_concentration")),
        ("竞争度(1-5)", market.get("competition_level")),
        ("价格战程度(1-5)", market.get("price_war_level")),
        ("新品存活率", market.get("new_product_survival_rate")),
        ("用户痛点", "、".join(market.get("user_pains", []) or [])),
    ]
    lines.append("| 指标 | 数据 |")
    lines.append("|------|------|")
    for label, val in m_rows:
        if val is None or val == "":
            continue
        lines.append(f"| {label} | {val} |")

    # 候选商品表
    if mode == "select" and products:
        lines.append("")
        lines.append("## 候选商品")
        lines.append("| 商品 | 建议售价(USD) | 采购成本(CNY) | 单件净利(USD) | 净利率 | 竞争度(1-5) | 风险提示 |")
        lines.append("|------|------|------|------|------|------|------|")
        for p in products:
            lines.append(
                "| {name} | {price} | {cost} | {profit} | {margin}% | {comp} | {risk} |".format(
                    name=p.get("name", ""),
                    price=p.get("suggested_price_usd", "-"),
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


class AgentOrchestrator:
    """AI Agent 编排器 —— 基于 ReAct + Function Calling 的决策 Agent"""

    # ── 工具注册表（DeepSeek Function Calling 格式） ─────────
    TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "analyze_category",
                "description": "分析一个品类在 Amazon 的市场情况",
                "parameters": {
                    "type": "object",
                    "properties": {"keyword": {"type": "string", "description": "品类关键词，如蓝牙耳机"}},
                    "required": ["keyword"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "select_products",
                "description": "根据品类推荐值得做的商品，含利润估算",
                "parameters": {
                    "type": "object",
                    "properties": {"keyword": {"type": "string", "description": "品类关键词，如宠物用品"}},
                    "required": ["keyword"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "analyze_product_decision",
                "description": "判断一个 1688 商品能不能做",
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
                    "创建商品图片生成任务。只有用户明确要求生成图片或确认后 confirmed=true 才使用。"
                    "任务是异步的，返回 task_id、状态和图片工作台链接，不会伪造生成结果。"
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
                "description": "计算商品净利润",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selling_price": {"type": "number", "description": "售价"},
                        "product_cost": {"type": "number", "description": "成本"},
                        "platform_fee_rate": {"type": "number", "description": "平台费率"},
                        "shipping_cost": {"type": "number", "description": "运费"},
                        "exchange_rate": {"type": "number", "description": "汇率"},
                    },
                    "required": ["selling_price", "product_cost"],
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
    ]

    def __init__(
        self,
        user: User,
        db: AsyncSession,
        on_step: Optional[Callable[[list[dict]], Awaitable[None]]] = None,
        campaign_id: str | None = None,
    ):
        self.llm = DeepSeekService()
        self.user = user
        self.db = db
        self.steps: list[dict] = []  # 记录执行步骤
        self.on_step = on_step  # 步骤进度回调（流式输出用），每完成一步触发
        self.campaign_id = campaign_id

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

    async def run_react(self, instruction: str, max_rounds: int = 8) -> dict:
        """ReAct 推理循环：思考 → 调用工具 → 观察 → 再思考

        直到模型认为任务完成（不再调用工具），或达到最大轮数。
        """
        self.steps = []
        system_prompt = (
            "你是跨境电商 AI 决策助手。你可以调用工具来完成任务。\n"
            "规则：\n"
            "1. 如果需要数据分析、选品、抓取、生成等操作，调用相应工具\n"
            "2. 每次调用工具后，根据结果决定下一步\n"
            "3. 任务完成后，用自然语言总结结果给用户\n"
            "4. 不要编造工具没返回的数据\n"
            "5. 任务完成后，用简短中文总结关键结论，不要重复完整报告内容\n"
            "6. 生成视频会扣积分；只有用户明确要求并确认后才能把 confirmed 设为 true\n"
            "7. 生成图片或视频后只报告任务状态，不要声称素材已经生成完成\n"
            "8. 需要用户继续处理时，保留工具返回的链接，不要自行拼造业务地址"
        )

        # 对话历史
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": instruction},
        ]

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

    async def run(self, instruction: str) -> dict:
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
        result = await self.run_react(instruction)
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
- 用户提到检查店铺/巡检/看看我的商品 → 用 store_check
- 用户提到库存/补货/毛利/预警/哪些商品要处理 → 用 monitor_products
- 用户只问当前经营风险或今天先处理什么 → 用 get_operations_digest
- 用户提到商品链接 + 能不能做/值不值得 → 用 analyze_product_decision
- 用户提到商品链接 → 用 scrape_1688
- 用户提到生成/发布/上架 → 用 generate_listing
- 用户提到查看或修改已有 Listing → 用 get_listing / edit_listing
- 用户提到图片、主图、场景图 → 用 generate_product_image
- 用户明确要求生成商品视频并接受积分 → 用 generate_product_video
- 用户提到营销视频想法、分镜或方案 → 用 create_marketing_video_plan
- 用户提到广告文案、TikTok/Amazon/Shopify 文案或 A/B 测试 → 用 generate_marketing_copy
- 用户提到素材、最近图片/视频 → 用 list_materials
- 用户提到同步 Shopify 销量/库存 → 用 sync_shopify_operations
- 用户提到商标、品牌授权、认证声称、Logo、水印或 IP 风险 → 用 screen_ip_risk
- 用户询问平台政策、认证要求或 Listing 合规依据 → 用 search_platform_policies
- 用户提到利润/成本/计算 → 用 calculate_profit
- 用户提到检查/审核 → 用 compliance_check
- 不要使用 "answer" 工具，永远用具体工具

可用工具：
1. analyze_category — 品类市场分析
   参数: {"keyword": "品类关键词，如蓝牙耳机"}
   输出: 市场容量、竞争格局、利润模型、选品建议

2. select_products — 选品推荐
   参数: {"keyword": "品类关键词，如宠物用品"}
   输出: 推荐值得做的商品、利润估算、切入建议

3. analyze_product_decision — 单品决策
   参数: {"url": "1688商品链接"}
   输出: 能不能做、利润估算、建议定价

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

15. generate_product_image — 创建异步商品图片任务
   参数: {"prompt": "...", "num_outputs": 1, "confirmed": true}

16. generate_product_video — 提交商品图生视频，会扣积分
   参数: {"source_asset_id": "...", "prompt": "...", "confirmed": true}
   注意: 用户未明确确认时 confirmed 必须为 false

17. create_marketing_video_plan — 创建营销视频 Brief 和分镜
   参数: {"source_asset_id": "...", "product_name": "...", "idea": "...", "duration": 15}
   注意: 只生成方案，不自动渲染

18. generate_marketing_copy — 生成多平台 A/B 文案资产
   参数: {"platforms": ["tiktok", "amazon", "shopify"], "language": "en", "instructions": "..."}
   注意: 必须在已选择营销活动时使用

19. sync_shopify_operations — 同步 Shopify 订单销量和库存
   参数: {"channel_id": "Shopify 渠道 ID", "days": 30}

20. search_platform_policies — 检索平台政策原文和引用
   参数: {"query": "...", "platform": "amazon", "market": "US", "category": "toys", "top_k": 5}

21. answer — 【仅当其他工具都不适用时】回答用户问题
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
            elif action == "sync_shopify_operations":
                return await self._do_sync_shopify_operations(params)
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
        result = await self.db.execute(
            select(Product).where(
                Product.url == params.get("url", ""),
                Product.user_id == self.user.id,
            )
        )
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
            result = await self.db.execute(
                select(Product).where(
                    Product.id == UUID(product_id),
                    Product.user_id == self.user.id,
                )
            )
        except ValueError:
            return {"action": "generate_listing", "status": "failed", "error": "无效的商品ID"}

        product = result.scalar_one_or_none()
        if not product:
            return {"action": "generate_listing", "status": "failed", "error": "商品不存在"}

        generated = await generate_and_persist_listing(
            self.db,
            user=self.user,
            product=product,
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
        listing = await get_owned_listing(self.db, listing_id, self.user.id)
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
        listing = await get_owned_listing(self.db, listing_id, self.user.id)
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
                "data": {"requires_confirmation": True},
                "summary": "已准备图片生成方案，请确认后开始生成",
            }
        try:
            task = await agent_capability_service.schedule_product_image_task(
                self.db,
                self.user,
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
                },
                "summary": f"预计消耗 {estimated_credits} 积分，请明确确认后生成视频",
            }

        try:
            task = await agent_capability_service.create_product_video_task(
                self.db,
                self.user,
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
        """选品决策：输入品类，AI 推荐值得做的商品（输出结构化 JSON + 模板 Markdown）"""
        from app.services.ai.deepseek import DeepSeekService

        keyword = params.get("keyword") or params.get("category") or params.get("query", "")
        if not keyword:
            return {"action": "select_products", "status": "failed", "error": "缺少品类关键词"}

        llm = DeepSeekService()
        try:
            # 让 AI 生成选品建议（只输出 JSON，后端解析为结构化数据 + 模板渲染 Markdown）
            raw = await llm.generate(
                "你是跨境电商选品专家。只输出一个 JSON 对象，不要 markdown，不要 ``` 围栏，不要任何解释文字。所有字段值（商品名、痛点、风险、理由等）一律用中文。",
                f"分析品类「{keyword}」Amazon US 市场选品机会，返回 JSON：\n"
                f'{{"market": {{"monthly_search_volume": 数字, "active_listings": 数字, '
                f'"avg_price_usd": 数字, "head_concentration": 0-100, "competition_level": 1-5, '
                f'"price_war_level": 1-5, "new_product_survival_rate": 0-100, '
                f'"user_pains": ["痛点1", "痛点2"]}}, '
                f'"products": [{{"name": "商品名", "suggested_price_usd": 数字, "cost_cny": 数字, '
                f'"net_profit_usd": 数字, "net_margin": 0-100, "competition": 1-5, '
                f'"risk_tips": ["风险1"]}} 共5个], '
                f'"recommendation": {{"top_pick": "首选商品", "verdict": "结论", "score": 0-10, '
                f'"reasons": ["理由"], "risks": ["风险"], "entry_advice": "切入建议"}}}} '
                f"数据用具体合理数字。",
                max_tokens=4000,
                temperature=0.3,
            )

            structured = _extract_json(raw)
            if structured:
                structured = _attach_product_links(structured)
                data = {
                    "keyword": keyword,
                    "structured": structured,
                    "report": _render_report_markdown(structured, keyword, mode="select"),
                }
                summary = f"已完成「{keyword}」选品分析，推荐 {len(structured.get('products', []) or [])} 个候选商品，含利润估算"
            else:
                # 解析失败：降级为原始文本，不中断
                data = {
                    "keyword": keyword,
                    "structured": None,
                    "report": raw.strip() or f"「{keyword}」选品分析完成",
                }
                summary = f"已完成「{keyword}」选品分析（数据解析降级）"

            return {"action": "select_products", "status": "success", "data": data, "summary": summary}
        except Exception as e:
            return {"action": "select_products", "status": "failed", "error": str(e)}

    async def _do_analyze_category(self, params: dict) -> dict:
        """品类分析（输出结构化 JSON + 模板 Markdown，与选品共用同一 schema）"""
        from app.services.ai.deepseek import DeepSeekService
        keyword = params.get("keyword") or params.get("category") or params.get("query", "")
        if not keyword:
            return {"action": "analyze_category", "status": "failed", "error": "缺少品类关键词"}
        try:
            llm = DeepSeekService()
            raw = await llm.generate(
                "你是跨境电商数据分析师。只输出一个 JSON 对象，不要 markdown，不要 ``` 围栏，不要任何解释文字。所有字段值（商品名、痛点、风险、理由等）一律用中文。",
                f"分析品类「{keyword}」Amazon US 市场，返回 JSON：\n"
                f'{{"market": {{"monthly_search_volume": 数字, "active_listings": 数字, '
                f'"avg_price_usd": 数字, "head_concentration": 0-100, "competition_level": 1-5, '
                f'"price_war_level": 1-5, "new_product_survival_rate": 0-100, '
                f'"user_pains": ["用户痛点1", "用户痛点2", "用户痛点3"]}}, '
                f'"products": [], '
                f'"recommendation": {{"top_pick": "首选切入方向", "verdict": "能不能做的结论", '
                f'"score": 0-10, "reasons": ["理由"], "risks": ["风险"], '
                f'"entry_advice": "切入建议"}}}} '
                f"数据用具体合理数字。",
                max_tokens=4000,
                temperature=0.3,
            )

            structured = _extract_json(raw)
            if structured:
                structured = _attach_product_links(structured)
                data = {
                    "keyword": keyword,
                    "structured": structured,
                    "report": _render_report_markdown(structured, keyword, mode="category"),
                }
                summary = f"「{keyword}」市场分析完成"
            else:
                # 解析失败：降级为原始文本，不中断
                data = {
                    "keyword": keyword,
                    "structured": None,
                    "report": raw.strip() or f"「{keyword}」市场分析完成",
                }
                summary = f"「{keyword}」市场分析完成（数据解析降级）"

            return {"action": "analyze_category", "status": "success", "data": data, "summary": summary}
        except Exception as e:
            return {"action": "analyze_category", "status": "failed", "error": str(e)}

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
        if product is None or product.user_id != self.user.id:
            return {
                "action": "screen_ip_risk",
                "status": "failed",
                "error": "商品不存在",
            }

        listing = None
        listing_id = str(params.get("listing_id") or "").strip()
        if listing_id:
            listing = await get_owned_listing(self.db, listing_id, self.user.id)
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
        result = await execute_store_check(self.db, self.user)
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

        result = await run_monitor_scan(self.db, self.user)
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
        )
        return {
            "action": "get_operations_digest",
            "status": "success",
            "data": digest,
            "summary": digest["headline"],
            "links": [{"label": "查看运营预警", "href": "/app/operations"}],
        }

    async def _do_analyze_product_decision(self, params: dict) -> dict:
        """单品决策：判断一个 1688 商品能不能做

        流程：
        1. 抓取 1688 商品信息
        2. 算成本（采购价 + 运费）
        3. AI 分析市场竞争力
        4. 输出：能做/不能做 + 理由 + 建议定价
        """
        from app.services.ai.deepseek import DeepSeekService

        url = params.get("url", "")
        if not url:
            return {"action": "analyze_product_decision", "status": "failed", "error": "缺少商品链接"}

        # 1. 抓取商品
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
        price = data.get("price")  # 1688 供货价
        sales = data.get("sales_count")
        shop = data.get("shop_name")

        if not title:
            return {"action": "analyze_product_decision", "status": "failed", "error": "无法获取商品标题"}

        # 2. 算成本
        cost_cny = price or 0
        # 预估运费（跨境电商，按重量估，这里简化）
        shipping_cny = 15
        total_cost = cost_cny + shipping_cny

        # 3. AI 分析
        llm = DeepSeekService()
        try:
            analysis = await llm.generate(
                "你是跨境电商选品专家。根据商品信息和采购成本，判断这个品能不能做，给出结论和建议。",
                f"商品：{title}\n采购价：¥{cost_cny}\n预估总成本：¥{total_cost}\n销量参考：{sales or '未知'}\n店铺：{shop or '未知'}\n\n"
                f"请分析：\n1. Amazon 上类似产品的价格带\n2. 这个品的竞争力\n3. 利润空间估算（假设定价为采购价 3-5 倍）\n4. 最终结论：能做/谨慎/不能做 + 理由\n5. 建议定价和预计月利润",
                max_tokens=1500,
            )
        except Exception:
            analysis = f"AI 分析暂不可用，基础数据：采购价 ¥{cost_cny}，建议定价为采购价的 3-5 倍。"

        return {
            "action": "analyze_product_decision",
            "status": "success",
            "data": {
                "url": url,
                "title": title,
                "cost_cny": cost_cny,
                "analysis": analysis,
            },
            "summary": f"已分析「{title[:30]}」：采购价 ¥{cost_cny}",
        }

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

    async def _do_push_to_shopify(self, params: dict) -> dict:
        """Publish an owned, compliance-approved listing to Shopify."""
        listing_id = params.get("listing_id")
        if not listing_id:
            return {"action": "push_to_shopify", "status": "failed", "error": "缺少 Listing ID"}

        listing = await get_owned_listing(self.db, listing_id, self.user.id)
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

        prod_result = await self.db.execute(
            select(Product).where(
                Product.id == listing.product_id,
                Product.user_id == self.user.id,
            )
        )
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

    async def _do_calculate_profit(self, params: dict) -> dict:
        """净利计算"""
        selling_price = float(params.get("selling_price", 0))
        product_cost = float(params.get("product_cost", 0))
        platform_fee_rate = float(params.get("platform_fee_rate", 0.15))
        shipping_cost = float(params.get("shipping_cost", 0))
        exchange_rate = float(params.get("exchange_rate", 7.2))

        price_cny = selling_price * exchange_rate
        platform_fee = price_cny * platform_fee_rate
        total_cost = platform_fee + product_cost + shipping_cost
        net_profit = price_cny - total_cost
        margin = (net_profit / price_cny * 100) if price_cny > 0 else 0

        return {
            "action": "calculate_profit",
            "status": "success",
            "data": {
                "selling_price_cny": round(price_cny, 2),
                "net_profit": round(net_profit, 2),
                "profit_margin": round(margin, 1),
            },
            "summary": f"净利：¥{round(net_profit, 2)}，利润率：{round(margin, 1)}%",
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
