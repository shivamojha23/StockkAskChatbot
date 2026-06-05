"""
embeddings.py — Embedding service supporting both local FastEmbed and OpenAI.
"""

import logging
from functools import lru_cache

from config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Generates text embeddings using either local FastEmbed or OpenAI's API.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._provider = settings.embedding_provider

        if self._provider == "fastembed":
            logger.info("Initialising local FastEmbed model '%s'...", settings.embedding_model)
            from fastembed import TextEmbedding
            # This downloads the model on the first load if it's not present
            self._model = TextEmbedding(model_name=settings.embedding_model)
            logger.info("FastEmbed model loaded successfully.")
        elif self._provider == "openai":
            logger.info("Initialising OpenAI Embeddings with model '%s'...", settings.embedding_model)
            import tiktoken
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
            self._model_name = settings.embedding_model
            self._encoder = tiktoken.get_encoding("cl100k_base")
            self.MAX_TOKENS_PER_CHUNK = 8191
        else:
            raise ValueError(f"Unknown embedding provider: {self._provider}")

    def _truncate_to_limit(self, text: str) -> str:
        """Truncate text to fit within the model's context window (OpenAI only)."""
        if self._provider == "openai":
            tokens = self._encoder.encode(text)
            if len(tokens) <= self.MAX_TOKENS_PER_CHUNK:
                return text
            truncated = self._encoder.decode(tokens[: self.MAX_TOKENS_PER_CHUNK])
            logger.warning("Text truncated from %d to %d tokens.", len(tokens), self.MAX_TOKENS_PER_CHUNK)
            return truncated
        return text

    async def embed_single(self, text: str) -> list[float]:
        """
        Embed a single text string.
        Used for query embedding during RAG retrieval.
        """
        if self._provider == "fastembed":
            # fastembed is synchronous but very fast, so we can wrap it or call it directly.
            # Using list(self._model.embed([text])) returns a generator of numpy arrays.
            embeddings = list(self._model.embed([text]))
            return embeddings[0].tolist()
        
        elif self._provider == "openai":
            from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
            
            # We can define a local retryable function to perform the api call
            @retry(
                retry=retry_if_exception_type(Exception),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                stop=stop_after_attempt(3),
                reraise=True,
            )
            async def _call_api():
                truncated = self._truncate_to_limit(text)
                response = await self._client.embeddings.create(
                    model=self._model_name,
                    input=truncated,
                )
                return response.data[0].embedding
                
            return await _call_api()

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a batch of texts.
        Used during knowledge base ingestion.
        """
        if self._provider == "fastembed":
            embeddings = list(self._model.embed(texts))
            return [e.tolist() for e in embeddings]
            
        elif self._provider == "openai":
            from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
            
            @retry(
                retry=retry_if_exception_type(Exception),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                stop=stop_after_attempt(3),
                reraise=True,
            )
            async def _call_api():
                truncated_texts = [self._truncate_to_limit(t) for t in texts]
                response = await self._client.embeddings.create(
                    model=self._model_name,
                    input=truncated_texts,
                )
                # Sort by index to guarantee ordering
                sorted_data = sorted(response.data, key=lambda x: x.index)
                return [item.embedding for item in sorted_data]
                
            return await _call_api()


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    """Return a cached singleton EmbeddingService."""
    return EmbeddingService()
