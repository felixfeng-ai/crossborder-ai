"""SEO 摘要生成与降级行为测试。"""

import json

import pytest

from app.services.ai.deepseek import DeepSeekService


MARKDOWN_HTML_DESCRIPTION = """## 商品标题
**304 不锈钢真空保温杯 500ml**

## 商品详情描述
```html
<h2>通勤和办公都能用</h2>
<p>这只 <strong>500ml 保温杯</strong> 适合日常携带，保温保冷。</p>
<ul>
  <li>304 不锈钢内胆</li>
  <li>密封杯盖，放入包中更安心</li>
</ul>
```
"""


@pytest.mark.asyncio
async def test_seo_fallback_uses_short_plain_text_summary(monkeypatch):
    """AI 返回非 JSON 时，SEO 描述不得退化为整篇商品详情。"""

    async def fake_generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        return "这不是 JSON"

    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)

    result = await DeepSeekService().optimize_seo(
        title="304 Stainless Steel Bottle",
        description=MARKDOWN_HTML_DESCRIPTION,
        platform="shopify",
    )

    description = result["seo_description"]
    assert description
    assert description != MARKDOWN_HTML_DESCRIPTION
    assert len(description) <= 160
    assert "##" not in description
    assert "```" not in description
    assert "<h2>" not in description
    assert "<strong>" not in description


@pytest.mark.asyncio
async def test_seo_json_output_is_normalized_to_plain_text(monkeypatch):
    """即使 AI 返回 Markdown/HTML 或超长内容，也必须规范化为短摘要。"""
    long_description = (
        "## 不适合直接展示的标题\n"
        "<p><strong>Daily hydration</strong> for commuters and office workers.</p>"
        + " 这是一段会被截断的补充说明。" * 30
    )

    async def fake_generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        return json.dumps(
            {
                "seo_title": "Portable Insulated Bottle",
                "seo_description": long_description,
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)

    result = await DeepSeekService().optimize_seo(
        title="Portable Insulated Bottle",
        description=MARKDOWN_HTML_DESCRIPTION,
        platform="shopify",
    )

    description = result["seo_description"]
    assert len(description) <= 160
    assert "##" not in description
    assert "<p>" not in description
    assert "<strong>" not in description
    assert "Daily hydration" in description


@pytest.mark.asyncio
async def test_description_prompt_returns_body_only(monkeypatch):
    """商品描述不能再次携带标题、简短描述或代码围栏等外层元数据。"""
    captured: dict[str, str] = {}

    async def fake_generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        captured["system"] = system_prompt
        captured["user"] = user_prompt
        return "<p>Body only</p>"

    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)

    await DeepSeekService().generate_product_description(
        product_title="Insulated Bottle",
        product_features="500ml, stainless steel",
        platform="shopify",
    )

    prompt = f"{captured['system']}\n{captured['user']}".lower()
    assert "body only" in prompt
    assert "do not repeat the product title" in prompt
    assert "do not wrap the result in markdown fences" in prompt


@pytest.mark.asyncio
async def test_bullet_points_parser_keeps_only_requested_count(monkeypatch):
    """卖点生成继续兼容列表符号、数字和普通行，并限制最终数量。"""

    async def fake_generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        return "- Durable stainless steel body\n2. Leak-proof lid for travel\nA long plain benefit line"

    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)

    bullets = await DeepSeekService().generate_bullet_points(
        product_title="Insulated Bottle",
        features="500ml stainless steel",
        count=2,
    )

    assert bullets == [
        "Durable stainless steel body",
        "Leak-proof lid for travel",
    ]
