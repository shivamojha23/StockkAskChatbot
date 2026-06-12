"""
backend/guardrails.py
---------------------
Programmatic guardrail layer for StockkBot.
Runs BEFORE the LLM (input rails) and AFTER the LLM (output rails).

Input Rails:
  1. Prompt injection detection
  2. Toxicity / hate speech keyword filter
  3. PII detection and redaction (Aadhaar, PAN, bank accounts, phone, email)
  4. Off-topic query detection
  5. Message length (already in Pydantic — secondary check here)

Output Rails:
  1. Financial advice detection (SEBI violations)
  2. Prompt leakage detection
  3. PII echo detection
  4. Grounding check (response references content not in context)

All violations are logged via structlog with session_id, violation_type, and
severity for compliance audit trails.
"""

import re
import time
import structlog
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = structlog.get_logger(__name__)

# Timestamp of module import — used by the guardrails health endpoint
_MODULE_LOAD_TIME = time.time()


# ─────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────

class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ViolationType(str, Enum):
    PROMPT_INJECTION = "prompt_injection"
    TOXICITY = "toxicity"
    PII_INPUT = "pii_input"
    OFF_TOPIC = "off_topic"
    SESSION_ABUSE = "session_abuse"
    FINANCIAL_ADVICE = "financial_advice_output"
    PROMPT_LEAKAGE = "prompt_leakage_output"
    PII_OUTPUT = "pii_output"
    GROUNDING_FAILURE = "grounding_failure"


@dataclass
class GuardrailResult:
    passed: bool
    violation_type: Optional[ViolationType] = None
    severity: Optional[Severity] = None
    reason: str = ""
    safe_response: str = ""          # Pre-written user-facing response for blocked requests
    redacted_content: str = ""       # For PII redaction — the cleaned message
    metadata: dict = field(default_factory=dict)


# ─────────────────────────────────────────────
# PATTERN LIBRARIES
# ─────────────────────────────────────────────

# --- Prompt Injection Patterns ---
INJECTION_PATTERNS = [
    # Direct override
    r"ignore\s+(all\s+)?(previous|prior|above|your)\s+instructions?",
    r"disregard\s+(your\s+)?(system\s+prompt|instructions?|rules?|guidelines?)",
    r"forget\s+everything\s+(above|before|prior)",
    r"your\s+(new\s+)?instructions?\s+(are|is)\s*[:\-]",
    r"override\s+(rule|instruction|guideline)",
    r"act\s+as\s+if\s+you\s+have\s+no\s+(rules?|restrictions?|limits?|guidelines?)",
    # Persona attacks
    r"\bDAN\b",                                   # "Do Anything Now" jailbreak
    r"jailbreak",
    r"developer\s+mode",
    r"unrestricted\s+mode",
    r"god\s+mode",
    r"pretend\s+(you\s+are|to\s+be)\s+(an?\s+)?(evil|uncensored|unfiltered|unrestricted)",
    r"simulate\s+(being\s+)?(an?\s+)?(AI|assistant|bot)\s+(with(out)?\s+)?no\s+(rules?|restrictions?)",
    # Authority impersonation
    r"i\s+am\s+(an?\s+)?(admin|administrator|developer|engineer|anthropic|openai|groq)",
    r"this\s+is\s+(a\s+)?(test|debug)\s+(by|from)\s+(anthropic|openai|indira|groq)",
    # Prompt exfiltration
    r"(print|output|show|reveal|display|repeat|list|write|tell\s+me)\s+(your\s+)?(system\s+prompt|instructions?|rules?|prompt|constraints?)",
    r"what\s+(are\s+)?(your\s+)?(instructions?|rules?|system\s+prompt|constraints?)",
    r"(translate|encode|decode|convert|repeat)\s+(your\s+)?(system\s+prompt|instructions?|rules?)",
    # Encoding obfuscation (used to extract restricted content)
    r"(in\s+)?(base64|rot13|morse\s+code|hex|binary)\s*(encode|decode|format|output|answer)",
]

# --- Toxicity / Hate Speech Keywords ---
# Kept minimal and context-appropriate for a professional financial platform.
# Extend with a proper list for production.
TOXICITY_KEYWORDS = [
    r"\bfuck\b", r"\bshit\b", r"\bbitch\b", r"\basshole\b",
    r"\bkill\s+(yourself|urself)\b",
    r"(hate|kill|attack|bomb)\s+(all\s+)?(muslims?|hindus?|sikhs?|christians?|jews?|dalits?)",
    r"\bn[i1]gg[ae3]r\b",
    r"\bterrorist\b.*\b(attack|plan|bomb)\b",
]

# --- PII Detection Patterns (India-specific) ---
PII_PATTERNS = {
    "aadhaar": r"\b[2-9]{1}[0-9]{3}\s?[0-9]{4}\s?[0-9]{4}\b",
    "pan":     r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b",
    "bank_account": r"\b[0-9]{9,18}\b",          # Broad; combine with context keywords
    "credit_card":  r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|6(?:011|5[0-9]{2})[0-9]{12}|3[47][0-9]{13})\b",
    "phone_in": r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b",
    "email":    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
    "ifsc":     r"\b[A-Z]{4}0[A-Z0-9]{6}\b",
}

# --- Off-Topic Rejection Keywords ---
# Catch blatantly out-of-scope requests early to save LLM tokens.
OFF_TOPIC_HARD_PATTERNS = [
    r"\b(write|compose|create|give\s+me)\s+(\w+\s+)?(a\s+)?(poem|song|essay|story|haiku|joke)\b",
    r"\b(write|generate|create|give\s+me|build)\s+(\w+\s+)?(a\s+)?(code|program|script|function|algorithm)\b",
    r"\b(homework|assignment|thesis|dissertation)\b",
    r"\b(recipe|cook|bake|food)\b",
    r"\b(medical|doctor|diagnos|symptom|medicine|drug\s+dosage)\b",
    r"\b(legal\s+advice|lawyer|attorney|sue|lawsuit)\b",
    r"\b(relationship\s+advice|dating|marriage|divorce)\b",
    r"\b(political\s+party|vote|election|politician)\b",
    r"\b(crypto|bitcoin|ethereum|nft|web3|blockchain\s+investment)\b",   # investment angle
]

# --- SEBI Financial Advice Patterns (Output Rail) ---
SEBI_VIOLATION_PATTERNS = [
    r"\b(buy|purchase|acquire)\s+(this\s+)?(stock|share|equity|scrip)\b",
    r"\b(sell|exit|offload)\s+(this\s+)?(stock|share|position)\b",
    r"\b(hold|accumulate|add)\s+(this\s+)?(stock|position)\b",
    r"\b(invest\s+in|put\s+your\s+money\s+in)\b",
    r"\bprice\s+target\s+(of|is|will\s+be)\b",
    r"\b(will|should)\s+(go|reach|hit|touch)\s+(rs\.?|₹|inr)?\s*\d+",
    r"\b(strong\s+buy|buy\s+signal|sell\s+signal|bullish\s+outlook|bearish\s+outlook)\b",
    r"\b(multibagger|10x|100x)\s+(stock|return|opportunity)\b",
    r"\bstock\s+tip\b",
    r"\b(recommended|recommendation)\s+(to\s+)?(buy|sell|invest)\b",
    r"\byou\s+should\s+(buy|sell|invest|consider\s+buying|consider\s+selling)\b",
    r"\b(portfolio\s+allocation|asset\s+allocation)\s+(of|should\s+be)\b",
]

# --- Prompt Leakage Detection (Output Rail) ---
LEAKAGE_PATTERNS = [
    r"PART\s+[1-8]\s+[—\-]",                            # Section headers from this prompt
    r"RULE\s+[CSTIHT]-\d",                               # Rule identifiers
    r"PATTERN\s+I-\d",
    r"system\s+prompt\s+(says?|states?|contains?|reads?)",
    r"my\s+instructions?\s+(say|state|include|are)\s*[:\-]",
    r"i\s+was\s+(told|instructed|programmed|trained)\s+to\s+(never|always|not)\b",
    r"(context|document)\s+id[:\s]+[a-z]+-\d+",         # Internal doc IDs like "platform-001"
    r"pinecone|qdrant|vector\s+(store|db|database)",     # Internal infrastructure
    r"groq|llama-3|gpt-4o-mini",                         # LLM model names
    r"rag_service|knowledge_base\.py|ingest\.py",        # Internal file names
]


# ─────────────────────────────────────────────
# SESSION ABUSE TRACKING
# ─────────────────────────────────────────────

@dataclass
class SessionAbuseRecord:
    """Tracks per-session violation counts for multi-turn abuse detection."""
    injection_attempts: int = 0
    toxicity_attempts: int = 0
    total_violations: int = 0
    first_violation_time: Optional[float] = None
    last_violation_time: Optional[float] = None


SESSION_ABUSE_TRACKER: dict[str, SessionAbuseRecord] = {}
_cleanup_call_counter: int = 0


def cleanup_old_sessions() -> None:
    """Remove session records where last_violation_time is more than 3600s ago."""
    now = time.time()
    stale_ids = [
        sid for sid, rec in SESSION_ABUSE_TRACKER.items()
        if rec.last_violation_time is not None and (now - rec.last_violation_time) > 3600
    ]
    for sid in stale_ids:
        del SESSION_ABUSE_TRACKER[sid]
    if stale_ids:
        logger.info("guardrail.session.cleanup", removed_sessions=len(stale_ids))


def record_violation(
    session_id: str,
    violation_type: ViolationType,
    severity: Severity,
) -> None:
    """Record a guardrail violation against a session for abuse tracking."""
    global _cleanup_call_counter
    _cleanup_call_counter += 1

    # Periodic cleanup every 100 calls
    if _cleanup_call_counter % 100 == 0:
        cleanup_old_sessions()

    if session_id not in SESSION_ABUSE_TRACKER:
        SESSION_ABUSE_TRACKER[session_id] = SessionAbuseRecord()

    rec = SESSION_ABUSE_TRACKER[session_id]
    now = time.time()

    if rec.first_violation_time is None:
        rec.first_violation_time = now
    rec.last_violation_time = now
    rec.total_violations += 1

    if violation_type == ViolationType.PROMPT_INJECTION:
        rec.injection_attempts += 1
    elif violation_type == ViolationType.TOXICITY:
        rec.toxicity_attempts += 1


def check_session_abuse(session_id: str) -> GuardrailResult:
    """
    Check if a session has exceeded abuse thresholds.
    Thresholds:
      - injection_attempts >= 3
      - toxicity_attempts >= 2
      - total_violations >= 5
    """
    rec = SESSION_ABUSE_TRACKER.get(session_id)
    if rec is None:
        return GuardrailResult(passed=True)

    exceeded = (
        rec.injection_attempts >= 3
        or rec.toxicity_attempts >= 2
        or rec.total_violations >= 5
    )

    if exceeded:
        logger.error(
            "guardrail.session.abuse_threshold_exceeded",
            session_id=session_id,
            violation_type=ViolationType.SESSION_ABUSE,
            severity=Severity.CRITICAL,
            injection_attempts=rec.injection_attempts,
            toxicity_attempts=rec.toxicity_attempts,
            total_violations=rec.total_violations,
        )
        return GuardrailResult(
            passed=False,
            violation_type=ViolationType.PROMPT_INJECTION,
            severity=Severity.CRITICAL,
            reason=(
                f"Session abuse threshold exceeded: "
                f"injections={rec.injection_attempts}, "
                f"toxicity={rec.toxicity_attempts}, "
                f"total={rec.total_violations}"
            ),
            safe_response=(
                "Your session has been flagged for repeated policy violations. "
                "Please start a new conversation."
            ),
        )
    return GuardrailResult(passed=True)


# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────

def _compile(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE | re.DOTALL) for p in patterns]


_INJECTION_RE    = _compile(INJECTION_PATTERNS)
_TOXICITY_RE     = _compile(TOXICITY_KEYWORDS)
_OFF_TOPIC_RE    = _compile(OFF_TOPIC_HARD_PATTERNS)
_SEBI_RE         = _compile(SEBI_VIOLATION_PATTERNS)
_LEAKAGE_RE      = _compile(LEAKAGE_PATTERNS)

_PII_RE = {k: re.compile(v, re.IGNORECASE) for k, v in PII_PATTERNS.items()}


def _first_match(patterns: list[re.Pattern], text: str) -> Optional[str]:
    """Return the pattern string of the first matching pattern, or None."""
    for p in patterns:
        if p.search(text):
            return p.pattern
    return None


# ─────────────────────────────────────────────
# INPUT GUARDRAILS
# ─────────────────────────────────────────────

def check_prompt_injection(message: str, session_id: str) -> GuardrailResult:
    """Detect prompt injection and jailbreak attempts in the user's message."""
    matched = _first_match(_INJECTION_RE, message)
    if matched:
        logger.warning(
            "guardrail.input.prompt_injection",
            session_id=session_id,
            violation_type=ViolationType.PROMPT_INJECTION,
            severity=Severity.HIGH,
            matched_pattern=matched,
            message_snippet=message[:120],
        )
        return GuardrailResult(
            passed=False,
            violation_type=ViolationType.PROMPT_INJECTION,
            severity=Severity.HIGH,
            reason=f"Prompt injection pattern detected: {matched}",
            safe_response=(
                "I can't override my guidelines. I'm here to help you navigate "
                "StockkAsk and understand financial concepts. What would you like "
                "to know about the platform?"
            ),
        )
    return GuardrailResult(passed=True)


def check_toxicity(message: str, session_id: str) -> GuardrailResult:
    """Block hate speech, harassment, and abusive content."""
    matched = _first_match(_TOXICITY_RE, message)
    if matched:
        logger.warning(
            "guardrail.input.toxicity",
            session_id=session_id,
            violation_type=ViolationType.TOXICITY,
            severity=Severity.HIGH,
            message_snippet=message[:80],
        )
        return GuardrailResult(
            passed=False,
            violation_type=ViolationType.TOXICITY,
            severity=Severity.HIGH,
            reason="Toxic or abusive content detected.",
            safe_response=(
                "I'm here to provide a respectful and helpful experience. "
                "Please feel free to ask me anything about StockkAsk or "
                "financial concepts."
            ),
        )
    return GuardrailResult(passed=True)


def redact_pii(message: str, session_id: str) -> GuardrailResult:
    """
    Detect and redact PII from user input.
    Returns passed=True with redacted_content set to the cleaned message.
    Logs a MEDIUM severity event for compliance audit.
    Does NOT block the request — just sanitises it.
    """
    redacted = message
    found_pii_types = []

    for pii_type, pattern in _PII_RE.items():
        if pattern.search(redacted):
            found_pii_types.append(pii_type)
            redacted = pattern.sub(f"[{pii_type.upper()}_REDACTED]", redacted)

    if found_pii_types:
        logger.info(
            "guardrail.input.pii_redacted",
            session_id=session_id,
            violation_type=ViolationType.PII_INPUT,
            severity=Severity.MEDIUM,
            pii_types_found=found_pii_types,
        )
        return GuardrailResult(
            passed=True,                     # Allow — but use redacted_content downstream
            violation_type=ViolationType.PII_INPUT,
            severity=Severity.MEDIUM,
            reason=f"PII detected and redacted: {found_pii_types}",
            redacted_content=redacted,
            metadata={"pii_types": found_pii_types},
        )

    return GuardrailResult(passed=True, redacted_content=message)


def check_off_topic(message: str, session_id: str) -> GuardrailResult:
    """
    Detect hard off-topic requests (poems, homework, medical/legal advice, etc.).
    Soft off-topic (mildly unrelated questions) is handled by the system prompt's
    scope rules — this rail catches only the obvious, token-wasting cases.
    """
    matched = _first_match(_OFF_TOPIC_RE, message)
    if matched:
        logger.info(
            "guardrail.input.off_topic",
            session_id=session_id,
            violation_type=ViolationType.OFF_TOPIC,
            severity=Severity.LOW,
            matched_pattern=matched,
        )
        return GuardrailResult(
            passed=False,
            violation_type=ViolationType.OFF_TOPIC,
            severity=Severity.LOW,
            reason=f"Off-topic request detected: {matched}",
            safe_response=(
                "That's a bit outside my area! I'm focused on helping you with "
                "the StockkAsk platform and financial concepts. Is there something "
                "about the screener, news feed, or a financial term I can help with?"
            ),
        )
    return GuardrailResult(passed=True)


def run_input_guardrails(message: str, session_id: str) -> GuardrailResult:
    """
    Master input guardrail runner. Runs all input checks in priority order.
    Returns the FIRST failing check, or a passing result with PII-redacted content.

    Guarantees: result.redacted_content is ALWAYS populated (either the
    PII-cleaned version or the original message unchanged).

    Order:
      0. Session abuse check (blocks repeat offenders before any processing)
      1. Prompt injection (CRITICAL — check first)
      2. Toxicity
      3. Off-topic (before PII — no point redacting if we're going to block anyway)
      4. PII redaction (passes through, but cleans the message)
    """
    # 0. Session abuse check — blocks sessions that have exceeded thresholds
    abuse_result = check_session_abuse(session_id)
    if not abuse_result.passed:
        return abuse_result

    # 1-3. Blocking checks
    for check in [check_prompt_injection, check_toxicity, check_off_topic]:
        result = check(message, session_id)
        if not result.passed:
            # Record the violation for session abuse tracking
            if result.violation_type:
                record_violation(session_id, result.violation_type, result.severity or Severity.HIGH)
            return result

    # 4. PII redaction always runs on non-blocked messages
    pii_result = redact_pii(message, session_id)

    # Guarantee: redacted_content is always populated
    clean_message = pii_result.redacted_content if pii_result.redacted_content else message
    pii_result.redacted_content = clean_message
    return pii_result


# ─────────────────────────────────────────────
# OUTPUT GUARDRAILS
# ─────────────────────────────────────────────

def check_financial_advice_output(response: str, session_id: str) -> GuardrailResult:
    """Detect SEBI violations in the LLM's generated response."""
    matched = _first_match(_SEBI_RE, response)
    if matched:
        logger.error(
            "guardrail.output.sebi_violation",
            session_id=session_id,
            violation_type=ViolationType.FINANCIAL_ADVICE,
            severity=Severity.CRITICAL,
            matched_pattern=matched,
            response_snippet=response[:200],
        )
        return GuardrailResult(
            passed=False,
            violation_type=ViolationType.FINANCIAL_ADVICE,
            severity=Severity.CRITICAL,
            reason=f"SEBI violation detected in output: {matched}",
            safe_response=(
                "I'm not able to provide specific investment recommendations or "
                "stock advice — this is outside my role as a platform guide and "
                "would conflict with SEBI regulations. For personalised advice, "
                "please consult a SEBI-registered investment advisor. I can help "
                "you understand platform features or explain financial concepts instead."
            ),
        )
    return GuardrailResult(passed=True)


def check_prompt_leakage_output(response: str, session_id: str) -> GuardrailResult:
    """Detect accidental or forced leakage of system prompt / internal details."""
    matched = _first_match(_LEAKAGE_RE, response)
    if matched:
        logger.error(
            "guardrail.output.prompt_leakage",
            session_id=session_id,
            violation_type=ViolationType.PROMPT_LEAKAGE,
            severity=Severity.CRITICAL,
            matched_pattern=matched,
            response_snippet=response[:200],
        )
        return GuardrailResult(
            passed=False,
            violation_type=ViolationType.PROMPT_LEAKAGE,
            severity=Severity.CRITICAL,
            reason=f"Potential prompt leakage in output: {matched}",
            safe_response=(
                "I'm not able to share internal configuration details. "
                "How can I help you with StockkAsk today?"
            ),
        )
    return GuardrailResult(passed=True)


def check_pii_in_output(response: str, session_id: str) -> GuardrailResult:
    """Detect if the LLM has echoed or generated PII in its response."""
    for pii_type, pattern in _PII_RE.items():
        if pattern.search(response):
            logger.error(
                "guardrail.output.pii_detected",
                session_id=session_id,
                violation_type=ViolationType.PII_OUTPUT,
                severity=Severity.CRITICAL,
                pii_type=pii_type,
            )
            return GuardrailResult(
                passed=False,
                violation_type=ViolationType.PII_OUTPUT,
                severity=Severity.CRITICAL,
                reason=f"PII ({pii_type}) detected in LLM output.",
                safe_response=(
                    "I noticed my response contained personal information which I "
                    "shouldn't share. Please don't include personal details in your "
                    "questions. How else can I help you with StockkAsk?"
                ),
            )
    return GuardrailResult(passed=True)


def check_grounding(
    response: str,
    context: str,
    session_id: str,
    history: str = "",
) -> GuardrailResult:
    """
    Lightweight grounding check: warn (do not block) if the response makes specific
    numerical claims that are not found in the retrieved context.

    This is a heuristic, not a semantic check. For full hallucination detection,
    integrate an NLI (Natural Language Inference) model like cross-encoder/nli-deberta.

    Filtering applied to reduce false positives:
      - Integers 1-100 (common financial ratio values like PE, ROCE, ROE)
      - Integers 1900-2030 (years)
      - Numbers present in conversation history

    Currently: Logs a warning for compliance audit. Does not block the response
    to avoid false positives on well-known financial definitions.
    """
    # Extract numbers from response that look like specific stats/metrics
    response_numbers = set(re.findall(r'\b\d{2,}\b', response))
    context_numbers  = set(re.findall(r'\b\d{2,}\b', context))
    history_numbers  = set(re.findall(r'\b\d{2,}\b', history)) if history else set()

    ungrounded_numbers = response_numbers - context_numbers - history_numbers

    # Filter out common financial education values and years
    suspicious = set()
    for n in ungrounded_numbers:
        val = int(n)
        if 1 <= val <= 100:        # Common ratio values (PE 15, ROCE 18, ROE 22, etc.)
            continue
        if 1900 <= val <= 2030:     # Years
            continue
        suspicious.add(n)

    if len(suspicious) > 3:
        logger.warning(
            "guardrail.output.grounding_warning",
            session_id=session_id,
            violation_type=ViolationType.GROUNDING_FAILURE,
            severity=Severity.MEDIUM,
            ungrounded_numbers=list(suspicious),
        )
        # Warning only — do not block. Human review via logs.
        return GuardrailResult(
            passed=True,      # Still passes — log for review
            violation_type=ViolationType.GROUNDING_FAILURE,
            severity=Severity.MEDIUM,
            reason=f"Response contains numbers not found in retrieved context: {suspicious}",
        )
    return GuardrailResult(passed=True)


def run_output_guardrails(
    response: str,
    context: str,
    session_id: str,
) -> GuardrailResult:
    """
    Master output guardrail runner. Run after full response is assembled.
    For streaming: buffer all tokens, then run this on the complete buffer.

    Order:
      1. Financial advice / SEBI (highest business risk)
      2. Prompt leakage (security risk)
      3. PII in output (privacy risk)
      4. Grounding check (quality warning — does not block)
    """
    for check_fn, args in [
        (check_financial_advice_output, (response, session_id)),
        (check_prompt_leakage_output,   (response, session_id)),
        (check_pii_in_output,           (response, session_id)),
    ]:
        result = check_fn(*args)
        if not result.passed:
            return result

    # Grounding check — non-blocking, logs warning only
    check_grounding(response, context, session_id)

    return GuardrailResult(passed=True)


# ─────────────────────────────────────────────
# GUARDRAIL HEALTH / STATS
# ─────────────────────────────────────────────

def get_guardrail_stats() -> dict:
    """
    Return guardrail system statistics for the health endpoint.
    Never exposes message content, matched patterns, or PII.
    """
    # Count active sessions and find top violators
    active_sessions = len(SESSION_ABUSE_TRACKER)
    top_violators = sorted(
        SESSION_ABUSE_TRACKER.items(),
        key=lambda x: x[1].total_violations,
        reverse=True,
    )[:3]

    return {
        "module_loaded_at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(_MODULE_LOAD_TIME)
        ),
        "input_patterns": {
            "prompt_injection": len(_INJECTION_RE),
            "toxicity": len(_TOXICITY_RE),
            "off_topic": len(_OFF_TOPIC_RE),
            "pii": len(_PII_RE),
        },
        "output_patterns": {
            "sebi_financial_advice": len(_SEBI_RE),
            "prompt_leakage": len(_LEAKAGE_RE),
            "pii_output": len(_PII_RE),
        },
        "session_abuse_tracker": {
            "active_sessions": active_sessions,
            "top_violators": [
                {
                    "session_id": sid,
                    "total_violations": rec.total_violations,
                    "injection_attempts": rec.injection_attempts,
                    "toxicity_attempts": rec.toxicity_attempts,
                }
                for sid, rec in top_violators
            ],
        },
    }
