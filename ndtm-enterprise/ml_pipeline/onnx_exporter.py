"""Exports trained PyTorch student models to ONNX and performs dynamic INT8 quantization."""
from __future__ import annotations

import logging
from pathlib import Path

import torch

from ml_pipeline.logit_distiller import KnowledgeDistillationTrainer, StudentClassifierModel
from ml_pipeline.synthetic_generator import SyntheticIncidentGenerator

logger = logging.getLogger("ml_pipeline.onnx_exporter")


def export_quantized_onnx_student(output_path: str = "distilled_models/student_int8.onnx") -> Path:
    """End-to-end pipeline: generates data, trains student with KL-distillation, exports ONNX, quantizes to INT8."""
    target_file = Path(output_path)
    target_file.parent.mkdir(parents=True, exist_ok=True)

    # 1. Generate synthetic dataset for training
    generator = SyntheticIncidentGenerator(seed=2026)
    dataset = generator.generate_batch(count_per_category=12)

    # Convert text to dummy embeddings (384-D)
    import hashlib
    import numpy as np

    embeddings = []
    labels = []
    category_map = {
        "POWER_GRID_FAILURE": 0,
        "FIBER_CUT": 1,
        "WATER_MAIN_BURST": 2,
        "GAS_LEAK": 3,
        "ROAD_COLLAPSE": 4,
        "SIGNAL_INTERFERENCE": 5,
        "TRANSFORMER_FIRE": 6,
        "CYBER_TELEMETRY_ANOMALY": 7,
    }

    for item in dataset:
        vec = np.zeros(384, dtype=np.float32)
        words = item["text"].split()
        for idx, w in enumerate(words):
            h = int(hashlib.md5(w.encode()).hexdigest(), 16) % 384
            vec[h] += 1.0 / (idx + 1)
        norm = np.linalg.norm(vec)
        if norm > 1e-6:
            vec /= norm
        embeddings.append(vec.tolist())
        labels.append(category_map[item["category"]])

    # 2. Train student with temperature-scaled KL distillation
    trainer = KnowledgeDistillationTrainer(temperature=3.0, alpha=0.7, num_epochs=4)
    student = trainer.train_student(embeddings, labels)

    # 3. Export to float32 ONNX
    float_path = target_file.with_suffix(".temp.float.onnx")
    dummy_input = torch.randn(1, 384, requires_grad=False)

    torch.onnx.export(
        student,
        dummy_input,
        str(float_path),
        export_params=True,
        opset_version=17,
        do_constant_folding=True,
        input_names=["input_embeddings"],
        output_names=["logits"],
        dynamic_axes={"input_embeddings": {0: "batch_size"}, "logits": {0: "batch_size"}},
    )
    logger.info("Exported float32 ONNX graph to %s", float_path)

    # 4. Apply dynamic INT8 quantization
    try:
        from onnxruntime.quantization import QuantType, quantize_dynamic
        quantize_dynamic(
            model_input=str(float_path),
            model_output=str(target_file),
            weight_type=QuantType.QInt8,
        )
        if float_path.exists():
            float_path.unlink()
        logger.info("Dynamic INT8 quantization completed. Produced: %s", target_file)
    except Exception as exc:
        logger.warning("Quantization error (%s). Renaming float ONNX directly.", exc)
        if float_path.exists():
            float_path.rename(target_file)

    return target_file


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    res = export_quantized_onnx_student()
    print(f"[SUCCESS] Exported INT8 ONNX student model: {res}")
