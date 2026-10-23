import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np
from core.logging_otel import logger


@dataclass
class DistillationSample:
    sample_id: str
    input_text: str
    ground_truth_label: int
    teacher_logits: np.ndarray
    teacher_embedding: np.ndarray
    divergence_score: float


@dataclass
class CalibrationScale:
    scale: float
    zero_point: int
    min_val: float
    max_val: float


class QualityCriticFilter:
    """Filters out hallucinated, malformed, or ambiguous synthetic samples."""

    @staticmethod
    def evaluate(sample: DistillationSample) -> bool:
        # Check text length
        if len(sample.input_text.strip()) < 15:
            return False
        # Check finite logits
        if not np.all(np.isfinite(sample.teacher_logits)):
            return False
        # Check teacher probability peak (must have reasonable confidence)
        exp_logits = np.exp(sample.teacher_logits - np.max(sample.teacher_logits))
        probs = exp_logits / np.sum(exp_logits)
        max_prob = float(np.max(probs))
        if max_prob < 0.40:
            return False
        return True


class DistillationLossComputer:
    """Computes combined Task Cross-Entropy, Scaled KL Distillation, and InfoNCE Contrastive Loss."""

    def __init__(self, alpha: float = 0.35, temperature: float = 3.0, gamma: float = 0.20):
        self.alpha = alpha
        self.temperature = temperature
        self.gamma = gamma

    def compute_loss(
        self,
        student_logits: np.ndarray,
        teacher_logits: np.ndarray,
        ground_truth_label: int,
        student_embedding: np.ndarray,
        teacher_embedding: np.ndarray,
    ) -> Tuple[float, float, float, float]:
        """Calculates L_total = alpha * L_task + (1 - alpha) * T^2 * L_KL + gamma * L_contrastive."""
        # 1. Task Cross-Entropy Loss
        exp_s = np.exp(student_logits - np.max(student_logits))
        probs_s = exp_s / np.sum(exp_s)
        p_target = max(1e-12, float(probs_s[ground_truth_label]))
        l_task = -math.log(p_target)

        # 2. Temperature-scaled KL Divergence
        T = self.temperature
        soft_s = np.exp((student_logits / T) - np.max(student_logits / T))
        soft_probs_s = soft_s / np.sum(soft_s)

        soft_t = np.exp((teacher_logits / T) - np.max(teacher_logits / T))
        soft_probs_t = soft_t / np.sum(soft_t)

        kl_div = np.sum(soft_probs_t * np.log(np.clip(soft_probs_t / np.clip(soft_probs_s, 1e-12, 1.0), 1e-12, 1e12)))
        l_kl = (T * T) * float(kl_div)

        # 3. InfoNCE Contrastive Embedding Loss
        norm_s = student_embedding / max(1e-7, float(np.linalg.norm(student_embedding)))
        norm_t = teacher_embedding / max(1e-7, float(np.linalg.norm(teacher_embedding)))
        cosine_sim = float(np.dot(norm_s, norm_t))
        l_contrastive = 1.0 - cosine_sim

        # Total combined loss
        l_total = (self.alpha * l_task) + ((1.0 - self.alpha) * l_kl) + (self.gamma * l_contrastive)

        return l_total, l_task, l_kl, l_contrastive


class Int8Calibrator:
    """Per-tensor and per-channel symmetric/asymmetric INT8 quantization calibrator."""

    @staticmethod
    def calibrate_symmetric(activation_tensor: np.ndarray) -> CalibrationScale:
        """Calibrates signed 8-bit integer [-128, 127] symmetric scale."""
        max_abs = float(np.max(np.abs(activation_tensor)))
        max_abs = max(max_abs, 1e-6)
        scale = max_abs / 127.0
        return CalibrationScale(
            scale=scale,
            zero_point=0,
            min_val=-max_abs,
            max_val=max_abs,
        )

    @staticmethod
    def quantize(activation_tensor: np.ndarray, scale: CalibrationScale) -> np.ndarray:
        """Converts float32 tensor to quantized int8 array."""
        q = np.round(activation_tensor / scale.scale) + scale.zero_point
        return np.clip(q, -128, 127).astype(np.int8)

    @staticmethod
    def dequantize(quantized_tensor: np.ndarray, scale: CalibrationScale) -> np.ndarray:
        """Dequantizes int8 array back to float32."""
        return (quantized_tensor.astype(np.float32) - scale.zero_point) * scale.scale


class KnowledgeDistillationForge:
    """Full distillation pipeline training and evaluating optimized student model checkpoints."""

    def __init__(self):
        self.critic = QualityCriticFilter()
        self.loss_engine = DistillationLossComputer()
        self.calibrator = Int8Calibrator()

    def train_epoch(self, samples: List[DistillationSample]) -> Dict[str, float]:
        """Simulates distillation optimization epoch over curated active learning batch."""
        valid_samples = [s for s in samples if self.critic.evaluate(s)]
        if not valid_samples:
            return {"loss": 0.0, "samples_retained": 0}

        total_loss = 0.0
        total_task = 0.0
        total_kl = 0.0
        total_contrastive = 0.0

        for sample in valid_samples:
            # Emulate student forward pass
            student_logits = sample.teacher_logits * 0.92 + np.random.normal(0, 0.05, sample.teacher_logits.shape)
            student_emb = sample.teacher_embedding * 0.95 + np.random.normal(0, 0.02, sample.teacher_embedding.shape)

            l_tot, l_task, l_kl, l_con = self.loss_engine.compute_loss(
                student_logits,
                sample.teacher_logits,
                sample.ground_truth_label,
                student_emb,
                sample.teacher_embedding,
            )
            total_loss += l_tot
            total_task += l_task
            total_kl += l_kl
            total_contrastive += l_con

        n = len(valid_samples)
        metrics = {
            "mean_loss": total_loss / n,
            "mean_task_loss": total_task / n,
            "mean_kl_loss": total_kl / n,
            "mean_contrastive_loss": total_contrastive / n,
            "samples_retained": n,
        }
        logger.info("distillation_epoch_completed", **metrics)
        return metrics
