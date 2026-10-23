"""Pytest fixtures and configuration for NDTM Enterprise test suite."""
from __future__ import annotations

import asyncio
import os
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Set test environment flags
os.environ["ENVIRONMENT"] = "development"
os.environ["DEBUG"] = "true"
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["REDIS_HOST"] = "localhost"

from backend.core.config import get_settings
from backend.core.security import create_access_token
from backend.main import app


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Provides a session-wide event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_settings():
    """Returns application test settings."""
    return get_settings()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Generates valid JWT Authorization headers for test requests."""
    token = create_access_token("test-user-uuid-1234", "ARCHITECT")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def operator_auth_headers() -> dict[str, str]:
    """Generates valid JWT Authorization headers for OPERATOR role."""
    token = create_access_token("test-operator-uuid-5678", "OPERATOR")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_redis():
    """Mock Redis client for rate limiting and semantic caching tests."""
    redis_mock = AsyncMock()
    redis_mock.get.return_value = None
    redis_mock.set.return_value = True
    redis_mock.eval.return_value = [1, 120]  # Rate limit ok
    return redis_mock


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Provides an httpx AsyncClient pointing to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
