"""VeyaShip - 合规后置校验 + 回写前拦截（CAP-05）测试

覆盖行为契约：
1. 命中用户品牌禁词（如 best seller）→ blocked=True + violations 含该词
2. 命中平台极限词库（如 全网最低价）→ blocked=True + violations 含该词
3. 干净文案 → blocked=False（正常通过，不拦截）
4. AI 深度改写降级：AI 服务不可用时返回原文，不抛 500
"""

import uuid

import pytest
from httpx import AsyncClient

from app.services.ai import compliance
from app.services.ai.deepseek import DeepSeekService
from tests.ai_mock_helpers import mock_listing_ai


async def _create_product(client: AsyncClient, auth_headers: dict, idx: int = 1) -> str:
    """创建测试商品，返回 product_id"""
    resp = await client.post(
        "/api/v1/products/manual",
        json={
            "url": f"https://detail.1688.com/offer/cap05-{uuid.uuid4().hex}.html",
            "title": f"合规测试耳机 {idx}",
            "price": 29.9,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["product"]["id"]


async def _set_persona(client: AsyncClient, auth_headers: dict, banned_words: list[str]):
    """写品牌禁词（其余字段留空）"""
    resp = await client.put(
        "/api/v1/settings/persona",
        json={"brand_name": "测试品牌", "banned_words": banned_words},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text


def _mock_generate(monkeypatch, canned: str):
    """把 DeepSeekService.generate 替换为固定返回，避开真实 API 与重试等待"""
    mock_listing_ai(
        monkeypatch,
        canned,
        bullets=[canned, f"{canned} 2", f"{canned} 3", f"{canned} 4", f"{canned} 5"],
    )


async def _generate(
    client: AsyncClient, auth_headers: dict, product_id: str
) -> dict:
    resp = await client.post(
        "/api/v1/content/generate",
        json={"product_id": product_id, "platform": "amazon", "language": "en"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── 1. 命中用户品牌禁词 ─────────────────────────────────────

@pytest.mark.asyncio
async def test_user_banned_word_blocks(client: AsyncClient, auth_headers: dict, monkeypatch):
    """用户禁词 "best seller" → 生成内容 blocked=True 且 violations 含该词"""
    product_id = await _create_product(client, auth_headers)
    await _set_persona(client, auth_headers, banned_words=["best seller"])
    # AI 在文案里产出了禁词
    _mock_generate(monkeypatch, "The best seller wireless earbuds with superb sound.")

    data = await _generate(client, auth_headers, product_id)
    assert data["blocked"] is True
    assert any("best seller" in v for v in data["violations"])
    # 回写/发布前置拦截：返回了建议（即便无预设替词也提示手动改写）
    assert isinstance(data["suggestions"], list)


# ── 2. 命中平台极限词库 ─────────────────────────────────────

@pytest.mark.asyncio
async def test_platform_extreme_word_blocks(client: AsyncClient, auth_headers: dict, monkeypatch):
    """平台极限词（全网最低价）→ 即便用户未配置禁词也 blocked=True"""
    product_id = await _create_product(client, auth_headers, idx=2)
    await _set_persona(client, auth_headers, banned_words=[])
    _mock_generate(monkeypatch, "无线耳机，全网最低价，先到先得。")

    data = await _generate(client, auth_headers, product_id)
    assert data["blocked"] is True
    assert any("全网最低价" in v for v in data["violations"])


# ── 3. 干净文案不拦截 ───────────────────────────────────────

@pytest.mark.asyncio
async def test_clean_text_not_blocked(client: AsyncClient, auth_headers: dict, monkeypatch):
    """干净文案 → blocked=False，正常通过"""
    product_id = await _create_product(client, auth_headers, idx=3)
    await _set_persona(client, auth_headers, banned_words=[])
    _mock_generate(monkeypatch, "Premium wireless earbuds with long battery life.")

    data = await _generate(client, auth_headers, product_id)
    assert data["blocked"] is False
    assert data["violations"] == []


# ── 4. AI 深度改写降级不抛 500 ───────────────────────────────

@pytest.mark.asyncio
async def test_ai_review_fix_degrades_gracefully(monkeypatch):
    """AI 服务不可用 → ai_review_fix 返回 (原文, False, [], 提示)，绝不抛 500"""
    original = "这是全网最低价的好耳机。"

    async def raise_generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        raise RuntimeError("DeepSeek API down")

    monkeypatch.setattr(DeepSeekService, "generate", raise_generate)

    # 不应抛异常
    fixed, ok, violations, msg = await compliance.ai_review_fix(original, banned_words=["最低价"])
    assert fixed == original
    assert ok is False
    assert violations == []
    assert msg == "合规检查暂不可用"


# ── 附加：词库/正则单元校验（锁定行为） ─────────────────────

@pytest.mark.asyncio
async def test_check_text_detects_platform_word():
    """check_text 对平台词库/用户词大小写不敏感、支持中文"""
    hits = compliance.check_text(
        "The best product 全网最低价 today",
        compliance.merge_banned_words(["BEST"]),
    )
    assert "best" in hits          # 用户词小写命中大写文本
    assert "全网最低价" in hits      # 平台词库命中


@pytest.mark.asyncio
async def test_check_text_ascii_boundary_no_false_positive():
    """纯 ASCII 词加词边界：bestseller 不应误命中 best"""
    hits = compliance.check_text("a bestseller ebook", ["best"])
    assert hits == []
