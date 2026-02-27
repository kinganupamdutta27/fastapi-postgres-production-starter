"""Prometheus metrics definitions.

Instruments:
- DB query latency
- DB pool utilisation
- HTTP request count & latency
"""

from prometheus_client import Counter, Gauge, Histogram

# ── Database ─────────────────────────────────────────────────────────────
DB_QUERY_DURATION = Histogram(
    "db_query_duration_seconds",
    "Time spent executing a single database query",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

DB_POOL_SIZE = Gauge(
    "db_pool_size",
    "Current number of connections in the asyncpg pool",
)

DB_POOL_FREE_SIZE = Gauge(
    "db_pool_free_size",
    "Number of free (idle) connections in the asyncpg pool",
)

# ── HTTP ─────────────────────────────────────────────────────────────────
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
