# FastAPI + PostgreSQL — Industry-Standard POC

High-performance async **FastAPI** application with **PostgreSQL**, featuring connection pooling, resilience patterns, and observability — all containerised with Docker Compose.

## Architecture

```
┌────────────┐     ┌────────────┐     ┌────────────┐
│   Client   │────▶│  FastAPI    │────▶│ PgBouncer  │────▶│ PostgreSQL │
│            │     │  (uvicorn)  │     │  (txn mode)│     │   16       │
└────────────┘     └─────┬──────┘     └────────────┘     └────────────┘
                         │
                         ▼
                   ┌────────────┐
                   │ Prometheus │
                   │   :9090    │
                   └────────────┘
```

### Key Patterns

| Pattern | Library | Purpose |
|---------|---------|---------|
| **Async DB Pool** | `asyncpg` | Small app-side pool (2–10); PgBouncer handles multiplexing |
| **Connection Pooler** | PgBouncer | Transaction-mode pooling for high concurrency |
| **Circuit Breaker** | `aiobreaker` | Fast-fail when PostgreSQL is unhealthy |
| **Retry + Backoff** | `tenacity` | Exponential backoff for transient failures |
| **Observability** | `prometheus-client` | Request latency, DB query duration, pool gauges |
| **Timeouts** | PostgreSQL server settings | `statement_timeout` + `idle_in_transaction_session_timeout` |

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ (for local development)

### Run with Docker Compose

```bash
# Start all services
docker-compose up --build

# The app will be available at:
#   API:        http://localhost:8000
#   Docs:       http://localhost:8000/docs
#   Metrics:    http://localhost:8000/metrics
#   Prometheus: http://localhost:9090
```

### Local Development

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

# Install dependencies
pip install -e ".[dev]"

# Copy environment file
copy .env.example .env

# Start PostgreSQL + PgBouncer (via Docker)
docker-compose up postgres pgbouncer -d

# Run migrations
alembic upgrade head

# Start the app
uvicorn app.main:app --reload --port 8000
```

### Run Tests

```bash
pytest tests/ -v
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health/` | Liveness probe |
| `GET` | `/health/ready` | Readiness probe (checks DB) |
| `POST` | `/items/` | Create an item |
| `GET` | `/items/` | List items (paginated) |
| `GET` | `/items/{id}` | Get item by ID |
| `DELETE` | `/items/{id}` | Delete an item |
| `GET` | `/metrics` | Prometheus metrics |
| `GET` | `/docs` | Swagger UI |

## Project Structure

```
fastapi-postgres-poc/
├── app/
│   ├── api/
│   │   ├── health.py          # Health check endpoints
│   │   ├── routes.py          # Item CRUD endpoints
│   │   └── schemas.py         # Pydantic models
│   ├── core/
│   │   └── config.py          # pydantic-settings config
│   ├── db/
│   │   ├── pool.py            # asyncpg pool management
│   │   ├── repository.py      # CRUD operations
│   │   └── resilience.py      # Circuit breaker + retry
│   ├── observability/
│   │   ├── metrics.py         # Prometheus metric definitions
│   │   └── middleware.py      # HTTP instrumentation
│   └── main.py                # FastAPI app entry point
├── infra/
│   ├── pgbouncer.ini          # PgBouncer configuration
│   ├── prometheus.yml         # Prometheus scrape config
│   └── userlist.txt           # PgBouncer auth
├── migrations/
│   ├── versions/
│   │   └── 001_create_items.py
│   └── env.py
├── tests/
│   ├── conftest.py
│   ├── test_health.py
│   └── test_items.py
├── .env.example
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── README.md
```

## Configuration

All settings are loaded from environment variables (or `.env` file) via `pydantic-settings`. See `.env.example` for all available options.

## License

MIT
