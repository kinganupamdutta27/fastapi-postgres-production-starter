"""Tests for health endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_liveness(client: AsyncClient):
    """Liveness probe should always return 200."""
    response = await client.get("/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_readiness_success(client: AsyncClient):
    """Readiness probe should return connected when DB is available."""
    mock_conn = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value=1)

    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=AsyncMock().__aenter__.return_value)

    # Create a proper async context manager for pool.acquire()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    mock_pool.acquire = MagicMock(return_value=cm)

    with patch("app.api.health.get_pool", return_value=mock_pool):
        response = await client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"


@pytest.mark.asyncio
async def test_readiness_failure(client: AsyncClient):
    """Readiness probe should return degraded when DB is unavailable."""
    with patch("app.api.health.get_pool", side_effect=RuntimeError("No pool")):
        response = await client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"] == "disconnected"
