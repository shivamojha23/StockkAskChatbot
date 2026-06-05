"""
ingest.py — Knowledge Base Ingestion Script
============================================

Deliverable A: Ingests the StockkAsk knowledge base into the
configured vector database (Pinecone or Qdrant).

Workflow:
  1. Load all entries from knowledge_base.py
  2. Optionally crawl the live site for additional content
  3. Generate embeddings via OpenAI text-embedding-3-small
  4. Upsert into the vector DB with full metadata

Run:
    python ingest.py              # Ingest built-in knowledge base
    python ingest.py --crawl      # Also crawl the live StockkAsk site
    python ingest.py --reset      # Delete existing vectors first
    python ingest.py --dry-run    # Print chunks, don't upsert

Design Principles:
  - Idempotent: running multiple times produces the same result
    (upsert uses stable IDs from knowledge_base.py)
  - Modular: crawl, embed, and upsert are separate functions
  - Resilient: batch embedding with retry via EmbeddingService
"""

import argparse
import asyncio
import hashlib
import logging
import sys
from typing import TYPE_CHECKING

import httpx
from bs4 import BeautifulSoup

# --- Local imports ---
from config import get_settings
from embeddings import get_embedding_service
from knowledge_base import KnowledgeEntry, get_all_knowledge
from vector_store import VectorRecord, get_vector_store

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ingest")

# ---------------------------------------------------------------------------
# Site Crawler
# ---------------------------------------------------------------------------

CRAWL_URLS = [
    "https://stockk.trade/stockkask/",
    "https://stockk.trade/stockkask/smart-screener",
    "https://stockk.trade/stockkask/live-news",
    "https://stockk.trade/stockkask/trade-opportunities",
    "https://stockk.trade/stockkask/privacy-policy",
    "https://stockk.trade/stockkask/terms-and-conditions",
]

CRAWL_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; StockkBotIndexer/1.0; "
        "+https://stockk.trade/stockkask)"
    )
}


async def crawl_site() -> list[KnowledgeEntry]:
    """
    Crawl the StockkAsk website and extract text chunks
    to supplement the static knowledge base.
    Returns a list of KnowledgeEntry dicts.
    """
    entries: list[KnowledgeEntry] = []
    async with httpx.AsyncClient(
        headers=CRAWL_HEADERS,
        timeout=15.0,
        follow_redirects=True,
    ) as client:
        for url in CRAWL_URLS:
            try:
                logger.info("Crawling: %s", url)
                response = await client.get(url)
                response.raise_for_status()
                chunks = _parse_html_to_chunks(url, response.text)
                entries.extend(chunks)
                logger.info("  → Extracted %d chunks from %s", len(chunks), url)
            except httpx.HTTPStatusError as exc:
                logger.warning("HTTP error crawling %s: %s", url, exc)
            except Exception as exc:
                logger.warning("Failed to crawl %s: %s", url, exc)
    return entries


def _parse_html_to_chunks(url: str, html: str) -> list[KnowledgeEntry]:
    """
    Parse an HTML page and extract meaningful text paragraphs
    as knowledge base entries.
    """
    soup = BeautifulSoup(html, "lxml")

    # Remove navigation, scripts, styles, footers
    for tag in soup.select("nav, script, style, footer, .navbar, .sidebar"):
        tag.decompose()

    chunks: list[KnowledgeEntry] = []
    page_title = soup.title.get_text(strip=True) if soup.title else url

    # Extract headings + their following paragraphs as logical chunks
    for heading in soup.find_all(["h1", "h2", "h3"]):
        title_text = heading.get_text(strip=True)
        if not title_text or len(title_text) < 5:
            continue

        # Collect sibling paragraphs until next heading
        body_parts: list[str] = []
        for sibling in heading.find_next_siblings():
            if sibling.name in ("h1", "h2", "h3"):
                break
            text = sibling.get_text(separator=" ", strip=True)
            if text and len(text) > 30:
                body_parts.append(text)

        if not body_parts:
            continue

        content = f"{title_text}. " + " ".join(body_parts)
        if len(content) < 50:
            continue

        # Generate a deterministic ID from the URL + title
        chunk_id = "crawl-" + hashlib.md5(f"{url}::{title_text}".encode()).hexdigest()[:12]  # nosec B324

        chunks.append({
            "id": chunk_id,
            "category": "crawled",
            "title": f"{page_title} — {title_text}",
            "content": content[:2000],  # Safety cap
        })

    return chunks


# ---------------------------------------------------------------------------
# Text preparation
# ---------------------------------------------------------------------------

def _entry_to_embed_text(entry: KnowledgeEntry) -> str:
    """
    Build the text string to embed.
    Combining title + content gives richer semantic representation.
    """
    return f"Title: {entry['title']}\n\nContent: {entry['content']}"


# ---------------------------------------------------------------------------
# Main ingestion logic
# ---------------------------------------------------------------------------

async def run_ingestion(
    *,
    crawl: bool = False,
    reset: bool = False,
    dry_run: bool = False,
    batch_size: int = 50,
) -> None:
    """
    Full ingestion pipeline.

    Args:
        crawl:      Also crawl live site pages.
        reset:      Delete all existing vectors before upsert.
        dry_run:    Print entries, skip API calls.
        batch_size: Number of texts to embed per API call.
    """
    settings = get_settings()
    logger.info("=== StockkAsk RAG Ingestion ===")
    logger.info("Vector DB   : %s", settings.vector_db)
    logger.info("Embed model : %s", settings.embedding_model)
    logger.info("Index/Coll  : %s", settings.pinecone_index_name)

    # 1. Load knowledge base
    entries = get_all_knowledge()
    logger.info("Loaded %d entries from built-in knowledge base.", len(entries))

    # 2. Optionally crawl
    if crawl:
        crawled = await crawl_site()
        entries.extend(crawled)
        logger.info("After crawling: %d total entries.", len(entries))

    # 3. Dry run — just print
    if dry_run:
        for i, e in enumerate(entries, 1):
            print(f"\n[{i}] ID={e['id']} | Category={e['category']}")
            print(f"     Title  : {e['title']}")
            print(f"     Content: {e['content'][:120]}...")
        logger.info("Dry run complete. %d entries would be ingested.", len(entries))
        return

    # 4. Initialise services
    embed_svc = get_embedding_service()
    store = get_vector_store()

    # 5. Optionally reset
    if reset:
        logger.warning("Resetting vector DB — deleting all existing vectors.")
        await store.delete_all()

    # 6. Embed in batches
    texts = [_entry_to_embed_text(e) for e in entries]
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i : i + batch_size]
        logger.info(
            "Embedding batch %d-%d / %d ...",
            i + 1, min(i + batch_size, len(texts)), len(texts),
        )
        batch_vecs = await embed_svc.embed_batch(batch_texts)
        all_embeddings.extend(batch_vecs)

    logger.info("Embeddings generated: %d vectors.", len(all_embeddings))

    # 7. Build VectorRecord list
    records: list[VectorRecord] = []
    for entry, vector in zip(entries, all_embeddings):
        records.append(
            VectorRecord(
                id=entry["id"],
                vector=vector,
                metadata={
                    "category": entry["category"],
                    "title": entry["title"],
                    "content": entry["content"],  # Stored for prompt injection
                    "source_url": "https://stockk.trade/stockkask/",
                },
            )
        )

    # 8. Upsert
    upserted = await store.upsert(records)
    logger.info("✅ Ingestion complete. %d / %d vectors upserted.", upserted, len(records))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="StockkAsk RAG Knowledge Base Ingestion Script"
    )
    parser.add_argument(
        "--crawl",
        action="store_true",
        help="Also crawl the live StockkAsk website for additional content.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all existing vectors before ingesting.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print entries to stdout without making any API calls.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of texts per embedding API call (default: 50).",
    )
    args = parser.parse_args()

    asyncio.run(
        run_ingestion(
            crawl=args.crawl,
            reset=args.reset,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
        )
    )
