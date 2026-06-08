"""
main.py — StockkBot FastAPI Backend
=====================================

Deliverable B: The main FastAPI application.

Endpoints:
  POST /api/chat         — RAG chatbot (streaming)
  GET  /api/health       — Health check
  GET  /api/session/new  — Generate a new session UUID

Architecture:
  - Stateless: no server-side session storage
  - Rate limited: per-IP via SlowAPI
  - CORS: restricted to configured origins
  - Structured logging via structlog
  - All business logic in services, not routes

Run:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from config import get_settings
from rag_service import get_rag_service

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Rate Limiter Setup
# ---------------------------------------------------------------------------

settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.rate_limit_per_day}/day"],
    storage_uri="memory://",  # Use "redis://..." for distributed rate limiting
)

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="StockkBot API",
    description=(
        "RAG-powered chatbot backend for StockkAsk — "
        "AI Stock Research Platform by Indira Securities."
    ),
    version="1.0.0",
    docs_url="/docs" if settings.app_env == "development" else None,
    redoc_url="/redoc" if settings.app_env == "development" else None,
)

# --- Rate limit error handler ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS ---
# Support local development subnets dynamically (localhost, 127.0.0.1, 192.168.x.x, 10.x.x.x, 172.16-31.x.x, 20.x.x.x)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|20\.\d+\.\d+\.\d+)(:\d+)?",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Session-ID"],
    max_age=600,
)

# ---------------------------------------------------------------------------
# Request / Response Models (Pydantic)
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    """A single message in the conversation history."""
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    """
    Incoming request for the /api/chat endpoint.

    session_id:  Frontend-generated UUID for context continuity.
    message:     The user's current question.
    history:     Previous turns in this session (max 20 messages).
    """
    session_id: str = Field(..., min_length=8, max_length=64)
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)

    @field_validator("message")
    @classmethod
    def strip_message(cls, v: str) -> str:
        return v.strip()

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        # Accept UUIDs and alphanumeric session IDs
        v = v.strip()
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("session_id must be alphanumeric.")
        return v


class ChatResponse(BaseModel):
    """Non-streaming response shape (used for error states)."""
    session_id: str
    message: str
    error: bool = False


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str


class SessionResponse(BaseModel):
    session_id: str


# ---------------------------------------------------------------------------
# Startup / Shutdown
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def startup_event() -> None:
    """Warm up services on startup to avoid cold-start latency."""
    logger.info("StockkBot API starting up...", env=settings.app_env)
    try:
        # Pre-initialise the RAG service (connects to vector DB)
        get_rag_service()
        logger.info("RAG service initialised successfully.")
    except Exception as exc:
        logger.error("Failed to initialise RAG service on startup.", error=str(exc))
        # Don't crash the app — individual requests will fail gracefully


@app.on_event("shutdown")
async def shutdown_event() -> None:
    logger.info("StockkBot API shutting down.")


# ---------------------------------------------------------------------------
# Utility: SSE Streaming
# ---------------------------------------------------------------------------


async def sse_event_generator(
    request: Request,
    session_id: str,
    message: str,
    history: list[dict],
) -> str:
    """
    Yields Server-Sent Events (SSE) formatted chunks.

    Format:
        data: {"token": "..."}\n\n
        data: [DONE]\n\n
    """
    rag = get_rag_service()
    full_response: list[str] = []

    try:
        async for token in rag.generate_stream(message, history):
            if await request.is_disconnected():
                logger.info("Client disconnected mid-stream.", session_id=session_id)
                break
            full_response.append(token)
            payload = json.dumps({"token": token, "session_id": session_id})
            yield f"data: {payload}\n\n"

        # Signal stream end
        yield "data: [DONE]\n\n"
        logger.info(
            "Stream complete.",
            session_id=session_id,
            response_chars=sum(len(t) for t in full_response),
        )

    except Exception as exc:
        logger.error("Stream error.", session_id=session_id, error=str(exc))
        error_payload = json.dumps(
            {"token": "", "error": "An unexpected error occurred.", "session_id": session_id}
        )
        yield f"data: {error_payload}\n\n"
        yield "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/api/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """Health check endpoint for load balancer probes."""
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="1.0.0",
    )


@app.get("/api/session/new", response_model=SessionResponse, tags=["Session"])
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def new_session(request: Request) -> SessionResponse:
    """
    Generate a new session UUID.
    The frontend can call this on first load or when no session exists.
    """
    return SessionResponse(session_id=str(uuid.uuid4()))


@app.post("/api/chat", tags=["Chat"])
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def chat(
    request: Request,
    body: ChatRequest,
) -> StreamingResponse:
    """
    Main RAG chatbot endpoint.

    Accepts a user message + optional conversation history.
    Returns a Server-Sent Events stream of LLM tokens.

    Rate limited to {rate_limit_per_minute} requests/IP/minute.
    """
    logger.info(
        "Chat request received.",
        session_id=body.session_id,
        message_preview=body.message[:60],
        history_length=len(body.history),
    )

    # Convert Pydantic models to plain dicts for the RAG service
    history_dicts = [{"role": m.role, "content": m.content} for m in body.history]

    return StreamingResponse(
        sse_event_generator(
            request=request,
            session_id=body.session_id,
            message=body.message,
            history=history_dicts,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",      # Disable nginx buffering for SSE
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Global Exception Handler
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled exception.",
        path=str(request.url.path),
        error=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal error occurred. Please try again."},
    )


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",  # nosec B104
        port=8000,
        reload=settings.app_env == "development",
        log_level=settings.log_level.lower(),
    )
