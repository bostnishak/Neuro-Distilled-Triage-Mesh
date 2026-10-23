"""Domain and operational exceptions for NDTM Enterprise."""
from __future__ import annotations

from typing import Any


class NDTMException(Exception):
    """Base exception for all NDTM enterprise platform errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AuthenticationError(NDTMException):
    """Raised when authentication credentials or JWT tokens are invalid or expired."""


class AuthorizationError(NDTMException):
    """Raised when an authenticated user lacks required RBAC privileges."""


class QualityGateFailedError(NDTMException):
    """Raised when an uploaded image fails Laplacian sharpness or exposure validation."""

    def __init__(self, reason: str, laplacian_score: float, prompt: str) -> None:
        super().__init__(
            f"Image quality gate failed: {reason}",
            {"reason": reason, "laplacian_score": laplacian_score, "prompt": prompt},
        )
        self.reason = reason
        self.laplacian_score = laplacian_score
        self.prompt = prompt


class PromptInjectionDetectedError(NDTMException):
    """Raised when input matches OWASP LLM prompt injection markers or malicious delimiters."""

    def __init__(self, matched_pattern: str) -> None:
        super().__init__(
            "Prompt injection or delimiter attack detected.",
            {"pattern": matched_pattern},
        )
        self.matched_pattern = matched_pattern


class CircuitBreakerOpenError(NDTMException):
    """Raised when external Teacher LLM calls are blocked due to open circuit breaker."""


class RateLimitExceededError(NDTMException):
    """Raised when sliding-window rate limit is exhausted."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(
            f"Rate limit exceeded. Retry after {retry_after} seconds.",
            {"retry_after": retry_after},
        )
        self.retry_after = retry_after


class SymbolicUnsatError(NDTMException):
    """Raised when Z3 SMT solver determines an unsat contradiction in resource allocation."""

    def __init__(self, unsat_core: list[str]) -> None:
        super().__init__(
            f"Z3 solver returned UNSAT with {len(unsat_core)} core conflicts.",
            {"unsat_core": unsat_core},
        )
        self.unsat_core = unsat_core
