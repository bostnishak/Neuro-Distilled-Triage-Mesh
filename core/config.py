"""Application configuration loaded from environment variables / `.env`.

All tunables live here so that every service (API, worker, distillation CLI)
reads the exact same, validated configuration.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly typed application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ---- General ---------------------------------------------------------------
    app_name: str = "Neuro-Distilled Triage Mesh"
    environment: str = "development"
    log_level: str = "INFO"
    json_logs: bool = True
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"])

    # ---- PostgreSQL ------------------------------------------------------------
    database_url: str = "postgresql://triage:triage_secret@localhost:5432/triage"
    db_pool_min_size: int = Field(2, ge=1)
    db_pool_max_size: int = Field(10, ge=1)
    db_command_timeout_seconds: float = Field(30.0, gt=0)
    hnsw_ef_search: int = Field(100, ge=10, le=1000)

    # ---- RabbitMQ --------------------------------------------------------------
    rabbitmq_url: str = "amqp://triage:triage_secret@localhost:5672/"
    triage_exchange: str = "triage"
    triage_routing_key: str = "triage.new"
    triage_queue: str = "triage_queue"
    triage_retry_queue: str = "triage_retry"
    triage_dlx: str = "triage.dlx"
    triage_dlq: str = "triage_dlq"
    triage_dead_routing_key: str = "triage.dead"
    triage_retry_delay_ms: int = Field(10_000, ge=100)
    triage_max_retries: int = Field(3, ge=0)
    worker_prefetch: int = Field(8, ge=1)

    # ---- Embeddings ------------------------------------------------------------
    embedding_model: str = "intfloat/multilingual-e5-base"
    embedding_dim: int = 768
    embedding_device: str = "cpu"
    # e5 models expect a "query: " prefix; None => auto-detect from model name.
    embedding_prefix: str | None = None

    # ---- Triage / dedup --------------------------------------------------------
    dedup_similarity_threshold: float = Field(0.88, ge=0.0, le=1.0)
    dedup_radius_km: float = Field(0.5, gt=0)
    upload_dir: str = "/data/uploads"
    max_image_bytes: int = 10 * 1024 * 1024
    min_image_width: int = 320
    min_image_height: int = 240
    blur_threshold: float = 100.0  # variance of Laplacian; lower = blurrier
    min_brightness: float = 25.0
    max_brightness: float = 235.0
    require_image: bool = True
    min_description_chars: int = 20
    min_description_words: int = 4

    # ---- Teacher LLM / VLM (OpenAI-compatible) ---------------------------------
    llm_enabled: bool = False
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr | None = None
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = Field(3, ge=1)
    vlm_enabled: bool = False
    vlm_model: str = "gpt-4o-mini"
    vlm_fail_open: bool = True  # if the VLM is down, accept the report rather than block citizens

    # ---- DistillMesh router ----------------------------------------------------
    student_model_dir: str = "models/student"
    onnx_intra_op_threads: int = Field(2, ge=1)
    router_confidence_threshold: float = Field(0.80, ge=0, le=1)
    router_margin_threshold: float = Field(0.15, ge=0, le=1)
    # None => use the calibrated threshold stored in prototypes.npz.
    router_ood_threshold: float | None = None
    teacher_cost_per_call_usd: float = 0.002

    # ---- Neuro-symbolic engine -------------------------------------------------
    z3_timeout_ms: int = Field(10_000, ge=100)
    symbolic_max_rounds: int = Field(4, ge=1, le=10)

    # ---- Outbox relay ----------------------------------------------------------
    outbox_poll_interval_seconds: float = Field(5.0, gt=0)

    @field_validator("llm_api_key", mode="before")
    @classmethod
    def _empty_key_is_none(cls, value: object) -> object:
        return None if value in ("", None) else value

    @property
    def resolved_embedding_prefix(self) -> str:
        if self.embedding_prefix is not None:
            return self.embedding_prefix
        return "query: " if "e5" in self.embedding_model.lower() else ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached settings instance."""
    return Settings()
