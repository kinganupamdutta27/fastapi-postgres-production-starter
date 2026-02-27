"""Async connection pool management using asyncpg.

Design choices (per the ChatGPT conversation):
- Small application-side pool (2–10) because PgBouncer handles multiplexing.
- `max_inactive_connection_lifetime` evicts idle connections quickly.
- `statement_timeout` and `idle_in_transaction_session_timeout` prevent zombie
  transactions and long-running queries.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import asyncpg

from app.core.config import settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Module-level pool reference
_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    """Create and return the asyncpg connection pool."""
    global _pool  # noqa: PLW0603

    if _pool is not None:
        return _pool

    logger.info(
        "Creating asyncpg pool  host=%s  port=%s  db=%s  min=%d  max=%d",
        settings.database_host,
        settings.database_port,
        settings.database_name,
        settings.db_pool_min_size,
        settings.db_pool_max_size,
    )

    async def _connection_init(conn: asyncpg.Connection) -> None:
        """Apply session-level timeouts after each connection is established."""
        await conn.execute(
            f"SET statement_timeout = {settings.db_statement_timeout}"
        )
        await conn.execute(
            f"SET idle_in_transaction_session_timeout = {settings.db_idle_in_transaction_timeout}"
        )

    _pool = await asyncpg.create_pool(
        host=settings.database_host,
        port=settings.database_port,
        user=settings.database_user,
        password=settings.database_password,
        database=settings.database_name,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        max_inactive_connection_lifetime=settings.db_pool_max_inactive_lifetime,
        init=_connection_init,
    )

    logger.info("asyncpg pool created successfully")
    return _pool


async def close_pool() -> None:
    """Gracefully close the asyncpg connection pool."""
    global _pool  # noqa: PLW0603

    if _pool is not None:
        logger.info("Closing asyncpg pool …")
        await _pool.close()
        _pool = None
        logger.info("asyncpg pool closed")


def get_pool() -> asyncpg.Pool:
    """Return the current pool instance. Raises if not initialised."""
    if _pool is None:
        raise RuntimeError("Database pool is not initialised. Call init_pool() first.")
    return _pool
