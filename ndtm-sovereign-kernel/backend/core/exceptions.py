from typing import Any, Dict, List, Optional


class NDTMKernelException(Exception):
    """Base domain exception for all NDTM sovereign operating kernel faults."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AuthenticationError(NDTMKernelException):
    """Raised when authentication credentials or cryptographic signatures are invalid."""
    pass


class AuthorizationError(NDTMKernelException):
    """Raised when user or token role lacks required domain permissions."""
    pass


class NotFoundError(NDTMKernelException):
    """Raised when requested entity or resource is not found."""
    pass


class ConflictError(NDTMKernelException):
    """Raised when state transition violates consistency invariants."""
    pass


class GCRAExceededException(NDTMKernelException):
    """Raised when Generic Cell Rate Algorithm leaky bucket rejects traffic."""

    def __init__(self, message: str, retry_after_ms: int):
        super().__init__(message, {"retry_after_ms": retry_after_ms})
        self.retry_after_ms = retry_after_ms


class IdempotencyConflictException(NDTMKernelException):
    """Raised when concurrent request with identical idempotency key is in progress."""
    pass


class CircuitBreakerOpenException(NDTMKernelException):
    """Raised when downstream inference or external dependency circuit is OPEN."""

    def __init__(self, target_service: str, reset_timeout_seconds: float):
        super().__init__(
            f"Circuit breaker is OPEN for {target_service}",
            {"service": target_service, "reset_timeout_seconds": reset_timeout_seconds},
        )
        self.target_service = target_service
        self.reset_timeout_seconds = reset_timeout_seconds


class SmtUnsatException(NDTMKernelException):
    """Raised when Z3 SMT solver finds constraints unsatisfiable."""

    def __init__(self, message: str, unsat_core: List[str]):
        super().__init__(message, {"unsat_core": unsat_core})
        self.unsat_core = unsat_core


class SpeculativeRejectionException(NDTMKernelException):
    """Raised when speculative verification score drops below acceptance threshold."""

    def __init__(self, draft_id: str, rejection_score: float, threshold: float):
        super().__init__(
            f"Speculative draft {draft_id} rejected (score: {rejection_score:.4f} < {threshold:.4f})",
            {"draft_id": draft_id, "score": rejection_score, "threshold": threshold},
        )
        self.draft_id = draft_id
        self.rejection_score = rejection_score


class ByzantineFaultDetectedException(NDTMKernelException):
    """Raised when federated node updates fail Multi-Krum Euclidean distance thresholds."""

    def __init__(self, malformed_node_ids: List[str]):
        super().__init__(
            f"Byzantine fault detected in nodes: {malformed_node_ids}",
            {"byzantine_nodes": malformed_node_ids},
        )
        self.malformed_node_ids = malformed_node_ids


class MerkleTamperDetectedException(NDTMKernelException):
    """Raised when Merkle block SHA-256 state or parent hash chain is violated."""

    def __init__(self, block_height: int, expected_hash: str, computed_hash: str):
        super().__init__(
            f"Merkle audit block tamper detected at height {block_height}",
            {
                "block_height": block_height,
                "expected_hash": expected_hash,
                "computed_hash": computed_hash,
            },
        )
        self.block_height = block_height


class ShmArenaExhaustedException(NDTMKernelException):
    """Raised when all C++ shared memory tensor slots are occupied."""
    pass


class RuleCompilationError(NDTMKernelException):
    """Raised when NDTM-RuleLang fails lexical, syntactic, or type analysis."""

    def __init__(self, message: str, line: int, column: int):
        super().__init__(message, {"line": line, "column": column})
        self.line = line
        self.column = column
