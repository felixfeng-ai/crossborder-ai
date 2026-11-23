"""Listing 生成测试的 DeepSeek 模拟方法。"""


def mock_listing_ai(
    monkeypatch,
    canned: str,
    *,
    description: str | None = None,
    bullets: list[str] | None = None,
    seo_title: str | None = None,
    seo_description: str | None = None,
) -> None:
    """同时替换标题、描述、卖点和 SEO 生成，避免测试访问真实 API。"""

    from app.services.ai.deepseek import DeepSeekService

    async def fake_generate(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs,
    ) -> str:
        return canned

    async def fake_description(self, **kwargs) -> str:
        return description or canned

    async def fake_bullets(self, **kwargs) -> list[str]:
        return bullets or [canned]

    async def fake_seo(self, **kwargs) -> dict:
        return {
            "seo_title": seo_title or canned[:80],
            "seo_description": seo_description or canned[:160],
        }

    monkeypatch.setattr(DeepSeekService, "generate", fake_generate)
    monkeypatch.setattr(
        DeepSeekService,
        "generate_product_description",
        fake_description,
    )
    monkeypatch.setattr(
        DeepSeekService,
        "generate_bullet_points",
        fake_bullets,
    )
    monkeypatch.setattr(DeepSeekService, "optimize_seo", fake_seo)
