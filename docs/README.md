# 📚 Documentation — FastAPI + PostgreSQL POC

Welcome to the documentation for the **FastAPI + PostgreSQL POC** — an industry-standard async web application showcasing production-ready patterns.

> **Tip:** If you're new to this project, start with [Getting Started](01-GETTING_STARTED.md) and work your way down.

---

## Documentation Index

| #  | Document                                              | Audience             | What You'll Learn                                     |
|----|-------------------------------------------------------|----------------------|-------------------------------------------------------|
| 01 | [Getting Started](01-GETTING_STARTED.md)              | 🟢 Beginner          | Prerequisites, setup, running the app, first API call |
| 02 | [Project Structure](02-PROJECT_STRUCTURE.md)          | 🟢 Beginner          | File-by-file walkthrough of the entire codebase       |
| 03 | [API Reference](03-API_REFERENCE.md)                  | 🟡 Intermediate      | Every endpoint with curl/PowerShell examples          |
| 04 | [Database Deep Dive](04-DATABASE.md)                  | 🟡 Intermediate      | PostgreSQL, asyncpg, PgBouncer, connection pooling    |
| 05 | [Resilience Patterns](05-RESILIENCE.md)               | 🟡 Intermediate      | Circuit breaker, retry with exponential backoff       |
| 06 | [Observability & Monitoring](06-OBSERVABILITY.md)     | 🔴 Advanced          | Prometheus metrics, middleware, dashboarding           |
| 07 | [Configuration Reference](07-CONFIGURATION.md)       | 🔴 Advanced          | Every environment variable, tuning guide              |
| 08 | [Deployment & Docker](08-DEPLOYMENT.md)               | 🔴 Advanced          | Docker, Compose, migrations, production checklist     |

---

## Quick Links

- **[Architecture Overview](../ARCHITECTURE.md)** — High-level system diagram and design decisions
- **[Swagger UI](http://localhost:8000/docs)** — Interactive API documentation (when running)
- **[Prometheus Dashboard](http://localhost:9090)** — Metrics explorer (when running)

---

## Audience Guide

### 🟢 Beginner — "I want to understand and run this project"
Start with documents **01** and **02**. These explain what the project does, how to set it up, and walk through every file in the codebase.

### 🟡 Intermediate — "I want to understand the design decisions"
Documents **03**, **04**, and **05** explain the API design, why we use PgBouncer, how connection pooling works, and how the app handles database failures gracefully.

### 🔴 Advanced — "I want to deploy and maintain this in production"
Documents **06**, **07**, and **08** cover Prometheus metrics, production tuning, Docker deployment, and operational best practices.
