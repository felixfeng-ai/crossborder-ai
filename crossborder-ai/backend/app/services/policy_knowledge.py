"""跨境平台政策切分、向量入库与可降级检索。"""

import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.models.policy_knowledge import (
    PolicyChunk,
    PolicySource,
    PolicySyncRun,
)
from app.services import provider_config


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*|[\u4e00-\u9fff]{2,}")
QUERY_STOPWORDS = {
    "amazon",
    "tiktok",
    "shopify",
    "shop",
    "us",
    "product",
    "products",
    "listing",
    "listings",
    "policy",
    "policies",
    "requirement",
    "requirements",
    "platform",
    "market",
}


def normalize_policy_text(value: str) -> str:
    """统一换行并去除 BOM，保证同一文档校验和稳定。"""
    return (value or "").replace("\ufeff", "").replace("\r\n", "\n").strip()


def _split_long_text(value: str, max_chars: int) -> list[str]:
    """先按段落和句子切分，最后才做硬截断。"""
    paragraphs = [
        item.strip()
        for item in re.split(r"\n\s*\n", value)
        if item.strip()
    ]
    pieces: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            pieces.append(paragraph)
            continue
        sentences = [
            item.strip()
            for item in re.split(r"(?<=[。！？.!?])\s+", paragraph)
            if item.strip()
        ]
        for sentence in sentences or [paragraph]:
            if len(sentence) <= max_chars:
                pieces.append(sentence)
            else:
                pieces.extend(
                    sentence[index : index + max_chars]
                    for index in range(0, len(sentence), max_chars)
                )
    return pieces


def _merge_pieces(pieces: list[str], max_chars: int) -> list[str]:
    """把短句合并为不超过上限的检索切分。"""
    merged: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}\n\n{piece}".strip() if current else piece
        if current and len(candidate) > max_chars:
            merged.append(current)
            current = piece
        else:
            current = candidate
    if current:
        merged.append(current)
    return merged


def chunk_policy_text(
    content_text: str,
    *,
    max_chars: int = 1200,
) -> list[dict[str, Any]]:
    """按 Markdown 标题层级切分，并保留可展示的标题路径。"""
    normalized = normalize_policy_text(content_text)
    if not normalized:
        return []

    sections: list[tuple[str, list[str]]] = []
    heading_stack: list[tuple[int, str]] = []
    current_path = "Preamble"
    current_lines: list[str] = []

    def flush_section() -> None:
        body = "\n".join(current_lines).strip()
        if body:
            sections.append((current_path, _split_long_text(body, max_chars)))

    for line in normalized.splitlines():
        match = HEADING_PATTERN.match(line)
        if match:
            flush_section()
            current_lines = []
            level = len(match.group(1))
            title = match.group(2).strip()
            heading_stack = [
                item for item in heading_stack if item[0] < level
            ]
            heading_stack.append((level, title))
            current_path = " > ".join(item[1] for item in heading_stack)
            continue
        current_lines.append(line)
    flush_section()

    chunks: list[dict[str, Any]] = []
    for title_path, pieces in sections:
        for content in _merge_pieces(pieces, max_chars):
            chunk_hash = hashlib.sha256(
                f"{title_path}\n{content}".encode("utf-8")
            ).hexdigest()
            chunks.append(
                {
                    "title_path": title_path,
                    "content": content,
                    "chunk_hash": chunk_hash,
                    "estimated_tokens": max(1, len(content) // 4),
                }
            )
    return chunks


def get_policy_embedding_config() -> tuple[str, str, str, int] | None:
    """读取政策 Embedding 配置；缺少 Key 时静默降级到关键词检索。"""
    if not settings.POLICY_EMBEDDING_ENABLED:
        return None
    api_key = (
        provider_config.get("aliyun", "api_key")
        or settings.ALIYUN_DASHSCOPE_API_KEY
        or ""
    )
    if not api_key:
        return None
    return (
        api_key,
        (
            provider_config.get("aliyun", "embedding_model")
            or settings.POLICY_EMBEDDING_MODEL
        ),
        settings.POLICY_EMBEDDING_BASE_URL.rstrip("/"),
        settings.POLICY_EMBEDDING_DIMENSION,
    )


async def embed_policy_texts(texts: list[str]) -> list[list[float]]:
    """调用 DashScope OpenAI 兼容 Embedding 接口。"""
    config = get_policy_embedding_config()
    if config is None:
        raise ValueError("政策 Embedding 未配置")
    api_key, model, base_url, dimension = config
    vectors: list[list[float]] = []
    async with httpx.AsyncClient(timeout=30) as client:
        for index in range(0, len(texts), 10):
            batch = texts[index : index + 10]
            response = await client.post(
                f"{base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "input": batch,
                    "dimensions": dimension,
                },
            )
            response.raise_for_status()
            data = sorted(
                response.json().get("data") or [],
                key=lambda item: int(item.get("index") or 0),
            )
            vectors.extend(
                [float(value) for value in item.get("embedding") or []]
                for item in data
            )
    if len(vectors) != len(texts):
        raise ValueError("Embedding 返回数量与输入不一致")
    return vectors


def _qdrant_client() -> QdrantClient:
    return QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)


def _ensure_policy_collection(client: QdrantClient) -> None:
    collections = client.get_collections().collections
    if any(
        item.name == settings.POLICY_QDRANT_COLLECTION
        for item in collections
    ):
        return
    client.create_collection(
        collection_name=settings.POLICY_QDRANT_COLLECTION,
        vectors_config=qdrant_models.VectorParams(
            size=settings.POLICY_EMBEDDING_DIMENSION,
            distance=qdrant_models.Distance.COSINE,
        ),
    )


def _delete_policy_source_vectors(source_id: str) -> None:
    client = _qdrant_client()
    client.delete(
        collection_name=settings.POLICY_QDRANT_COLLECTION,
        points_selector=qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="source_id",
                    match=qdrant_models.MatchValue(value=source_id),
                )
            ]
        ),
    )


def _upsert_policy_vector_points(points: list[qdrant_models.PointStruct]) -> None:
    """在线程池中执行同步 Qdrant 写入，避免阻塞事件循环。"""
    client = _qdrant_client()
    _ensure_policy_collection(client)
    client.upsert(
        collection_name=settings.POLICY_QDRANT_COLLECTION,
        points=points,
    )


def _search_policy_vector_points(
    vector: list[float],
    query_filter: qdrant_models.Filter | None,
    top_k: int,
):
    client = _qdrant_client()
    _ensure_policy_collection(client)
    return client.search(
        collection_name=settings.POLICY_QDRANT_COLLECTION,
        query_vector=vector,
        query_filter=query_filter,
        limit=top_k,
        with_payload=True,
    )


def _serialize_policy_item(
    source: PolicySource,
    chunk: PolicyChunk,
    *,
    score: float,
) -> dict[str, Any]:
    return {
        "chunk_id": str(chunk.id),
        "source_id": str(source.id),
        "title": source.title,
        "source_url": source.source_url,
        "platform": source.platform,
        "market": source.market,
        "category": source.category,
        "version": source.version,
        "effective_at": (
            source.effective_at.isoformat() if source.effective_at else None
        ),
        "title_path": chunk.heading_path,
        "content": chunk.content,
        "score": round(float(score), 4),
    }


async def _lexical_search(
    db: AsyncSession,
    *,
    query: str,
    platform: str | None,
    market: str | None,
    category: str | None,
    top_k: int,
) -> list[dict[str, Any]]:
    """Qdrant 不可用时使用 PostgreSQL 关键词检索。"""
    tokens = [
        token
        for token in dict.fromkeys(TOKEN_PATTERN.findall(query.lower()))
        if token not in QUERY_STOPWORDS
    ][:8]
    if not tokens:
        return []
    statement = (
        select(PolicyChunk, PolicySource)
        .join(PolicySource, PolicySource.id == PolicyChunk.source_id)
        .where(PolicySource.status == "active")
    )
    if platform:
        statement = statement.where(
            PolicySource.platform == platform.strip().lower()
        )
    if market:
        statement = statement.where(
            PolicySource.market == market.strip().upper()
        )
    if category:
        statement = statement.where(
            or_(
                PolicySource.category.is_(None),
                func.lower(PolicySource.category) == category.strip().lower(),
            )
        )
    statement = statement.where(
        or_(
            *[
                PolicyChunk.content.ilike(f"%{token}%")
                for token in tokens
            ]
        )
    ).limit(120)
    rows = (await db.execute(statement)).all()
    ranked: list[tuple[float, PolicyChunk, PolicySource]] = []
    minimum_hits = 2 if len(tokens) >= 4 else 1
    for chunk, source in rows:
        haystack = f"{chunk.heading_path}\n{chunk.content}".lower()
        hits = sum(token in haystack for token in tokens)
        if hits < minimum_hits:
            continue
        title_tokens = set(
            TOKEN_PATTERN.findall(source.title.lower())
        )
        title_bonus = len(set(tokens).intersection(title_tokens)) * 0.08
        phrase_bonus = 0.12 if query.lower() in haystack else 0.0
        score = min(1.0, hits / len(tokens) + title_bonus + phrase_bonus)
        ranked.append((score, chunk, source))
    ranked.sort(
        key=lambda item: (item[0], item[1].created_at),
        reverse=True,
    )
    return [
        _serialize_policy_item(source, chunk, score=score)
        for score, chunk, source in ranked[:top_k]
    ]


async def _vector_search(
    *,
    query: str,
    platform: str | None,
    market: str | None,
    category: str | None,
    top_k: int,
) -> list[dict[str, Any]]:
    vectors = await embed_policy_texts([query])
    if not vectors:
        return []
    must = []
    if platform:
        must.append(
            qdrant_models.FieldCondition(
                key="platform",
                match=qdrant_models.MatchValue(value=platform.strip().lower()),
            )
        )
    if market:
        must.append(
            qdrant_models.FieldCondition(
                key="market",
                match=qdrant_models.MatchValue(value=market.strip().upper()),
            )
        )
    if category:
        must.append(
            qdrant_models.FieldCondition(
                key="category",
                match=qdrant_models.MatchAny(
                    any=[category.strip().lower(), "general"]
                ),
            )
        )
    results = await run_in_threadpool(
        _search_policy_vector_points,
        vectors[0],
        qdrant_models.Filter(must=must) if must else None,
        max(1, min(top_k, 10)),
    )
    items = []
    for result in results:
        if float(result.score) < 0.2:
            continue
        payload = result.payload or {}
        items.append(
            {
                "chunk_id": str(payload.get("chunk_id") or ""),
                "source_id": str(payload.get("source_id") or ""),
                "title": str(payload.get("title") or ""),
                "source_url": str(payload.get("source_url") or ""),
                "platform": str(payload.get("platform") or ""),
                "market": str(payload.get("market") or ""),
                "category": payload.get("category"),
                "version": str(payload.get("version") or ""),
                "effective_at": payload.get("effective_at"),
                "title_path": str(payload.get("title_path") or ""),
                "content": str(payload.get("content") or ""),
                "score": round(float(result.score), 4),
            }
        )
    return items


async def search_policy_knowledge(
    db: AsyncSession,
    *,
    query: str,
    platform: str | None = None,
    market: str | None = None,
    category: str | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    """优先向量检索，任何外部依赖失败都降级到关键词检索。"""
    safe_query = (query or "").strip()
    safe_top_k = max(1, min(int(top_k or 5), 10))
    if not safe_query:
        return {
            "query": "",
            "has_evidence": False,
            "retrieval_mode": "none",
            "items": [],
        }
    retrieval_mode = "vector"
    items: list[dict[str, Any]] = []
    if get_policy_embedding_config() is not None:
        try:
            items = await _vector_search(
                query=safe_query,
                platform=platform,
                market=market,
                category=category,
                top_k=safe_top_k,
            )
        except Exception:
            items = []
    if not items:
        retrieval_mode = "keywords"
        try:
            items = await _lexical_search(
                db,
                query=safe_query,
                platform=platform,
                market=market,
                category=category,
                top_k=safe_top_k,
            )
        except Exception:
            items = []
    return {
        "query": safe_query,
        "has_evidence": bool(items),
        "retrieval_mode": retrieval_mode if items else "none",
        "items": items,
    }


async def ingest_policy_text(
    db: AsyncSession,
    *,
    title: str,
    platform: str,
    market: str,
    category: str | None,
    document_type: str,
    source_url: str,
    version: str,
    effective_at: datetime | None,
    content_text: str,
) -> dict[str, Any]:
    """导入单个政策文本；向量失败时仍保留 PostgreSQL 文本索引。"""
    normalized = normalize_policy_text(content_text)
    if not normalized:
        raise ValueError("政策内容不能为空")
    checksum = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    normalized_platform = platform.strip().lower()
    normalized_market = market.strip().upper()
    normalized_category = (
        category.strip().lower() if category and category.strip() else None
    )

    identity_filters = [
        PolicySource.platform == normalized_platform,
        PolicySource.market == normalized_market,
        PolicySource.document_type == document_type,
        PolicySource.source_url == source_url,
    ]
    if normalized_category:
        identity_filters.append(
            func.lower(PolicySource.category) == normalized_category
        )
    else:
        identity_filters.append(PolicySource.category.is_(None))
    existing_rows = (
        await db.execute(select(PolicySource).where(*identity_filters))
    ).scalars().all()
    existing = next(
        (item for item in existing_rows if item.version == version),
        None,
    )
    if existing is not None and existing.checksum == checksum:
        chunk_count = (
            await db.execute(
                select(func.count()).select_from(PolicyChunk).where(
                    PolicyChunk.source_id == existing.id
                )
            )
        ).scalar_one()
        return {
            "source_id": str(existing.id),
            "changed": False,
            "chunk_count": int(chunk_count),
            "vector_status": "unchanged",
            "sync_run_id": None,
        }

    started_at = datetime.now(timezone.utc)
    sync_run = PolicySyncRun(
        status="running",
        added=0,
        updated=0,
        removed=0,
        started_at=started_at,
    )
    db.add(sync_run)
    await db.flush()

    for item in existing_rows:
        if existing is not None and item.id == existing.id:
            continue
        item.status = "superseded"
        item.updated_at = started_at

    if existing is None:
        source = PolicySource(
            title=title.strip(),
            platform=normalized_platform,
            market=normalized_market,
            category=normalized_category,
            document_type=document_type,
            source_url=source_url,
            version=version,
            effective_at=effective_at,
            checksum=checksum,
            status="active",
        )
        db.add(source)
        await db.flush()
        changed = True
        sync_run.added = 1
    else:
        source = existing
        source.title = title.strip()
        source.effective_at = effective_at
        source.checksum = checksum
        source.status = "active"
        source.updated_at = started_at
        old_chunks = (
            await db.execute(
                select(PolicyChunk).where(PolicyChunk.source_id == source.id)
            )
        ).scalars().all()
        for old_chunk in old_chunks:
            await db.delete(old_chunk)
        changed = True
        sync_run.updated = 1
        try:
            await run_in_threadpool(
                _delete_policy_source_vectors,
                str(source.id),
            )
        except Exception:
            pass

    chunks = chunk_policy_text(normalized)
    chunk_rows = [
        PolicyChunk(
            source_id=source.id,
            heading_path=item["title_path"],
            content=item["content"],
            estimated_tokens=item["estimated_tokens"],
            chunk_hash=item["chunk_hash"],
            qdrant_point_id=str(uuid.uuid4()),
        )
        for item in chunks
    ]
    db.add_all(chunk_rows)
    await db.flush()

    vector_status = "degraded"
    if get_policy_embedding_config() is not None:
        try:
            vectors = await embed_policy_texts(
                [item.content for item in chunk_rows]
            )
            points = [
                    qdrant_models.PointStruct(
                        id=chunk.qdrant_point_id,
                        vector=vector,
                        payload={
                            "chunk_id": str(chunk.id),
                            "source_id": str(source.id),
                            "title": source.title,
                            "source_url": source.source_url,
                            "platform": source.platform,
                            "market": source.market,
                            "category": source.category or "general",
                            "version": source.version,
                            "effective_at": (
                                source.effective_at.isoformat()
                                if source.effective_at
                                else None
                            ),
                            "title_path": chunk.heading_path,
                            "content": chunk.content,
                        },
                    )
                    for chunk, vector in zip(chunk_rows, vectors)
                ]
            await run_in_threadpool(_upsert_policy_vector_points, points)
            vector_status = "synced"
        except Exception:
            vector_status = "degraded"

    sync_run.status = (
        "completed" if vector_status == "synced" else "completed_degraded"
    )
    sync_run.finished_at = datetime.now(timezone.utc)
    await db.flush()
    return {
        "source_id": str(source.id),
        "changed": changed,
        "chunk_count": len(chunk_rows),
        "vector_status": vector_status,
        "sync_run_id": str(sync_run.id),
    }
