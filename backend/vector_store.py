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
# FAISS Implementation (Local In-Memory)
# ---------------------------------------------------------------------------

class FAISSVectorStore(VectorStore):
    """
    FAISS implementation of VectorStore — ultra-low-latency local search.

    Uses faiss-cpu for in-memory cosine similarity search.
    Persists index + metadata to disk so it survives server restarts.
    For small KBs (< 10K vectors), search takes < 1ms.
    """

    INDEX_DIR = "faiss_index"
    INDEX_FILE = "index.faiss"
    META_FILE = "metadata.json"

    def __init__(self) -> None:
        import json
        import os

        import faiss
        import numpy as np

        self._faiss = faiss
        self._np = np
        self._json = json
        self._os = os

        self._index_path = os.path.join(self.INDEX_DIR, self.INDEX_FILE)
        self._meta_path = os.path.join(self.INDEX_DIR, self.META_FILE)

        # Try to load persisted index from disk
        if os.path.exists(self._index_path) and os.path.exists(self._meta_path):
            self._index = faiss.read_index(self._index_path)
            with open(self._meta_path, "r", encoding="utf-8") as f:
                self._metadata: dict[str, dict[str, Any]] = json.load(f)
            self._id_list: list[str] = list(self._metadata.keys())
            logger.info(
                "FAISS index loaded from disk. %d vectors ready.",
                self._index.ntotal,
            )
        else:
            self._index = None
            self._metadata = {}
            self._id_list = []
            logger.info("FAISS index not found on disk. Will be created on first upsert.")

    def _save_to_disk(self) -> None:
        """Persist the FAISS index and metadata to disk."""
        self._os.makedirs(self.INDEX_DIR, exist_ok=True)
        self._faiss.write_index(self._index, self._index_path)
        with open(self._meta_path, "w", encoding="utf-8") as f:
            self._json.dump(self._metadata, f, ensure_ascii=False)
        logger.debug("FAISS index saved to disk (%d vectors).", self._index.ntotal)

    async def upsert(self, records: list[VectorRecord]) -> int:
        if not records:
            return 0

        dim = len(records[0].vector)

        # Create index if it doesn't exist yet
        if self._index is None:
            # Use IndexFlatIP (inner product) with normalized vectors = cosine similarity
            self._index = self._faiss.IndexFlatIP(dim)
            logger.info("Created new FAISS IndexFlatIP with dimension %d.", dim)

        # Build numpy array of vectors and normalize for cosine similarity
        vectors = self._np.array(
            [r.vector for r in records], dtype=self._np.float32
        )
        self._faiss.normalize_L2(vectors)

        # Add to index
        self._index.add(vectors)

        # Store metadata keyed by record ID
        for r in records:
            self._metadata[r.id] = r.metadata
            self._id_list.append(r.id)

        # Persist to disk
        self._save_to_disk()

        logger.info("FAISS upserted %d vectors (total: %d).", len(records), self._index.ntotal)
        return len(records)

    async def query(
        self,
        vector: list[float],
        top_k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        if self._index is None or self._index.ntotal == 0:
            logger.warning("FAISS index is empty. Returning no results.")
            return []

        # Normalize query vector for cosine similarity
        query_vec = self._np.array([vector], dtype=self._np.float32)
        self._faiss.normalize_L2(query_vec)

        # Search
        k = min(top_k, self._index.ntotal)
        scores, indices = self._index.search(query_vec, k)

        results: list[SearchResult] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._id_list):
                continue
            record_id = self._id_list[idx]
            meta = self._metadata.get(record_id, {})

            # Apply metadata filter if provided
            if filter_metadata:
                if not all(meta.get(fk) == fv for fk, fv in filter_metadata.items()):
                    continue

            results.append(
                SearchResult(id=record_id, score=float(score), metadata=meta)
            )

        return results

    async def delete_all(self) -> None:
        import shutil

        self._index = None
        self._metadata = {}
        self._id_list = []
        if self._os.path.exists(self.INDEX_DIR):
            shutil.rmtree(self.INDEX_DIR)
        logger.warning("FAISS index deleted.")


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
    elif settings.vector_db == "faiss":
        return FAISSVectorStore()
    else:
        raise ValueError(f"Unknown vector_db config: '{settings.vector_db}'")

