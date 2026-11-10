"""VeyaShip - AI 内容生成路由（F2 Refinery）

【全栈学习者必读】
这个模块展示了后端最复杂的业务流程：
1. 数据库操作：查商品、查品牌调性、查/改积分
2. 外部 API 调用：DeepSeek AI、Replicate FLUX
3. 业务逻辑：积分扣减、品牌调性注入、生成模式选择
4. 异常处理：各种失败场景的优雅处理

多层架构：
- routers/ 层：处理 HTTP 请求/响应（本文件）
- services/ai/ 层：调用 LLM API
- models/ 层：数据库数据结构
- schemas/ 层：API 请求/响应校验

请求处理流程：
1. 验证用户认证 → get_current_user
2. 检查积分 → 不够则 402
3. 查数据库 → 从 products 表读商品
4. 查品牌调性 → 从 personas 表读用户配置
5. 调用 AI → services/ai/deepseek.py
6. 可选生成图片 → services/ai/replicate.py
7. 扣减积分 → user.deduct_credits()
8. 返回结果 → GenerateResponse
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import RateLimit
from app.dependencies import get_current_user
from app.models.product import Product
from app.models.user import User
from app.services.ai.deepseek import DeepSeekService
from app.services.ai.persona_kit import (
    fetch_persona,
    build_persona_kit,
    format_persona_block,
    image_style_phrase,
    strip_banned_words,
)
from app.services.ai.compliance import merge_banned_words, check_text, suggest_replacements
from app.services.listing_service import persist_generated_listing
from app.services import provider_config
from pydantic import BaseModel, Field

logger = logging.getLogger("veyaship")

router = APIRouter(prefix="/content", tags=["AI 内容生成"])


# ── 请求/响应模型 ──────────────────────────────────────────────
# Pydantic 模型 vs SQLAlchemy 模型：
# - Pydantic 模型：校验 HTTP 请求/响应的数据格式（本文件）
# - SQLAlchemy 模型：定义数据库表结构（models/ 下）
# 两者分层清晰，各司其职

class GenerateRequest(BaseModel):
    """AI 生成请求的参数

    FastAPI 会自动：
    1. 从请求体 JSON 解析
    2. 按类型校验（product_id 必须是字符串）
    3. 按约束校验（min_length、ge=1 等）
    4. 不符合就返回 422 错误
    """
    product_id: str = Field(..., description="商品 ID（UUID 字符串）")
    platform: str = Field(default="amazon", description="目标平台: amazon, ebay, shopify, etsy, shein, temu, tiktok, aliexpress, walmart, shopee, lazada")
    tone: str = Field(default="professional", description="语气: professional, casual, luxury")
    language: str = Field(default="en", description="输出语言: en, ja, es, fr, de, pt 等")
    generate_image: bool = Field(default=False, description="是否同时用 FLUX 生成商品主图")
    image_prompt: str = Field(default="", description="自定义图片描述，留空则自动根据商品标题生成")
    expert_mode: bool = Field(default=False, description="启用 Agent 深度优化（多轮自检+优化，较慢但质量更高）")


class GenerateResponse(BaseModel):
    """AI 生成的结果"""
    title: str = ""
    description: str = ""
    bullet_points: list[str] = []
    seo_title: str = ""
    seo_description: str = ""
    image_url: str = ""
    image_task_id: str = ""  # 异步图片任务ID，前端可轮询
    model_used: str = ""
    listing_id: str = ""
    listing_status: str = ""
    compliance_status: str = ""
    # 合规后置校验（CAP-05）：命中平台/品牌违禁词时 blocked=True，内容不视为可发布
    blocked: bool = False
    violations: list[str] = []
    suggestions: list[dict] = []  # [{word, replacement}]


@router.post("/generate", response_model=GenerateResponse)
async def generate_listing(
    payload: GenerateRequest,
    request: Request,
    # RateLimit("ai_generate") 限制 AI 生成频率：10 次/分钟
    current_user: User = Depends(get_current_user),
    _ratelimit=Depends(RateLimit("ai_generate")),
    db: AsyncSession = Depends(get_db),
):
    """【核心】AI 根据商品数据自动生成 Listing 内容

    这就是 F2 模块的核心功能：
    1. 选一个已抓取的商品
    2. 选目标平台（Amazon/eBay/Shopify 等）
    3. AI 自动生成：标题、描述、卖点、SEO

    为什么不在前端直接调 DeepSeek API？
    - 安全性：API Key 不能暴露给前端
    - 业务逻辑：品牌调性注入、积分扣减在后端做
    - 可控性：可以限流、监控、计费
    - 扩展性：未来可以切换 AI 服务商，前端无感知

    Args:
        payload: 生成请求参数（商品ID、平台、语气等）
        request: HTTP 请求对象
        current_user: 当前登录的用户（从 JWT 解析）
        db: 数据库会话

    Returns:
        GenerateResponse: AI 生成的标题、描述、卖点、SEO

    Raises:
        HTTPException 402: 积分不足
        HTTPException 400: 商品 ID 无效或商品缺标题
        HTTPException 404: 商品不存在
        HTTPException 502: AI 服务不可用
    """
    from uuid import UUID

    # ════════════════════════════════════════════════════════════
    # 第 1 步：积分检查
    # ════════════════════════════════════════════════════════════
    # 每次 AI 生成消耗 1 积分
    # credit 字段在 User 模型上，通过 deduct_credits 方法原子扣减
    if current_user.credits < 1:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="积分不足，每次 AI 生成消耗 1 积分",
        )

    # ════════════════════════════════════════════════════════════
    # 第 2 步：查商品
    # ════════════════════════════════════════════════════════════
    # SELECT * FROM products WHERE id = ?
    # UUID 字符串转 UUID 对象，格式错误则 400
    try:
        product_id = UUID(payload.product_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的商品 ID 格式",
        )

    # 归属过滤：只允许基于自己的商品生成文案，他人商品等同不存在
    result = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.user_id == current_user.id,
        )
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="商品不存在",
        )

    if not product.title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="商品缺少标题，请先补充商品信息",
        )

    # ════════════════════════════════════════════════════════════
    # 第 3 步：加载品牌调性（F5 Persona → Brand Kit，CAP-04）
    # ════════════════════════════════════════════════════════════
    # 统一经 services/ai/persona_kit.py 读取并渲染成中文「品牌档案」块，
    # 缺失字段跳过；无配置则 block 为空（AI 不感知品牌）。
    # 同一 kit 同时驱动文案注入（block）与图片风格（image_style_phrase）。
    persona_block = ""
    brand_banned_words: list[str] = []
    image_style_suffix = ""
    brand_name_identity = ""
    persona = await fetch_persona(db, current_user.id)
    if persona:
        kit = build_persona_kit(persona)
        persona_block = format_persona_block(kit)
        brand_banned_words = kit.get("banned_words") or []
        image_style_suffix = image_style_phrase(kit)
        brand_name_identity = kit.get("brand_name") or ""

    # ════════════════════════════════════════════════════════════
    # 第 4 步：调用 AI 生成内容
    # ════════════════════════════════════════════════════════════
    # 两种模式：
    # 1. 普通模式：三步调用 DeepSeek（标题 → 描述 → 卖点 → SEO）
    # 2. 专家模式：用 LangGraph Agent 自动自检和优化
    try:
        if payload.expert_mode:
            # ── 专家模式（多轮自检） ────────────────────────
            # ListingAgent 是一个 LangGraph 驱动的 Agent
            # 它会自我审视、优化、再审视，重复多次
            from app.services.ai.agent import ListingAgent
            agent = ListingAgent()
            agent_result = await agent.run(
                product_title=product.title or "",
                product_description=product.description or "",
                features=f"价格: {product.price}" if product.price else "",
                platform=payload.platform,
                tone=payload.tone,
                target_language=payload.language if payload.language != "en" else None,
                max_iterations=2,
                persona_block=persona_block,
            )
            title = agent_result.get("title", "")
            description = agent_result.get("description", "")
            bullets = agent_result.get("bullet_points", [])
            seo = {
                "seo_title": agent_result.get("seo_title", ""),
                "seo_description": agent_result.get("seo_description", ""),
            }
        else:
            # ── 普通模式（分步调用） ────────────────────────
            llm = DeepSeekService()
            # 标题、描述、卖点互不依赖，并发执行
            t1 = _generate_title(llm, product, payload, persona_block)
            t2 = _generate_description(llm, product, payload, persona_block)
            t3 = _generate_bullets(llm, product, payload, persona_block)
            title, description, bullets = await asyncio.gather(t1, t2, t3)
            seo = await _optimize_seo(llm, title, description, payload, persona_block)
    except Exception as e:
        # 捕获所有 AI 调用异常，返回统一的中文错误提示
        # 不暴露具体的 API 错误信息，因为终端用户看不懂
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 生成服务暂不可用，请稍后重试",
        )

    # ════════════════════════════════════════════════════════════
    # 第 4.5 步：合规后置校验（CAP-05）
    # ════════════════════════════════════════════════════════════
    # 回写/发布前扫描：用户品牌禁词 + 平台极限词库；命中任一 → blocked=True，
    # 返回 violations 与修正建议 suggestions，由前端拦截保存并引导一键替换。
    violations: list[str] = []
    texts_to_check = {
        "title": title,
        "description": description,
        "bullet_points": "\n".join(bullets),
        "seo_title": seo.get("seo_title", ""),
        "seo_description": seo.get("seo_description", ""),
    }
    word_list = merge_banned_words(brand_banned_words)
    for v in texts_to_check.values():
        if v:
            for w in check_text(v, word_list):
                if w not in violations:
                    violations.append(w)
    blocked = bool(violations)
    suggestions = suggest_replacements(violations) if blocked else []

    # ════════════════════════════════════════════════════════════
    # 第 5 步：生成商品主图（可选，后台异步执行）
    # ════════════════════════════════════════════════════════════
    # 图片生成较慢（10s+），后台异步执行，不阻塞内容返回。
    image_url = ""
    image_task_id = ""
    if payload.generate_image:
        # settings 已在本模块顶部导入，禁止在此再 import（会把 settings 变成函数局部变量，
        # 未走该分支时函数末尾读 settings 会 UnboundLocalError）
        aliyun_key = provider_config.get("aliyun", "api_key", settings.ALIYUN_DASHSCOPE_API_KEY or "")
        replicate_key = provider_config.get("replicate", "api_key", settings.REPLICATE_API_KEY or "")
        if not aliyun_key and not replicate_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="图片生成功能暂未配置",
            )

        prompt = payload.image_prompt or (
            f"Professional e-commerce product photo of {product.title}, "
            f"white background, studio lighting, 8K, photorealistic"
        )
        # 图片路径不做合规拦截，但把品牌禁词从描述里简单移除，再附品牌视觉风格
        prompt = strip_banned_words(prompt, brand_banned_words)
        if image_style_suffix:
            prompt = f"{prompt}, {image_style_suffix}"
        if brand_name_identity:
            prompt = f"{prompt}, {brand_name_identity} brand identity"

        try:
            from app.routers.images import schedule_image_task
            image_task_id = await schedule_image_task(db, current_user.id, prompt, 1)
        except Exception as exc:
            # 主文案已生成成功，附图失败不阻塞主结果：记日志并留空 task_id，前端不再轮询
            logger.warning("Listing 附图调度失败: %s", exc)

    # ════════════════════════════════════════════════════════════
    # 第 5.5 步：持久化 ListingDraft + 版本化合规报告
    # ════════════════════════════════════════════════════════════
    draft = await persist_generated_listing(
        db,
        user=current_user,
        product=product,
        platform=payload.platform,
        language=payload.language,
        tone=payload.tone,
        title=title,
        description=description,
        bullet_points=bullets,
        seo_title=seo.get("seo_title", ""),
        seo_description=seo.get("seo_description", ""),
        violations=violations,
        blocked=blocked,
        ai_model_used=provider_config.get("deepseek", "model", settings.DEEPSEEK_MODEL),
        image_task_id=image_task_id,
    )

    # ════════════════════════════════════════════════════════════
    # 第 6 步：扣减积分
    # ════════════════════════════════════════════════════════════
    # deduct_credits 用了行级锁（select_for_update），防并发扣超
    # 如果只剩 1 分，但两个请求同时来，锁确保只有一个能成功
    await current_user.deduct_credits(db, 1)

    # ════════════════════════════════════════════════════════════
    # 第 7 步：返回结果
    # ════════════════════════════════════════════════════════════
    # FastAPI 自动把 GenerateResponse 序列化为 JSON
    # response_model=GenerateResponse 也起到了文档作用（自动生成 API 文档）
    return GenerateResponse(
        title=title,
        description=description,
        bullet_points=bullets,
        seo_title=seo.get("seo_title", ""),
        seo_description=seo.get("seo_description", ""),
        image_url=image_url,
        image_task_id=image_task_id,
        model_used=provider_config.get("deepseek", "model", settings.DEEPSEEK_MODEL),
        listing_id=str(draft.id),
        listing_status=draft.status,
        compliance_status=draft.compliance_status,
        blocked=blocked,
        violations=violations,
        suggestions=suggestions,
    )


@router.post("/a-plus")
async def generate_a_plus(
    payload: GenerateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    _ratelimit=Depends(RateLimit("ai_generate")),
    db: AsyncSession = Depends(get_db),
):
    """生成 A+ 内容（带格式的图文商品详情）

    对标 Amazon A+ Content / Shopify 增强描述。
    生成 HTML 格式的丰富商品描述，含卖点图、对比表、品牌故事等。
    """
    from uuid import UUID
    if current_user.credits < 1:
        raise HTTPException(status_code=402, detail="积分不足")

    try:
        product_id = UUID(payload.product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的商品 ID")

    # 归属过滤：只允许基于自己的商品生成 A+，他人商品等同不存在
    result = await db.execute(
        select(Product).where(
            Product.id == product_id,
            Product.user_id == current_user.id,
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    if not product.title:
        raise HTTPException(status_code=400, detail="商品缺少标题")

    # 品牌档案注入（CAP-04）：A+ 也是文案生成出口，persona 放到 system prompt 顶部
    persona = await fetch_persona(db, current_user.id)
    kit = build_persona_kit(persona) if persona else None
    persona_block = format_persona_block(kit) if kit else ""
    brand_banned_words = (kit.get("banned_words") or []) if kit else []

    llm = DeepSeekService()
    html = await llm.generate(
        system_prompt=f"You are an expert A+ Content designer for {payload.platform}. Output only valid HTML.",
        user_prompt=(
            f"Create an A+ Content product description for {payload.platform} in {payload.language.upper()}.\n"
            f"Product: {product.title}\n"
            f"Price: {product.price}\n\n"
            f"Structure:\n"
            f"1. Hero section with product name and tagline\n"
            f"2. Key features grid (4 items, each with emoji icon)\n"
            f"3. Specification comparison table\n"
            f"4. Usage scenarios (3 scenarios)\n"
            f"5. Call to action\n\n"
            f"Use clean HTML: <h2>, <p>, <ul>, <li>, <table>, <tr>, <td>. "
            f"Use emoji for visual appeal. No CSS, no style attributes."
        ),
        max_tokens=2000,
        persona_block=persona_block,
    )

    # 清洗：只保留 HTML body 内容
    import re
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL)
    if body_match:
        html = body_match.group(1)

    # 合规后置校验（CAP-05）：A+ 输出文本同样拦截平台/品牌违禁词
    word_list = merge_banned_words(brand_banned_words)
    violations = [w for w in check_text(html, word_list)]
    blocked = bool(violations)
    suggestions = suggest_replacements(violations) if blocked else []

    await current_user.deduct_credits(db, 1)

    return {
        "html": html,
        "product_title": product.title,
        "platform": payload.platform,
        "blocked": blocked,
        "violations": violations,
        "suggestions": suggestions,
    }

# ── 辅助函数（私有，不暴露为 API 路由） ─────────────────────
# 这些函数以下划线开头，是 Python 约定：表示"内部使用，不要外部导入"
# 它们拆分了生成流程，使主函数更清晰

async def _generate_title(
    llm: DeepSeekService,
    product: Product,
    payload: GenerateRequest,
    persona_block: str = "",
) -> str:
    """调用 AI 生成商品标题

    把所有上下文拼成一个 prompt，传给 DeepSeek。
    品牌档案（persona_block）放到 system prompt 顶部统一注入（CAP-04）。
    """
    lang_instruction = f"Write the title in {payload.language.upper()}." if payload.language != "zh" else "用中文写标题。"
    prompt = (
        f"Generate an optimized {payload.platform} product title (max 200 chars, {payload.tone} tone)."
        f"{lang_instruction}\n"
        f"Product: {product.title}\n"
        f"Price: {product.price}\n"
        f"Shop: {product.shop_name or ''}"
    )
    # 重试最多3次，应对 DeepSeek API 限流导致的空响应
    for attempt in range(3):
        result = await llm.generate(
            system_prompt=f"You are a professional {payload.platform} listing copywriter.",
            user_prompt=prompt,
            max_tokens=300,
            persona_block=persona_block,
        )
        if result and result.strip():
            return result
        await asyncio.sleep(1)
    return ""


async def _generate_description(
    llm: DeepSeekService,
    product: Product,
    payload: GenerateRequest,
    persona_block: str = "",
) -> str:
    """调用 AI 生成商品描述"""
    return await llm.generate_product_description(
        product_title=product.title,
        platform=payload.platform,
        tone=payload.tone,
        target_language=payload.language if payload.language != "en" else None,
        persona_block=persona_block,
    )


async def _generate_bullets(
    llm: DeepSeekService,
    product: Product,
    payload: GenerateRequest,
    persona_block: str = "",
) -> list[str]:
    """调用 AI 生成卖点列表（Bullet Points）"""
    features = f"价格: {product.price}" if product.price else ""
    return await llm.generate_bullet_points(
        product_title=product.title,
        features=features,
        platform=payload.platform,
        persona_block=persona_block,
    )


async def _optimize_seo(
    llm: DeepSeekService,
    title: str,
    description: str,
    payload: GenerateRequest,
    persona_block: str = "",
) -> dict:
    """调用 AI 生成 SEO 标题和描述"""
    return await llm.optimize_seo(
        title=title,
        description=description,
        platform=payload.platform,
        persona_block=persona_block,
    )
