"""Example CRUD repository for the `items` table.

Demonstrates resilient query execution via the helpers in ``app.db.resilience``.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.db.resilience import execute_query


async def create_item(name: str, description: str | None = None) -> dict[str, Any]:
    """Insert a new item and return its record."""
    item_id = uuid.uuid4()
    row = await execute_query(
        """
        INSERT INTO items (id, name, description)
        VALUES ($1, $2, $3)
        RETURNING id, name, description, created_at, updated_at
        """,
        item_id,
        name,
        description,
        fetch_one=True,
    )
    return dict(row) if row else {}


async def get_item(item_id: uuid.UUID) -> dict[str, Any] | None:
    """Fetch a single item by its primary key."""
    row = await execute_query(
        "SELECT id, name, description, created_at, updated_at FROM items WHERE id = $1",
        item_id,
        fetch_one=True,
    )
    return dict(row) if row else None


async def list_items(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    """Return a paginated list of items."""
    rows = await execute_query(
        "SELECT id, name, description, created_at, updated_at FROM items ORDER BY created_at DESC LIMIT $1 OFFSET $2",
        limit,
        offset,
        fetch_all=True,
    )
    return [dict(r) for r in rows]


async def delete_item(item_id: uuid.UUID) -> bool:
    """Delete an item. Returns True if a row was actually removed."""
    result = await execute_query(
        "DELETE FROM items WHERE id = $1",
        item_id,
    )
    # asyncpg returns "DELETE <count>"
    return result == "DELETE 1"
