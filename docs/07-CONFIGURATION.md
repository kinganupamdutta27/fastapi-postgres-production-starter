# 07 — Configuration Reference

> **Audience:** 🔴 Advanced — Every environment variable explained with tuning guidance.

---

## Table of Contents

- [How Configuration Works](#how-configuration-works)
- [Configuration Sources](#configuration-sources)
- [All Environment Variables](#all-environment-variables)
  - [Application Settings](#application-settings)
  - [Database Connection](#database-connection)
  - [Connection Pool](#connection-pool)
  - [Timeouts](#timeouts)
  - [Circuit Breaker](#circuit-breaker)
- [Environment Profiles](#environment-profiles)
- [The .env File](#the-env-file)
- [Adding New Configuration](#adding-new-configuration)

---

## How Configuration Works

This project uses **pydantic-settings** for configuration management. Here's how it works:

```
Environment Variables (highest priority)
         │
         ▼
    .env File (fallback)
         │
         ▼
    Default Values (in Settings class)
         │
         ▼
    settings = Settings()  ← Singleton used throughout the app
```

**Priority order:** Environment variables > `.env` file > Default values in code.

This means:
- In **Docker**, environment variables in `docker-compose.yml` override everything
- In **local development**, the `.env` file is used
- If neither is set, the defaults in `config.py` are used

---

## Configuration Sources

| Source                    | Used When           | Example                              |
|---------------------------|---------------------|--------------------------------------|
| `docker-compose.yml` env  | Running in Docker   | `DATABASE_HOST: pgbouncer`           |
| `.env` file               | Local development   | `DATABASE_HOST=localhost`            |
| Code defaults             | Always (fallback)   | `database_host: str = "localhost"`   |
| CLI environment           | CI/CD pipelines     | `export DATABASE_HOST=db.prod.com`   |

---

## All Environment Variables

### Application Settings

| Variable     | Type   | Default       | Description                              |
|-------------|--------|---------------|------------------------------------------|
| `APP_HOST`  | string | `0.0.0.0`     | Network interface to bind to             |
| `APP_PORT`  | int    | `8000`        | Port number for the HTTP server          |
| `APP_ENV`   | string | `development` | Environment name (development/staging/production) |
| `APP_DEBUG` | bool   | `false`       | Enable debug mode (verbose logging)      |

**`APP_HOST`** — `0.0.0.0` means "listen on all network interfaces." In Docker, this is required so the container can receive traffic. For local development, `127.0.0.1` restricts to localhost only.

**`APP_ENV`** — Used for conditional behavior (e.g., disable debug in production). Does not change runtime behavior in the current codebase, but is a best practice for observability tags.

---

### Database Connection

| Variable            | Type   | Default      | Description                              |
|--------------------|--------|--------------|------------------------------------------|
| `DATABASE_HOST`    | string | `localhost`  | PostgreSQL/PgBouncer hostname            |
| `DATABASE_PORT`    | int    | `6432`       | PgBouncer port (5432 for direct PG)      |
| `DATABASE_USER`    | string | `app_user`   | PostgreSQL username                      |
| `DATABASE_PASSWORD`| string | `app_secret` | PostgreSQL password                      |
| `DATABASE_NAME`    | string | `app_db`     | Database name                            |

**`DATABASE_PORT`** — The default is `6432` (PgBouncer), not `5432` (PostgreSQL). This is intentional — in production, all queries should go through PgBouncer.

**For local development without PgBouncer**, change to `5432`:
```env
DATABASE_PORT=5432
```

---

### Connection Pool

| Variable                       | Type  | Default | Unit    | Description                              |
|-------------------------------|-------|---------|---------|------------------------------------------|
| `DB_POOL_MIN_SIZE`            | int   | `2`     | conns   | Minimum connections kept warm            |
| `DB_POOL_MAX_SIZE`            | int   | `10`    | conns   | Maximum connections allowed              |
| `DB_POOL_MAX_INACTIVE_LIFETIME`| float| `300`   | seconds | Close idle connections after this time   |

#### Tuning `DB_POOL_MIN_SIZE`

| Value | Trade-off                                                    |
|:-----:|--------------------------------------------------------------|
| `0`   | No pre-warmed connections — first request pays ~50ms penalty |
| `2`   | ✅ Good default — 2 warm connections, minimal resource use   |
| `5`   | Faster response for first 5 concurrent queries              |

#### Tuning `DB_POOL_MAX_SIZE`

| Value | Trade-off                                                    |
|:-----:|--------------------------------------------------------------|
| `5`   | Conservative — may queue queries under moderate load         |
| `10`  | ✅ Good default — handles most workloads                     |
| `20`  | Aggressive — only if PgBouncer pool is large enough          |

**Rule of thumb:** `DB_POOL_MAX_SIZE` should be ≤ PgBouncer's `default_pool_size` (currently 20).

#### Tuning `DB_POOL_MAX_INACTIVE_LIFETIME`

| Value   | Trade-off                                                  |
|:-------:|-------------------------------------------------------------|
| `60`    | Aggressive cleanup — connections close after 1 minute idle  |
| `300`   | ✅ Good default — 5 minutes balances reuse vs. cleanup      |
| `3600`  | Keep connections alive for an hour (only for steady traffic) |

---

### Timeouts

| Variable                         | Type | Default  | Unit         | Description                     |
|----------------------------------|------|----------|--------------|---------------------------------|
| `DB_STATEMENT_TIMEOUT`          | int  | `5000`   | milliseconds | Max query execution time        |
| `DB_IDLE_IN_TRANSACTION_TIMEOUT`| int  | `10000`  | milliseconds | Max idle time in a transaction  |

#### Tuning `DB_STATEMENT_TIMEOUT`

This is the **maximum time a single SQL query can run** before PostgreSQL kills it.

| Value    | Trade-off                                                |
|:--------:|----------------------------------------------------------|
| `1000`   | Strict — only fast queries survive (good for OLTP)       |
| `5000`   | ✅ Good default — allows moderately complex queries      |
| `30000`  | Permissive — for reporting/analytics queries             |
| `0`      | ⚠️ No timeout — queries can run forever (dangerous!)    |

**What happens when it triggers:**
```
ERROR: canceling statement due to statement timeout
```

#### Tuning `DB_IDLE_IN_TRANSACTION_TIMEOUT`

This kills transactions that stay open without executing queries (zombie transactions).

| Value    | Trade-off                                                |
|:--------:|----------------------------------------------------------|
| `5000`   | Strict — 5 seconds idle in a transaction triggers kill   |
| `10000`  | ✅ Good default                                          |
| `60000`  | Permissive — only for apps with long-lived transactions  |

**Why this matters:** An idle-in-transaction connection holds a PgBouncer slot and potentially holds database locks, blocking other queries.

---

### Circuit Breaker

| Variable            | Type | Default | Unit    | Description                              |
|--------------------|------|---------|---------|------------------------------------------|
| `CB_FAIL_MAX`      | int  | `5`     | count   | Consecutive failures before circuit opens |
| `CB_TIMEOUT_DURATION`| int| `30`    | seconds | Time circuit stays open before half-open |

#### Tuning `CB_FAIL_MAX`

| Value | Trade-off                                                    |
|:-----:|--------------------------------------------------------------|
| `2`   | Very sensitive — circuit opens after 2 failures              |
| `5`   | ✅ Good default — tolerates brief glitches                   |
| `10`  | Tolerant — more failures before stopping (batch workloads)   |

#### Tuning `CB_TIMEOUT_DURATION`

| Value | Trade-off                                                    |
|:-----:|--------------------------------------------------------------|
| `10`  | Fast recovery attempt — checks DB every 10 seconds           |
| `30`  | ✅ Good default — reasonable wait before retry               |
| `120` | Conservative — waits 2 minutes (for known slow recoveries)   |

---

## Environment Profiles

### Development (`.env` file)

```env
DATABASE_HOST=localhost
DATABASE_PORT=5432       # Direct to PostgreSQL (no PgBouncer)
APP_ENV=development
APP_DEBUG=true
DB_STATEMENT_TIMEOUT=30000   # Generous for debugging
```

### Docker Compose (`docker-compose.yml`)

```yaml
environment:
  DATABASE_HOST: pgbouncer
  DATABASE_PORT: "6432"
  APP_ENV: production
  DB_STATEMENT_TIMEOUT: "5000"
```

### Production (recommended)

```env
DATABASE_HOST=pgbouncer.internal
DATABASE_PORT=6432
APP_ENV=production
APP_DEBUG=false
DB_POOL_MIN_SIZE=5
DB_POOL_MAX_SIZE=20
DB_STATEMENT_TIMEOUT=5000
DB_IDLE_IN_TRANSACTION_TIMEOUT=10000
CB_FAIL_MAX=3
CB_TIMEOUT_DURATION=15
```

---

## The .env File

The `.env` file is read automatically by pydantic-settings. It should **never** be committed to Git with real credentials.

**Current `.env` (development defaults):**
```env
# === Database ===
DATABASE_HOST=localhost
DATABASE_PORT=6432
DATABASE_USER=app_user
DATABASE_PASSWORD=app_secret
DATABASE_NAME=app_db

# === Connection Pool ===
DB_POOL_MIN_SIZE=2
DB_POOL_MAX_SIZE=10
DB_POOL_MAX_INACTIVE_LIFETIME=300

# === Timeouts (ms) ===
DB_STATEMENT_TIMEOUT=5000
DB_IDLE_IN_TRANSACTION_TIMEOUT=10000

# === Circuit Breaker ===
CB_FAIL_MAX=5
CB_TIMEOUT_DURATION=30

# === App ===
APP_HOST=0.0.0.0
APP_PORT=8000
APP_ENV=development
APP_DEBUG=true
```

---

## Adding New Configuration

To add a new configuration variable:

### Step 1: Add to `Settings` class

```python
# app/core/config.py
class Settings(BaseSettings):
    # ... existing settings ...
    my_new_setting: str = "default_value"
```

### Step 2: Set in environment

```env
# .env
MY_NEW_SETTING=production_value
```

### Step 3: Use in code

```python
from app.core.config import settings

print(settings.my_new_setting)  # "production_value"
```

**Naming convention:** Python uses `snake_case`, environment variables use `UPPER_SNAKE_CASE`. pydantic-settings converts automatically (`my_new_setting` ↔ `MY_NEW_SETTING`).

---

**← [Observability & Monitoring](06-OBSERVABILITY.md) | [Deployment & Docker →](08-DEPLOYMENT.md)**
