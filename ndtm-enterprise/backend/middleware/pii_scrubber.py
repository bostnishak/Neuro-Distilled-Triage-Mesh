"""Vatandaş bildirimlerindeki TCKN, telefon, IBAN ve kart numaralarını maskeleyen modül."""
from __future__ import annotations

import re
from typing import Any

from backend.core.security import hmac_pseudonymize

# =============================================================================
# Regex Kalıpları
# =============================================================================
_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b",
    re.IGNORECASE,
)

# Turkish phone formats: +90 5xx xxx xxxx, 05xx xxx xx xx, 05xxxxxxxxx, 5xxxxxxxxx
_PHONE_RE = re.compile(
    r"(?:\+?90\s*|\b0)?5\d{2}[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}\b"
)

# Turkish IBAN (TR followed by 24 digits)
_IBAN_RE = re.compile(
    r"\bTR\d{2}(?:\s*\d{4}){5}\s*\d{2}\b",
    re.IGNORECASE,
)

# Credit card formats (13 to 19 digits)
_CREDIT_CARD_RE = re.compile(
    r"\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{15,16}\b"
)

# 11-digit sequences starting with non-zero (TCKN candidate)
_TCKN_CANDIDATE_RE = re.compile(r"\b[1-9]\d{10}\b")


def validate_tckn_algorithm(tckn: str) -> bool:
    """TC Kimlik No algoritmasını doğrular (11 hane, 0 ile başlayamaz, Modulo-10/11 kontrolü)."""
    if len(tckn) != 11 or not tckn.isdigit() or tckn[0] == "0":
        return False
    digits = [int(c) for c in tckn]

    # Rule 1: d10 = ((sum(odd digits 1..9) * 7) - sum(even digits 2..8)) % 10
    odd_sum = sum(digits[0:9:2])
    even_sum = sum(digits[1:8:2])
    tenth = ((odd_sum * 7) - even_sum) % 10
    if tenth != digits[9]:
        return False

    # Rule 2: d11 = sum(d1..d10) % 10
    eleventh = sum(digits[:10]) % 10
    return eleventh == digits[10]


def validate_luhn_credit_card(card_num: str) -> bool:
    """Validates credit card numbers using Luhn checksum algorithm."""
    digits = [int(c) for c in card_num if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    total = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = d * 2
            total += (doubled - 9) if doubled > 9 else doubled
        else:
            total += d
    return total % 10 == 0


class PIIScrubber:
    """Enterprise PII Sanitizer replacing personal data with HMAC-SHA256 correlation tokens."""

    def __init__(self, salt: str | None = None) -> None:
        self.salt = salt

    def scrub(self, text: str) -> tuple[str, list[dict[str, Any]]]:
        """Scrubs raw text and returns (sanitized_text, list_of_redaction_metadata)."""
        if not text:
            return text, []

        redactions: list[dict[str, Any]] = []

        # 1. TCKN (Algorithmic validation)
        def _tckn_replacer(match: re.Match[str]) -> str:
            candidate = match.group(0)
            if validate_tckn_algorithm(candidate):
                token = hmac_pseudonymize(candidate, self.salt)
                redactions.append({"type": "TCKN", "pseudonym": token})
                return f"[REDACTED_TCKN_{token}]"
            return candidate

        scrubbed = _TCKN_CANDIDATE_RE.sub(_tckn_replacer, text)

        # 2. Email Scrubbing
        def _email_replacer(match: re.Match[str]) -> str:
            val = match.group(0)
            token = hmac_pseudonymize(val.lower(), self.salt)
            redactions.append({"type": "EMAIL", "pseudonym": token})
            return f"[REDACTED_EMAIL_{token}]"

        scrubbed = _EMAIL_RE.sub(_email_replacer, scrubbed)

        # 3. Phone Scrubbing
        def _phone_replacer(match: re.Match[str]) -> str:
            val = match.group(0)
            # Normalize digits for consistent pseudonymization
            clean_digits = re.sub(r"\D", "", val)
            token = hmac_pseudonymize(clean_digits, self.salt)
            redactions.append({"type": "PHONE", "pseudonym": token})
            return f"[REDACTED_PHONE_{token}]"

        scrubbed = _PHONE_RE.sub(_phone_replacer, scrubbed)

        # 4. IBAN Scrubbing
        def _iban_replacer(match: re.Match[str]) -> str:
            val = match.group(0)
            clean_iban = re.sub(r"\s+", "", val).upper()
            token = hmac_pseudonymize(clean_iban, self.salt)
            redactions.append({"type": "IBAN", "pseudonym": token})
            return f"[REDACTED_IBAN_{token}]"

        scrubbed = _IBAN_RE.sub(_iban_replacer, scrubbed)

        # 5. Credit Card Scrubbing
        def _card_replacer(match: re.Match[str]) -> str:
            val = match.group(0)
            if validate_luhn_credit_card(val):
                clean_card = re.sub(r"\D", "", val)
                token = hmac_pseudonymize(clean_card, self.salt)
                redactions.append({"type": "CREDIT_CARD", "pseudonym": token})
                return f"[REDACTED_CARD_{token}]"
            return val

        scrubbed = _CREDIT_CARD_RE.sub(_card_replacer, scrubbed)

        return scrubbed, redactions


# Default singleton instance
_default_scrubber = PIIScrubber()


def scrub_pii(text: str) -> str:
    """Convenience functional helper returning scrubbed text."""
    scrubbed, _ = _default_scrubber.scrub(text)
    return scrubbed
