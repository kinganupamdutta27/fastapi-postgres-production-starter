"""Health check endpoints — liveness and readiness probes."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.db.pool import get_pool

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/")
async def liveness():
    """Liveness probe — always returns OK if the process is running."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness():
    """Readiness probe — verifies database connectivity."""
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ok", "database": "connected"}
    except Exception:
        logger.exception("Readiness check failed")
        return {"status": "degraded", "database": "disconnected"}
