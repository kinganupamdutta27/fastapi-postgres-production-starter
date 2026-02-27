# 01 — Getting Started

> **Audience:** 🟢 Beginner — No prior experience with this project required.

This guide will take you from zero to a running application with your first successful API call.

---

## Table of Contents

- [What Is This Project?](#what-is-this-project)
- [Prerequisites](#prerequisites)
- [Clone & Setup](#clone--setup)
- [Option A: Run with Docker (Recommended)](#option-a-run-with-docker-recommended)
- [Option B: Run Locally (Without Docker)](#option-b-run-locally-without-docker)
- [Your First API Call](#your-first-api-call)
- [Exploring the API](#exploring-the-api)
- [Stopping the Application](#stopping-the-application)
- [Common Issues & Fixes](#common-issues--fixes)

---

## What Is This Project?

This is a **proof-of-concept (POC)** web application that demonstrates how to build a production-quality backend API using:

- **FastAPI** — A modern Python web framework that handles HTTP requests and responses
- **PostgreSQL** — A database that stores your data permanently
- **PgBouncer** — A connection pooler that sits between the app and the database to manage connections efficiently
- **Prometheus** — A monitoring tool that tracks application performance

Think of it as a "create, read, and delete items" app — simple in functionality but built with the same patterns used by large-scale production systems.

### What can the app do?

| Action          | Plain English                           |
|-----------------|------------------------------------------|
| Create an item  | Save a new item (with a name and optional description) to the database |
| Get an item     | Retrieve a single item by its unique ID  |
| List all items  | Show all items with pagination support   |
| Delete an item  | Remove an item from the database         |
| Health check    | Verify the app and database are running  |

---

## Prerequisites

Before you begin, make sure you have these installed on your computer:

### For Docker Setup (Recommended)

| Software        | Minimum Version | Check Command            | Download Link                                    |
|-----------------|-----------------|--------------------------|--------------------------------------------------|
| Docker Desktop  | 4.x             | `docker --version`       | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) |
| Git             | 2.x             | `git --version`          | [git-scm.com](https://git-scm.com/)             |

### For Local Setup (Without Docker)

| Software        | Minimum Version | Check Command            | Download Link                                    |
|-----------------|-----------------|--------------------------|--------------------------------------------------|
| Python          | 3.11+           | `python --version`       | [python.org](https://www.python.org/downloads/)  |
| PostgreSQL      | 14+             | `psql --version`         | [postgresql.org](https://www.postgresql.org/download/) |
| Git             | 2.x             | `git --version`          | [git-scm.com](https://git-scm.com/)             |

---

## Clone & Setup

```bash
# Clone the repository
git clone <your-repo-url>
cd fastapi-postgres-poc
```

---

## Option A: Run with Docker (Recommended)

This is the easiest way — Docker handles everything (database, connection pooler, app, monitoring) in one command.

### Step 1: Start Docker Desktop

Open **Docker Desktop** from your Start menu (Windows) or Applications (Mac). Wait until the Docker icon in your system tray shows "Docker Desktop is running".

### Step 2: Build and Start

```powershell
# Build the application image
docker compose build

# Start all services
docker compose up
```

You'll see logs from all four services (PostgreSQL, PgBouncer, App, Prometheus). Wait until you see:

```
app-1  | INFO:     Started server process [1]
app-1  | INFO:     Waiting for application startup.
app-1  | INFO:     Application startup complete.
app-1  | INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Step 3: Verify

Open your browser and go to: **http://localhost:8000/docs**

You should see the Swagger UI — an interactive API documentation page.

### What's Running?

| Service     | URL                         | Purpose                         |
|-------------|-----------------------------|---------------------------------|
| FastAPI App | http://localhost:8000       | Your API server                 |
| Swagger UI  | http://localhost:8000/docs  | Interactive API documentation   |
| Prometheus  | http://localhost:9090       | Metrics & monitoring dashboard  |
| PostgreSQL  | localhost:5432              | Database (not web-accessible)   |
| PgBouncer   | localhost:6432              | Connection pooler (internal)    |

---

## Option B: Run Locally (Without Docker)

### Step 1: Set Up PostgreSQL

Install PostgreSQL and create the database:

```bash
# Connect to PostgreSQL
psql -U postgres

# Create the user and database
CREATE USER app_user WITH PASSWORD 'app_secret';
CREATE DATABASE app_db OWNER app_user;
\q
```

### Step 2: Create a Virtual Environment

```powershell
# Create a virtual environment
python -m venv venv

# Activate it (Windows PowerShell)
.\venv\Scripts\Activate

# Activate it (Mac/Linux)
source venv/bin/activate
```

### Step 3: Install Dependencies

```powershell
pip install -r requirements.txt
```

### Step 4: Configure Environment

The `.env` file is already configured for local development. If your PostgreSQL is on a different port or uses different credentials, edit `.env`:

```env
DATABASE_HOST=localhost
DATABASE_PORT=5432        # Direct to PostgreSQL (not PgBouncer)
DATABASE_USER=app_user
DATABASE_PASSWORD=app_secret
DATABASE_NAME=app_db
```

> **Note:** When running locally without PgBouncer, change the port to `5432` (PostgreSQL's default port).

### Step 5: Run Database Migrations

```powershell
alembic upgrade head
```

This creates the `items` table in your database.

### Step 6: Start the Application

```powershell
uvicorn app.main:app --reload
```

The `--reload` flag auto-restarts the server when you change code (development mode).

---

## Your First API Call

Now that the app is running, let's create your first item!

### Using Swagger UI (Easiest)

1. Open **http://localhost:8000/docs** in your browser
2. Click on **POST /items/** to expand it
3. Click **"Try it out"**
4. Replace the request body with:
   ```json
   {
     "name": "My First Item",
     "description": "Created from Swagger UI!"
   }
   ```
5. Click **"Execute"**
6. You should see a **201 Created** response with your new item, including its auto-generated UUID

### Using PowerShell

```powershell
# Create an item
Invoke-RestMethod -Uri http://localhost:8000/items/ -Method POST -ContentType "application/json" -Body '{"name":"My First Item","description":"Hello from PowerShell!"}'

# List all items
Invoke-RestMethod -Uri http://localhost:8000/items/ -Method GET

# Check app health
Invoke-RestMethod -Uri http://localhost:8000/health/ -Method GET
```

### Using curl (Mac/Linux)

```bash
# Create an item
curl -X POST http://localhost:8000/items/ \
  -H "Content-Type: application/json" \
  -d '{"name":"My First Item","description":"Hello from curl!"}'

# List all items
curl http://localhost:8000/items/

# Check app health
curl http://localhost:8000/health/
```

---

## Exploring the API

After creating a few items, try these operations:

```powershell
# Get a specific item (replace with your item's UUID)
Invoke-RestMethod -Uri http://localhost:8000/items/<uuid-here> -Method GET

# List items with pagination (first 10 items)
Invoke-RestMethod -Uri "http://localhost:8000/items/?limit=10&offset=0" -Method GET

# Delete an item
Invoke-RestMethod -Uri http://localhost:8000/items/<uuid-here> -Method DELETE

# Check database connectivity
Invoke-RestMethod -Uri http://localhost:8000/health/ready -Method GET
```

---

## Stopping the Application

### Docker
Press `Ctrl+C` in the terminal, then:
```powershell
docker compose down       # Stop and remove containers
docker compose down -v    # Also remove the database volume (deletes all data!)
```

### Local
Press `Ctrl+C` in the terminal running uvicorn.

---

## Common Issues & Fixes

### "Docker Desktop is not running"
**Error:** `error during connect: ... open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified`

**Fix:** Open Docker Desktop from the Start menu and wait for it to fully start before running `docker compose` commands.

### "Connection refused" on startup
**Error:** `ConnectionRefusedError: [Errno 111] Connection refused`

**Fix:** This usually means the app started before the database was ready. The Docker Compose configuration includes health checks to prevent this, but if it happens, simply restart with `docker compose down && docker compose up`.

### "No module named 'app'"
**Error:** `ModuleNotFoundError: No module named 'app'`

**Fix:** Make sure you're running commands from the project root directory (`fastapi-postgres-poc/`), not from inside a subdirectory.

### "Port already in use"
**Error:** `OSError: [Errno 98] Address already in use`

**Fix:** Another process is using port 8000. Either stop it or run on a different port:
```powershell
uvicorn app.main:app --reload --port 8001
```

---

**Next:** [Project Structure →](02-PROJECT_STRUCTURE.md)
