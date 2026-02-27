# 02 — Project Structure

> **Audience:** 🟢 Beginner — Understand what every file does and how they connect.

This document walks through the entire codebase, file by file, explaining the purpose and responsibility of each component.

---

## Table of Contents

- [Top-Level Overview](#top-level-overview)
- [Root Files](#root-files)
- [app/ — Application Code](#app--application-code)
  - [app/main.py — The Entry Point](#appmainpy--the-entry-point)
  - [app/core/ — Configuration](#appcore--configuration)
  - [app/api/ — HTTP Layer](#appapi--http-layer)
  - [app/db/ — Database Layer](#appdb--database-layer)
  - [app/observability/ — Monitoring](#appobservability--monitoring)
- [migrations/ — Database Migrations](#migrations--database-migrations)
- [infra/ — Infrastructure Config](#infra--infrastructure-config)
- [tests/ — Test Suite](#tests--test-suite)
- [How the Layers Connect](#how-the-layers-connect)

---

## Top-Level Overview

```
fastapi-postgres-poc/
├── app/                     # 🟢 All application source code
│   ├── main.py              #    Entry point — creates the FastAPI app
│   ├── core/                #    Configuration management
│   ├── api/                 #    HTTP routes, schemas, health checks
│   ├── db/                  #    Database pool, queries, resilience
│   └── observability/       #    Prometheus metrics & middleware
├── migrations/              # 🟡 Alembic database migration scripts
├── infra/                   # 🟡 Infrastructure configuration files
├── tests/                   # 🟡 Automated tests
├── .env                     #    Local environment variables
├── pyproject.toml           #    Python project metadata & dependencies
├── requirements.txt         #    Pip-installable dependency list
├── Dockerfile               #    Docker image build instructions
├── docker-compose.yml       #    Multi-service orchestration
├── entrypoint.sh            #    Docker container startup script
├── alembic.ini              #    Alembic migration configuration
└── ARCHITECTURE.md          #    High-level architecture documentation
```

---

## Root Files

### `pyproject.toml`
**What:** The modern Python project metadata file. Defines the project name, version, Python version requirement, and all dependencies.

**Why this file?** The Python ecosystem has moved from `setup.py` to `pyproject.toml` as the standard way to define project metadata. It's cleaner, declarative, and supports multiple build backends.

**Key sections:**
```toml
[project]
dependencies = [...]         # Runtime dependencies (FastAPI, asyncpg, etc.)

[project.optional-dependencies]
dev = [...]                  # Development-only dependencies (pytest, ruff)

[tool.ruff]                  # Linter configuration
[tool.pytest.ini_options]    # Test runner configuration
```

### `requirements.txt`
**What:** A flat list of all dependencies for `pip install -r requirements.txt`.

**Why both?** `pyproject.toml` is the source of truth. `requirements.txt` exists for convenience and compatibility with tools that don't support `pyproject.toml` yet.

### `.env`
**What:** Environment variables for local development (database credentials, ports, timeouts).

**Why?** Keeps secrets and configuration outside the code. The app reads these automatically via `pydantic-settings`.

### `Dockerfile`
**What:** Instructions to build a Docker image for the application.

**Why multi-stage?** Uses a "builder" stage to install dependencies, then copies only the installed packages to a small runtime image —  halving the image size and removing build tools.

### `docker-compose.yml`
**What:** Defines all four services (PostgreSQL, PgBouncer, App, Prometheus) and how they connect.

**Why?** One command (`docker compose up`) starts the entire stack with proper networking, health checks, and dependency ordering.

### `entrypoint.sh`
**What:** Shell script that runs Alembic migrations before starting the application server.

**Why?** Ensures the database schema is always up-to-date when the container starts — without manual intervention.

### `alembic.ini`
**What:** Configuration for Alembic (the database migration tool). Points to the `migrations/` directory and specifies the database connection string.

---

## app/ — Application Code

### `app/main.py` — The Entry Point

This is where everything starts. It:

1. **Creates the FastAPI app** with title, description, and version
2. **Registers middleware** (Prometheus request instrumentation)
3. **Includes routers** (health checks and item CRUD routes)
4. **Manages the lifecycle** (initialize database pool on startup, close it on shutdown)
5. **Exposes `/metrics`** endpoint for Prometheus

```
main.py
  ├── Creates FastAPI(lifespan=...)
  ├── Adds PrometheusMiddleware
  ├── Includes health_router (/health/*)
  ├── Includes items_router (/items/*)
  ├── Defines /metrics endpoint
  └── Lifespan:
       ├── Startup: init_pool(), start pool gauge task
       └── Shutdown: cancel gauge task, close_pool()
```

**Key concept — Lifespan:** The `lifespan` function is an async context manager that FastAPI calls once when the app starts and once when it stops. It replaces the older `@app.on_event("startup")` pattern.

---

### `app/core/` — Configuration

#### `app/core/config.py`

**What:** A single `Settings` class that loads all configuration from environment variables.

**How it works:**
```python
class Settings(BaseSettings):
    database_host: str = "localhost"    # Read from DATABASE_HOST env var
    database_port: int = 6432          # Read from DATABASE_PORT env var
    # ... more settings

settings = Settings()  # This singleton is imported everywhere
```

**Why pydantic-settings?**
- Automatically reads env vars and `.env` files
- Validates types (e.g., `database_port` must be an integer)
- Provides defaults for development
- Fails fast with clear errors if a required value is missing

---

### `app/api/` — HTTP Layer

This layer handles incoming HTTP requests and outgoing HTTP responses. It does NOT contain any database logic.

#### `app/api/schemas.py` — Data Shapes

Defines the "shape" of data going in and coming out of the API using Pydantic models:

| Schema             | Used For         | Fields                                          |
|--------------------|------------------|-------------------------------------------------|
| `ItemCreate`       | POST request body| `name` (required, 1-255 chars), `description` (optional) |
| `ItemResponse`     | Response body    | `id`, `name`, `description`, `created_at`, `updated_at` |
| `ItemListResponse` | List response    | `items[]`, `count`                              |

**Why Pydantic schemas?**
- FastAPI automatically validates incoming requests against these schemas
- Invalid requests return a **422 Unprocessable Entity** response with detailed error messages
- Response schemas ensure the API never leaks internal data

#### `app/api/routes.py` — Item Endpoints

The CRUD routes for items. Each function:
1. Receives a validated request (thanks to schemas)
2. Calls a repository function (database layer)
3. Returns a response

```
POST   /items/          → create_item() → repository.create_item()
GET    /items/{item_id} → get_item()    → repository.get_item()
GET    /items/          → list_items()  → repository.list_items()
DELETE /items/{item_id} → delete_item() → repository.delete_item()
```

**Key principle — Thin routes:** The route functions are intentionally simple. They don't contain SQL queries or business logic. They delegate to the repository layer.

#### `app/api/health.py` — Health Checks

Two endpoints for container orchestrators (Docker, Kubernetes):

| Endpoint        | Type      | What It Checks                        |
|-----------------|-----------|---------------------------------------|
| `/health/`      | Liveness  | Is the process running? (Always yes)  |
| `/health/ready` | Readiness | Can we reach the database?            |

---

### `app/db/` — Database Layer

This layer handles all database communication. No other layer touches the database directly.

#### `app/db/pool.py` — Connection Pool

Manages a pool of database connections using **asyncpg**:

| Function      | When It Runs         | What It Does                          |
|---------------|----------------------|---------------------------------------|
| `init_pool()` | App startup          | Creates a pool of 2-10 connections    |
| `get_pool()`  | Every query          | Returns the pool (or raises an error) |
| `close_pool()`| App shutdown         | Closes all connections gracefully     |

**Analogy:** Think of the pool like a parking lot. Instead of building a new parking space every time a car arrives (creating a new connection), you pre-build a small lot (the pool). Cars come and go, but the spaces are reused.

#### `app/db/repository.py` — Data Access

Contains all SQL queries. Each function:
1. Calls `execute_query()` (which provides resilience)
2. Converts the result from an asyncpg `Record` to a Python `dict`

**Why a separate repository?** This is the **Repository Pattern** — it separates "what data we need" from "how we get it." The routes don't know SQL exists; they just call `repository.create_item()`.

#### `app/db/resilience.py` — Fault Tolerance

Wraps every database call with two protection layers:

```
Your query → Retry (3 attempts) → Circuit Breaker → Database
```

1. **Circuit Breaker:** If the database fails 5 times in a row, stop trying for 30 seconds (prevents hammering a dead database)
2. **Retry:** If a query fails due to a network blip, wait and try again (up to 3 times)

See [Resilience Patterns](05-RESILIENCE.md) for a deep dive.

---

### `app/observability/` — Monitoring

#### `app/observability/metrics.py` — Metric Definitions

Defines 5 Prometheus metrics that track application performance:
- Database query speed
- Connection pool utilization
- HTTP request count and speed

#### `app/observability/middleware.py` — Request Instrumentation

A middleware that runs on **every HTTP request** and records:
- How long the request took
- The HTTP method, path, and status code

See [Observability & Monitoring](06-OBSERVABILITY.md) for a deep dive.

---

## migrations/ — Database Migrations

| File                         | Purpose                                    |
|------------------------------|--------------------------------------------|
| `env.py`                     | Alembic environment — how to connect to DB |
| `script.py.mako`             | Template for new migration files           |
| `versions/001_create_items.py` | Creates the `items` table and index      |

**What are migrations?** They're version-controlled scripts that change the database schema. Instead of manually running SQL, you write a migration script that Alembic runs for you. This ensures every environment (dev, staging, production) has the same schema.

---

## infra/ — Infrastructure Config

| File              | Purpose                                         |
|-------------------|-------------------------------------------------|
| `pgbouncer.ini`   | PgBouncer configuration (pool mode, sizing, timeouts) |
| `prometheus.yml`  | Prometheus scrape configuration                  |
| `userlist.txt`    | PgBouncer authentication credentials             |

---

## tests/ — Test Suite

| File              | Tests                                           |
|-------------------|-------------------------------------------------|
| `conftest.py`     | Shared test fixtures (test client setup)         |
| `test_health.py`  | Health endpoint tests (liveness, readiness)      |
| `test_items.py`   | Item CRUD endpoint tests (create, read, delete)  |

Run tests with:
```bash
pytest
```

---

## How the Layers Connect

```
                    HTTP Request
                         │
                         ▼
                  ┌──────────────┐
                  │  Middleware   │  ← Records metrics
                  │ (observability)│
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │   Routes     │  ← Validates request, returns response
                  │   (api/)     │
                  └──────┬───────┘
                         │ calls
                         ▼
                  ┌──────────────┐
                  │  Repository  │  ← SQL queries
                  │   (db/)      │
                  └──────┬───────┘
                         │ uses
                         ▼
                  ┌──────────────┐
                  │  Resilience  │  ← Retry + Circuit Breaker
                  │   (db/)      │
                  └──────┬───────┘
                         │ uses
                         ▼
                  ┌──────────────┐
                  │    Pool      │  ← Connection management
                  │   (db/)      │
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │  PgBouncer   │  ← Connection multiplexing
                  └──────┬───────┘
                         │
                         ▼
                  ┌──────────────┐
                  │  PostgreSQL  │  ← Data storage
                  └──────────────┘
```

**Key rule:** Each layer only talks to the layer directly below it. Routes never touch the pool. The pool never touches the routes. This is called **layered architecture** and it keeps the code organized and testable.

---

**← [Getting Started](01-GETTING_STARTED.md) | [API Reference →](03-API_REFERENCE.md)**
