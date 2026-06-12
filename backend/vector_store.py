"""
vector_store.py — Abstraction layer for vector database operations.

Pattern: Abstract Base Class + Concrete Implementations.
This allows swapping Pinecone ↔ Qdrant with zero changes to
calling code (Open/Closed Principle).

Usage:
    store = get_vector_store()          # Returns configured impl
    await store.upsert(vectors)
    results = await store.query(vector, top_k=5)
"""

import abc
import logging
from dataclasses import dataclass
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Transfer Objects
# ---------------------------------------------------------------------------

@dataclass
class VectorRecord:
    """A single document chunk ready for upsert."""
    id: str
    vector: list[float]
    metadata: dict[str, Any]


@dataclass
class SearchResult:
    """A single result returned from a similarity search."""
    id: str
    score: float
    metadata: dict[str, Any]


# ---------------------------------------------------------------------------
# Abstract Base Class
# ---------------------------------------------------------------------------

class VectorStore(abc.ABC):
    """
    Abstract interface for vector database operations.
    All vector DB integrations must implement this interface.
    """

    @abc.abstractmethod
    async def upsert(self, records: list[VectorRecord]) -> int:
        """
        Insert or update vector records.
        Returns the count of successfully upserted records.
        """

    @abc.abstractmethod
    async def query(
        self,
        vector: list[float],
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """
        Find the top_k most similar vectors.
        Optional metadata filter for scoped searches.
        """

    @abc.abstractmethod
    async def delete_all(self) -> None:
        """Delete all vectors — used during re-ingestion."""


# ---------------------------------------------------------------------------
# Pinecone Implementation
# ---------------------------------------------------------------------------

class PineconeVectorStore(VectorStore):
    """
    Pinecone implementation of VectorStore.
    Uses pinecone-client v4 serverless API.
    """

    def __init__(self) -> None:
        settings = get_settings()
        try:
            import asyncio
            from pinecone.grpc import PineconeGRPC as Pinecone
            pc = Pinecone(api_key=settings.pinecone_api_key)
            self._index = pc.Index(settings.pinecone_index_name)
            logger.info("Pinecone index '%s' connected.", settings.pinecone_index_name)
        except Exception as exc:
            logger.error("Failed to initialise Pinecone: %s", exc)
            raise

    async def upsert(self, records: list[VectorRecord]) -> int:
        """Batch upsert to Pinecone in chunks of 100 (API limit)."""
        import asyncio
        BATCH_SIZE = 100
        total = 0
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i : i + BATCH_SIZE]
            vectors = [
                {"id": r.id, "values": r.vector, "metadata": r.metadata}
                for r in batch
            ]
            await asyncio.to_thread(self._index.upsert, vectors=vectors)
            total += len(batch)
            logger.debug("Upserted batch %d/%d", i + BATCH_SIZE, len(records))
        return total

    async def query(
        self,
        vector: list[float],
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        kwargs: dict[str, Any] = {
            "vector": vector,
            "top_k": top_k,
            "include_metadata": True,
        }
        if filter_metadata:
            kwargs["filter"] = filter_metadata

        import asyncio
        response = await asyncio.to_thread(self._index.query, **kwargs)
        return [
            SearchResult(
                id=match["id"],
                score=match["score"],
                metadata=match.get("metadata", {}),
            )
            for match in response.get("matches", [])
        ]

    async def delete_all(self) -> None:
        import asyncio
        await asyncio.to_thread(self._index.delete, delete_all=True)
        logger.warning("All vectors deleted from Pinecone index.")


# ---------------------------------------------------------------------------
# Qdrant Implementation
# ---------------------------------------------------------------------------

class QdrantVectorStore(VectorStore):
    """
    Qdrant implementation of VectorStore.
    Works with both local and cloud-hosted Qdrant.
    """

    VECTOR_DIM = 1536  # text-embedding-3-small dimension

    def __init__(self) -> None:
        settings = get_settings()
        try:
            from qdrant_client import AsyncQdrantClient
            from qdrant_client.models import Distance, VectorParams

            self._client = AsyncQdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key or None,
            )
            self._collection = settings.qdrant_collection
            logger.info("Qdrant collection '%s' connected.", self._collection)
        except Exception as exc:
            logger.error("Failed to initialise Qdrant: %s", exc)
            raise

    async def _ensure_collection(self) -> None:
        """Create the collection if it doesn't exist."""
        from qdrant_client.models import Distance, VectorParams
        collections = await self._client.get_collections()
        names = [c.name for c in collections.collections]
        if self._collection not in names:
            await self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=self.VECTOR_DIM, distance=Distance.COSINE
                ),
            )
            logger.info("Created Qdrant collection '%s'.", self._collection)

    async def upsert(self, records: list[VectorRecord]) -> int:
        from qdrant_client.models import PointStruct

        await self._ensure_collection()
        points = [
            PointStruct(id=r.id, vector=r.vector, payload=r.metadata)
            for r in records
        ]
        await self._client.upsert(
            collection_name=self._collection, points=points
        )
        return len(records)

    async def query(
        self,
        vector: list[float],
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        qfilter = None
        if filter_metadata:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filter_metadata.items()
            ]
            qfilter = Filter(must=conditions)

        results = await self._client.search(
            collection_name=self._collection,
            query_vector=vector,
            limit=top_k,
            query_filter=qfilter,
        )
        return [
            SearchResult(
                id=str(r.id),
                score=r.score,
                metadata=r.payload or {},
            )
            for r in results
        ]

    async def delete_all(self) -> None:
        await self._client.delete_collection(self._collection)
        logger.warning("Qdrant collection '%s' deleted.", self._collection)


# ---------------------------------------------------------------------------
# Factory Function
# ---------------------------------------------------------------------------

def get_vector_store() -> VectorStore:
    """
    Factory: returns the correct VectorStore based on config.
    This is the only place in the codebase that knows which
    implementation to instantiate.
    """
    settings = get_settings()
    if settings.vector_db == "pinecone":
        return PineconeVectorStore()
    elif settings.vector_db == "qdrant":
        return QdrantVectorStore()
    else:
        raise ValueError(f"Unknown vector_db config: '{settings.vector_db}'")
