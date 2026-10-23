import os
import math
import numpy as np
from typing import Any, Dict, List, Optional, Tuple
from core.config import settings
from core.logging_otel import logger

try:
    import onnxruntime as ort
    _HAS_ONNX = True
except ImportError:
    _HAS_ONNX = False


class ModelUnavailableError(RuntimeError):
    """Raised when inference is requested but no trained model is loaded."""


class OnnxRuntimeEngine:
    """Thread-safe ONNX Runtime inference engine for quantized student and teacher models."""

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path or settings.ONNX_STUDENT_PATH
        self._session: Optional[Any] = None
        self._input_names: List[str] = []
        self._output_names: List[str] = []
        self._initialize_session()

    def _initialize_session(self) -> None:
        if not _HAS_ONNX:
            logger.error("onnxruntime_not_installed")
            return

        if os.path.exists(self.model_path):
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 4
            opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            providers = ["CPUExecutionProvider"]
            self._session = ort.InferenceSession(self.model_path, sess_options=opts, providers=providers)
            self._input_names = [inp.name for inp in self._session.get_inputs()]
            self._output_names = [out.name for out in self._session.get_outputs()]
            logger.info("onnx_session_loaded", model_path=self.model_path)
        else:
            logger.error("onnx_model_file_missing", model_path=self.model_path)

    @property
    def is_ready(self) -> bool:
        return self._session is not None

    @staticmethod
    def softmax(logits: np.ndarray) -> np.ndarray:
        exp_vals = np.exp(logits - np.max(logits, axis=-1, keepdims=True))
        return exp_vals / np.sum(exp_vals, axis=-1, keepdims=True)

    def infer_triage(self, text_features: np.ndarray) -> Tuple[str, float, np.ndarray, np.ndarray]:
        """Runs model inference.

        Returns (predicted_category, confidence_score, softmax_probs, 384d_embedding).
        """
        categories = [
            "GAS_PIPELINE",
            "ELECTRICAL_GRID",
            "WATER_MAINS",
            "STRUCTURAL_COLLAPSE",
            "INDUSTRIAL_FIRE",
            "HAZMAT_LEAK",
            "ROAD_HAZARD",
            "CIVIL_DEFENSE",
        ]

        if self._session is None:
            raise ModelUnavailableError(
                f"No trained model loaded from '{self.model_path}'. Refusing to fabricate a triage result."
            )

        inp = text_features.astype(np.float32)
        if inp.ndim == 1:
            inp = np.expand_dims(inp, axis=0)
        feed = {self._input_names[0]: inp}
        outputs = self._session.run(self._output_names, feed)
        logits = outputs[0][0]
        embedding = outputs[1][0] if len(outputs) > 1 else np.zeros(384, dtype=np.float32)

        probs = self.softmax(logits)
        pred_idx = int(np.argmax(probs))
        confidence = float(probs[pred_idx])
        predicted_cat = categories[pred_idx % len(categories)]

        return predicted_cat, confidence, probs, embedding
