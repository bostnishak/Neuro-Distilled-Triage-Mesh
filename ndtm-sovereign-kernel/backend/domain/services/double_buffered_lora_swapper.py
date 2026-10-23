import os
import threading
from typing import Any, Dict, Optional, Tuple
import numpy as np
from core.config import settings
from core.logging_otel import logger


class LoRASlot:
    """Holds a set of Low-Rank Adaptation (LoRA) projection matrices."""

    def __init__(self, slot_id: str):
        self.slot_id = slot_id
        self.weights: Dict[str, np.ndarray] = {}
        self.version: str = "genesis"
        self.rank: int = 16
        self.alpha: float = 32.0

    def load_weights(self, weights_dict: Dict[str, np.ndarray], version: str, rank: int = 16, alpha: float = 32.0) -> bool:
        """Loads and validates new weight tensor matrices."""
        for k, v in weights_dict.items():
            if not np.all(np.isfinite(v)):
                logger.error("lora_validation_failed_non_finite", key=k)
                return False
            if np.linalg.norm(v) < 1e-7:
                logger.error("lora_validation_failed_zero_norm", key=k)
                return False

        self.weights = weights_dict
        self.version = version
        self.rank = rank
        self.alpha = alpha
        return True


class DoubleBufferedLoRASwapper:
    """Zero-downtime double-buffered LoRA adapter hot-swapper with atomic pointer swap."""

    def __init__(self):
        self._slot_a = LoRASlot("SLOT_A")
        self._slot_b = LoRASlot("SLOT_B")
        self._active_slot_index = 0  # 0 -> Slot A, 1 -> Slot B
        self._lock = threading.Lock()
        self._initialize_default_weights()

    def _initialize_default_weights(self) -> None:
        """Pre-allocates rank-16 identity/scaling matrices for 384-d embeddings."""
        rng = np.random.RandomState(42)
        default_lora = {
            "lora_A": rng.normal(0.0, 0.02, (16, 384)).astype(np.float32),
            "lora_B": np.zeros((384, 16), dtype=np.float32),
        }
        self._slot_a.load_weights(default_lora, version="v1.0.0-genesis")
        self._slot_b.load_weights(default_lora, version="v1.0.0-genesis")

    @property
    def active_slot(self) -> LoRASlot:
        with self._lock:
            return self._slot_a if self._active_slot_index == 0 else self._slot_b

    @property
    def inactive_slot(self) -> LoRASlot:
        with self._lock:
            return self._slot_b if self._active_slot_index == 0 else self._slot_a

    def hot_swap(self, new_weights: Dict[str, np.ndarray], version: str, rank: int = 16, alpha: float = 32.0) -> bool:
        """Loads into background buffer and atomically flips active pointer."""
        with self._lock:
            target_inactive = self._slot_b if self._active_slot_index == 0 else self._slot_a

            success = target_inactive.load_weights(new_weights, version, rank, alpha)
            if not success:
                logger.error("hot_swap_aborted_due_to_validation_failure", version=version)
                return False

            # Atomic switch
            self._active_slot_index = 1 - self._active_slot_index
            logger.info(
                "lora_adapter_hot_swapped_successfully",
                active_slot=target_inactive.slot_id,
                version=version,
            )
            return True

    def apply_lora_projection(self, base_embedding: np.ndarray) -> np.ndarray:
        """Applies LoRA delta W = (alpha / rank) * (B @ A) to embedding vector."""
        slot = self.active_slot
        if "lora_A" in slot.weights and "lora_B" in slot.weights:
            A = slot.weights["lora_A"]  # (16, 384)
            B = slot.weights["lora_B"]  # (384, 16)
            scale = slot.alpha / slot.rank
            delta = scale * (B @ (A @ base_embedding))
            return base_embedding + delta
        return base_embedding
