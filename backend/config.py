"""
config.py — Centralised settings management.

Uses pydantic-settings to validate and expose all environment
variables as typed attributes. Single import point for the
entire application — no scattered os.getenv() calls.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings validated at startup."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- OpenAI ---
    openai_api_key: str = ""

    # --- Groq ---
    groq_api_key: str = ""

    # --- Providers ---
    llm_provider: Literal["openai", "groq"] = "groq"
    embedding_provider: Literal["openai", "fastembed"] = "fastembed"

    # --- Vector DB: Pinecone ---
    pinecone_api_key: str = ""
    pinecone_index_name: str = "stockkask-faq"
    pinecone_environment: str = "us-east-1"

    # --- Vector DB: Qdrant (optional alternative) ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "stockkask-faq"

    # --- Which vector DB to use ---
    vector_db: Literal["pinecone", "qdrant"] = "pinecone"

    # --- App ---
    app_env: Literal["development", "production"] = "development"
    allowed_origins: str = "https://stockk.trade,http://localhost:3000"
    log_level: str = "INFO"

    # --- Rate Limiting ---
    rate_limit_per_minute: int = 20
    rate_limit_per_day: int = 500

    # --- RAG / LLM ---
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    chat_model: str = "llama-3.1-8b-instant"
    top_k_results: int = 5
    max_context_tokens: int = 2000

    @property
    def cors_origins(self) -> list[str]:
        """Parse comma-separated origins into a list."""
        return [o.strip() for o in self.allowed_origins.split(",")]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()
