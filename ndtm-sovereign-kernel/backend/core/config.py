import os
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # Environment
    ENVIRONMENT: str = Field(default="production")
    DEBUG: bool = Field(default=False)
    SERVICE_NAME: str = Field(default="ndtm-sovereign-kernel")
    API_V1_PREFIX: str = Field(default="/api/v1")

    # Direct connection overrides
    DATABASE_URL: Optional[str] = Field(default=None)
    REDIS_URL: Optional[str] = Field(default=None)
    RABBITMQ_URL: Optional[str] = Field(default=None)

    # PostgreSQL & pgvector
    POSTGRES_HOST: str = Field(default="localhost")
    POSTGRES_PORT: int = Field(default=5432)
    POSTGRES_DB: str = Field(default="ndtm_sovereign")
    POSTGRES_USER: str = Field(default="ndtm_admin")
    POSTGRES_PASSWORD: str = Field(default="SovereignKernel2026!SecureKey")
    DATABASE_POOL_SIZE: int = Field(default=20)
    DATABASE_MAX_OVERFLOW: int = Field(default=10)
    DATABASE_POOL_TIMEOUT: float = Field(default=30.0)

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def sync_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Redis Cache & Leaky Bucket
    REDIS_HOST: str = Field(default="localhost")
    REDIS_PORT: int = Field(default=6379)
    REDIS_PASSWORD: str = Field(default="")
    REDIS_DB: int = Field(default=0)

    @property
    def redis_url(self) -> str:
        if self.REDIS_URL:
            return self.REDIS_URL
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # RabbitMQ Event Bus
    RABBITMQ_HOST: str = Field(default="localhost")
    RABBITMQ_PORT: int = Field(default=5672)
    RABBITMQ_USER: str = Field(default="ndtm_mesh")
    RABBITMQ_PASSWORD: str = Field(default="AmqpMesh2026!Distributed")
    RABBITMQ_VHOST: str = Field(default="/")

    @property
    def rabbitmq_url(self) -> str:
        if self.RABBITMQ_URL:
            return self.RABBITMQ_URL
        return (
            f"amqp://{self.RABBITMQ_USER}:{self.RABBITMQ_PASSWORD}@"
            f"{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}/{self.RABBITMQ_VHOST}"
        )

    # Security & Ed25519 Cryptography
    JWT_SECRET_KEY: str = Field(
        default="e7b2354c0e63499499ad97cebbca453f605a2efad09dfa538289416a2d10665b"
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=120)
    ED25519_PRIVATE_KEY_HEX: str = Field(
        default="9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
    )
    ED25519_PUBLIC_KEY_HEX: str = Field(
        default="d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
    )
    HMAC_SECRET_SALT: str = Field(
        default="SOVEREIGN_MESH_HMAC_SALT_KEY_CHANGE_IN_PROD_2026"
    )

    # C++ SHM Zero-Copy
    SHM_ARENA_NAME: str = Field(default="/ndtm_zero_copy_arena")
    SHM_SLOT_COUNT: int = Field(default=64)
    SHM_SLOT_SIZE_BYTES: int = Field(default=1048576)

    ONNX_STUDENT_PATH: str = Field(
        default="/models/student_quantized.onnx" if os.path.exists("/models/student_quantized.onnx") else "models/student_quantized.onnx"
    )
    ONNX_TEACHER_PATH: str = Field(default="models/teacher_bfloat16.onnx")
    ROUTER_ENTROPY_THRESHOLD: float = Field(default=0.45)
    SPECULATIVE_REJECTION_THRESHOLD: float = Field(default=0.75)
    LORA_ACTIVE_WEIGHT_PATH: str = Field(default="models/lora_active.safetensors")

    # Rate Limiting & GCRA
    GCRA_RATE_PER_SECOND: int = Field(default=50)
    GCRA_BURST_CAPACITY: int = Field(default=100)

    # SMT & MaxSMT Verification
    Z3_SOLVER_TIMEOUT_MS: int = Field(default=2500)

    # CORS
    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173"]
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: object) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v  # type: ignore[return-value]
        return ["*"]


settings = Settings()
