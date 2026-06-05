# StockkBot — RAG Chatbot for StockkAsk

> **AI-powered platform guide for [StockkAsk](https://stockk.trade/stockkask/)**  
> Built for Indira Securities Pvt. Ltd. · SEBI-registered stockbroker · 38+ years of market legacy.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Project Structure](#project-structure)
3. [Software Engineering Principles](#software-engineering-principles)
4. [Quick Start](#quick-start)
5. [Configuration](#configuration)
6. [Deliverables](#deliverables)
7. [API Reference](#api-reference)
8. [Embedding the Widget](#embedding-the-widget)
9. [Updating the Knowledge Base](#updating-the-knowledge-base)
10. [Production Deployment](#production-deployment)
11. [What You Still Need](#what-you-still-need)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        StockkBot System                         │
│                                                                 │
│  ┌──────────────┐    SSE Stream    ┌──────────────────────────┐ │
│  │  chatbot-    │ ◄──────────────► │   FastAPI Backend        │ │
│  │  widget.js   │   POST /api/chat │   main.py                │ │
│  │  (Shadow DOM)│                  │   Rate limited (SlowAPI) │ │
│  └──────────────┘                  │   CORS restricted        │ │
│   sessionStorage                   └──────────┬───────────────┘ │
│   UUID session                                │                 │
│                                    ┌──────────▼───────────────┐ │
│                                    │   RAG Pipeline           │ │
│                                    │   rag_service.py         │ │
│                                    │                          │ │
│                                    │  1. Embed query          │ │
│                                    │     (OpenAI embeddings)  │ │
│                                    │  2. Search Vector DB     │ │
│                                    │     (Pinecone/Qdrant)    │ │
│                                    │  3. Inject context into  │ │
│                                    │     system prompt        │ │
│                                    │  4. Stream GPT-4o-mini   │ │
│                                    └──────────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  ingest.py  →  knowledge_base.py  →  Vector DB           │   │
│  │  (One-time setup + on knowledge update)                  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
User types question
        │
        ▼
Frontend generates session UUID (sessionStorage)
        │
        ▼  POST /api/chat  {session_id, message, history}
FastAPI receives request → rate-limit check → validate input
        │
        ▼
EmbeddingService.embed_single(query)   → OpenAI API
        │
        ▼
VectorStore.query(vector, top_k=5)     → Pinecone / Qdrant
        │  Returns: [{title, content, score}, ...]
        ▼
Build system prompt with injected context chunks
        │
        ▼
OpenAI GPT-4o-mini (streaming)
        │  Server-Sent Events (token by token)
        ▼
Frontend renders tokens in real-time → full response
```

---

## Project Structure

```
stockkask-chatbot/
├── backend/
│   ├── main.py              # FastAPI app, endpoints, rate limiting
│   ├── rag_service.py       # Core RAG pipeline (embed → retrieve → generate)
│   ├── vector_store.py      # Abstract VectorStore + Pinecone & Qdrant impls
│   ├── embeddings.py        # OpenAI embedding service with retry
│   ├── knowledge_base.py    # Structured FAQ & glossary data
│   ├── ingest.py            # CLI script to populate the vector DB
│   ├── config.py            # Centralised settings (pydantic-settings)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── chatbot-widget.js    # Self-contained Web Component (Shadow DOM)
│   └── demo.html            # Test page
├── docker-compose.yml
└── README.md
```

---

## Software Engineering Principles

| Principle | How It's Applied |
|-----------|-----------------|
| **Single Responsibility** | Each module has one job: `embeddings.py` only embeds, `vector_store.py` only queries the DB, `rag_service.py` orchestrates |
| **Open/Closed** | `VectorStore` ABC allows adding new DB backends without changing callers |
| **Dependency Inversion** | `rag_service.py` depends on `VectorStore` interface, not Pinecone/Qdrant |
| **DRY** | `config.py` is the single source for all settings — no scattered `os.getenv()` |
| **Statelessness** | Backend holds zero session state; all history is passed in per request |
| **Idempotent Ingestion** | `ingest.py` uses stable IDs — running it N times produces the same DB state |
| **Loose Coupling** | Frontend ↔ Backend speak only via HTTP + SSE; web component is isolated in Shadow DOM |
| **High Cohesion** | All vector DB code in `vector_store.py`, all RAG logic in `rag_service.py` |
| **Security** | CORS whitelist, IP rate limiting, input validation via Pydantic, non-root Docker user |
| **Scalability** | Stateless FastAPI + multiple Uvicorn workers; Redis-upgradeable rate limiter |

---

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js (optional, only for serving the demo HTML)
- A [Pinecone](https://www.pinecone.io/) account (free tier works) **OR** local Qdrant
- An [OpenAI API key](https://platform.openai.com/)

### 1. Clone and set up

```bash
cd stockkask-chatbot/backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Create the Pinecone index

In your Pinecone console:
- Index name: `stockkask-faq`
- Dimensions: `1536` (text-embedding-3-small)
- Metric: `cosine`
- Spec: Serverless (recommended) or pod-based

### 4. Run ingestion

```bash
python ingest.py                  # Load built-in knowledge base
python ingest.py --crawl          # Also crawl the live StockkAsk site
python ingest.py --reset --crawl  # Full fresh ingest
python ingest.py --dry-run        # Preview what would be ingested
```

### 5. Start the backend

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 6. Test the widget

Open `frontend/demo.html` in your browser (served via a local server):

```bash
cd frontend
python -m http.server 3000
# Visit http://localhost:3000/demo.html
```

---

## Configuration

All configuration lives in `backend/.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | **Required** |
| `PINECONE_API_KEY` | Pinecone API key | Required if using Pinecone |
| `PINECONE_INDEX_NAME` | Pinecone index name | `stockkask-faq` |
| `VECTOR_DB` | `pinecone` or `qdrant` | `pinecone` |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins | `https://stockk.trade,...` |
| `RATE_LIMIT_PER_MINUTE` | Requests per IP per minute | `20` |
| `RATE_LIMIT_PER_DAY` | Requests per IP per day | `500` |
| `TOP_K_RESULTS` | Context chunks to retrieve | `5` |
| `CHAT_MODEL` | OpenAI model | `gpt-4o-mini` |

---

## Deliverables

### Deliverable A — `ingest.py`
- Loads `knowledge_base.py` (44 entries covering all StockkAsk features)
- Optionally crawls the live StockkAsk website
- Generates embeddings via `text-embedding-3-small`
- Upserts to Pinecone or Qdrant
- CLI flags: `--crawl`, `--reset`, `--dry-run`, `--batch-size`

### Deliverable B — `main.py`
- `POST /api/chat` — streaming RAG endpoint
- `GET /api/health` — load balancer probe
- `GET /api/session/new` — UUID generation
- IP-based rate limiting via SlowAPI
- CORS, structured logging, global error handling

### Deliverable C — `chatbot-widget.js`
- Zero-dependency Vanilla JS Web Component (Shadow DOM)
- Floating launcher bubble with animation
- Real-time SSE streaming token display
- Session UUID in `sessionStorage`
- Conversation history context
- Quick suggestion chips
- SEBI compliance disclaimer always visible
- Full responsive design
- Single `<script>` tag embed

---

## API Reference

### `POST /api/chat`

**Request:**
```json
{
  "session_id": "uuid-string",
  "message": "What is the Smart Screener?",
  "history": [
    {"role": "user", "content": "Hi"},
    {"role": "assistant", "content": "Hello! How can I help?"}
  ]
}
```

**Response:** `text/event-stream`
```
data: {"token": "The", "session_id": "..."}
data: {"token": " Smart", "session_id": "..."}
data: {"token": " Screener", "session_id": "..."}
...
data: [DONE]
```

**Rate limits:** 20 req/IP/min · 500 req/IP/day

---

## Embedding the Widget

### Option 1 — Script tag (simplest)
```html
<script
  src="https://your-cdn.com/chatbot-widget.js"
  data-api-url="https://api.yourdomain.com"
  data-theme="dark"
  data-position="bottom-right"
  defer
></script>
```

### Option 2 — Programmatic
```html
<script src="chatbot-widget.js"></script>
<script>
  StockkBotWidget.init({
    apiUrl: 'https://api.yourdomain.com',
    theme: 'dark',
    position: 'bottom-right',
    primaryColor: '#00C896',
  });
</script>
```

---

## Updating the Knowledge Base

1. Edit `backend/knowledge_base.py` — add/modify entries with stable `id` values
2. Re-run ingestion (no `--reset` needed for additions; use `--reset` for edits):

```bash
python ingest.py                   # Add new entries only
python ingest.py --reset --crawl   # Full rebuild
```

---

## Production Deployment

### Docker

```bash
docker-compose up -d
```

### Environment checklist

- [ ] `APP_ENV=production` (disables `/docs` and `/redoc`)
- [ ] `ALLOWED_ORIGINS` set to your exact domains only
- [ ] Deploy behind HTTPS (nginx/Caddy/Cloudflare)
- [ ] Set `RATE_LIMIT_PER_MINUTE` conservatively (recommend 10)
- [ ] For multi-instance deployments: switch rate limiter to Redis:
  ```python
  # In main.py, change storage_uri:
  limiter = Limiter(..., storage_uri="redis://redis:6379")
  ```
- [ ] Set Pinecone index environment to match your cloud region

---

## What You Still Need

1. **Pinecone / Qdrant credentials** — Sign up at [pinecone.io](https://pinecone.io) (free tier available)
2. **OpenAI API key** — At [platform.openai.com](https://platform.openai.com)
3. **A hosting platform** — Railway, Render, AWS ECS, GCP Cloud Run, or any Docker host
4. **CDN for the widget** — CloudFront, Cloudflare R2, or Vercel to serve `chatbot-widget.js`
5. **Add more knowledge** — Run `python ingest.py --crawl` periodically as the site updates
6. **Redis** (optional) — For distributed rate limiting across multiple backend instances
