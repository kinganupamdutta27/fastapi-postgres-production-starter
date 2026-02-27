# 08 — Deployment & Docker

> **Audience:** 🔴 Advanced — Docker internals, production deployment, and operational best practices.

---

## Table of Contents

- [Docker Architecture](#docker-architecture)
- [The Dockerfile Explained](#the-dockerfile-explained)
- [Docker Compose Explained](#docker-compose-explained)
- [Service Startup Order](#service-startup-order)
- [The Entrypoint Script](#the-entrypoint-script)
- [Building and Running](#building-and-running)
- [Data Persistence](#data-persistence)
- [Production Checklist](#production-checklist)
- [Scaling](#scaling)
- [CI/CD Integration](#cicd-integration)
- [Troubleshooting](#troubleshooting)

---

## Docker Architecture

```
┌────────────────────── Docker Compose ──────────────────────┐
│                                                            │
│  ┌────────────┐  ┌────────────┐  ┌──────────┐  ┌────────┐ │
│  │ PostgreSQL │  │ PgBouncer  │  │ FastAPI  │  │Promethe│ │
│  │   :5432    │  │   :6432    │  │  :8000   │  │  :9090 │ │
│  │   (data)   │  │  (pooler)  │  │  (app)   │  │(metrics│ │
│  └─────┬──────┘  └─────┬──────┘  └────┬─────┘  └────┬───┘ │
│        │               │              │              │      │
│        └──────────┬─────┘              │              │      │
│  Docker Network   │                    │              │      │
│  (bridge mode)    └────────────────────┘              │      │
│                                        └───────────────┘     │
│                                                            │
│  Named Volume: pgdata (persists database files)            │
└────────────────────────────────────────────────────────────┘
```

---

## The Dockerfile Explained

The Dockerfile uses a **multi-stage build** pattern — this is a best practice for production Docker images.

### Stage 1: Builder

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /build

# Copy only the dependency file first (Docker layer caching)
COPY pyproject.toml ./

# Install all Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .
```

**Why this stage?**
- Installs pip, setuptools, compilers, and all Python packages
- These build tools are **NOT needed at runtime** (about ~200 MB of waste)
- By copying `pyproject.toml` first, Docker caches this layer — dependencies only reinstall if `pyproject.toml` changes

### Stage 2: Runtime

```dockerfile
FROM python:3.12-slim
WORKDIR /app

# Create non-root user (security)
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy ONLY installed packages from builder (not build tools)
COPY --from=builder /usr/local/lib/python3.12/site-packages ...
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini entrypoint.sh ./

RUN chmod +x /app/entrypoint.sh
USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

**Why this stage?**
- Starts from a **clean** python:3.12-slim image
- Only copies the installed packages (no pip, no setuptools, no compilers)
- Runs as `appuser` (non-root) for security
- Final image is ~150 MB instead of ~400 MB

### Layer caching strategy

```
Least frequently changed (top)
    │
    ├── FROM python:3.12-slim           ← Changes: almost never
    ├── RUN groupadd / useradd          ← Changes: never
    ├── COPY pyproject.toml             ← Changes: when dependencies change
    ├── RUN pip install                 ← Changes: when dependencies change
    ├── COPY app/ migrations/           ← Changes: every code change
    └── CMD [...]                       ← Changes: rarely
    │
Most frequently changed (bottom)
```

When you change only application code, Docker reuses the cached dependency layers — making rebuilds take **seconds** instead of minutes.

---

## Docker Compose Explained

### Service definitions

| Service       | Image                   | Ports    | Depends On    | Health Check                |
|---------------|-------------------------|----------|---------------|-----------------------------|
| `postgres`    | `postgres:16-alpine`    | 5432     | —             | `pg_isready` every 5s       |
| `pgbouncer`   | `edoburu/pgbouncer`     | 6432     | postgres ✅   | Port check every 5s         |
| `app`         | Built from Dockerfile   | 8000     | pgbouncer ✅  | —                           |
| `prometheus`  | `prom/prometheus`       | 9090     | app           | —                           |

### Health check gating

```
postgres         ──(healthy?)──▶  pgbouncer  ──(healthy?)──▶  app  ──▶  prometheus
   │                                 │                         │
   pg_isready                  port 6432 check           (no check)
   interval: 5s                interval: 5s
   retries: 5                  retries: 5
```

**Why?** Without health checks, services start simultaneously. The app would try to connect to PgBouncer before PgBouncer is ready, causing `ConnectionRefusedError`.

With `condition: service_healthy`, Docker Compose waits until the dependency passes its health check before starting the dependent service.

---

## Service Startup Order

```
Time 0s:  postgres container starts
          │
Time 3s:  postgres passes pg_isready health check
          │
Time 3s:  pgbouncer container starts (depends on postgres: healthy)
          │
Time 5s:  pgbouncer passes port health check
          │
Time 5s:  app container starts (depends on pgbouncer: healthy)
          │
Time 6s:  entrypoint.sh runs alembic upgrade head
          │
Time 8s:  uvicorn starts, app is ready
          │
Time 8s:  prometheus container starts (depends on app)
          │
Time 9s:  prometheus begins scraping /metrics
```

---

## The Entrypoint Script

**File:** `entrypoint.sh`

```bash
#!/bin/sh
set -e

# Run migrations directly against PostgreSQL (bypass PgBouncer for DDL)
alembic -x sqlalchemy.url=postgresql://${DATABASE_USER}:${DATABASE_PASSWORD}@postgres:5432/${DATABASE_NAME} upgrade head

# Start the application (passed as CMD arguments)
exec "$@"
```

**Why connect to PostgreSQL directly for migrations?**
PgBouncer in transaction mode can cause issues with DDL (schema changes) because the connection may switch between statements. Migrations connect directly to PostgreSQL on port 5432 to avoid this.

**Why `exec "$@"`?**
This replaces the shell process with the uvicorn process, so Docker's signal handling (SIGTERM for graceful shutdown) goes directly to uvicorn.

---

## Building and Running

### Standard workflow

```powershell
# Build the Docker image
docker compose build

# Start all services
docker compose up

# Start in background (detached)
docker compose up -d

# View logs
docker compose logs -f app

# Stop all services
docker compose down

# Stop and remove data volume
docker compose down -v
```

### Rebuild after code changes

```powershell
# Rebuild only the app (not postgres/pgbouncer/prometheus)
docker compose build app

# Restart the app container
docker compose up -d app
```

### Force full rebuild (no cache)

```powershell
docker compose build --no-cache
```

---

## Data Persistence

### What persists

| Data                | Volume      | Survives `docker compose down` | Survives `down -v` |
|---------------------|-------------|:------------------------------:|:-------------------:|
| PostgreSQL data     | `pgdata`    | ✅ Yes                         | ❌ No              |
| Prometheus metrics  | (none)      | ❌ No                          | ❌ No              |
| Application state   | (none)      | ❌ No (stateless)              | ❌ No              |

**To delete everything and start fresh:**
```powershell
docker compose down -v    # -v removes named volumes
```

**To persist Prometheus data**, add a named volume:
```yaml
prometheus:
  volumes:
    - prometheus-data:/prometheus
    - ./infra/prometheus.yml:/etc/prometheus/prometheus.yml:ro
```

---

## Production Checklist

### Security

- [ ] **Change default passwords** — `app_secret` is for development only!
- [ ] **Use Docker secrets** or a vault for credentials (not environment variables in plain text)
- [ ] **Enable TLS/SSL** between app ↔ PgBouncer ↔ PostgreSQL
- [ ] **Restrict network access** — use Docker networks to isolate services
- [ ] **Run as non-root** — already done (`USER appuser` in Dockerfile)
- [ ] **Scan image for vulnerabilities** — `docker scout quickview`

### Performance

- [ ] **Increase Uvicorn workers** — `--workers 4` (1 per CPU core)
- [ ] **Tune pool sizes** — Match to expected concurrent load
- [ ] **Enable PostgreSQL connection limits** — Set `max_connections` appropriately
- [ ] **Add resource limits** to Docker Compose services

### Reliability

- [ ] **Add liveness/readiness probes** for the app container
- [ ] **Set `restart: always`** (not just `on-failure`)
- [ ] **Monitor with alerts** — Set up Prometheus alerting rules
- [ ] **Backup PostgreSQL** — Use `pg_dump` or continuous archiving

### Observability

- [ ] **Add Grafana** for dashboarding
- [ ] **Set up alerting** — PagerDuty, Slack, email via Alertmanager
- [ ] **Structured logging** — Use JSON logging for log aggregation (ELK, Loki)
- [ ] **Add request tracing** — OpenTelemetry + Jaeger for distributed tracing

---

## Scaling

### Horizontal scaling (multiple app instances)

```yaml
app:
  deploy:
    replicas: 3    # Run 3 instances of the app
```

The two-tier pooling architecture supports this:
```
App Instance 1 (pool: 10)  ──┐
App Instance 2 (pool: 10)  ──┼──▶ PgBouncer (pool: 20) ──▶ PostgreSQL
App Instance 3 (pool: 10)  ──┘
    30 client connections       20 real connections        20 processes
```

PgBouncer handles 30 concurrent client connections with only 20 PostgreSQL connections.

### Vertical scaling (bigger containers)

Add resource limits to prevent runaway memory/CPU usage:

```yaml
app:
  deploy:
    resources:
      limits:
        cpus: "2.0"
        memory: 512M
      reservations:
        cpus: "0.5"
        memory: 128M
```

---

## CI/CD Integration

### GitHub Actions example

```yaml
name: Build and Test
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: app_user
          POSTGRES_PASSWORD: app_secret
          POSTGRES_DB: app_db
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: alembic upgrade head
        env:
          DATABASE_HOST: localhost
          DATABASE_PORT: 5432
      - run: pytest
        env:
          DATABASE_HOST: localhost
          DATABASE_PORT: 5432
```

---

## Troubleshooting

### Container won't start

```powershell
# Check logs
docker compose logs app

# Check if port is in use
netstat -an | findstr 8000
```

### Database connection errors

```powershell
# Verify PostgreSQL is running
docker compose exec postgres pg_isready -U app_user

# Verify PgBouncer is running
docker compose logs pgbouncer

# Test direct PostgreSQL connection
docker compose exec postgres psql -U app_user -d app_db -c "SELECT 1"
```

### Migration failures

```powershell
# Run migrations manually
docker compose exec app alembic upgrade head

# Check current migration version
docker compose exec app alembic current

# View migration history
docker compose exec app alembic history
```

### Full reset

```powershell
docker compose down -v           # Remove everything
docker compose build --no-cache  # Rebuild from scratch
docker compose up                # Fresh start
```

---

**← [Configuration Reference](07-CONFIGURATION.md) | [Documentation Index →](README.md)**
