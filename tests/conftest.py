"""Pytest configuration and shared fixtures."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_pool_init():
    """Prevent actual DB pool initialization during tests."""
    mock_pool = MagicMock()
    mock_pool.get_size.return_value = 5
    mock_pool.get_idle_size.return_value = 3
    mock_pool.close = AsyncMock()

    with (
        patch("app.db.pool.init_pool", new_callable=AsyncMock, return_value=mock_pool),
        patch("app.db.pool.close_pool", new_callable=AsyncMock),
        patch("app.db.pool._pool", mock_pool),
        patch("app.main._update_pool_gauges", new_callable=AsyncMock),
    ):
        yield
