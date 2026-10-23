"""Fast bootstrapping tool to generate an initial INT8 ONNX student model.

Ensures `models/student/` has all necessary model files, configs, and calibrated
prototypes immediately so the container or local server starts with ONNX fast routing.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from transformers import AutoTokenizer

from core.config import get_settings
from core.embeddings import EmbeddingService
from core.taxonomy import BIO_LABELS, INTENT_DESCRIPTIONS, INTENTS
from distillation.pipeline import MultiTaskStudent, calibrate_prototypes, export_and_quantize_onnx

logger = logging.getLogger(__name__)


def bootstrap_quick_student(output_dir: Path, base_model: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Bootstrapping fast ONNX student model into %s...", output_dir)

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    student = MultiTaskStudent(
        base_model_name=base_model,
        num_intents=len(INTENTS),
        num_bio_labels=len(BIO_LABELS),
    )

    # Export & Quantize
    export_and_quantize_onnx(student, tokenizer, output_dir, max_length=128)

    # Generate baseline prototype index
    settings = get_settings()
    embedder = EmbeddingService(
        model_name=settings.embedding_model,
        expected_dim=settings.embedding_dim,
        device=settings.embedding_device,
        prefix=settings.resolved_embedding_prefix,
    )
    embedder.load()

    # Generate prototypes from seed definitions
    from distillation.pipeline import TeacherDataGenerator
    generator = TeacherDataGenerator()
    seed_samples = generator._generate_template_samples(count=100)
    calibrate_prototypes(seed_samples, embedder, output_dir)

    logger.info("Bootstrap student model and prototypes created successfully!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    bootstrap_quick_student(Path(settings.student_model_dir))
