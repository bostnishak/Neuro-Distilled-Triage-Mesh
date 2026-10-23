"""PII (Personally Identifiable Information) Redaction & Prompt Injection Defense."""
from __future__ import annotations

import re
from typing import Any

# =============================================================================
# Regex Patterns
# =============================================================================
_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b",
    re.IGNORECASE,
)

# Turkish phone formats: 05xx xxx xx xx, +90 5xx xxx xxxx, 05xxxxxxxxx
_PHONE_RE = re.compile(
    r"(?:\+?90\s*|\b0)?5\d{2}[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}\b"
)

# IBAN (TR followed by 24 digits)
_IBAN_RE = re.compile(
    r"\bTR\d{2}(?:\s*\d{4}){5}\s*\d{2}\b",
    re.IGNORECASE,
)

# Credit card (13 to 19 digits)
_CREDIT_CARD_RE = re.compile(
    r"\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{15,16}\b"
)

# Potential 11-digit national ID (TCKN)
_TCKN_CANDIDATE_RE = re.compile(r"\b[1-9]\d{10}\b")

# Prompt injection markers
_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"<\s*\|\s*im_start\s*\|>", re.IGNORECASE),
    re.compile(r"<\s*\|\s*im_end\s*\|>", re.IGNORECASE),
    re.compile(r"\[\s*INST\s*\]", re.IGNORECASE),
    re.compile(r"system\s*:", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+(developer|dan)\s+mode", re.IGNORECASE),
]


def validate_tckn(tckn: str) -> bool:
    """Validate Turkish Republic Identification Number (TC Kimlik No) checksum algorithm."""
    if len(tckn) != 11 or not tckn.isdigit() or tckn[0] == "0":
        return False
    digits = [int(c) for c in tckn]
    # 10th digit: ((sum(odd digits 1..9) * 7) - sum(even digits 2..8)) % 10 == d10
    odd_sum = sum(digits[0:9:2])
    even_sum = sum(digits[1:8:2])
    tenth = ((odd_sum * 7) - even_sum) % 10
    if tenth != digits[9]:
        return False
    # 11th digit: sum(d1..d10) % 10 == d11
    eleventh = sum(digits[:10]) % 10
    return eleventh == digits[10]


validate_tckn_checksum = validate_tckn


class PIIRedactor:
    """High-performance PII scrubber for Turkish phones, TCKN, IBAN, cards, and emails."""

    def redact(self, text: str) -> tuple[str, list[dict[str, Any]]]:
        if not text:
            return text, []

        redactions: list[dict[str, Any]] = []

        # 1. Emails
        def _email_sub(match: re.Match[str]) -> str:
            val = match.group(0)
            redactions.append({"type": "email", "value": val})
            return "[REDACTED_EMAIL]"

        cleaned = _EMAIL_RE.sub(_email_sub, text)

        # 2. Financials
        def _iban_sub(match: re.Match[str]) -> str:
            val = match.group(0)
            redactions.append({"type": "iban", "value": val})
            return "[REDACTED_IBAN]"

        def _card_sub(match: re.Match[str]) -> str:
            val = match.group(0)
            redactions.append({"type": "credit_card", "value": val})
            return "[REDACTED_CARD]"

        cleaned = _IBAN_RE.sub(_iban_sub, cleaned)
        cleaned = _CREDIT_CARD_RE.sub(_card_sub, cleaned)

        # 3. Phone Numbers
        def _phone_sub(match: re.Match[str]) -> str:
            val = match.group(0)
            redactions.append({"type": "phone", "value": val})
            return "[REDACTED_PHONE]"

        cleaned = _PHONE_RE.sub(_phone_sub, cleaned)

        # 4. TCKN (only if checksum validates)
        def _tckn_sub(match: re.Match[str]) -> str:
            val = match.group(0)
            if validate_tckn(val):
                redactions.append({"type": "tckn", "value": val})
                return "[REDACTED_TCKN]"
            return val

        cleaned = _TCKN_CANDIDATE_RE.sub(_tckn_sub, cleaned)
        return cleaned, redactions


def redact_pii(text: str) -> str:
    """Convenience helper returning just the redacted text."""
    redactor = PIIRedactor()
    cleaned, _ = redactor.redact(text)
    return cleaned


def sanitize_input_text(text: str) -> str:
    """Neutralize non-printable control characters and prompt injection delimiters."""
    if not text:
        return text

    # Remove non-printable characters except newline and tab
    sanitized = "".join(c for c in text if c >= " " or c in "\n\t")

    # Filter prompt injection delimiter attacks
    for pattern in _PROMPT_INJECTION_PATTERNS:
        sanitized = pattern.sub("[FILTERED_PROMPT_DELIMITER]", sanitized)

    return sanitized.strip()
