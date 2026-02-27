# 03 — API Reference

> **Audience:** 🟡 Intermediate — Complete endpoint reference with examples.

This document covers every API endpoint, including request/response formats, status codes, validation rules, and practical examples in both PowerShell and curl.

---

## Table of Contents

- [Base URL](#base-url)
- [Authentication](#authentication)
- [Health Endpoints](#health-endpoints)
  - [GET /health/ — Liveness Probe](#get-health--liveness-probe)
  - [GET /health/ready — Readiness Probe](#get-healthready--readiness-probe)
- [Items Endpoints](#items-endpoints)
  - [POST /items/ — Create Item](#post-items--create-item)
  - [GET /items/ — List Items](#get-items--list-items)
  - [GET /items/{item_id} — Get Item](#get-itemsitem_id--get-item)
  - [DELETE /items/{item_id} — Delete Item](#delete-itemsitem_id--delete-item)
- [Metrics Endpoint](#metrics-endpoint)
- [Error Responses](#error-responses)
- [Data Types](#data-types)

---

## Base URL

| Environment | URL                       |
|-------------|---------------------------|
| Local       | `http://localhost:8000`    |
| Docker      | `http://localhost:8000`    |
| Swagger UI  | `http://localhost:8000/docs` |

## Authentication

This POC does **not** include authentication. All endpoints are publicly accessible. In a production application, you would add JWT tokens, API keys, or OAuth2.

---

## Health Endpoints

### GET /health/ — Liveness Probe

Returns OK if the application process is running. This endpoint does **not** check database connectivity.

**Use case:** Container orchestrators (Docker, Kubernetes) call this to determine if the container needs to be restarted.

**Request:**
```powershell
# PowerShell
Invoke-RestMethod -Uri http://localhost:8000/health/ -Method GET

# curl
curl http://localhost:8000/health/
```

**Response (200 OK):**
```json
{
  "status": "ok"
}
```

---

### GET /health/ready — Readiness Probe

Checks if the application can serve traffic by verifying database connectivity (executes `SELECT 1`).

**Use case:** Load balancers use this to decide whether to route traffic to this instance. A container can be alive but not ready (e.g., database is down).

**Request:**
```powershell
# PowerShell
Invoke-RestMethod -Uri http://localhost:8000/health/ready -Method GET

# curl
curl http://localhost:8000/health/ready
```

**Response — Healthy (200 OK):**
```json
{
  "status": "ok",
  "database": "connected"
}
```

**Response — Degraded (200 OK):**
```json
{
  "status": "degraded",
  "database": "disconnected"
}
```

> **Note:** This returns 200 even when degraded. In production, you might return 503 to signal the load balancer to stop sending traffic.

---

## Items Endpoints

### POST /items/ — Create Item

Creates a new item in the database with an auto-generated UUID.

**Request Body (JSON):**

| Field         | Type     | Required | Constraints       | Example                |
|---------------|----------|----------|-------------------|------------------------|
| `name`        | string   | ✅ Yes   | 1–255 characters  | `"Widget X"`           |
| `description` | string   | ❌ No    | Max 2000 chars    | `"A high-quality widget"` |

**Request:**
```powershell
# PowerShell
Invoke-RestMethod -Uri http://localhost:8000/items/ -Method POST `
  -ContentType "application/json" `
  -Body '{"name":"Widget X","description":"A high-quality widget"}'

# curl
curl -X POST http://localhost:8000/items/ \
  -H "Content-Type: application/json" \
  -d '{"name":"Widget X","description":"A high-quality widget"}'
```

**Response (201 Created):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "Widget X",
  "description": "A high-quality widget",
  "created_at": "2026-02-27T09:15:30.123456Z",
  "updated_at": "2026-02-27T09:15:30.123456Z"
}
```

**Error — Missing name (422 Unprocessable Entity):**
```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "name"],
      "msg": "Field required",
      "input": {}
    }
  ]
}
```

**Error — Empty name (422 Unprocessable Entity):**
```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "name"],
      "msg": "String should have at least 1 character",
      "input": ""
    }
  ]
}
```

---

### GET /items/ — List Items

Returns a paginated list of all items, ordered by creation date (newest first).

**Query Parameters:**

| Parameter | Type | Default | Constraints | Description         |
|-----------|------|---------|-------------|---------------------|
| `limit`   | int  | 50      | 1–200       | Items per page      |
| `offset`  | int  | 0       | ≥ 0         | Items to skip       |

**Request:**
```powershell
# PowerShell — default (first 50 items)
Invoke-RestMethod -Uri http://localhost:8000/items/ -Method GET

# PowerShell — with pagination
Invoke-RestMethod -Uri "http://localhost:8000/items/?limit=10&offset=0" -Method GET

# curl
curl "http://localhost:8000/items/?limit=10&offset=0"
```

**Response (200 OK):**
```json
{
  "items": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "name": "Widget X",
      "description": "A high-quality widget",
      "created_at": "2026-02-27T09:15:30.123456Z",
      "updated_at": "2026-02-27T09:15:30.123456Z"
    },
    {
      "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "name": "Gadget Y",
      "description": null,
      "created_at": "2026-02-27T09:10:00.000000Z",
      "updated_at": "2026-02-27T09:10:00.000000Z"
    }
  ],
  "count": 2
}
```

**Pagination example:** To implement "page 3 with 10 items per page":
```
limit=10&offset=20    (skip first 20 items, show next 10)
```

---

### GET /items/{item_id} — Get Item

Retrieve a single item by its UUID.

**Path Parameters:**

| Parameter | Type | Format | Example                                |
|-----------|------|--------|----------------------------------------|
| `item_id` | UUID | v4     | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |

**Request:**
```powershell
# PowerShell
Invoke-RestMethod -Uri http://localhost:8000/items/a1b2c3d4-e5f6-7890-abcd-ef1234567890 -Method GET

# curl
curl http://localhost:8000/items/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Response — Found (200 OK):**
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "Widget X",
  "description": "A high-quality widget",
  "created_at": "2026-02-27T09:15:30.123456Z",
  "updated_at": "2026-02-27T09:15:30.123456Z"
}
```

**Response — Not Found (404):**
```json
{
  "detail": "Item not found"
}
```

**Response — Invalid UUID (422):**
```json
{
  "detail": [
    {
      "type": "uuid_parsing",
      "loc": ["path", "item_id"],
      "msg": "Input should be a valid UUID"
    }
  ]
}
```

---

### DELETE /items/{item_id} — Delete Item

Permanently removes an item from the database.

**Request:**
```powershell
# PowerShell
Invoke-RestMethod -Uri http://localhost:8000/items/a1b2c3d4-e5f6-7890-abcd-ef1234567890 -Method DELETE

# curl
curl -X DELETE http://localhost:8000/items/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**Response — Deleted (204 No Content):**
No response body. The 204 status code confirms the deletion succeeded.

**Response — Not Found (404):**
```json
{
  "detail": "Item not found"
}
```

---

## Metrics Endpoint

### GET /metrics — Prometheus Metrics

Exposes application metrics in Prometheus text format. This endpoint is **not** listed in Swagger UI (it's excluded from the OpenAPI schema).

**Request:**
```powershell
# PowerShell
Invoke-RestMethod -Uri http://localhost:8000/metrics -Method GET

# curl
curl http://localhost:8000/metrics
```

**Response (200 OK):** Prometheus text format
```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",path="/health/",status="200"} 5.0
http_requests_total{method="POST",path="/items/",status="201"} 2.0

# HELP db_query_duration_seconds Time spent executing a single database query
# TYPE db_query_duration_seconds histogram
db_query_duration_seconds_bucket{le="0.005"} 3.0
db_query_duration_seconds_bucket{le="0.01"} 5.0
...
```

---

## Error Responses

All error responses follow a consistent format:

### 404 Not Found
```json
{
  "detail": "Item not found"
}
```

### 422 Validation Error
```json
{
  "detail": [
    {
      "type": "error_type",
      "loc": ["body", "field_name"],
      "msg": "Human-readable error message",
      "input": "the_invalid_value"
    }
  ]
}
```

### 500 Internal Server Error
```json
{
  "detail": "Internal Server Error"
}
```

### HTTP Status Code Reference

| Code | Meaning                | When It Happens                         |
|------|------------------------|-----------------------------------------|
| 200  | OK                     | Successful read operation               |
| 201  | Created                | Item successfully created               |
| 204  | No Content             | Item successfully deleted               |
| 404  | Not Found              | Item with given UUID doesn't exist      |
| 422  | Unprocessable Entity   | Request validation failed               |
| 500  | Internal Server Error  | Unexpected server error                 |

---

## Data Types

### Item Object

| Field         | Type     | Format              | Nullable | Description                    |
|---------------|----------|---------------------|----------|--------------------------------|
| `id`          | string   | UUID v4             | No       | Auto-generated unique identifier |
| `name`        | string   | 1–255 chars         | No       | Item name                      |
| `description` | string   | Max 2000 chars      | Yes      | Optional description           |
| `created_at`  | string   | ISO 8601 datetime   | No       | When the item was created (UTC)|
| `updated_at`  | string   | ISO 8601 datetime   | No       | When the item was last updated |

---

**← [Project Structure](02-PROJECT_STRUCTURE.md) | [Database Deep Dive →](04-DATABASE.md)**
