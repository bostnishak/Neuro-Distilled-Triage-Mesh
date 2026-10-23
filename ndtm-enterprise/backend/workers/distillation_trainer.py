"""Asynchronous background worker orchestrating active learning distillation and model hot-swapping."""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select, update

from backend.core.config import get_settings
from backend.core.logging import setup_enterprise_logging
from backend.db.models import ShadowDriftSample
from backend.db.session import async_session_factory
from backend.services.onnx_runtime_engine import ONNXRuntimeEngine
from backend.services.websocket_manager import ws_manager

setup_enterprise_logging("INFO")
logger = logging.getLogger("workers.distillation_trainer")
settings = get_settings()


class DistillationTrainerWorker:
    def __init__(self, onnx_engine: ONNXRuntimeEngine | None = None) -> None:
        self.onnx_engine = onnx_engine or ONNXRuntimeEngine(settings.ONNX_STUDENT_MODEL_PATH)
        self._is_training = False

    async def run_distillation_cycle(self) -> dict[str, Any]:
        """Collects unretrained drift samples, adapts student model, and hot-swaps in memory."""
        if self._is_training:
            return {"status": "in_progress", "message": "Training job already running."}

        self._is_training = True
        start_time = time.perf_counter()
        version = f"v_{int(time.time())}"
        target_onnx = Path(f"distilled_models/student_int8_{version}.onnx")

        await ws_manager.broadcast_event(
            "retraining_progress",
            {"phase": "curating_samples", "version": version, "progress_percent": 15},
        )

        try:
            # 1. Fetch unretrained drift samples
            async with async_session_factory() as session:
                stmt = (
                    select(ShadowDriftSample)
                    .where(ShadowDriftSample.used_for_retraining == False)  # noqa: E712
                    .order_by(ShadowDriftSample.kl_divergence.desc())
                    .limit(500)
                )
                res = await session.execute(stmt)
                samples = res.scalars().all()
                sample_ids = [s.id for s in samples]

            logger.info("Curated %d high-drift samples for active learning distillation.", len(samples))

            await ws_manager.broadcast_event(
                "retraining_progress",
                {"phase": "training_logits", "samples_count": len(samples), "progress_percent": 50},
            )

            # 2. Run distillation and ONNX export in executor
            loop = asyncio.get_running_loop()
            from ml_pipeline.onnx_exporter import export_quantized_onnx_student
            exported_path = await loop.run_in_executor(
                None,
                export_quantized_onnx_student,
                str(target_onnx),
            )

            await ws_manager.broadcast_event(
                "retraining_progress",
                {"phase": "quantizing_int8", "model_path": str(exported_path), "progress_percent": 85},
            )

            # 3. Perform zero-downtime hot-swap in running ONNX session
            hot_swapped = self.onnx_engine.hot_swap_model(str(exported_path))

            # 4. Mark samples as retrained
            if sample_ids:
                async with async_session_factory() as session:
                    async with session.begin():
                        await session.execute(
                            update(ShadowDriftSample)
                            .where(ShadowDriftSample.id.in_(sample_ids))
                            .values(used_for_retraining=True)
                        )

            elapsed = round(time.perf_counter() - start_time, 2)
            logger.info("Distillation cycle %s completed in %.2fs. Hot-swap status: %s", version, elapsed, hot_swapped)

            await ws_manager.broadcast_event(
                "retraining_progress",
                {
                    "phase": "completed",
                    "version": version,
                    "elapsed_seconds": elapsed,
                    "hot_swap_active": hot_swapped,
                    "progress_percent": 100,
                },
            )

            return {
                "status": "completed",
                "version": version,
                "samples_count": len(sample_ids),
                "model_path": str(exported_path),
                "elapsed_seconds": elapsed,
                "hot_swapped": hot_swapped,
            }

        finally:
            self._is_training = False
