"""Resilience utilities: circuit breaker + retry with exponential backoff.

Patterns from the ChatGPT conversation:
- `tenacity` for transient-failure retries with exponential backoff.
- `aiobreaker` circuit breaker to fast-fail when PostgreSQL is unhealthy.
- A combined `execute_query` helper that wraps both patterns.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import asyncpg
from aiobreaker import CircuitBreaker
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.db.pool import get_pool
from app.observability.metrics import DB_QUERY_DURATION

logger = logging.getLogger(__name__)

# ── Circuit Breaker ──────────────────────────────────────────────────────
db_circuit_breaker = CircuitBreaker(
    fail_max=settings.cb_fail_max,
    timeout_duration=settings.cb_timeout_duration,
)


# ── Retry decorator ─────────────────────────────────────────────────────
_TRANSIENT_EXCEPTIONS = (
    asyncpg.PostgresConnectionError,
    asyncpg.InterfaceError,
    ConnectionRefusedError,
    OSError,
)

db_retry = retry(
    retry=retry_if_exception_type(_TRANSIENT_EXCEPTIONS),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
    reraise=True,
)


# ── Combined helper ─────────────────────────────────────────────────────
@db_retry
@db_circuit_breaker
async def execute_query(
    query: str,
    *args: Any,
    fetch_one: bool = False,
    fetch_all: bool = False,
) -> Any:
    """Execute a query with retry + circuit breaker + Prometheus timing.

    Parameters
    ----------
    query : str
        SQL query string with ``$1, $2, …`` placeholders.
    *args : Any
        Positional bind parameters.
    fetch_one : bool
        Return a single ``asyncpg.Record`` (or ``None``).
    fetch_all : bool
        Return a list of ``asyncpg.Record``.

    Returns
    -------
    Record, list[Record], str, or None depending on flags.
    """
    pool = get_pool()
    start = time.perf_counter()

    try:
        async with pool.acquire() as conn:
            if fetch_one:
                result = await conn.fetchrow(query, *args)
            elif fetch_all:
                result = await conn.fetch(query, *args)
            else:
                result = await conn.execute(query, *args)
        return result
    except Exception:
        logger.exception("Query failed: %s", query[:120])
        raise
    finally:
        elapsed = time.perf_counter() - start
        DB_QUERY_DURATION.observe(elapsed)
