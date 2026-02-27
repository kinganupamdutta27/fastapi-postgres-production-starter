# 06 — Observability & Monitoring

> **Audience:** 🔴 Advanced — Understand the metrics, middleware, and how to monitor the app in production.

---

## Table of Contents

- [What Is Observability?](#what-is-observability)
- [The Three Pillars](#the-three-pillars)
- [Metrics Architecture](#metrics-architecture)
- [Prometheus Metrics Reference](#prometheus-metrics-reference)
- [HTTP Middleware](#http-middleware)
- [Database Pool Gauges](#database-pool-gauges)
- [Database Query Timing](#database-query-timing)
- [Prometheus Setup](#prometheus-setup)
- [Useful PromQL Queries](#useful-promql-queries)
- [Adding Grafana (Optional)](#adding-grafana-optional)
- [Adding Custom Metrics](#adding-custom-metrics)

---

## What Is Observability?

Observability is the ability to understand what's happening inside your application **without modifying it at runtime**. It answers questions like:

- How many requests per second is the app handling?
- What's the 95th-percentile response time?
- Is the database connection pool running out of connections?
- Which endpoint is the slowest?

**Without observability:** You find out something is wrong when users complain.
**With observability:** You see degradation in metrics before users notice.

---

## The Three Pillars

| Pillar    | What                                    | This Project       |
|-----------|-----------------------------------------|---------------------|
| **Metrics** | Numeric measurements over time         | ✅ Prometheus       |
| **Logs**    | Timestamped text events                | ✅ Python logging   |
| **Traces**  | Request journey across services        | ❌ Not implemented  |

This project focuses on **metrics** via Prometheus.

---

## Metrics Architecture

```
┌─────────────────────────────────────────────────────────┐
│  FastAPI Application                                     │
│                                                         │
│  ┌─────────────────┐    ┌────────────────┐              │
│  │  HTTP Middleware │──▶│  metrics.py     │              │
│  │  (every request)│    │                │              │
│  └─────────────────┘    │  HTTP_REQUESTS │              │
│                         │  HTTP_DURATION │              │
│  ┌─────────────────┐    │  DB_QUERY_DUR  │              │
│  │  resilience.py  │──▶│  DB_POOL_SIZE  │              │
│  │  (every query)  │    │  DB_POOL_FREE  │              │
│  └─────────────────┘    └───────┬────────┘              │
│                                 │                        │
│  ┌─────────────────┐            │                        │
│  │  Pool gauge task │───────────┘                        │
│  │  (every 5 sec)  │                                     │
│  └─────────────────┘                                     │
│                                                         │
│              GET /metrics ──────────────────────┐       │
└─────────────────────────────────────────────────┼───────┘
                                                   │
                                                   ▼
                                          ┌──────────────┐
                                          │  Prometheus   │
                                          │  (scrapes     │
                                          │   every 15s)  │
                                          └──────────────┘
```

---

## Prometheus Metrics Reference

### HTTP Metrics

| Metric Name                      | Type      | Labels                 | Description                      |
|----------------------------------|-----------|------------------------|----------------------------------|
| `http_requests_total`            | Counter   | method, path, status   | Total number of HTTP requests    |
| `http_request_duration_seconds`  | Histogram | method, path           | Request latency distribution     |

**Counter** — Only goes up. Useful for rates (requests/second).
**Histogram** — Records the distribution of values in configurable buckets. Useful for percentiles (p50, p95, p99).

**Histogram buckets** for HTTP requests:
```
10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s, 2.5s, 5s, 10s
```

### Database Metrics

| Metric Name                  | Type      | Labels | Description                           |
|------------------------------|-----------|--------|---------------------------------------|
| `db_query_duration_seconds`  | Histogram | —      | Time spent executing database queries |
| `db_pool_size`               | Gauge     | —      | Current connections in the pool       |
| `db_pool_free_size`          | Gauge     | —      | Idle connections in the pool          |

**Gauge** — Goes up and down. Represents a current value (like a speedometer).

**Histogram buckets** for DB queries:
```
5ms, 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s, 2.5s, 5s
```

---

## HTTP Middleware

**File:** `app/observability/middleware.py`

The `PrometheusMiddleware` wraps **every HTTP request** and records metrics automatically:

```
Request arrives
    │
    ▼
middleware.dispatch()
    ├── Skip if path == "/metrics" (no self-instrumentation)
    ├── Record start time
    ├── Call the actual route handler
    ├── Record elapsed time
    ├── Increment http_requests_total{method, path, status}
    └── Observe http_request_duration_seconds{method, path}
```

**Why skip `/metrics`?** If we instrument the metrics endpoint itself, scraping metrics would create metrics about scraping metrics — an infinite feedback loop that inflates the data.

### What the labels tell you

```
http_requests_total{method="POST", path="/items/", status="201"}  → 42
http_requests_total{method="GET",  path="/items/", status="200"}  → 156
http_requests_total{method="GET",  path="/items/abc", status="404"} → 3
```

This tells you: 42 items were created, 156 list requests, 3 "not found" lookups.

---

## Database Pool Gauges

**File:** `app/main.py` — `_update_pool_gauges()` background task

A background `asyncio.Task` runs every **5 seconds** and updates two gauges:

```python
DB_POOL_SIZE.set(pool.get_size())         # Total connections
DB_POOL_FREE_SIZE.set(pool.get_idle_size())  # Idle connections
```

**How to interpret:**
```
db_pool_size = 10      # Pool is at max capacity
db_pool_free_size = 0  # ⚠️ All connections in use — new queries will wait!

db_pool_size = 4       # 4 connections open
db_pool_free_size = 3  # ✅ 3 idle — plenty of headroom
```

**Alert rule idea:** If `db_pool_free_size == 0` for more than 30 seconds, your pool is exhausted and queries are queuing.

---

## Database Query Timing

**File:** `app/db/resilience.py` — inside `execute_query()`

Every database query's execution time is recorded in `db_query_duration_seconds`:

```python
start = time.perf_counter()
# ... execute query ...
elapsed = time.perf_counter() - start
DB_QUERY_DURATION.observe(elapsed)  # Record in histogram
```

**This metric includes** the full time from acquiring a pooled connection through query execution to result return.

---

## Prometheus Setup

### Scrape Configuration

**File:** `infra/prometheus.yml`

```yaml
global:
  scrape_interval: 15s      # How often Prometheus fetches /metrics
  evaluation_interval: 15s  # How often Prometheus evaluates alert rules

scrape_configs:
  - job_name: "fastapi-app"
    metrics_path: /metrics
    static_configs:
      - targets: ["app:8000"]
        labels:
          instance: "fastapi-poc"
```

**How it works:**
1. Prometheus runs as a Docker container alongside the app
2. Every 15 seconds, it sends `GET http://app:8000/metrics`
3. The app returns all metrics in Prometheus text format
4. Prometheus stores them in its time-series database
5. You query them via PromQL at `http://localhost:9090`

### Accessing Prometheus

With the Docker stack running, open: **http://localhost:9090**

---

## Useful PromQL Queries

Open Prometheus at `http://localhost:9090` and try these queries:

### Request Rate

```promql
# Requests per second (over the last 5 minutes)
rate(http_requests_total[5m])

# Requests per second by endpoint
sum by(path) (rate(http_requests_total[5m]))

# Error rate (4xx + 5xx)
sum(rate(http_requests_total{status=~"[45].."}[5m]))
```

### Latency

```promql
# Average request latency
rate(http_request_duration_seconds_sum[5m]) / rate(http_request_duration_seconds_count[5m])

# 95th percentile request latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# 95th percentile DB query latency
histogram_quantile(0.95, rate(db_query_duration_seconds_bucket[5m]))
```

### Connection Pool

```promql
# Current pool utilization (% of connections in use)
1 - (db_pool_free_size / db_pool_size)

# Pool is exhausted (all connections busy)
db_pool_free_size == 0
```

---

## Adding Grafana (Optional)

To add a Grafana dashboard, add this to `docker-compose.yml`:

```yaml
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - grafana-data:/var/lib/grafana
    depends_on:
      - prometheus
```

And add `grafana-data:` to the `volumes:` section.

Then:
1. Open `http://localhost:3000` (default: admin/admin)
2. Add Prometheus as a data source: `http://prometheus:9090`
3. Create dashboards using the PromQL queries above

---

## Adding Custom Metrics

To add your own metrics, follow this pattern:

### Step 1: Define the metric in `metrics.py`

```python
from prometheus_client import Counter

ITEMS_CREATED_TOTAL = Counter(
    "items_created_total",
    "Total number of items created",
    ["user_id"],  # Optional labels
)
```

### Step 2: Record values in your code

```python
from app.observability.metrics import ITEMS_CREATED_TOTAL

async def create_item(payload):
    item = await repository.create_item(...)
    ITEMS_CREATED_TOTAL.labels(user_id="anonymous").inc()
    return item
```

### Step 3: Query in Prometheus

```promql
rate(items_created_total[5m])  # Items created per second
```

---

**← [Resilience Patterns](05-RESILIENCE.md) | [Configuration Reference →](07-CONFIGURATION.md)**
