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
import structlog
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = structlog.get_logger(__name__)


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

    Order:
      1. Prompt injection (CRITICAL — check first, before any processing)
      2. Toxicity
      3. Off-topic (before PII — no point redacting if we're going to block anyway)
      4. PII redaction (passes through, but cleans the message)
    """
    for check in [check_prompt_injection, check_toxicity, check_off_topic]:
        result = check(message, session_id)
        if not result.passed:
            return result

    # PII redaction always runs on non-blocked messages
    return redact_pii(message, session_id)


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


def check_grounding(response: str, context: str, session_id: str) -> GuardrailResult:
    """
    Lightweight grounding check: warn (do not block) if the response makes specific
    numerical claims that are not found in the retrieved context.

    This is a heuristic, not a semantic check. For full hallucination detection,
    integrate an NLI (Natural Language Inference) model like cross-encoder/nli-deberta.

    Currently: Logs a warning for compliance audit. Does not block the response
    to avoid false positives on well-known financial definitions.
    """
    # Extract numbers from response that look like specific stats/metrics
    response_numbers = set(re.findall(r'\b\d{2,}\b', response))
    context_numbers  = set(re.findall(r'\b\d{2,}\b', context))

    ungrounded_numbers = response_numbers - context_numbers
    # Filter out obvious non-facts (years, round numbers, etc.)
    suspicious = {n for n in ungrounded_numbers if not (1900 <= int(n) <= 2030)}

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
