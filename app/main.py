"""FastAPI application entry point.

Sets up:
- Async lifespan for pool init / teardown
- Prometheus middleware & /metrics endpoint
- API + health routers
- Pool gauge background task
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from app.api.health import router as health_router
from app.api.routes import router as items_router
from app.db.pool import close_pool, get_pool, init_pool
from app.observability.metrics import DB_POOL_FREE_SIZE, DB_POOL_SIZE
from app.observability.middleware import PrometheusMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

_pool_gauge_task: asyncio.Task | None = None


async def _update_pool_gauges() -> None:
    """Periodically update Prometheus gauges for the DB pool."""
    while True:
        try:
            pool = get_pool()
            DB_POOL_SIZE.set(pool.get_size())
            DB_POOL_FREE_SIZE.set(pool.get_idle_size())
        except RuntimeError:
            pass
        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle: init pool → yield → close pool."""
    global _pool_gauge_task  # noqa: PLW0603

    # Startup
    await init_pool()
    _pool_gauge_task = asyncio.create_task(_update_pool_gauges())
    logger.info("Application started")

    yield

    # Shutdown
    if _pool_gauge_task:
        _pool_gauge_task.cancel()
    await close_pool()
    logger.info("Application shut down")


app = FastAPI(
    title="FastAPI + PostgreSQL POC",
    description="Industry-standard async FastAPI application with asyncpg, PgBouncer, circuit breakers, and Prometheus observability.",
    version="0.1.0",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────
app.add_middleware(PrometheusMiddleware)

# ── Routers ──────────────────────────────────────────────────────────────
app.include_router(health_router)
app.include_router(items_router)


# ── Prometheus metrics endpoint ──────────────────────────────────────────
@app.get("/metrics", include_in_schema=False)
async def metrics():
    """Expose Prometheus metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
