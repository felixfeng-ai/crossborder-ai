"""VeyaShip - DeepSeek LLM 服务封装

【全栈学习者必读】
这个文件展示了后端如何调用外部的 AI API（LLM = Large Language Model）。
这是理解"AI SaaS 平台"技术架构的关键。

核心模式：
1. 后端作为 AI 的"中间人"——前端不直接调 DeepSeek API
2. 封装所有 prompt 模板——业务逻辑在后端控制
3. 重试机制——网络调用可能失败，自动重试

为什么不让前端直接调 DeepSeek？
- 安全：API Key 放前端 = 公开秘密，任何人可以盗用
- 控制：后端可以限流、计费、审计
- 灵活：换模型（DeepSeek → GPT → Claude）只需改这里
- 业务集成：需注入品牌调性、积分扣减等逻辑

API 调用流程：
  前端 → POST /api/v1/content/generate → 本服务 → httpx → DeepSeek API
  前端 ← 结构化 JSON ← 本服务 ← DeepSeek Response ←
"""

import html
import json
import re
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.services import provider_config

# DeepSeek API 基础地址
# DeepSeek 是国内大模型，API 兼容 OpenAI 格式
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
SEO_DESCRIPTION_MAX_LENGTH = 160


class DeepSeekService:
    """DeepSeek LLM 服务类

    这个类封装了所有与 DeepSeek API 的交互逻辑。
    每次调用生成一个新的 httpx 客户端，用完自动关闭。

    关键设计决策：
    - 异步：所有方法都是 async，不阻塞服务器线程
    - 自动重试：网络不稳定时自动重试最多 3 次
    - 温度参数：控制 AI 的"创造性"，低 = 精确，高 = 有创意
    """

    def __init__(self):
        """初始化服务

        配置从 settings 读取（来自 .env 文件或环境变量）
        所有配置集中管理，改配置不修改代码
        """
        self.api_key = settings.DEEPSEEK_API_KEY
        self.model = settings.DEEPSEEK_MODEL       # 如 "deepseek-chat"
        self.temperature = settings.DEEPSEEK_TEMPERATURE  # 如 0.7
        self.base_url = DEEPSEEK_BASE_URL

    def _build_headers(self, api_key: str | None = None) -> Dict[str, str]:
        """构建 HTTP 请求头

        Bearer Token 是 REST API 通用的认证方式：
        Authorization: Bearer <api-key>
        """
        return {
            "Authorization": f"Bearer {api_key or self.api_key}",
            "Content-Type": "application/json",
        }

    # ── @retry 装饰器 ─────────────────────────────────────────
    # tenacity 库的自动重试机制：
    # - stop_after_attempt(3)：最多重试 3 次
    # - wait_exponential(multiplier=1, min=2, max=10)：
    #   第 1 次失败等 2 秒，第 2 次等 4 秒，第 3 次等 8 秒
    #   指数退避（Exponential Backoff）避免加重服务器负担
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2000,
        temperature: Optional[float] = None,
        persona_block: Optional[str] = None,
    ) -> str:
        """【核心方法】调用 DeepSeek Chat API 生成文本

        Chat API 的消息格式：
        - system：系统指令，定义 AI 的角色和行为（你是一个 XX 专家...）
        - user：用户请求，具体要 AI 做的事情

        为什么拆成 system 和 user？
        - system prompt 是"你是谁，应该怎么回答"
        - user prompt 是"具体做什么"
        - 这种分离让 system prompt 可以被复用

        Args:
            system_prompt: AI 角色设定（System Message）
            user_prompt: 具体任务描述（User Message）
            max_tokens: 最大生成长度（字符数 ≈ token 数 × 0.75）
            temperature: 创造性参数（0~2，默认 0.7）
                - 0.0：每次都输出一样，适合精确任务
                - 0.7：适度创造，适合文案生成
                - 1.5：非常随机，适合创意写作

        Returns:
            AI 生成的文本内容

        Raises:
            httpx.HTTPError: API 调用失败（经过十重试后仍失败）
        """
        # 统一品牌档案注入（CAP-04）：有 persona_block 则放到 system prompt 顶部
        if persona_block:
            system_prompt = f"{persona_block}\n\n{system_prompt}"

        api_key = provider_config.get("deepseek", "api_key", self.api_key or "")
        model = provider_config.get("deepseek", "model", self.model)

        # httpx.AsyncClient 是异步 HTTP 客户端
        # 相比 requests 库，它不阻塞事件循环
        # with 语句确保请求完成后自动关闭连接
        async with httpx.AsyncClient(timeout=60.0) as client:
            # POST 请求到 DeepSeek 的 chat completions 接口
            # 这个接口兼容 OpenAI 的 API 格式
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._build_headers(api_key),
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature or self.temperature,
                },
            )

            # raise_for_status() 在 HTTP 状态码 >= 400 时抛出异常
            # 触发了 retry 装饰器的重试逻辑
            response.raise_for_status()

            # 解析响应 JSON
            # OpenAI 兼容格式：
            # {
            #   "choices": [
            #     {"message": {"content": "生成的文本..."}}
            #   ]
            # }
            data = response.json()
            return data["choices"][0]["message"]["content"]

    # ── 业务方法（以下是针对电商场景的 prompt 模板） ──────────

    async def chat_with_tools(
        self,
        messages: list,
        tools: Optional[list] = None,
        max_tokens: int = 2000,
    ) -> dict:
        """调用 DeepSeek Chat API，支持 Function Calling

        【全栈学习者必读】
        Function Calling 是 Agent 的核心能力：
        模型不直接执行操作，而是返回"我要调用哪个工具、传什么参数"，
        由代码执行工具，再把结果传回给模型继续推理。

        这就是 ReAct 模式的循环：
        思考 → 调用工具 → 观察结果 → 再思考 → ...

        Args:
            messages: 对话消息列表
                [{"role": "system", "content": "..."},
                 {"role": "user", "content": "..."},
                 {"role": "tool", "content": "工具返回的结果", "tool_call_id": "..."}]
            tools: 工具定义列表（OpenAI 格式）
            max_tokens: 最大生成长度

        Returns:
            dict: 包含 content（文本回复）和 tool_calls（要调用的工具）
        """
        api_key = provider_config.get("deepseek", "api_key", self.api_key or "")
        model = provider_config.get("deepseek", "model", self.model)
        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if tools:
            body["tools"] = tools

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._build_headers(api_key),
                json=body,
            )
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
            return {
                "content": message.get("content", ""),
                "tool_calls": message.get("tool_calls", []),
            }

    async def generate_product_description(
        self,
        product_title: str,
        product_features: Optional[str] = None,
        tone: str = "professional",
        platform: str = "amazon",
        target_language: Optional[str] = None,
        max_length: Optional[int] = None,
        persona_block: Optional[str] = None,
    ) -> str:
        """生成优化的商品描述

        这个方法的本质是"用固定的 prompt 模板 + 动态参数"调 generate()。
        所有业务方法都遵循这个模式。

        Args:
            product_title: 商品名
            product_features: 商品特性
            tone: 语气风格（professional / casual / luxury）
            platform: 目标平台（影响 SEO 关键词和格式）
            target_language: 目标语言（如 ja = 日语）
            max_length: 最大字符数

        Returns:
            AI 生成的商品描述
        """
        # system prompt 设定 AI 的角色
        system_prompt = (
            f"You are an expert cross-border e-commerce copywriter specializing in {platform} listings. "
            f"Write compelling, conversion-optimized product content in a {tone} tone. "
            f"Include relevant SEO keywords naturally. "
            f"Return the product description body only, formatted for {platform}. "
            f"Do not repeat the product title, short description, SEO title, SEO description, "
            f"section labels, or metadata. Do not wrap the result in Markdown fences. "
            f"Do not return a complete HTML document; omit html, head, body, style, and script. "
            f"Use semantic HTML such as <p>, <h2>, <ul>, <li>, and <strong> when the platform supports it."
        )
        if persona_block:
            system_prompt = f"{persona_block}\n\n{system_prompt}"

        # user prompt 说明具体任务
        user_prompt = (
            f"Product: {product_title}\n"
            f"Write only the detailed description body. Start directly with the first product detail.\n"
        )
        if product_features:
            user_prompt += f"Features: {product_features}\n"
        if target_language:
            user_prompt += f"\nWrite the description in {target_language}."
        if max_length:
            user_prompt += f"\nKeep the description under {max_length} characters."

        return await self.generate(system_prompt, user_prompt)

    async def generate_bullet_points(
        self,
        product_title: str,
        features: str,
        count: int = 5,
        platform: str = "amazon",
        persona_block: Optional[str] = None,
    ) -> List[str]:
        """生成卖点列表（Bullet Points）

        这是 Amazon Listing 最重要的部分。
        AI 返回一段文本，然后按行解析成列表。

        Args:
            product_title: 商品名
            features: 商品特性描述
            count: 需要的卖点数量
            platform: 目标平台

        Returns:
            卖点字符串列表
        """
        system_prompt = (
            f"You are an expert Amazon/eBay listing optimizer. "
            f"Generate {count} compelling bullet points that highlight key benefits and features. "
            f"Each bullet should start with a capitalized benefit word followed by a colon."
        )
        if persona_block:
            system_prompt = f"{persona_block}\n\n{system_prompt}"

        user_prompt = (
            f"Product: {product_title}\n"
            f"Features/Specs: {features}\n"
            f"Generate exactly {count} bullet points for {platform}."
        )

        result = await self.generate(system_prompt, user_prompt, max_tokens=1000)

        # ── 解析返回文本 ──────────────────────────────────────
        # AI 返回的是纯文本，我们需要把它转成列表
        # 支持多种格式：- 开头、* 开头、数字开头
        bullets = []
        for line in result.strip().split("\n"):
            line = line.strip()
            if line and (line.startswith("-") or line.startswith("*") or line[0].isdigit()):
                bullets.append(line.lstrip("-*0123456789. ").strip())
            elif line and len(line) > 10:
                bullets.append(line)

        return bullets[:count]

    async def translate_content(
        self,
        text: str,
        target_language: str,
        source_language: str = "en",
    ) -> str:
        """翻译商品内容到目标语言"""
        system_prompt = (
            f"You are a professional e-commerce translator. "
            f"Translate the following product content from {source_language} to {target_language}. "
            f"Maintain SEO keywords, tone, and marketing appeal. "
            f"Adapt cultural references appropriately for the target market."
        )

        user_prompt = (
            f"Translate the following e-commerce content to {target_language}:\n\n{text}"
        )

        return await self.generate(system_prompt, user_prompt)

    async def optimize_seo(
        self,
        title: str,
        description: str,
        platform: str = "amazon",
        persona_block: Optional[str] = None,
    ) -> Dict[str, str]:
        """优化商品内容的 SEO

        这个方法的特殊之处：要求 AI 返回 JSON 格式的数据。
        让 AI 输出结构化数据是高级用法，需要明确的格式指令。

        Args:
            title: 原标题
            description: 原描述
            platform: 目标平台

        Returns:
            包含 seo_title 和 seo_description 的字典
        """
        # 关键提示技巧：明确告诉 AI 只输出 JSON，不加额外文字
        system_prompt = (
            f"You are an SEO specialist for {platform}. "
            f"Output ONLY a JSON object with 'seo_title' and 'seo_description'. "
            f"No markdown, no bold markers, no extra text. "
            f"Front-load important keywords. Keep the title under 200 characters. "
            f"Write seo_description as one plain-text paragraph of 140-160 characters. "
            f"Do not repeat the full product description and do not include HTML."
        )
        if persona_block:
            system_prompt = f"{persona_block}\n\n{system_prompt}"

        user_prompt = (
            f"Original Title: {title}\n"
            f"Original Description: {description}\n\n"
            f"Return JSON: {{\"seo_title\": \"...\", \"seo_description\": \"...\"}}. "
            f"seo_description must be a concise plain-text summary."
        )

        result = await self.generate(system_prompt, user_prompt, max_tokens=500)

        # ── 解析 JSON ─────────────────────────────────────────
        # AI 的 JSON 输出有时不标准，用正则提取大括号内容
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                seo_title = data.get("seo_title", "")
                seo_description = data.get("seo_description", "")
                if seo_title and seo_title != "**" and len(seo_title) > 5:
                    return {
                        "seo_title": seo_title,
                        "seo_description": _normalize_seo_description(
                            seo_description, description
                        ),
                    }
            except json.JSONDecodeError:
                pass

        # 降级时从正文提取短摘要，不能把整篇 Markdown/HTML 当作 SEO 描述。
        return {
            "seo_title": title,
            "seo_description": _normalize_seo_description("", description),
        }


def _normalize_seo_description(value: str, description: str) -> str:
    """把任意模型输出规范化为可用于搜索结果展示的纯文本摘要。"""
    plain = _to_plain_text(value or "")
    if not plain:
        plain = _to_plain_text(description or "")
    return _truncate_text(plain, SEO_DESCRIPTION_MAX_LENGTH)


def _to_plain_text(value: str) -> str:
    """移除代码围栏、HTML 和常见 Markdown 标记，保留可读正文。"""
    text = re.sub(r"```(?:html)?\s*(.*?)```", r"\1", value, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*(?:[-*+]|\d+\.)\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"(?:\*\*|__|~~|`)", "", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _truncate_text(value: str, max_length: int) -> str:
    """优先在句末截断，避免 SEO 摘要出现半句话。"""
    if len(value) <= max_length:
        return value

    candidate = value[: max_length - 1]
    sentence_end = max(
        candidate.rfind(mark) for mark in ("。", "！", "？", ".", "!", "?", "；", ";")
    )
    if sentence_end >= int(max_length * 0.6):
        return candidate[: sentence_end + 1]
    return candidate.rstrip() + "…"
