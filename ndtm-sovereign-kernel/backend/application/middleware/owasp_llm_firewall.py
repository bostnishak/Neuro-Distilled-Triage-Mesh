import base64
import re
import unicodedata
from typing import List, Tuple


class OWASPLLMFirewall:
    """OWASP Top 10 for LLM Threat Neutralizer & Prompt Injection Firewall."""

    ZERO_WIDTH_CHARS = re.compile(r"[\u200B-\u200D\uFEFF\u202A-\u202E]")

    INJECTION_PATTERNS: List[re.Pattern] = [
        re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions?", re.IGNORECASE),
        re.compile(r"disregard\s+all\s+(?:rules|guidelines)", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+(?:DAN|unfiltered|jailbroken|an\s+AI\s+without\s+rules)", re.IGNORECASE),
        re.compile(r"system\s*prompt\s*override", re.IGNORECASE),
        re.compile(r"(?:reveal|print|show)\s+(?:your\s+)?system\s+prompt", re.IGNORECASE),
        re.compile(r"<\|im_start\|>|<\|im_end\|>|\[INST\]|\[/INST\]", re.IGNORECASE),
        re.compile(r"act\s+as\s+a\s+malicious\s+hacker", re.IGNORECASE),
    ]

    BASE64_CANDIDATE = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")

    @classmethod
    def sanitize_input(cls, text: str) -> str:
        """Strips zero-width characters and normalizes Unicode to NFKC form."""
        clean = cls.ZERO_WIDTH_CHARS.sub("", text)
        return unicodedata.normalize("NFKC", clean)

    @classmethod
    def inspect(cls, raw_text: str) -> Tuple[bool, List[str]]:
        """Scans input for adversarial injection, smuggling, or jailbreak attacks.

        Returns (is_threat_detected, list_of_threat_reasons).
        """
        threats: List[str] = []
        sanitized = cls.sanitize_input(raw_text)

        # Regex scan on direct text
        for pat in cls.INJECTION_PATTERNS:
            if pat.search(sanitized):
                threats.append(f"INJECTION_SIGNATURE_DETECTED: {pat.pattern}")

        # Check for Base64 payload smuggling
        for b64_match in cls.BASE64_CANDIDATE.findall(sanitized):
            try:
                padded = b64_match + ("=" * ((4 - len(b64_match) % 4) % 4))
                decoded = base64.b64decode(padded).decode("utf-8", errors="ignore")
                for pat in cls.INJECTION_PATTERNS:
                    if pat.search(decoded):
                        threats.append(f"BASE64_SMUGGLED_INJECTION_DETECTED: {pat.pattern}")
            except Exception:
                pass

        return len(threats) > 0, threats
