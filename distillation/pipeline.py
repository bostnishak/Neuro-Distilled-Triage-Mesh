"""Distillation pipeline: Teacher Generation -> Critic Filter -> Student Training -> ONNX INT8 Export.

Features:
1. Synthetic Generation: Uses Teacher LLM to produce realistic diverse samples.
   Includes a rich built-in template seed bank for offline/local generation.
2. Critic Step: Rejects noisy, mislabeled or invalid entity boundary samples.
3. Student Architecture: Multi-task Transformer (Intent classification + Urgency regression + BIO NER).
4. Optimization & Export: ONNX graph export + dynamic INT8 quantization.
5. Calibrator: Extracts centroid embeddings per intent for semantic routing & OOD detection.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel, AutoTokenizer

from core.config import get_settings
from core.embeddings import EmbeddingService
from core.llm import LLMClient
from core.taxonomy import BIO_LABELS, ENTITY_TYPES, FALLBACK_INTENT, INTENT_DESCRIPTIONS, INTENTS

logger = logging.getLogger(__name__)


# =============================================================================
# Synthetic Sample Definitions
# =============================================================================
@dataclass
class TrainingSample:
    text: str
    intent: str
    urgency: float
    entities: list[dict[str, Any]]


# Built-in high-quality seed templates for offline synthetic generation
OFFLINE_SEED_TEMPLATES = [
    # Road damage
    ("Huge pothole on {loc} that almost broke my car axle this morning. Need urgent asphalt repair.", "road_damage", 0.75, [{"type": "LOCATION", "text": "{loc}"}, {"type": "HAZARD", "text": "Huge pothole"}]),
    ("Deep pavement crack expanding across {loc}. It is dangerous for cyclists.", "road_damage", 0.60, [{"type": "LOCATION", "text": "{loc}"}, {"type": "HAZARD", "text": "Deep pavement crack"}]),
    ("The sidewalk on {loc} is uneven and broken concrete caused an elderly person to trip.", "road_damage", 0.70, [{"type": "LOCATION", "text": "{loc}"}, {"type": "HAZARD", "text": "broken concrete"}]),
    # Water leak
    ("Major water main burst at {loc}, flooding the street and basement.", "water_leak", 0.90, [{"type": "LOCATION", "text": "{loc}"}, {"type": "HAZARD", "text": "water main burst"}]),
    ("Sewage overflowing from the manhole near {loc}. Terrible stench and biohazard.", "water_leak", 0.85, [{"type": "LOCATION", "text": "{loc}"}, {"type": "HAZARD", "text": "Sewage overflowing"}]),
    ("Slow pipe leak on the curb outside {loc}. Clean water bubbling up for 2 days.", "water_leak", 0.40, [{"type": "LOCATION", "text": "{loc}"}, {"type": "ASSET", "text": "curb pipe"}]),
    # Power outage
    ("Complete blackout in the neighborhood around {loc}. Streetlights and houses have no power.", "power_outage", 0.85, [{"type": "LOCATION", "text": "{loc}"}]),
    ("Downed power line sparking on the street at {loc}! Stay away!", "power_outage", 0.95, [{"type": "LOCATION", "text": "{loc}"}, {"type": "HAZARD", "text": "Downed power line sparking"}]),
    ("Electrical transformer exploded on the utility pole near {loc}.", "power_outage", 0.90, [{"type": "LOCATION", "text": "{loc}"}, {"type": "ASSET", "text": "Electrical transformer"}]),
    # Streetlight failure
    ("Streetlight pole #42 outside {loc} is completely dark at night.", "streetlight_failure", 0.35, [{"type": "LOCATION", "text": "{loc}"}, {"type": "ASSET", "text": "Streetlight pole #42"}]),
    ("Lamp posts flickering intermittently on {loc}, causing poor visibility.", "streetlight_failure", 0.30, [{"type": "LOCATION", "text": "{loc}"}, {"type": "ASSET", "text": "Lamp posts"}]),
    # Waste management
    ("Illegal dumping of construction debris and chemicals in the alley behind {loc}.", "waste_management", 0.70, [{"type": "LOCATION", "text": "{loc}"}, {"type": "HAZARD", "text": "construction debris and chemicals"}]),
    ("Public garbage bins overflowing on {loc}. Trash scattered all over the walkway.", "waste_management", 0.45, [{"type": "LOCATION", "text": "{loc}"}, {"type": "ASSET", "text": "Public garbage bins"}]),
    # Public safety hazard
    ("Large oak tree branch cracked and hanging precariously over {loc}.", "public_safety_hazard", 0.85, [{"type": "LOCATION", "text": "{loc}"}, {"type": "HAZARD", "text": "tree branch cracked"}]),
    ("Strong smell of natural gas detected near the storm drain on {loc}.", "public_safety_hazard", 0.95, [{"type": "LOCATION", "text": "{loc}"}, {"type": "HAZARD", "text": "Strong smell of natural gas"}]),
    ("Scaffolding tilted dangerously near pedestrian sidewalk at {loc}.", "public_safety_hazard", 0.90, [{"type": "LOCATION", "text": "{loc}"}, {"type": "HAZARD", "text": "Scaffolding tilted"}]),
    # Traffic signal failure
    ("Traffic lights at the intersection of {loc} are completely unpowered. Gridlock and near misses.", "traffic_signal_failure", 0.90, [{"type": "LOCATION", "text": "{loc}"}, {"type": "ASSET", "text": "Traffic lights"}]),
    ("Pedestrian walk sign stuck on don't walk at {loc}.", "traffic_signal_failure", 0.50, [{"type": "LOCATION", "text": "{loc}"}, {"type": "ASSET", "text": "Pedestrian walk sign"}]),
    # IT Service request
    ("Unable to connect to internal VPN after updating laptop OS. Working from home.", "it_service_request", 0.35, [{"type": "ASSET", "text": "VPN"}]),
    ("Server rack in datacenter room 3B is reporting high temperature alarm.", "it_service_request", 0.85, [{"type": "LOCATION", "text": "datacenter room 3B"}, {"type": "ASSET", "text": "Server rack"}]),
    ("Corrupted database backup job on production PostgreSQL cluster.", "it_service_request", 0.80, [{"type": "ASSET", "text": "PostgreSQL cluster"}]),
]

LOCATIONS = [
    "Maple Street and 5th Ave", "Pine Road near Central Hospital", "Oak Boulevard",
    "Sunset Highway mile marker 14", "Elm Court across from the school",
    "Market Square north entrance", "Industrial Parkway Building 4",
    "River Road crossing", "Main Street pedestrian zone", "Civic Center plaza"
]


# =============================================================================
# Generator & Critic
# =============================================================================
class TeacherDataGenerator:
    """Generates synthetic dataset using either Teacher LLM or seed synthesizer."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm

    async def generate_dataset(self, target_count: int = 5000) -> list[TrainingSample]:
        logger.info("Generating %d synthetic samples...", target_count)
        samples: list[TrainingSample] = []

        # If LLM is available, generate batches using prompt expansion
        if self.llm and self.llm.available:
            try:
                samples.extend(await self._generate_with_teacher(target_count))
            except Exception as exc:
                logger.warning("Teacher LLM generation encountered error: %s. Using template engine.", exc)

        # Fill remainder with diversified permutation generator
        needed = target_count - len(samples)
        if needed > 0:
            samples.extend(self._generate_template_samples(needed))

        logger.info("Generated total %d raw samples.", len(samples))
        return samples

    async def _generate_with_teacher(self, count: int) -> list[TrainingSample]:
        samples: list[TrainingSample] = []
        batch_size = 20
        rounds = min(count // batch_size, 10)  # Reasonable cap for online generation

        for r in range(rounds):
            prompt = (
                f"Generate {batch_size} realistic citizen/IT reports across categories:\n"
                f"{list(INTENT_DESCRIPTIONS.keys())}\n"
                "Return a JSON list of objects: [{\"text\": \"...\", \"intent\": \"...\", "
                "\"urgency\": 0.0-1.0, \"entities\": [{\"type\": \"LOCATION\"|\"ASSET\"|\"HAZARD\", \"text\": \"...\"}]}]"
            )
            try:
                assert self.llm is not None
                res = await self.llm.chat_json([{"role": "user", "content": prompt}], temperature=0.7)
                items = res if isinstance(res, list) else res.get("samples") or res.get("data") or []
                for item in items:
                    samples.append(
                        TrainingSample(
                            text=item["text"],
                            intent=item["intent"],
                            urgency=float(item.get("urgency", 0.5)),
                            entities=item.get("entities", []),
                        )
                    )
            except Exception as e:
                logger.warning("Teacher batch failed: %e", e)
                break
        return samples

    def _generate_template_samples(self, count: int) -> list[TrainingSample]:
        generated: list[TrainingSample] = []
        modifiers = [
            "", "Please dispatch a crew immediately.", "Urgent attention required.",
            "Reported by local resident.", "Traffic is backing up because of this.",
            "Water is continuing to pool.", "Happened about 20 minutes ago."
        ]

        while len(generated) < count:
            tmpl, intent, urgency, entities_template = random.choice(OFFLINE_SEED_TEMPLATES)
            loc = random.choice(LOCATIONS)
            text = tmpl.format(loc=loc)
            if random.random() > 0.4:
                text += " " + random.choice(modifiers)

            # Re-align entity texts
            entities = []
            for ent in entities_template:
                ent_text = ent["text"].format(loc=loc)
                if ent_text in text:
                    entities.append({"type": ent["type"], "text": ent_text})

            # Add jitter to urgency
            jittered_urgency = max(0.05, min(0.99, urgency + random.uniform(-0.08, 0.08)))

            generated.append(
                TrainingSample(
                    text=text,
                    intent=intent,
                    urgency=round(jittered_urgency, 3),
                    entities=entities,
                )
            )

        return generated


class CriticFilter:
    """Critic step: validates and removes low-quality, inconsistent or invalid samples."""

    @staticmethod
    def filter(samples: list[TrainingSample]) -> list[TrainingSample]:
        valid_samples: list[TrainingSample] = []
        intent_set = set(INTENTS)
        type_set = set(ENTITY_TYPES)

        for s in samples:
            # 1. Text length check
            if len(s.text.strip()) < 15 or len(s.text.split()) < 3:
                continue

            # 2. Valid intent check
            if s.intent not in intent_set:
                continue

            # 3. Urgency bounds
            if not (0.0 <= s.urgency <= 1.0):
                continue

            # 4. Entity substring alignment
            clean_entities = []
            text_lower = s.text.lower()
            for ent in s.entities:
                etype = ent.get("type", "").upper()
                etext = ent.get("text", "").strip()
                if etype in type_set and etext and etext.lower() in text_lower:
                    clean_entities.append({"type": etype, "text": etext})

            s.entities = clean_entities
            valid_samples.append(s)

        logger.info("Critic filter kept %d / %d samples (%.1f%%)",
                    len(valid_samples), len(samples),
                    (len(valid_samples) / max(len(samples), 1)) * 100)
        return valid_samples


# =============================================================================
# PyTorch Multi-Task Student Model
# =============================================================================
class MultiTaskStudent(nn.Module):
    """Transformer encoder with intent classification, urgency regression, and token NER heads."""

    def __init__(self, base_model_name: str, num_intents: int, num_bio_labels: int) -> None:
        super().__init__()
        self.encoder = AutoModel.from_pretrained(base_model_name)
        hidden_size = self.encoder.config.hidden_size

        # Intent classification head
        self.intent_head = nn.Sequential(
            nn.Dropout(0.2),
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Linear(hidden_size // 2, num_intents),
        )

        # Urgency regression head (0.0 - 1.0)
        self.urgency_head = nn.Sequential(
            nn.Dropout(0.1),
            nn.Linear(hidden_size, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )

        # Entity BIO sequence tagging head
        self.ner_head = nn.Sequential(
            nn.Dropout(0.2),
            nn.Linear(hidden_size, num_bio_labels),
        )

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        outputs = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        sequence_output = outputs.last_hidden_state  # [B, L, H]
        cls_output = sequence_output[:, 0, :]  # [B, H]

        intent_logits = self.intent_head(cls_output)
        urgency = self.urgency_head(cls_output)
        ner_logits = self.ner_head(sequence_output)

        return intent_logits, urgency, ner_logits


# =============================================================================
# Dataset & Trainer
# =============================================================================
class TriageDataset(Dataset):
    def __init__(
        self,
        samples: list[TrainingSample],
        tokenizer: Any,
        max_length: int = 128,
    ) -> None:
        self.samples = samples
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.intent_to_id = {intent: i for i, intent in enumerate(INTENTS)}
        self.bio_to_id = {label: i for i, label in enumerate(BIO_LABELS)}

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        sample = self.samples[idx]
        encoding = self.tokenizer(
            sample.text,
            max_length=self.max_length,
            padding="max_length",
            truncation=True,
            return_offsets_mapping=True,
            return_tensors="pt",
        )

        input_ids = encoding["input_ids"].squeeze(0)
        attention_mask = encoding["attention_mask"].squeeze(0)
        offsets = encoding["offset_mapping"].squeeze(0)

        # Build BIO labels for tokens
        bio_ids = torch.zeros(self.max_length, dtype=torch.long)
        for ent in sample.entities:
            ent_type = ent["type"]
            ent_text = ent["text"]
            start_char = sample.text.lower().find(ent_text.lower())
            if start_char == -1:
                continue
            end_char = start_char + len(ent_text)

            first = True
            for i, (tok_start, tok_end) in enumerate(offsets):
                if tok_start == tok_end or tok_end <= start_char or tok_start >= end_char:
                    continue
                label = f"B-{ent_type}" if first else f"I-{ent_type}"
                bio_ids[i] = self.bio_to_id.get(label, 0)
                first = False

        intent_id = self.intent_to_id.get(sample.intent, self.intent_to_id[FALLBACK_INTENT])

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "intent_label": torch.tensor(intent_id, dtype=torch.long),
            "urgency_label": torch.tensor([sample.urgency], dtype=torch.float32),
            "ner_label": bio_ids,
        }


# =============================================================================
# Export, Quantization & Prototype Calibration
# =============================================================================
def export_and_quantize_onnx(
    model: MultiTaskStudent,
    tokenizer: Any,
    output_dir: Path,
    max_length: int = 128,
) -> Path:
    """Export PyTorch student to ONNX and apply INT8 dynamic quantization."""
    model.eval()
    model.to("cpu")
    output_dir.mkdir(parents=True, exist_ok=True)

    fp32_onnx_path = output_dir / "model.onnx"
    int8_onnx_path = output_dir / "model.int8.onnx"

    dummy_input_ids = torch.ones((1, max_length), dtype=torch.long)
    dummy_mask = torch.ones((1, max_length), dtype=torch.long)

    logger.info("Exporting model to ONNX: %s", fp32_onnx_path)
    torch.onnx.export(
        model,
        (dummy_input_ids, dummy_mask),
        str(fp32_onnx_path),
        input_names=["input_ids", "attention_mask"],
        output_names=["intent_logits", "urgency", "entity_logits"],
        dynamic_axes={
            "input_ids": {0: "batch_size", 1: "sequence_length"},
            "attention_mask": {0: "batch_size", 1: "sequence_length"},
            "intent_logits": {0: "batch_size"},
            "urgency": {0: "batch_size"},
            "entity_logits": {0: "batch_size", 1: "sequence_length"},
        },
        opset_version=14,
        do_constant_folding=True,
    )

    logger.info("Quantizing ONNX model to INT8: %s", int8_onnx_path)
    from onnxruntime.quantization import QuantType, quantize_dynamic

    quantize_dynamic(
        model_input=str(fp32_onnx_path),
        model_output=str(int8_onnx_path),
        weight_type=QuantType.QInt8,
    )

    # Save tokenizer and metadata config
    tokenizer.save_pretrained(str(output_dir))
    config_data = {
        "model_name": "distillmesh-student-int8",
        "onnx_file": "model.int8.onnx",
        "max_length": max_length,
        "intents": list(INTENTS),
        "bio_labels": list(BIO_LABELS),
    }
    (output_dir / "student_config.json").write_text(json.dumps(config_data, indent=2), encoding="utf-8")
    logger.info("Saved student configuration and tokenizer artifacts to %s", output_dir)

    return int8_onnx_path


def calibrate_prototypes(
    samples: list[TrainingSample],
    embedder: EmbeddingService,
    output_dir: Path,
) -> Path:
    """Compute per-intent centroid embeddings and calibrate OOD distance threshold."""
    logger.info("Calibrating semantic prototypes for OOD routing...")
    by_intent: dict[str, list[str]] = {intent: [] for intent in INTENTS}
    for s in samples:
        by_intent[s.intent].append(s.text)

    centroids = []
    min_in_dist_sims: list[float] = []

    for intent in INTENTS:
        texts = by_intent[intent]
        if not texts:
            texts = [INTENT_DESCRIPTIONS[intent]]
        vectors = embedder.encode_sync(texts)
        centroid = vectors.mean(axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm
        centroids.append(centroid)

        # Check self-similarity to compute threshold
        sims = vectors @ centroid
        min_in_dist_sims.append(float(np.percentile(sims, 5)))

    centroids_arr = np.array(centroids, dtype=np.float32)
    # Calibrated OOD threshold is conservative 5th percentile of in-domain similarities
    calibrated_threshold = max(0.50, min(float(np.median(min_in_dist_sims)), 0.85))

    proto_path = output_dir / "prototypes.npz"
    np.savez_compressed(
        proto_path,
        intents=list(INTENTS),
        centroids=centroids_arr,
        threshold=calibrated_threshold,
        embedding_model=embedder.model_name,
    )
    logger.info("Saved calibrated prototypes to %s (threshold=%.3f)", proto_path, calibrated_threshold)
    return proto_path


# =============================================================================
# Main Pipeline Runner
# =============================================================================
async def run_distillation_pipeline(
    sample_count: int = 5000,
    base_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    epochs: int = 3,
    output_dir: Path | None = None,
) -> None:
    """Execute end-to-end distillation."""
    settings = get_settings()
    target_dir = output_dir or Path(settings.student_model_dir)

    logger.info("=== Starting DistillMesh Knowledge Distillation Pipeline ===")
    llm = LLMClient(settings)
    generator = TeacherDataGenerator(llm)

    # 1. Generate & Critic
    raw_samples = await generator.generate_dataset(sample_count)
    clean_samples = CriticFilter.filter(raw_samples)

    # 2. Embedding Prototypes Calibration
    embedder = EmbeddingService(
        model_name=settings.embedding_model,
        expected_dim=settings.embedding_dim,
        device=settings.embedding_device,
        prefix=settings.resolved_embedding_prefix,
    )
    embedder.load()
    calibrate_prototypes(clean_samples, embedder, target_dir)

    # 3. Model Training
    logger.info("Initializing student model from base: %s", base_model)
    tokenizer = AutoTokenizer.from_pretrained(base_model)
    student = MultiTaskStudent(
        base_model_name=base_model,
        num_intents=len(INTENTS),
        num_bio_labels=len(BIO_LABELS),
    )

    dataset = TriageDataset(clean_samples, tokenizer)
    loader = DataLoader(dataset, batch_size=32, shuffle=True)

    optimizer = torch.optim.AdamW(student.parameters(), lr=3e-5)
    loss_intent_fn = nn.CrossEntropyLoss()
    loss_urgency_fn = nn.MSELoss()
    loss_ner_fn = nn.CrossEntropyLoss()

    student.train()
    for epoch in range(epochs):
        total_loss = 0.0
        for batch in loader:
            optimizer.zero_grad()
            i_logits, u_pred, ner_logits = student(batch["input_ids"], batch["attention_mask"])

            loss_i = loss_intent_fn(i_logits, batch["intent_label"])
            loss_u = loss_urgency_fn(u_pred, batch["urgency_label"])
            loss_ner = loss_ner_fn(ner_logits.view(-1, len(BIO_LABELS)), batch["ner_label"].view(-1))

            loss = loss_i + 2.0 * loss_u + loss_ner
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        logger.info("Epoch %d/%d completed | Avg Loss: %.4f", epoch + 1, epochs, total_loss / len(loader))

    # 4. Export & Quantize
    export_and_quantize_onnx(student, tokenizer, target_dir)
    await llm.aclose()
    logger.info("=== DistillMesh Pipeline Successfully Finished! ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DistillMesh Pipeline")
    parser.add_argument("--samples", type=int, default=5000)
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--base-model", type=str, default="sentence-transformers/all-MiniLM-L6-v2")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_distillation_pipeline(sample_count=args.samples, epochs=args.epochs, base_model=args.base_model))
