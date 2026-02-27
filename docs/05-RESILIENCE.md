# 05 — Resilience Patterns

> **Audience:** 🟡 Intermediate — Understand how the app survives database failures gracefully.

This document explains the two fault-tolerance patterns used in this project: **circuit breaker** and **retry with exponential backoff**.

---

## Table of Contents

- [Why Resilience Matters](#why-resilience-matters)
- [Pattern 1: Retry with Exponential Backoff](#pattern-1-retry-with-exponential-backoff)
- [Pattern 2: Circuit Breaker](#pattern-2-circuit-breaker)
- [How They Work Together](#how-they-work-together)
- [Real-World Failure Scenarios](#real-world-failure-scenarios)
- [Configuration Tuning](#configuration-tuning)
- [Code Walkthrough](#code-walkthrough)

---

## Why Resilience Matters

Databases aren't 100% reliable. They go down for:
- **Network blips** — A router hiccup drops the connection for 200ms
- **Maintenance** — PostgreSQL restarts for a config change
- **Overload** — Too many queries overwhelm the database
- **Hardware failure** — Disk dies, server crashes

**Without resilience patterns**, each of these causes a `500 Internal Server Error` for every user request during the outage.

**With resilience patterns**, the app can:
1. **Retry** transient failures automatically (user never notices)
2. **Fail fast** when the database is truly down (don't waste time waiting)
3. **Recover automatically** when the database comes back

---

## Pattern 1: Retry with Exponential Backoff

### The Concept (for beginners)

Imagine you're calling a friend and they don't pick up. You would:
1. Wait a few seconds, try again
2. Wait a bit longer, try again
3. If they still don't answer after 3 tries, give up

That's exactly what retry with exponential backoff does.

### How It Works

```
Attempt 1: Execute query
    ❌ Failed (ConnectionError)
    ⏳ Wait 0.5 seconds

Attempt 2: Execute query
    ❌ Failed (ConnectionError)
    ⏳ Wait 1.0 seconds

Attempt 3: Execute query
    ✅ Success! → Return result
    (or ❌ Failed → Give up, return error to user)
```

The wait time **doubles** each attempt (0.5s → 1s → 2s). This is "exponential backoff" — it prevents thousands of requests from retrying simultaneously and overwhelming the recovering database.

### Configuration

```python
db_retry = retry(
    retry=retry_if_exception_type(_TRANSIENT_EXCEPTIONS),  # Only retry these errors
    stop=stop_after_attempt(3),                            # Max 3 attempts
    wait=wait_exponential(multiplier=0.5, min=0.5, max=5), # 0.5s → 1s → 2s → ... (cap at 5s)
    reraise=True,                                          # After all attempts fail, raise the original error
)
```

### What gets retried?

Only **transient** (temporary) errors are retried:

| Exception                      | What It Means                    | Retryable? |
|--------------------------------|----------------------------------|:----------:|
| `PostgresConnectionError`      | Network issue to database        | ✅ Yes     |
| `InterfaceError`               | Connection dropped mid-query     | ✅ Yes     |
| `ConnectionRefusedError`       | Database isn't accepting connections | ✅ Yes  |
| `OSError`                      | Network-level failure            | ✅ Yes     |
| `UniqueViolationError`         | Duplicate key constraint         | ❌ No      |
| `UndefinedTableError`          | Table doesn't exist              | ❌ No      |
| `SyntaxError`                  | Bad SQL                          | ❌ No      |

**Why not retry everything?** Retrying a duplicate key error would fail every time. Retrying a syntax error is pointless. Only network-related errors have a chance of succeeding on the next attempt.

---

## Pattern 2: Circuit Breaker

### The Concept (for beginners)

Think of an electrical circuit breaker in your house. When there's a power surge:
1. The breaker **trips** (opens) — cuts the circuit to prevent damage
2. You wait for the problem to be fixed
3. You **manually reset** the breaker
4. If the problem is gone, power flows normally again

A software circuit breaker works the same way for database connections.

### The Three States

```
                          5 consecutive failures
    ┌──────────┐      ────────────────────────▶     ┌──────────┐
    │  CLOSED  │                                     │   OPEN   │
    │(normal)  │      ◀────────────────────────      │(rejecting│
    └──────────┘         success on test query        │ queries) │
         ▲                                            └──────────┘
         │                                                 │
         │              30 seconds elapsed                 │
         │                    ┌────────────┐               │
         └────────────────────│ HALF-OPEN  │◀──────────────┘
              success         │(testing)   │
                              └────────────┘
```

#### State: CLOSED (Normal Operation)
- All queries pass through to the database
- The circuit breaker counts consecutive failures
- If failures reach `fail_max` (5), the circuit **opens**

#### State: OPEN (Failure Mode)
- **All queries are immediately rejected** without touching the database
- This prevents a flood of requests from hitting an already-struggling database
- The error returned is `CircuitBreakerError`
- After `timeout_duration` (30 seconds), the circuit moves to **half-open**

#### State: HALF-OPEN (Testing)
- **One single test query** is allowed through
- If it succeeds → circuit **closes** (back to normal)
- If it fails → circuit **reopens** for another 30 seconds

### Why is this important?

**Without a circuit breaker:**
```
Database goes down
    → 1000 requests/sec × 5 second timeout = 5000 requests waiting
    → 5000 connections consumed
    → App becomes unresponsive
    → Database can't recover because of connection pressure
    → Cascading failure!
```

**With a circuit breaker:**
```
Database goes down
    → First 5 requests fail (circuit counts)
    → Circuit OPENS
    → Remaining 995 requests immediately get CircuitBreakerError (~1ms)
    → App stays responsive (returns error to users fast)
    → Database has no connection pressure
    → Database recovers
    → Circuit half-opens, test query succeeds
    → Circuit CLOSES, normal operation resumes
```

---

## How They Work Together

The two patterns are stacked as decorators on `execute_query()`:

```python
@db_retry                  # Outer: Retry the entire operation (including circuit breaker)
@db_circuit_breaker        # Inner: Fast-fail if circuit is open
async def execute_query(query, *args):
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)
```

### Execution flow

```
execute_query() called
    │
    ▼
┌─── Retry Layer (tenacity) ───────────────────────────────────┐
│                                                               │
│   Attempt 1:                                                  │
│   ┌─── Circuit Breaker Layer ─────────────────────────────┐   │
│   │  State = CLOSED? → Allow query                        │   │
│   │  State = OPEN?   → Raise CircuitBreakerError immediately│  │
│   │                                                       │   │
│   │  Execute query against database                       │   │
│   │  ├── Success → Return result ✅                       │   │
│   │  └── Failure → Record failure, raise exception        │   │
│   └───────────────────────────────────────────────────────┘   │
│                                                               │
│   Is exception retryable? (network error?)                    │
│   ├── Yes → Wait 0.5s, go to Attempt 2                       │
│   └── No  → Reraise immediately                              │
│                                                               │
│   Attempt 2: (same as above with 1s wait)                    │
│   Attempt 3: (same as above, last chance)                    │
│                                                               │
│   All attempts failed → Raise original exception              │
└───────────────────────────────────────────────────────────────┘
```

### Important interaction

The **retry layer wraps the circuit breaker**, meaning:
- If the circuit is OPEN, the retry layer will retry the `CircuitBreakerError`... but it's **not** in the retryable exception list, so it **immediately reraises**
- This means: open circuit = instant failure, no wasted retries

---

## Real-World Failure Scenarios

### Scenario 1: Brief Network Blip (50ms)

```
Request → execute_query()
    Attempt 1: ConnectionError (network blip)
    Wait 0.5s (network recovers in 50ms)
    Attempt 2: Success! ✅
    
User experience: 500ms slower than usual, but no error
```

### Scenario 2: PostgreSQL Restart (30 seconds)

```
Request 1: ConnectionError → retry → retry → fail (circuit: 1/5)
Request 2: ConnectionError → retry → retry → fail (circuit: 2/5)
Request 3: ConnectionError → retry → retry → fail (circuit: 3/5)
Request 4: ConnectionError → retry → retry → fail (circuit: 4/5)
Request 5: ConnectionError → retry → retry → fail (circuit: 5/5)
*** CIRCUIT OPENS ***

Request 6-1000: CircuitBreakerError instantly (~1ms each)

... 30 seconds pass, PostgreSQL restarts ...

Request 1001: half-open test → Success! ✅
*** CIRCUIT CLOSES ***

Request 1002+: Normal operation ✅
```

### Scenario 3: Invalid SQL (Programmer Error)

```
Request → execute_query("SELECT * FROM nonexistent_table")
    Attempt 1: UndefinedTableError
    Not in retryable exceptions → Reraise immediately
    
User experience: Instant 500 error (no wasted retries)
```

---

## Configuration Tuning

### When to increase retry attempts

| Situation                     | Recommended `stop_after_attempt` |
|-------------------------------|:---------------------------------:|
| Fast, reliable network        | 2                                |
| Cloud with occasional blips   | 3 (current default)             |
| Cross-region database         | 4-5                              |

### When to adjust circuit breaker

| Situation                          | `fail_max` | `timeout_duration` |
|------------------------------------|:----------:|:-------------------:|
| Critical production (fast recovery)| 3          | 15s                 |
| Standard production (current)      | 5          | 30s                 |
| Tolerant (batch processing)        | 10         | 60s                 |

### Env vars for tuning

```env
# Circuit Breaker
CB_FAIL_MAX=5              # Failures before circuit opens
CB_TIMEOUT_DURATION=30     # Seconds in open state

# Note: Retry attempts are hardcoded (3). Change in resilience.py if needed.
```

---

## Code Walkthrough

### `app/db/resilience.py` — Line by Line

```python
# 1. Define which exceptions are "transient" (retryable)
_TRANSIENT_EXCEPTIONS = (
    asyncpg.PostgresConnectionError,  # Network issue
    asyncpg.InterfaceError,           # Connection dropped
    ConnectionRefusedError,           # DB not accepting connections
    OSError,                          # Low-level network error
)

# 2. Create the retry decorator
db_retry = retry(
    retry=retry_if_exception_type(_TRANSIENT_EXCEPTIONS),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
    reraise=True,
)

# 3. Create the circuit breaker
db_circuit_breaker = CircuitBreaker(
    fail_max=settings.cb_fail_max,           # 5 failures
    timeout_duration=settings.cb_timeout_duration,  # 30 seconds
)

# 4. The combined helper — every query goes through this
@db_retry
@db_circuit_breaker
async def execute_query(query, *args, fetch_one=False, fetch_all=False):
    pool = get_pool()
    start = time.perf_counter()

    try:
        async with pool.acquire() as conn:      # Borrow a connection
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
        DB_QUERY_DURATION.observe(elapsed)       # Record latency in Prometheus
```

---

**← [Database Deep Dive](04-DATABASE.md) | [Observability & Monitoring →](06-OBSERVABILITY.md)**
