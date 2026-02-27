# 04 — Database Deep Dive

> **Audience:** 🟡 Intermediate — Understand the database architecture, connection pooling, and why two layers of pooling exist.

---

## Table of Contents

- [Why PostgreSQL?](#why-postgresql)
- [The Connection Problem](#the-connection-problem)
- [Two-Tier Pooling Architecture](#two-tier-pooling-architecture)
- [Layer 1: PgBouncer (Server-Side Pool)](#layer-1-pgbouncer-server-side-pool)
- [Layer 2: asyncpg (App-Side Pool)](#layer-2-asyncpg-app-side-pool)
- [Why asyncpg Over SQLAlchemy?](#why-asyncpg-over-sqlalchemy)
- [Connection Lifecycle](#connection-lifecycle)
- [Session-Level Timeouts](#session-level-timeouts)
- [The Items Table Schema](#the-items-table-schema)
- [The Repository Pattern](#the-repository-pattern)
- [Database Migrations with Alembic](#database-migrations-with-alembic)
- [Common Gotchas](#common-gotchas)

---

## Why PostgreSQL?

PostgreSQL is the most popular open-source relational database, chosen here for:

| Feature              | Why It Matters                                                    |
|----------------------|-------------------------------------------------------------------|
| **ACID compliance**  | Data integrity guaranteed — no half-written transactions          |
| **UUID support**     | Native `uuid-ossp` extension for generating UUIDs server-side    |
| **Timezone-aware**   | `TIMESTAMPTZ` stores UTC — no timezone bugs                      |
| **JSON support**     | `jsonb` column type for semi-structured data (future-proof)      |
| **Mature ecosystem** | Battle-tested with 35+ years of development                      |
| **Extensions**       | Rich extension ecosystem (PostGIS, pg_trgm, pg_stat_statements) |

---

## The Connection Problem

### What is a database connection?

A database connection is a network link between your application and PostgreSQL. Think of it like a phone call — your app "dials" PostgreSQL, they "pick up," and they talk back and forth until the call ends.

### Why are connections expensive?

Every PostgreSQL connection creates a **separate OS process** (not a thread — a full process):

```
App Connection 1  →  PostgreSQL Process 1  (~5-10 MB RAM)
App Connection 2  →  PostgreSQL Process 2  (~5-10 MB RAM)
App Connection 3  →  PostgreSQL Process 3  (~5-10 MB RAM)
...
App Connection 100 → PostgreSQL Process 100 (~500-1000 MB RAM!)
```

**The math:** 100 connections × 10 MB = 1 GB of RAM just for connections, not counting actual data processing.

PostgreSQL's default `max_connections = 100`. If your app needs more, you hit:
```
FATAL: too many connections for role "app_user"
```

### The naive approach (and why it fails)

```python
# ❌ BAD: 1 connection per request
async def get_item(item_id):
    conn = await asyncpg.connect(...)   # ~50ms to establish
    result = await conn.fetchrow(...)    # ~2ms for query
    await conn.close()                  # Connection wasted
    return result
```

Problems:
1. Creating a connection takes **~50ms** (TCP handshake + auth + TLS)
2. Under load, you create hundreds of connections simultaneously
3. PostgreSQL crashes or starts refusing connections

---

## Two-Tier Pooling Architecture

This project uses **two layers** of connection pooling to solve the connection problem:

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   FastAPI App                                                   │
│   ┌─────────────────────┐                                       │
│   │  asyncpg Pool       │  ← Layer 2: App-side pool (2-10)     │
│   │  (min=2, max=10)    │     Manages connections to PgBouncer  │
│   └────────┬────────────┘                                       │
│            │                                                     │
│   ┌────────▼────────────┐                                       │
│   │  PgBouncer          │  ← Layer 1: Server-side pool (20)    │
│   │  (pool_size=20)     │     Multiplexes to PostgreSQL         │
│   │  (max_client=200)   │     Transaction pooling mode          │
│   └────────┬────────────┘                                       │
│            │                                                     │
│   ┌────────▼────────────┐                                       │
│   │  PostgreSQL         │  ← Actual database (max_connections=100) │
│   │  (max_conn=100)     │                                       │
│   └─────────────────────┘                                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Why two layers?

| Layer       | Responsibility                              | Analogie                         |
|-------------|---------------------------------------------|----------------------------------|
| **asyncpg** | Manage app-side connections efficiently      | Your desk phone (quick access)   |
| **PgBouncer**| Multiplex many app connections onto fewer DB connections | Office PBX switchboard |

**Without PgBouncer:** If you run 5 app instances, each with max 10 connections = 50 PostgreSQL processes.

**With PgBouncer:** All 5 app instances connect to PgBouncer (50 client connections), but PgBouncer only opens 20 PostgreSQL connections. The 50 clients share the 20 real connections.

---

## Layer 1: PgBouncer (Server-Side Pool)

### What PgBouncer does

PgBouncer sits between the app and PostgreSQL. It accepts incoming connections from the app and routes them to a smaller pool of real PostgreSQL connections.

### Pool modes explained

| Mode         | Connection released after  | Use case                    | This project |
|--------------|----------------------------|-----------------------------|:------------:|
| **Session**  | Client disconnects         | Legacy apps, prepared statements | ❌ |
| **Transaction** | Transaction completes (`COMMIT`/`ROLLBACK`) | Modern async apps | ✅ |
| **Statement** | Each SQL statement       | Simple read-only queries    | ❌ |

**We use `transaction` mode** because:
- asyncpg doesn't use named prepared statements (compatible with transaction pooling)
- Connections are released back to the pool between transactions, maximizing reuse
- It's the recommended mode for FastAPI / async applications

### PgBouncer sizing

```
                   Clients                    PgBouncer                PostgreSQL
               ┌──────────┐              ┌──────────────┐          ┌──────────┐
               │ Client 1  │─────┐       │              │          │          │
               │ Client 2  │─────┤       │  20 real     │──────────│  20      │
               │ Client 3  │─────┤       │  connections │──────────│  backend │
               │ ...       │─────┤───────│              │──────────│  procs   │
               │ Client 198│─────┤       │              │          │          │
               │ Client 199│─────┤       │              │          │          │
               │ Client 200│─────┘       │              │          │          │
               └──────────┘              └──────────────┘          └──────────┘
                200 clients                20 connections            20 processes
```

| Setting             | Value | Why                                          |
|---------------------|-------|----------------------------------------------|
| `default_pool_size` | 20    | Enough for typical concurrent query load     |
| `min_pool_size`     | 5     | Pre-warmed connections avoid cold-start       |
| `reserve_pool_size` | 5     | Extra connections for traffic bursts          |
| `max_client_conn`   | 200   | Upper limit of simultaneous app connections  |
| `server_idle_timeout`| 600  | Reclaim idle backend connections after 10 min|

---

## Layer 2: asyncpg (App-Side Pool)

### What asyncpg Pool does

asyncpg maintains a small pool of connections **to PgBouncer** (not directly to PostgreSQL). When a request needs to run a query:

1. It "borrows" a connection from the pool (`pool.acquire()`)
2. Runs the query
3. Returns the connection to the pool (`pool.release()`)

### Why keep the app-side pool small?

Since PgBouncer already handles the heavy multiplexing, the app-side pool is intentionally small:

```python
_pool = await asyncpg.create_pool(
    min_size=2,     # Always keep 2 connections warm
    max_size=10,    # Never open more than 10 to PgBouncer
    max_inactive_connection_lifetime=300,  # Close idle connections after 5 min
)
```

| Setting                         | Value | Why                                    |
|---------------------------------|-------|----------------------------------------|
| `min_size`                      | 2     | Avoids cold-start latency              |
| `max_size`                      | 10    | Limits demand on PgBouncer             |
| `max_inactive_connection_lifetime` | 300s | Frees PgBouncer slots when idle     |

### Pool lifecycle

```
App Start
  │
  ├── init_pool()
  │   ├── Creates 2 connections (min_size)
  │   └── Applies session timeouts on each connection
  │
  ├── Request 1 → pool.acquire() → run query → pool.release()
  ├── Request 2 → pool.acquire() → run query → pool.release()
  │   ...
  ├── High load → pool grows to max_size (10)
  ├── Low load → idle connections closed after 300s
  │
  └── App Shutdown
      └── close_pool() → closes all connections
```

---

## Why asyncpg Over SQLAlchemy?

| Feature           | asyncpg              | SQLAlchemy + asyncpg      |
|-------------------|----------------------|---------------------------|
| **Speed**         | ⚡ 3x faster         | Slower (ORM overhead)     |
| **Async**         | Native               | Async via extension       |
| **Protocol**      | Binary (efficient)   | Text (through ORM)        |
| **Complexity**    | Simple               | Complex (sessions, models)|
| **Best for**      | Microservices, POCs  | Large apps with many tables|

**When to use asyncpg directly (like this project):**
- Small number of tables
- Performance-critical applications
- You're comfortable writing SQL

**When to switch to SQLAlchemy:**
- 20+ tables with complex relationships
- Need ORM features (lazy loading, joins, migrations auto-generation)
- Team prefers Python over SQL

---

## Connection Lifecycle

Here's what happens for a single database query:

```
Request arrives
    │
    ▼
pool.acquire()                    ← Borrow connection from asyncpg pool
    │
    ▼
PgBouncer assigns a               ← PgBouncer routes to a real PG connection
PostgreSQL connection
    │
    ▼
BEGIN (implicit)                   ← Transaction starts
    │
    ▼
Execute query                      ← Your SQL runs on PostgreSQL
    │
    ▼
COMMIT (implicit)                  ← Transaction ends
    │
    ▼
PgBouncer reclaims                 ← Connection returned to PgBouncer's pool
PostgreSQL connection
    │
    ▼
pool.release()                    ← Connection returned to asyncpg pool
```

---

## Session-Level Timeouts

When each connection is created, two safety timeouts are applied via `SET` commands:

### `statement_timeout` (default: 5,000 ms)

Kills any query that runs longer than 5 seconds. Prevents:
- Runaway queries that scan entire tables
- Lock contention causing cascading timeouts
- Resource exhaustion from expensive queries

```sql
SET statement_timeout = 5000;  -- Kill after 5 seconds
```

### `idle_in_transaction_session_timeout` (default: 10,000 ms)

Kills any transaction that has been idle for more than 10 seconds. Prevents:
- "Zombie transactions" — app opens a transaction, crashes, and never commits
- Lock holding — an idle transaction can block other queries
- Connection leaks — idle transactions keep PgBouncer connections occupied

```sql
SET idle_in_transaction_session_timeout = 10000;  -- Kill after 10 seconds
```

### Why SET instead of server_settings?

asyncpg supports passing these as `server_settings` (startup parameters), but PgBouncer **rejects** unknown startup parameters. The `SET` approach applies them after the connection is established, which works with any PostgreSQL configuration:

```python
# ✅ Works with PgBouncer
async def _connection_init(conn):
    await conn.execute(f"SET statement_timeout = {timeout}")

pool = await asyncpg.create_pool(..., init=_connection_init)

# ❌ Fails with PgBouncer
pool = await asyncpg.create_pool(
    ...,
    server_settings={"statement_timeout": "5000"}  # Rejected!
)
```

---

## The Items Table Schema

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

### Design decisions

| Decision                    | Why                                                        |
|-----------------------------|------------------------------------------------------------|
| **UUID v4 primary key**     | No sequential guessing (security), works in distributed systems, no table lock for sequence increment |
| **Server-generated UUIDs**  | `uuid_generate_v4()` default — even if the app doesn't provide an ID, one is generated |
| **`VARCHAR(255)` for name** | Enforces a reasonable limit at the database level           |
| **`TEXT` for description**  | Unlimited length (app validates at 2000 chars via Pydantic) |
| **`TIMESTAMPTZ`**           | Timezone-aware — stores UTC, avoids timezone bugs           |
| **`NOW()` defaults**        | Server time is the source of truth, not client time         |
| **Index on `created_at`**   | Optimizes `ORDER BY created_at DESC` in list queries        |

---

## The Repository Pattern

All database queries live in `app/db/repository.py`, separated from HTTP handling:

```
HTTP Layer (routes.py)          Database Layer (repository.py)
┌──────────────────────┐        ┌──────────────────────────┐
│ @router.post("/")     │───────▶│ create_item(name, desc)  │
│ @router.get("/{id}")  │───────▶│ get_item(item_id)        │
│ @router.get("/")      │───────▶│ list_items(limit, offset)│
│ @router.delete("/{id}")│──────▶│ delete_item(item_id)     │
└──────────────────────┘        └──────────────────────────┘
    Knows: HTTP, JSON               Knows: SQL, asyncpg
    Doesn't know: SQL               Doesn't know: HTTP
```

**Benefits:**
1. **Testable** — Test SQL logic without HTTP overhead
2. **Reusable** — Same query function works from routes, background tasks, CLI
3. **Swappable** — Replace asyncpg with SQLAlchemy without changing routes
4. **Readable** — Each layer has a single responsibility

---

## Database Migrations with Alembic

### What are migrations?

Migrations are version-controlled scripts that modify the database schema. Instead of running SQL manually, you write a script and Alembic applies it:

```
Version 001: CREATE TABLE items (...)         ← Current
Version 002: ALTER TABLE items ADD COLUMN category VARCHAR(100)  ← Future
Version 003: CREATE TABLE orders (...)        ← Future
```

### How it works in this project

1. **`alembic.ini`** — Points Alembic to the `migrations/` folder and database URL
2. **`migrations/env.py`** — Configures how Alembic connects (sync driver via psycopg2)
3. **`migrations/versions/001_create_items.py`** — The actual schema change

### Running migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Check current version
alembic current

# Rollback one version
alembic downgrade -1

# Create a new migration
alembic revision -m "add_category_column"
```

### Auto-migration in Docker

The `entrypoint.sh` script runs `alembic upgrade head` every time the container starts, ensuring the schema is always up-to-date without manual intervention.

---

## Common Gotchas

### 1. PgBouncer + Prepared Statements
PgBouncer in `transaction` mode doesn't support named prepared statements because the connection changes between transactions. asyncpg uses **anonymous** prepared statements by default, so this works fine.

### 2. PgBouncer + SET commands
`SET` commands are session-level, but in transaction pooling mode, "session" = "transaction." The `init` callback runs on the asyncpg side (before PgBouncer hands off the connection), so timeouts are correctly applied.

### 3. Connection exhaustion under load
If you see `pool.acquire()` hanging, the app-side pool is full (10 connections). Solutions:
- Increase `DB_POOL_MAX_SIZE`
- Optimize slow queries (check `db_query_duration_seconds` metric)
- Add connection wait timeout

### 4. Direct PostgreSQL vs PgBouncer
- **Alembic migrations** → Connect to PostgreSQL directly (port 5432) — DDL needs session mode
- **Application queries** → Connect through PgBouncer (port 6432) — transaction mode is fine

---

**← [API Reference](03-API_REFERENCE.md) | [Resilience Patterns →](05-RESILIENCE.md)**
