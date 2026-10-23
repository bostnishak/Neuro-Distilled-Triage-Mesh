import re
import hmac
import hashlib
from typing import Optional, Tuple
from core.config import settings


def is_valid_tc_kimlik(tc: str) -> bool:
    """Verifies official Turkish Citizen ID (TC Kimlik No) algorithm."""
    if len(tc) != 11 or not tc.isdigit() or tc[0] == "0":
        return False

    digits = [int(d) for d in tc]
    d1_to_9_odd = sum(digits[0:9:2])
    d2_to_8_even = sum(digits[1:8:2])

    digit_10 = ((d1_to_9_odd * 7) - d2_to_8_even) % 10
    if digits[9] != digit_10:
        return False

    digit_11 = sum(digits[:10]) % 10
    if digits[10] != digit_11:
        return False

    return True


def is_valid_luhn(cc_num: str) -> bool:
    """Verifies credit card Luhn checksum."""
    digits = [int(d) for d in cc_num if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = d * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += d
    return checksum % 10 == 0


class PIIScrubber:
    """High-assurance PII detector and deterministic pseudonymizer."""

    # Patterns
    RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    RE_PHONE = re.compile(r"(?:\+90|0)?\s*[5]\d{2}\s*\d{3}\s*\d{2}\s*\d{2}")
    RE_IBAN = re.compile(r"\bTR\d{2}[0-9A-Z]{5}[0-9A-Z]{17}\b", re.IGNORECASE)
    RE_CANDIDATE_TC = re.compile(r"\b[1-9]\d{10}\b")
    RE_CANDIDATE_CC = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")

    @classmethod
    def _hash_token(cls, prefix: str, raw_value: str, salt: Optional[str] = None) -> str:
        key = (salt or getattr(settings, "HMAC_SECRET_SALT", "SOVEREIGN_MESH_HMAC_SALT_KEY_CHANGE_IN_PROD_2026")).encode("utf-8")
        digest = hmac.new(key, raw_value.encode("utf-8"), hashlib.sha256).hexdigest()[:12]
        return f"[{prefix}:{digest}]"

    @classmethod
    def scrub_text(cls, text: str) -> Tuple[str, int]:
        """Scrubs all detected PII entities from text and returns (scrubbed_text, count_redactions)."""
        redactions = 0

        # Scrub Valid TC Kimlik
        def tc_replacer(match: re.Match) -> str:
            nonlocal redactions
            candidate = match.group(0)
            if is_valid_tc_kimlik(candidate):
                redactions += 1
                return cls._hash_token("REDACTED_TC", candidate)
            return candidate

        text = cls.RE_CANDIDATE_TC.sub(tc_replacer, text)

        # Scrub Credit Cards
        def cc_replacer(match: re.Match) -> str:
            nonlocal redactions
            candidate = match.group(0).replace("-", "").replace(" ", "")
            if is_valid_luhn(candidate):
                redactions += 1
                return cls._hash_token("REDACTED_CC", candidate)
            return match.group(0)

        text = cls.RE_CANDIDATE_CC.sub(cc_replacer, text)

        # Scrub Emails
        def email_replacer(match: re.Match) -> str:
            nonlocal redactions
            redactions += 1
            return cls._hash_token("REDACTED_EMAIL", match.group(0))

        text = cls.RE_EMAIL.sub(email_replacer, text)

        # Scrub Turkish Mobile Phones
        def phone_replacer(match: re.Match) -> str:
            nonlocal redactions
            redactions += 1
            clean_digits = re.sub(r"\D", "", match.group(0))
            return cls._hash_token("REDACTED_PHONE", clean_digits)

        text = cls.RE_PHONE.sub(phone_replacer, text)

        # Scrub IBAN
        def iban_replacer(match: re.Match) -> str:
            nonlocal redactions
            redactions += 1
            return cls._hash_token("REDACTED_IBAN", match.group(0).upper())

        text = cls.RE_IBAN.sub(iban_replacer, text)

        return text, redactions
