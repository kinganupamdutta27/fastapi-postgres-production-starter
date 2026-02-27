"""Tests for item CRUD endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

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


MOCK_ITEM = {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Test Widget",
    "description": "A test widget",
    "created_at": "2025-01-01T00:00:00+00:00",
    "updated_at": "2025-01-01T00:00:00+00:00",
}


@pytest.mark.asyncio
async def test_create_item(client: AsyncClient):
    """POST /items/ should create and return a new item."""
    with patch("app.api.routes.repository.create_item", new_callable=AsyncMock, return_value=MOCK_ITEM):
        response = await client.post("/items/", json={"name": "Test Widget", "description": "A test widget"})
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Widget"
        assert "id" in data


@pytest.mark.asyncio
async def test_get_item(client: AsyncClient):
    """GET /items/{id} should return the item."""
    with patch("app.api.routes.repository.get_item", new_callable=AsyncMock, return_value=MOCK_ITEM):
        response = await client.get(f"/items/{MOCK_ITEM['id']}")
        assert response.status_code == 200
        assert response.json()["name"] == "Test Widget"


@pytest.mark.asyncio
async def test_get_item_not_found(client: AsyncClient):
    """GET /items/{id} should return 404 for missing items."""
    with patch("app.api.routes.repository.get_item", new_callable=AsyncMock, return_value=None):
        response = await client.get("/items/550e8400-e29b-41d4-a716-446655440000")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_items(client: AsyncClient):
    """GET /items/ should return a list of items."""
    with patch("app.api.routes.repository.list_items", new_callable=AsyncMock, return_value=[MOCK_ITEM]):
        response = await client.get("/items/")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert len(data["items"]) == 1


@pytest.mark.asyncio
async def test_delete_item(client: AsyncClient):
    """DELETE /items/{id} should return 204 on success."""
    with patch("app.api.routes.repository.delete_item", new_callable=AsyncMock, return_value=True):
        response = await client.delete(f"/items/{MOCK_ITEM['id']}")
        assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_item_not_found(client: AsyncClient):
    """DELETE /items/{id} should return 404 for missing items."""
    with patch("app.api.routes.repository.delete_item", new_callable=AsyncMock, return_value=False):
        response = await client.delete("/items/550e8400-e29b-41d4-a716-446655440000")
        assert response.status_code == 404
