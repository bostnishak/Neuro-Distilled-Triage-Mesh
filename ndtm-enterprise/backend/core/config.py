"""Global application settings and environment configuration using Pydantic v2."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # Core
    PROJECT_NAME: str = "ndtm-enterprise"
    ENVIRONMENT: Literal["development", "staging", "production"] = "production"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    API_V2_PREFIX: str = "/api/v2"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    FRONTEND_PORT: int = 3000

    # Security & RBAC
    JWT_SECRET_KEY: str = "9a4f2c8d1e3b7a5f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e1d0c9b8a7f"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    HMAC_SECRET_SALT: str = "7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e"

    # Database & Vector Store
    POSTGRES_USER: str = "ndtm_db_user"
    POSTGRES_PASSWORD: str = "ndtm_db_secure_password_2026!"
    POSTGRES_DB: str = "ndtm_enterprise_db"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = "postgresql+asyncpg://ndtm_db_user:ndtm_db_secure_password_2026!@postgres:5432/ndtm_enterprise_db"
    EMBEDDING_DIMENSION: int = 384

    # Redis Cache & Rate Limiting
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = "ndtm_redis_secure_auth_token_2026!"
    REDIS_URL: str = "redis://:ndtm_redis_secure_auth_token_2026!@redis:6379/0"
    REDIS_CACHE_TTL_SECONDS: int = 86400
    RATE_LIMIT_PER_MINUTE: int = 120
    RATE_LIMIT_BURST_MAX: int = 30

    # RabbitMQ Event Mesh
    RABBITMQ_USER: str = "ndtm_user"
    RABBITMQ_PASSWORD: str = "ndtm_secret_amqp_pass_2026!"
    RABBITMQ_HOST: str = "rabbitmq"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_MGMT_PORT: int = 15672
    RABBITMQ_VHOST: str = "/"
    RABBITMQ_URL: str = "amqp://ndtm_user:ndtm_secret_amqp_pass_2026!@rabbitmq:5672//"
    OUTBOX_POLL_INTERVAL_MS: int = 250

    # Machine Learning & DistillMesh
    ONNX_STUDENT_MODEL_PATH: str = "distilled_models/student_int8.onnx"
    TEACHER_MODEL_BACKEND: str = "heuristic_engine"
    TEACHER_API_KEY: str = "dev_teacher_secret_key"
    ENTROPY_THRESHOLD: float = 0.28
    OOD_SIMILARITY_THRESHOLD: float = 0.75
    TEMPERATURE_CALIBRATION: float = 1.2
    SHADOW_SAMPLE_RATE: float = 0.15

    # Forensics & Quality Gate
    MIN_LAPLACIAN_VARIANCE: float = 85.0
    MIN_PIXEL_INTENSITY: float = 20.0
    MAX_PIXEL_INTENSITY: float = 245.0
    MAX_IMAGE_FILE_SIZE_BYTES: int = 10485760

    # Neuro-Symbolic Z3 Solver
    Z3_TIMEOUT_MS: int = 10000
    MAX_CORRECTION_ITERATIONS: int = 3
    CRITICAL_URGENCY_SLA_MINUTES: int = 45


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Returns singleton cached instance of system settings."""
    return Settings()
