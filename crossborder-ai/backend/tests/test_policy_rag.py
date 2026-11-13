"""跨境平台政策知识库 P0 测试。"""

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.policy_knowledge import PolicyChunk, PolicySource
from app.models.user import User
from app.services.ai.agent_orchestrator import AgentOrchestrator
from app.services.policy_knowledge import (
    chunk_policy_text,
    embed_policy_texts,
    ingest_policy_text,
    search_policy_knowledge,
)


POLICY_TEXT = """# Amazon Product Compliance

## Children's products

Children's products must include a small parts warning where required.
The warning must be visible and use the required wording.

## Claims

Do not claim that a product is approved by a regulator without evidence.
"""


async def _admin_headers(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "admin@veyaship.com",
            "username": "policy-admin",
            "password": "testpass123",
        },
    )
    assert response.status_code in (201, 409), response.text
    if response.status_code == 409:
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "admin@veyaship.com",
                "password": "testpass123",
            },
        )
    assert response.status_code in (200, 201), response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_chunk_policy_text_preserves_heading_paths():
    chunks = chunk_policy_text(POLICY_TEXT, max_chars=120)

    assert len(chunks) >= 2
    assert any(
        item["title_path"] == "Amazon Product Compliance > Children's products"
        for item in chunks
    )
    assert all(item["content"].strip() for item in chunks)
    assert all(len(item["content"]) <= 120 for item in chunks)


def test_chunk_policy_text_splits_oversized_sentences():
    chunks = chunk_policy_text(
        "# Rule\n\n" + ("A" * 95) + "。" + ("B" * 95),
        max_chars=40,
    )

    assert len(chunks) >= 5
    assert all(len(item["content"]) <= 40 for item in chunks)


class _FakeCollection:
    def __init__(self, name: str):
        self.name = name


class _FakeCollections:
    def __init__(self, names: list[str]):
        self.collections = [_FakeCollection(name) for name in names]


class _FakeSearchResult:
    def __init__(self, score: float, payload: dict):
        self.score = score
        self.payload = payload


class _FakeQdrant:
    def __init__(self, *, collection_exists: bool = False, search_results=None):
        self.collection_exists = collection_exists
        self.search_results = search_results or []
        self.created = False
        self.deleted = []
        self.upserted = []

    def get_collections(self):
        return _FakeCollections(
            ["platform_policies"] if self.collection_exists else []
        )

    def create_collection(self, **kwargs):
        self.created = True
        self.collection_exists = True

    def delete(self, **kwargs):
        self.deleted.append(kwargs)

    def upsert(self, **kwargs):
        self.upserted.append(kwargs)

    def search(self, **kwargs):
        return self.search_results


@pytest.mark.asyncio
async def test_policy_embedding_batches_and_parses_response(monkeypatch):
    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ]
            }

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers, json):
            captured.update(
                {
                    "url": url,
                    "headers": headers,
                    "json": json,
                }
            )
            return _Response()

    monkeypatch.setattr(
        "app.services.policy_knowledge.get_policy_embedding_config",
        lambda: ("test-key", "text-embedding-v4", "https://example.com/v1", 2),
    )
    monkeypatch.setattr(
        "app.services.policy_knowledge.httpx.AsyncClient",
        lambda **kwargs: _Client(),
    )

    vectors = await embed_policy_texts(["first", "second"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert captured["json"]["model"] == "text-embedding-v4"
    assert captured["json"]["dimensions"] == 2


@pytest.mark.asyncio
async def test_policy_ingestion_syncs_vectors_when_configured(
    db_session,
    monkeypatch,
):
    fake_qdrant = _FakeQdrant()

    async def fake_embed(texts):
        return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(
        "app.services.policy_knowledge.get_policy_embedding_config",
        lambda: ("key", "text-embedding-v4", "https://example.com", 3),
    )
    monkeypatch.setattr(
        "app.services.policy_knowledge.embed_policy_texts",
        fake_embed,
    )
    monkeypatch.setattr(
        "app.services.policy_knowledge._qdrant_client",
        lambda: fake_qdrant,
    )

    result = await ingest_policy_text(
        db_session,
        title="Amazon Toys Policy",
        platform="amazon",
        market="US",
        category="toys",
        document_type="listing_policy",
        source_url="https://sellercentral.amazon.com/toys-vector",
        version="2026.11",
        effective_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        content_text=POLICY_TEXT,
    )

    assert result["vector_status"] == "synced"
    assert fake_qdrant.created is True
    assert len(fake_qdrant.upserted) == 1
    assert len(fake_qdrant.upserted[0]["points"]) == result["chunk_count"]


@pytest.mark.asyncio
async def test_policy_vector_search_returns_citations(monkeypatch):
    payload = {
        "chunk_id": "chunk-vector",
        "source_id": "source-vector",
        "title": "Amazon Toys Policy",
        "source_url": "https://sellercentral.amazon.com/toys",
        "platform": "amazon",
        "market": "US",
        "category": "toys",
        "version": "2026.11",
        "effective_at": "2026-11-01T00:00:00+00:00",
        "title_path": "Amazon Toys Policy > Children's products",
        "content": "Children's products require a small parts warning.",
    }
    fake_qdrant = _FakeQdrant(
        collection_exists=True,
        search_results=[_FakeSearchResult(0.93, payload)],
    )

    async def fake_embed(texts):
        return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(
        "app.services.policy_knowledge.get_policy_embedding_config",
        lambda: ("key", "text-embedding-v4", "https://example.com", 3),
    )
    monkeypatch.setattr(
        "app.services.policy_knowledge.embed_policy_texts",
        fake_embed,
    )
    monkeypatch.setattr(
        "app.services.policy_knowledge._qdrant_client",
        lambda: fake_qdrant,
    )

    result = await search_policy_knowledge(
        None,
        query="small parts warning",
        platform="amazon",
        market="US",
        category="toys",
    )

    assert result["retrieval_mode"] == "vector"
    assert result["items"][0]["chunk_id"] == "chunk-vector"
    assert result["items"][0]["score"] == 0.93


@pytest.mark.asyncio
async def test_new_policy_version_supersedes_old_source(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.policy_knowledge.get_policy_embedding_config",
        lambda: None,
    )
    first = await ingest_policy_text(
        db_session,
        title="Amazon Toys Policy",
        platform="amazon",
        market="US",
        category="toys",
        document_type="listing_policy",
        source_url="https://sellercentral.amazon.com/toys-versioned",
        version="2026.10",
        effective_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        content_text=POLICY_TEXT,
    )
    second = await ingest_policy_text(
        db_session,
        title="Amazon Toys Policy",
        platform="amazon",
        market="US",
        category="toys",
        document_type="listing_policy",
        source_url="https://sellercentral.amazon.com/toys-versioned",
        version="2026.11",
        effective_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        content_text=POLICY_TEXT + "\n\nUpdated warning requirement.",
    )

    old = await db_session.get(PolicySource, uuid.UUID(first["source_id"]))
    current = await db_session.get(PolicySource, uuid.UUID(second["source_id"]))
    assert old.status == "superseded"
    assert current.status == "active"


@pytest.mark.asyncio
async def test_policy_ingestion_is_idempotent(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.policy_knowledge.get_policy_embedding_config",
        lambda: None,
    )

    first = await ingest_policy_text(
        db_session,
        title="Amazon Product Compliance",
        platform="amazon",
        market="US",
        category="toys",
        document_type="listing_policy",
        source_url="https://sellercentral.amazon.com/example",
        version="2026.11",
        effective_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        content_text=POLICY_TEXT,
    )
    second = await ingest_policy_text(
        db_session,
        title="Amazon Product Compliance",
        platform="amazon",
        market="US",
        category="toys",
        document_type="listing_policy",
        source_url="https://sellercentral.amazon.com/example",
        version="2026.11",
        effective_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        content_text=POLICY_TEXT,
    )

    assert first["changed"] is True
    assert second["changed"] is False
    source_count = (
        await db_session.execute(select(func.count()).select_from(PolicySource))
    ).scalar_one()
    chunk_count = (
        await db_session.execute(select(func.count()).select_from(PolicyChunk))
    ).scalar_one()
    assert source_count == 1
    assert chunk_count == first["chunk_count"]


@pytest.mark.asyncio
async def test_policy_search_filters_metadata_and_falls_back_to_text(
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.services.policy_knowledge.get_policy_embedding_config",
        lambda: None,
    )
    await ingest_policy_text(
        db_session,
        title="Amazon Toys Policy",
        platform="amazon",
        market="US",
        category="toys",
        document_type="listing_policy",
        source_url="https://sellercentral.amazon.com/toys",
        version="2026.11",
        effective_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        content_text=POLICY_TEXT,
    )
    await ingest_policy_text(
        db_session,
        title="TikTok Beauty Policy",
        platform="tiktok",
        market="US",
        category="beauty",
        document_type="listing_policy",
        source_url="https://seller-us.tiktok.com/university/beauty",
        version="2026.11",
        effective_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        content_text="# Beauty\n\nCosmetic claims require substantiation.",
    )

    result = await search_policy_knowledge(
        db_session,
        query="children small parts warning",
        platform="amazon",
        market="US",
        category="toys",
    )

    assert result["has_evidence"] is True
    assert result["retrieval_mode"] == "keywords"
    assert result["items"]
    assert all(item["platform"] == "amazon" for item in result["items"])
    assert result["items"][0]["source_url"].startswith("https://sellercentral")
    assert result["items"][0]["title_path"]

    missing = await search_policy_knowledge(
        db_session,
        query="cryptocurrency payment license",
        platform="amazon",
        market="US",
        category="toys",
    )
    assert missing["has_evidence"] is False
    assert missing["items"] == []


@pytest.mark.asyncio
async def test_agent_searches_policy_and_returns_citations(db_session, monkeypatch):
    user = User(
        email=f"policy-agent-{uuid.uuid4().hex[:8]}@test.com",
        username="policy-agent",
        password_hash="x",
        plan="professional",
        credits=30,
    )
    db_session.add(user)
    await db_session.flush()

    async def fake_search(*args, **kwargs):
        return {
            "has_evidence": True,
            "retrieval_mode": "keywords",
            "items": [
                {
                    "chunk_id": "chunk-1",
                    "source_id": "source-1",
                    "title": "Amazon Toys Policy",
                    "source_url": "https://sellercentral.amazon.com/toys",
                    "platform": "amazon",
                    "market": "US",
                    "category": "toys",
                    "version": "2026.11",
                    "effective_at": "2026-11-01T00:00:00+00:00",
                    "title_path": "Amazon Toys Policy > Children's products",
                    "content": "Children's products must include a small parts warning.",
                    "score": 0.91,
                }
            ],
        }

    monkeypatch.setattr(
        "app.services.policy_knowledge.search_policy_knowledge",
        fake_search,
    )
    orchestrator = AgentOrchestrator(user=user, db=db_session)
    result = await orchestrator._execute_step(
        "search_platform_policies",
        {
            "query": "small parts warning",
            "platform": "amazon",
            "market": "US",
            "category": "toys",
        },
    )

    assert result["status"] == "success"
    assert result["data"]["has_evidence"] is True
    assert result["data"]["items"][0]["source_url"].startswith(
        "https://sellercentral"
    )


@pytest.mark.asyncio
async def test_policy_api_allows_admin_ingest_and_user_search(
    client: AsyncClient,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.services.policy_knowledge.get_policy_embedding_config",
        lambda: None,
    )
    admin_headers = await _admin_headers(client)
    ingested = await client.post(
        "/api/v1/platform-policies/ingest",
        headers=admin_headers,
        json={
            "title": "Amazon Product Compliance",
            "platform": "amazon",
            "market": "US",
            "category": "toys",
            "document_type": "listing_policy",
            "source_url": "https://sellercentral.amazon.com/toys",
            "version": "2026.11",
            "effective_at": "2026-11-01T00:00:00Z",
            "content_text": POLICY_TEXT,
        },
    )
    assert ingested.status_code == 201, ingested.text
    assert ingested.json()["vector_status"] == "degraded"

    buyer = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"policy-buyer-{uuid.uuid4().hex[:8]}@test.com",
            "username": "policy-buyer",
            "password": "testpass123",
        },
    )
    buyer_headers = {
        "Authorization": f"Bearer {buyer.json()['access_token']}"
    }
    searched = await client.get(
        "/api/v1/platform-policies/search",
        headers=buyer_headers,
        params={
            "query": "small parts warning",
            "platform": "amazon",
            "market": "US",
            "category": "toys",
        },
    )
    assert searched.status_code == 200, searched.text
    assert searched.json()["has_evidence"] is True
    assert searched.json()["items"][0]["source_url"].startswith(
        "https://sellercentral"
    )

    forbidden = await client.post(
        "/api/v1/platform-policies/ingest",
        headers=buyer_headers,
        json={
            "title": "Unauthorized",
            "platform": "amazon",
            "market": "US",
            "document_type": "listing_policy",
            "source_url": "https://example.com/policy",
            "version": "1",
            "content_text": "This content must not be inserted by a buyer.",
        },
    )
    assert forbidden.status_code == 403
