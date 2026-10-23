"""Temperature-scaled Knowledge Distillation training loop using KL-Divergence and Cross-Entropy."""
from __future__ import annotations

import logging
from typing import Sequence

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger("ml_pipeline.logit_distiller")


class StudentClassifierModel(nn.Module):
    """PyTorch Student Classifier (384 -> 128 -> 8 classes)."""

    def __init__(self, in_features: int = 384, num_classes: int = 8) -> None:
        super().__init__()
        self.fc1 = nn.Linear(in_features, 128)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(0.1)
        self.fc2 = nn.Linear(128, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.dropout(self.relu(self.fc1(x)))
        return self.fc2(h)


class KnowledgeDistillationTrainer:
    """Trains student model with Temperature-Scaled KL Divergence + Cross Entropy:

    L_distill = (1 - alpha) * L_ce(y, sigma(z_s)) + alpha * T^2 * D_kl(sigma(z_t / T) || sigma(z_s / T))
    """

    def __init__(
        self,
        temperature: float = 3.0,
        alpha: float = 0.7,
        learning_rate: float = 1e-3,
        num_epochs: int = 5,
    ) -> None:
        self.temperature = temperature
        self.alpha = alpha
        self.lr = learning_rate
        self.num_epochs = num_epochs

    def train_student(
        self,
        embeddings: Sequence[Sequence[float]],
        labels: Sequence[int],
        teacher_logits: Sequence[Sequence[float]] | None = None,
    ) -> StudentClassifierModel:
        device = torch.device("cpu")
        student = StudentClassifierModel().to(device)
        student.train()

        optimizer = torch.optim.AdamW(student.parameters(), lr=self.lr, weight_decay=1e-4)
        ce_criterion = nn.CrossEntropyLoss()
        kl_criterion = nn.KLDivLoss(reduction="batchmean")

        x_tensor = torch.tensor(embeddings, dtype=torch.float32, device=device)
        y_tensor = torch.tensor(labels, dtype=torch.long, device=device)

        if teacher_logits is not None:
            t_tensor = torch.tensor(teacher_logits, dtype=torch.float32, device=device)
        else:
            # Generate one-hot pseudo-logits if offline without external teacher
            t_tensor = F.one_hot(y_tensor, num_classes=8).float() * 4.0

        num_samples = len(x_tensor)
        batch_size = min(32, max(4, num_samples))

        logger.info(
            "Starting Knowledge Distillation training on %d samples (T=%.1f, alpha=%.2f)...",
            num_samples,
            self.temperature,
            self.alpha,
        )

        for epoch in range(1, self.num_epochs + 1):
            epoch_loss = 0.0
            permutation = torch.randperm(num_samples)

            for i in range(0, num_samples, batch_size):
                indices = permutation[i : i + batch_size]
                batch_x = x_tensor[indices]
                batch_y = y_tensor[indices]
                batch_t = t_tensor[indices]

                optimizer.zero_grad()
                student_logits = student(batch_x)

                # 1. Hard Cross-Entropy Loss
                loss_ce = ce_criterion(student_logits, batch_y)

                # 2. Soft KL-Divergence Loss with Temperature Scaling
                soft_student = F.log_softmax(student_logits / self.temperature, dim=1)
                soft_teacher = F.softmax(batch_t / self.temperature, dim=1)
                loss_kl = kl_criterion(soft_student, soft_teacher) * (self.temperature ** 2)

                # Combined Objective
                total_loss = ((1.0 - self.alpha) * loss_ce) + (self.alpha * loss_kl)
                total_loss.backward()
                optimizer.step()

                epoch_loss += total_loss.item()

            avg_loss = epoch_loss / max(1, num_samples // batch_size)
            logger.info("Epoch %d/%d — Distillation Loss: %.4f", epoch, self.num_epochs, avg_loss)

        student.eval()
        return student
