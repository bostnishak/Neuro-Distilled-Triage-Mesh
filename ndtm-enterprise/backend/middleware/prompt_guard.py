"""OWASP LLM Top 10 Prompt Injection & SMT/SQL Delimiter Firewall."""
from __future__ import annotations

import base64
import logging
import re
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.core.exceptions import PromptInjectionDetectedError

logger = logging.getLogger("middleware.prompt_guard")

# Regex signatures for adversarial prompt injection and delimiter breaking
_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"<\s*\|\s*im_start\s*\|>", re.IGNORECASE),
    re.compile(r"<\s*\|\s*im_end\s*\|>", re.IGNORECASE),
    re.compile(r"\[\s*INST\s*\]", re.IGNORECASE),
    re.compile(r"system\s*:", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+(developer|dan|god)\s+mode", re.IGNORECASE),
    re.compile(r"disregard\s+(the\s+)?above\s+prompt", re.IGNORECASE),
    # SMT-LIB and SQL injection tokens
    re.compile(r"\(\s*declare-fun\s+", re.IGNORECASE),
    re.compile(r"\(\s*assert\s+", re.IGNORECASE),
    re.compile(r"\bUNION\s+SELECT\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
    re.compile(r"'\s*OR\s+'?1'?\s*=\s*'?1", re.IGNORECASE),
]

_BASE64_CANDIDATE_RE = re.compile(r"[A-Za-z0-9+/]{32,}={0,2}")


def check_prompt_injection(text: str) -> None:
    """Raises PromptInjectionDetectedError if adversarial tokens or smuggling patterns are detected."""
    if not text:
        return

    # 1. Direct Pattern Inspection
    for pattern in _PROMPT_INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            matched_str = match.group(0)
            logger.warning("Prompt injection blocked: matched pattern '%s'", matched_str)
            raise PromptInjectionDetectedError(matched_str)

    # 2. Base64 Smuggling Inspection
    candidates = _BASE64_CANDIDATE_RE.findall(text)
    for b64 in candidates:
        try:
            decoded = base64.b64decode(b64).decode("utf-8", errors="ignore")
        except Exception:
            continue

        for pattern in _PROMPT_INJECTION_PATTERNS:
            if pattern.search(decoded):
                logger.warning("Base64 smuggled prompt injection blocked: '%s'", decoded[:40])
                raise PromptInjectionDetectedError("BASE64_SMUGGLED_DELIMITER")


class PromptGuardMiddleware(BaseHTTPMiddleware):
    """Inspects JSON request payloads on POST/PUT endpoints for prompt injections."""

    async def dispatch(self, request: Request, call_next: Callable) -> JSONResponse:
        if request.method in ("POST", "PUT", "PATCH"):
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    body_bytes = await request.body()
                    if body_bytes:
                        body_str = body_bytes.decode("utf-8", errors="ignore")
                        check_prompt_injection(body_str)
                except PromptInjectionDetectedError as pie:
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": "FORBIDDEN_PROMPT_INJECTION",
                            "message": "Input was rejected by the Application Security Prompt Firewall.",
                            "detail": pie.details,
                        },
                    )

        return await call_next(request)
