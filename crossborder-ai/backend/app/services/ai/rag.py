"""政策与知识库 RAG 服务：检索、重排和上下文组装。

VeyaShip - RAG Service with Qdrant.

Vector search for knowledge retrieval to enhance AI content generation.
Indexes product listings, market research, and brand guidelines."""

from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models

from app.core.config import settings


class RAGService:
    """Retrieval-Augmented Generation service using Qdrant vector database.

    Stores and retrieves product knowledge, brand guidelines, and
    market research to improve AI-generated content accuracy.
    """

    def __init__(self):
        self.client = QdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
        )
        self.collection_name = settings.QDRANT_COLLECTION

    async def ensure_collection(self, vector_size: int = 1536):
        """Create the collection if it doesn't exist."""
        collections = self.client.get_collections().collections
        if not any(c.name == self.collection_name for c in collections):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=qdrant_models.VectorParams(
                    size=vector_size,
                    distance=qdrant_models.Distance.COSINE,
                ),
            )

    async def index_document(
        self,
        doc_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        vector: Optional[List[float]] = None,
    ):
        """Index a document with its embedding vector.

        Args:
            doc_id: Unique document identifier.
            text: The document text content.
            metadata: Optional metadata dict (user_id, product_id, etc.).
            vector: Pre-computed embedding. If None, uses a default.
        """
        # TODO: Integrate with an embedding model to generate vectors from text.
        # For now, uses a placeholder vector (needs actual embedding model).
        if vector is None:
            vector = [0.0] * 1536  # Placeholder

        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                qdrant_models.PointStruct(
                    id=hash(doc_id),
                    vector=vector,
                    payload={
                        "doc_id": doc_id,
                        "text": text,
                        **(metadata or {}),
                    },
                )
            ],
        )

    async def search(
        self,
        query_vector: List[float],
        filter_conditions: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Search for the most relevant documents.

        Args:
            query_vector: Embedding vector for the query.
            filter_conditions: Optional metadata filters (e.g., user_id).
            top_k: Number of results to return.

        Returns:
            List of matching documents with scores.
        """
        search_params = qdrant_models.SearchParams(hnsw_ef=128, exact=False)

        must_conditions = []
        if filter_conditions:
            for key, value in filter_conditions.items():
                must_conditions.append(
                    qdrant_models.FieldCondition(
                        key=key,
                        match=qdrant_models.MatchValue(value=value),
                    )
                )

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            query_filter=qdrant_models.Filter(must=must_conditions) if must_conditions else None,
            search_params=search_params,
            limit=top_k,
        )

        return [
            {
                "id": r.id,
                "score": r.score,
                "text": r.payload.get("text", ""),
                "metadata": {k: v for k, v in r.payload.items() if k != "text"},
            }
            for r in results
        ]

    async def delete_document(self, doc_id: str):
        """Remove a document from the index."""
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="doc_id",
                        match=qdrant_models.MatchValue(value=doc_id),
                    )
                ]
            ),
        )
