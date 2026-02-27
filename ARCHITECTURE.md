# Architecture Documentation

> **fastapi-postgres-production-starter** — A production-ready async FastAPI + PostgreSQL starter with PgBouncer connection pooling, circuit breaker & retry resilience, Prometheus observability, and Docker Compose orchestration. A complete blueprint for building scalable Python APIs.

## 📚 Detailed Documentation

For in-depth guides tailored to different experience levels, see the [docs/](docs/README.md) folder:

| Document | Audience | Topic |
|---|---|---|
| [Getting Started](docs/01-GETTING_STARTED.md) | 🟢 Beginner | Setup, running, first API call |
| [Project Structure](docs/02-PROJECT_STRUCTURE.md) | 🟢 Beginner | File-by-file codebase walkthrough |
| [API Reference](docs/03-API_REFERENCE.md) | 🟡 Intermediate | All endpoints with examples |
| [Database Deep Dive](docs/04-DATABASE.md) | 🟡 Intermediate | PostgreSQL, asyncpg, PgBouncer |
| [Resilience Patterns](docs/05-RESILIENCE.md) | 🟡 Intermediate | Circuit breaker, retry logic |
| [Observability](docs/06-OBSERVABILITY.md) | 🔴 Advanced | Prometheus metrics & monitoring |
| [Configuration](docs/07-CONFIGURATION.md) | 🔴 Advanced | Environment variables & tuning |
| [Deployment](docs/08-DEPLOYMENT.md) | 🔴 Advanced | Docker, CI/CD, production checklist |

---

## Table of Contents

- [High-Level Architecture](#high-level-architecture)
- [System Components](#system-components)
  - [FastAPI Application](#1-fastapi-application)
  - [PgBouncer — Connection Pooler](#2-pgbouncer--connection-pooler)
  - [PostgreSQL Database](#3-postgresql-database)
  - [Prometheus — Metrics & Monitoring](#4-prometheus--metrics--monitoring)
- [Application Internals](#application-internals)
  - [Project Structure](#project-structure)
  - [Configuration Management](#configuration-management)
  - [Database Layer](#database-layer)
  - [Resilience Patterns](#resilience-patterns)
  - [Observability Layer](#observability-layer)
  - [API Layer](#api-layer)
  - [Application Lifecycle](#application-lifecycle)
- [Data Model](#data-model)
- [Infrastructure & Deployment](#infrastructure--deployment)
  - [Docker Multi-Stage Build](#docker-multi-stage-build)
  - [Docker Compose Orchestration](#docker-compose-orchestration)
  - [Database Migrations](#database-migrations)
- [Request Flow](#request-flow)
- [Configuration Reference](#configuration-reference)
- [Technology Stack Summary](#technology-stack-summary)

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Docker Compose Network                       │
│                                                                     │
│  ┌──────────┐    ┌───────────┐    ┌────────────┐    ┌────────────┐ │
│  │  Client   │───▶│  FastAPI   │───▶│  PgBouncer  │───▶│ PostgreSQL │ │
│  │ (Browser/ │    │  App:8000  │    │    :6432    │    │   :5432    │ │
│  │   cURL)   │    │            │    │ (tx pool)   │    │ (16-alpine)│ │
│  └──────────┘    └─────┬──────┘    └────────────┘    └────────────┘ │
│                        │                                             │
│                        │  /metrics                                   │
│                        ▼                                             │
│                  ┌────────────┐                                      │
│                  │ Prometheus  │                                      │
│                  │   :9090     │                                      │
│                  └────────────┘                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**Data flow:**
1. Clients send HTTP requests to the FastAPI app on port `8000`.
2. The app connects to PostgreSQL through PgBouncer (port `6432`) for connection multiplexing.
3. Prometheus scrapes the `/metrics` endpoint every 15 seconds for observability data.

---

## System Components

### 1. FastAPI Application

| Property       | Value                                          |
|----------------|------------------------------------------------|
| **Framework**  | FastAPI (async, OpenAPI 3.1)                   |
| **Server**     | Uvicorn (ASGI, with uvloop for performance)    |
| **Port**       | 8000                                           |
| **Python**     | 3.12                                           |

**Why FastAPI?**
- **Native async support** — Built on Starlette and Pydantic, FastAPI is fully async-first, making it ideal for I/O-bound workloads like database queries.
- **Automatic API documentation** — Generates interactive Swagger UI (`/docs`) and ReDoc (`/redoc`) from type hints.
- **Pydantic validation** — Request/response schemas are validated at the framework level with detailed error messages (422 responses).
- **High performance** — One of the fastest Python web frameworks, leveraging `uvloop` and `httptools` via Uvicorn.

---

### 2. PgBouncer — Connection Pooler

| Property              | Value                  |
|-----------------------|------------------------|
| **Image**             | `edoburu/pgbouncer`    |
| **Pool Mode**         | `transaction`          |
| **Listen Port**       | 6432                   |
| **Default Pool Size** | 20                     |
| **Max Client Conns**  | 200                    |

**Why PgBouncer?**

PostgreSQL creates a **separate OS process per connection**, each consuming ~5–10 MB of RAM. Without a pooler, an application under load can easily exhaust PostgreSQL's `max_connections` limit (default: 100).

PgBouncer solves this by **multiplexing** many client connections onto a smaller number of real PostgreSQL connections:

```
200 app connections  →  PgBouncer (20 real connections)  →  PostgreSQL
```

**Why transaction pooling mode?**

In `transaction` mode, a PostgreSQL connection is assigned to a client only for the duration of a single transaction. Between transactions, the connection is returned to the pool and can be reused by other clients. This provides:

- **Maximum connection reuse** — Idle application connections don't hold open PostgreSQL backends.
- **Safe with asyncpg** — asyncpg uses simple queries compatible with transaction pooling.
- **Protection against connection storms** — Even if the app scales to many instances, PostgreSQL only sees a fixed number of backend connections.

**Pool sizing rationale:**
- `default_pool_size = 20` — Enough for typical concurrent query load.
- `min_pool_size = 5` — Pre-warmed connections avoid cold-start latency.
- `reserve_pool_size = 5` — Extra connections for burst traffic.
- `max_client_conn = 200` — Upper limit of simultaneous app-side connections.
- `server_idle_timeout = 600` — Reclaim idle backend connections after 10 minutes.

---

### 3. PostgreSQL Database

| Property       | Value                   |
|----------------|-------------------------|
| **Image**      | `postgres:16-alpine`    |
| **Port**       | 5432                    |
| **Database**   | `app_db`                |
| **User**       | `app_user`              |

**Why PostgreSQL 16?**
- Mature, battle-tested RDBMS with excellent JSON support, full-text search, and extensibility.
- Alpine variant keeps the Docker image lightweight (~230 MB vs ~430 MB for full image).
- Native UUID support via `uuid-ossp` extension, used for primary keys.

**Health checks** are configured with `pg_isready` to ensure the database is accepting connections before dependent services start.

---

### 4. Prometheus — Metrics & Monitoring

| Property           | Value              |
|--------------------|--------------------|
| **Image**          | `prom/prometheus`  |
| **Port**           | 9090               |
| **Scrape Interval**| 15 seconds         |

**Why Prometheus?**
- Industry-standard time-series database for metrics and alerting.
- Pull-based model — Prometheus scrapes the app's `/metrics` endpoint, requiring no push infrastructure.
- Native integration with Grafana for dashboarding.

**Configuration** (`infra/prometheus.yml`):
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: "fastapi-app"
    metrics_path: /metrics
    static_configs:
      - targets: ["app:8000"]
        labels:
          instance: "fastapi-poc"
```

---

## Application Internals

### Project Structure

```
app/
├── __init__.py
├── main.py                  # Application entry point & lifespan
├── api/
│   ├── __init__.py
│   ├── health.py            # Health check endpoints
│   ├── routes.py            # Item CRUD REST endpoints
│   └── schemas.py           # Pydantic request/response models
├── core/
│   └── config.py            # Centralized configuration (env vars)
├── db/
│   ├── __init__.py
│   ├── pool.py              # asyncpg connection pool management
│   ├── repository.py        # Data access layer (CRUD queries)
│   └── resilience.py        # Circuit breaker + retry logic
└── observability/
    ├── __init__.py
    ├── metrics.py            # Prometheus metric definitions
    └── middleware.py         # HTTP request instrumentation

migrations/
├── env.py                   # Alembic environment config
├── script.py.mako           # Migration template
└── versions/
    └── 001_create_items.py  # Initial schema migration

infra/
├── pgbouncer.ini            # PgBouncer configuration
├── prometheus.yml           # Prometheus scrape config
└── userlist.txt             # PgBouncer auth file

tests/
├── conftest.py              # Shared test fixtures
├── test_health.py           # Health endpoint tests
└── test_items.py            # Item CRUD endpoint tests
```

---

### Configuration Management

**File:** `app/core/config.py`

Uses **pydantic-settings** to load configuration from environment variables (or `.env` file) with full type validation and defaults.

**Why pydantic-settings?**
- **Type-safe** — Each config value is validated against its Python type at startup. Invalid configs fail fast with clear error messages.
- **12-Factor App compliance** — All config comes from environment variables, making the app portable across environments (dev, staging, production).
- **`.env` file support** — Local development uses a `.env` file; production uses real environment variables.
- **Singleton pattern** — A single `settings = Settings()` instance is imported throughout the app, ensuring consistent configuration.

**Configuration groups:**

| Group             | Variables                                  | Purpose                                  |
|-------------------|--------------------------------------------|------------------------------------------|
| App               | `APP_HOST`, `APP_PORT`, `APP_ENV`          | Server binding and environment mode      |
| Database          | `DATABASE_HOST`, `DATABASE_PORT`, etc.     | PostgreSQL/PgBouncer connection details  |
| Connection Pool   | `DB_POOL_MIN_SIZE`, `DB_POOL_MAX_SIZE`     | asyncpg pool sizing                      |
| Timeouts          | `DB_STATEMENT_TIMEOUT`, `DB_IDLE_IN_TRANSACTION_TIMEOUT` | Query and transaction safety limits |
| Circuit Breaker   | `CB_FAIL_MAX`, `CB_TIMEOUT_DURATION`       | Resilience tuning                        |

---

### Database Layer

#### Connection Pool (`app/db/pool.py`)

Uses **asyncpg** — the fastest async PostgreSQL driver for Python — to manage a connection pool.

**Why asyncpg (not SQLAlchemy)?**
- **Raw performance** — asyncpg is a pure C implementation, ~3x faster than psycopg2 and SQLAlchemy for simple queries.
- **Native async** — Built for `asyncio` from the ground up, no thread-pool hacks.
- **Binary protocol** — Communicates with PostgreSQL using the efficient binary wire protocol.
- **Perfect for microservices** — When you don't need an ORM, asyncpg gives maximum speed with minimal overhead.

**Pool lifecycle:**
1. `init_pool()` — Creates the pool during app startup. Applies session-level timeouts (`statement_timeout`, `idle_in_transaction_session_timeout`) via an `init` callback on each connection.
2. `get_pool()` — Returns the singleton pool instance for query execution.
3. `close_pool()` — Gracefully closes all connections during app shutdown.

**Why a small app-side pool (2–10)?**
Since PgBouncer already handles connection multiplexing with a larger pool (20), the application-side pool is intentionally small:
- `min_size = 2` — Keeps at least 2 connections warm to avoid cold-start latency.
- `max_size = 10` — Caps the application's demand on PgBouncer.
- `max_inactive_connection_lifetime = 300s` — Evicts idle connections after 5 minutes, freeing PgBouncer slots.

**Two-tier pooling architecture:**
```
App Pool (2–10 conns)  →  PgBouncer Pool (20 conns)  →  PostgreSQL (100 max_connections)
```

This design allows **multiple app instances** to share PgBouncer without overwhelming PostgreSQL.

---

#### Repository Pattern (`app/db/repository.py`)

Implements the **repository pattern** — all database queries are centralized in dedicated functions, keeping the API routes thin and testable.

**Why the repository pattern?**
- **Separation of concerns** — SQL logic lives separately from HTTP handling.
- **Testability** — Repository functions can be mocked in unit tests without HTTP overhead.
- **Reusability** — The same query function can be called from multiple routes or background tasks.

**CRUD operations:**
| Function       | SQL                          | Returns           |
|----------------|------------------------------|--------------------|
| `create_item`  | `INSERT ... RETURNING`       | Created record     |
| `get_item`     | `SELECT ... WHERE id = $1`   | Single record      |
| `list_items`   | `SELECT ... LIMIT ... OFFSET`| Paginated list     |
| `delete_item`  | `DELETE ... WHERE id = $1`   | Boolean (deleted?) |

All queries go through the `execute_query` resilience wrapper (see below).

---

### Resilience Patterns

**File:** `app/db/resilience.py`

Implements two critical resilience patterns to handle database failures gracefully:

#### Circuit Breaker (aiobreaker)

**What it does:** Monitors the failure rate of database queries. If failures exceed a threshold, the circuit "opens" and immediately rejects new queries for a cooldown period — preventing a failing database from being hammered with requests.

**Configuration:**
- `fail_max = 5` — Circuit opens after 5 consecutive failures.
- `timeout_duration = 30s` — After 30 seconds, the circuit moves to "half-open" state and allows one test query.

**State machine:**
```
CLOSED  ──(5 failures)──▶  OPEN  ──(30s timeout)──▶  HALF-OPEN
   ▲                                                       │
   └──────────────(success)────────────────────────────────┘
```

**Why aiobreaker?**
- Purpose-built for `asyncio` applications.
- Lightweight — no external dependencies.
- Prevents cascade failures when PostgreSQL or PgBouncer goes down.

#### Retry with Exponential Backoff (tenacity)

**What it does:** Automatically retries failed queries for transient errors (network blips, momentary connection loss) with increasing delays between attempts.

**Configuration:**
- **Retried exceptions:** `PostgresConnectionError`, `InterfaceError`, `ConnectionRefusedError`, `OSError`
- **Max attempts:** 3
- **Backoff:** Exponential (0.5s → 1s → 2s, capped at 5s)

**Why tenacity?**
- Feature-rich retry library — supports exponential backoff, jitter, custom predicates, and reraise.
- Native `asyncio` support.
- Composable with decorators — can be stacked with the circuit breaker.

#### Combined Execution — `execute_query()`

Both patterns are combined into a single `execute_query()` function that wraps every database call:

```python
@db_retry                  # Layer 1: Retry transient failures (3 attempts)
@db_circuit_breaker        # Layer 2: Fast-fail if DB is down
async def execute_query(query, *args, fetch_one=False, fetch_all=False):
    # Layer 3: Prometheus timing
    pool = get_pool()
    start = time.perf_counter()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(query, *args)  # or fetch/execute
    DB_QUERY_DURATION.observe(time.perf_counter() - start)
    return result
```

**Execution order for a failing query:**
1. `execute_query()` is called.
2. Circuit breaker checks state — if OPEN, raises `CircuitBreakerError` immediately.
3. If CLOSED, the query executes.
4. If it fails with a transient error, tenacity retries up to 3 times with exponential backoff.
5. If all retries fail, the circuit breaker records the failure (incrementing the failure counter).
6. After 5 such failed calls, the circuit opens for 30 seconds.

---

### Observability Layer

#### Metrics Definitions (`app/observability/metrics.py`)

Defines **5 Prometheus instruments** covering both database and HTTP performance:

| Metric                          | Type      | Labels                   | Purpose                          |
|---------------------------------|-----------|--------------------------|----------------------------------|
| `db_query_duration_seconds`     | Histogram | —                        | Query latency distribution       |
| `db_pool_size`                  | Gauge     | —                        | Current pool connection count    |
| `db_pool_free_size`             | Gauge     | —                        | Idle connections in pool         |
| `http_requests_total`           | Counter   | method, path, status     | Request throughput by endpoint   |
| `http_request_duration_seconds` | Histogram | method, path             | Request latency by endpoint      |

**Histogram buckets** are tuned for a database-backed API:
- DB queries: 5ms → 5s (10 buckets)
- HTTP requests: 10ms → 10s (10 buckets)

#### Prometheus Middleware (`app/observability/middleware.py`)

A Starlette `BaseHTTPMiddleware` that automatically instruments **every HTTP request** with:
- `http_requests_total` counter (method, path, status code)
- `http_request_duration_seconds` histogram (method, path)

The `/metrics` endpoint itself is excluded to avoid self-referential instrumentation.

#### Pool Gauge Background Task

A background `asyncio.Task` runs every 5 seconds during the app's lifetime, updating `db_pool_size` and `db_pool_free_size` gauges with live pool statistics.

---

### API Layer

#### Health Endpoints (`app/api/health.py`)

| Endpoint        | Method | Purpose                                              |
|-----------------|--------|------------------------------------------------------|
| `/health/`      | GET    | **Liveness probe** — returns OK if the process runs  |
| `/health/ready` | GET    | **Readiness probe** — verifies database connectivity |

**Why two separate probes?**
- **Kubernetes patterns** — Liveness probes tell the orchestrator the container is alive. Readiness probes indicate it can serve traffic. A container can be alive but not ready (e.g., during migration).
- The readiness probe executes `SELECT 1` through the full connection pool stack, validating end-to-end connectivity.

#### Items CRUD (`app/api/routes.py`)

| Endpoint            | Method | Status  | Description                    |
|---------------------|--------|---------|--------------------------------|
| `/items/`           | POST   | 201     | Create a new item              |
| `/items/{item_id}`  | GET    | 200/404 | Retrieve item by UUID          |
| `/items/`           | GET    | 200     | List items with pagination     |
| `/items/{item_id}`  | DELETE | 204/404 | Delete item by UUID            |

**Features:**
- **UUID primary keys** — Globally unique, no sequential guessing, safe for distributed systems.
- **Pagination** — `limit` (1–200, default 50) and `offset` query parameters.
- **Validation** — Pydantic enforces `name` (1–255 chars, required), `description` (max 2000 chars, optional).
- **Proper HTTP status codes** — 201 for creation, 204 for deletion, 404 for missing resources, 422 for validation errors.

#### Schemas (`app/api/schemas.py`)

| Schema             | Purpose                    | Fields                                        |
|--------------------|----------------------------|-----------------------------------------------|
| `ItemCreate`       | POST request body          | `name` (required), `description` (optional)   |
| `ItemResponse`     | Single item response       | `id`, `name`, `description`, `created_at`, `updated_at` |
| `ItemListResponse` | Paginated list response    | `items[]`, `count`                            |

---

### Application Lifecycle

**File:** `app/main.py`

The FastAPI app uses an **async context manager lifespan** to manage startup and shutdown:

```
STARTUP                                    SHUTDOWN
   │                                          │
   ├─ init_pool()          (create pool)      ├─ cancel pool gauge task
   ├─ start pool gauge     (background task)  └─ close_pool()  (drain & close)
   └─ yield (app serves requests)
```

**Why lifespan over events?**
- FastAPI's `lifespan` async context manager is the modern replacement for the deprecated `@app.on_event("startup")` pattern.
- Guarantees cleanup code runs even on crashes (via `finally` in the context manager).

---

## Data Model

### `items` Table

```sql
CREATE TABLE items (
    id          UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(255) NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_items_created_at ON items (created_at);
```

**Design decisions:**
- **UUID v4 primary key** — Avoids sequential IDs (security), works across distributed systems, no sequence contention.
- **Server-generated defaults** — `created_at` and `updated_at` are set by PostgreSQL, not the application, ensuring consistency.
- **Timezone-aware timestamps** — `TIMESTAMPTZ` stores UTC, avoiding timezone bugs.
- **Index on `created_at`** — Optimizes the `ORDER BY created_at DESC` used in list queries.

---

## Infrastructure & Deployment

### Docker Multi-Stage Build

**File:** `Dockerfile`

```dockerfile
# Stage 1: Builder — installs dependencies
FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Stage 2: Runtime — minimal image
FROM python:3.12-slim
COPY --from=builder /usr/local/lib/python3.12/site-packages ...
COPY app/ migrations/ alembic.ini entrypoint.sh ./
USER appuser  # Non-root!
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Why multi-stage?**
- **Smaller image** — Build tools (pip, setuptools, compilers) are discarded. Final image contains only runtime dependencies.
- **Security** — Runs as a non-root `appuser`.
- **Reproducibility** — Dependencies are installed from `pyproject.toml`, not a requirements file, ensuring consistency.

### Docker Compose Orchestration

**File:** `docker-compose.yml`

**Service dependency chain:**
```
PostgreSQL (healthcheck: pg_isready)
    └─▶ PgBouncer (healthcheck: port 6432)
            └─▶ FastAPI App (runs migrations → starts server)
                    └─▶ Prometheus (scrapes /metrics)
```

**Key design decisions:**
- **Health-check gating** — Each service waits for its dependency to pass a health check before starting. This prevents race conditions during startup.
- **`restart: on-failure`** — The app container auto-restarts if it crashes, providing basic self-healing.
- **Named volume** (`pgdata`) — PostgreSQL data persists across container restarts.

### Database Migrations

**Tool:** Alembic

**File:** `migrations/env.py`

Alembic manages schema changes with versioned migration scripts. The `entrypoint.sh` script runs `alembic upgrade head` before starting the application, ensuring the database schema is always up-to-date.

**Migration flow:**
```
Container starts → entrypoint.sh → alembic upgrade head → uvicorn starts
```

**Why Alembic?**
- Industry-standard migration tool for Python/SQLAlchemy.
- Supports both online (connected) and offline (SQL script) modes.
- Version-controlled migrations enable safe rollbacks.

---

## Request Flow

Here's the complete journey of a `POST /items/` request:

```
Client                 FastAPI App                    PgBouncer           PostgreSQL
  │                        │                              │                    │
  │──POST /items/──────▶   │                              │                    │
  │                        │                              │                    │
  │                    PrometheusMiddleware                │                    │
  │                    (start timer)                       │                    │
  │                        │                              │                    │
  │                    Pydantic validates                  │                    │
  │                    ItemCreate schema                   │                    │
  │                        │                              │                    │
  │                    routes.create_item()                │                    │
  │                        │                              │                    │
  │                    repository.create_item()            │                    │
  │                        │                              │                    │
  │                    execute_query()                     │                    │
  │                    ├─ circuit breaker check            │                    │
  │                    ├─ pool.acquire()───────────▶  get connection  ─────▶  │
  │                    ├─ INSERT INTO items ...                   ─────▶  execute
  │                    ├─ RETURNING ... ◀──────────────────────────────◀  result
  │                    ├─ pool.release()                   │                    │
  │                    └─ DB_QUERY_DURATION.observe()      │                    │
  │                        │                              │                    │
  │                    PrometheusMiddleware                │                    │
  │                    (record latency + count)            │                    │
  │                        │                              │                    │
  │◀──201 Created──────    │                              │                    │
```

---

## Configuration Reference

| Variable                         | Default      | Description                                 |
|----------------------------------|--------------|---------------------------------------------|
| `DATABASE_HOST`                  | `localhost`  | PostgreSQL/PgBouncer hostname               |
| `DATABASE_PORT`                  | `6432`       | PgBouncer port                              |
| `DATABASE_USER`                  | `app_user`   | Database username                           |
| `DATABASE_PASSWORD`              | `app_secret` | Database password                           |
| `DATABASE_NAME`                  | `app_db`     | Database name                               |
| `DB_POOL_MIN_SIZE`              | `2`          | Minimum connections in app pool             |
| `DB_POOL_MAX_SIZE`              | `10`         | Maximum connections in app pool             |
| `DB_POOL_MAX_INACTIVE_LIFETIME` | `300`        | Seconds before idle connections are evicted  |
| `DB_STATEMENT_TIMEOUT`          | `5000`       | Max query execution time (ms)               |
| `DB_IDLE_IN_TRANSACTION_TIMEOUT`| `10000`      | Max idle time in a transaction (ms)         |
| `CB_FAIL_MAX`                    | `5`          | Failures before circuit breaker opens       |
| `CB_TIMEOUT_DURATION`            | `30`         | Seconds in open state before half-open      |
| `APP_HOST`                       | `0.0.0.0`   | Server bind address                         |
| `APP_PORT`                       | `8000`       | Server bind port                            |
| `APP_ENV`                        | `development`| Environment identifier                      |

---

## Technology Stack Summary

| Layer            | Technology         | Version   | Role                                  |
|------------------|--------------------|-----------|---------------------------------------|
| Web Framework    | FastAPI            | ≥0.115    | Async HTTP routing & validation       |
| ASGI Server      | Uvicorn            | ≥0.32     | High-performance ASGI server          |
| DB Driver        | asyncpg            | ≥0.30     | Async PostgreSQL binary protocol      |
| Connection Pool  | PgBouncer          | latest    | Server-side connection multiplexing   |
| Database         | PostgreSQL         | 16-alpine | Relational data store                 |
| Configuration    | pydantic-settings  | ≥2.6      | Type-safe environment config          |
| Migrations       | Alembic            | ≥1.14     | Schema version control                |
| Circuit Breaker  | aiobreaker         | ≥1.2      | Async circuit breaker pattern         |
| Retry            | tenacity           | ≥9.0      | Retry with exponential backoff        |
| Metrics          | prometheus-client  | ≥0.21     | Prometheus metric instrumentation     |
| Monitoring       | Prometheus         | latest    | Time-series metrics collection        |
| Containerization | Docker             | multi-stage| Lightweight, reproducible builds     |
| Orchestration    | Docker Compose     | —         | Multi-service local deployment        |
| Testing          | pytest + httpx     | ≥8.3      | Async API testing                     |
| Linting          | Ruff               | ≥0.8      | Fast Python linter & formatter        |
