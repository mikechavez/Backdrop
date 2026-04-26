# Application Entry Points & Initialization

## Overview

This document traces how the application starts: FastAPI server initialization, Celery worker startup, beat scheduler setup, and CLI commands. Understanding entry points enables debugging startup failures and verifying correct component initialization.

**Anchor:** `#application-entrypoints`

## Architecture

### Key Components

- **FastAPI Application**: REST API server exposing briefing endpoints
- **Celery Worker**: Long-running process executing async tasks
- **Celery Beat Scheduler**: Periodic task dispatcher
- **Configuration Loader**: Initializes settings from environment
- **Database Client**: Establishes MongoDB connection pool
- **LLM Provider**: Initializes Claude API client

### Initialization Sequence

```
1. Load Configuration      → Parse environment variables
2. Initialize Database     → Connect to MongoDB, register collections
3. Create FastAPI App      → Instantiate FastAPI() with routes
4. Register Blueprints     → Attach API routers to app
5. Initialize Celery       → Register tasks and beat schedule
6. Start Server/Worker     → Begin listening for requests/tasks
```

## Implementation Details

### FastAPI Application Initialization

**File:** `src/crypto_news_aggregator/main.py:1-60`

Main entry point for the web server:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from crypto_news_aggregator.api.v1 import router

app = FastAPI(
    title="Crypto News Aggregator API",
    description="Market briefings and signal analysis",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", ...],  # Line 18
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(router, prefix="/api/v1")  # Line 25
```

**Key initialization steps:**

1. **Sentry initialization** (lines 8-22): Runs at module load time, before FastAPI instantiation — not in a startup event. Integrates with both FastAPI and Celery.
2. **FastAPI instantiation** (line 8): Creates app instance
3. **CORS middleware** (line 11-17): Enables frontend requests
4. **Router registration** (line 25-30): Includes API endpoints from `api/v1/__init__.py`
5. **Lifespan events** (line 32-50): Startup/shutdown hooks for database initialization

**File:** `src/crypto_news_aggregator/main.py:32-50` (Lifespan events)

```python
@app.on_event("startup")
async def startup_event():
    """Initialize database clients on application startup."""
    from crypto_news_aggregator.db.mongodb import get_database
    db = await get_database()
    logger.info("✓ Database connection established")

@app.on_event("shutdown")
async def shutdown_event():
    """Close connections on shutdown."""
    # Connection cleanup
    logger.info("✓ Graceful shutdown")
```

**Launch command:**
```bash
uvicorn src/crypto_news_aggregator/main:app --host 0.0.0.0 --port 8000 --reload
```

### Database Initialization

**File:** `src/crypto_news_aggregator/db/mongodb.py:1-80`

Database client setup:

```python
class MongoDBClient:
    def __init__(self, uri: str):
        self.client = AsyncClient(uri)  # Line 18
        self.db = self.client.get_database("crypto_news")  # Line 19

async def get_database():
    """Singleton database connection."""
    settings = get_settings()
    client = MongoDBClient(settings.MONGODB_URI)  # Line 45
    await client.connect()  # Line 46
    return client
```

**Configuration source:**
- **File:** `src/crypto_news_aggregator/core/config.py:1-50`
- **MONGODB_URI**: From environment variable (`.env` or production secrets)
- **Connection pool size**: 10 (default, configurable)
- **Retry policy**: 3 retries with exponential backoff

**Collections registered** (line 85-120):
- `daily_briefings` - Generated briefings
- `narratives` - Story threads
- `articles` - News articles
- `entity_mentions` - Entity index
- `signals` - Market signals
- `llm_traces` - LLM call traces with cost attribution (TTL 30 days; Sprint 13)
- `llm_cache` - LLM request/response cache (BUG-072)

**Health check:**
```bash
# Verify MongoDB connection
python -c "
import asyncio
from crypto_news_aggregator.db.mongodb import get_database
db = asyncio.run(get_database())
print('✓ Connected to:', db.db.name)
"
```

### Celery Worker Initialization

**File:** `src/crypto_news_aggregator/worker.py:1-40`

Worker entry point:

```python
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # Line 8

from crypto_news_aggregator.tasks import celery_app

if __name__ == "__main__":
    celery_app.worker_main(
        argv=["worker", "-l", "info", "-c", "4"]  # Line 18
    )
```

**Key initialization:**
1. **Path setup** (line 8): Ensures imports work correctly
2. **Import tasks** (line 12): Triggers `@shared_task` decorator registration
3. **Worker start** (line 15-18): Launches 4 concurrent workers

**Celery app configuration:**
- **File:** `src/crypto_news_aggregator/tasks/__init__.py:1-30`
- **Broker**: Redis (from CELERY_BROKER_URL)
- **Backend**: Redis (from CELERY_RESULT_BACKEND)
- **Task queues**: "default" and "alerts"
- **Task serialization**: JSON

**Launch command:**
```bash
celery -A crypto_news_aggregator.tasks worker --loglevel=info --concurrency=4
```

**Verification:**
```bash
# List registered tasks
celery -A crypto_news_aggregator.tasks inspect registered
# Output: Should include "generate_morning_briefing", "generate_afternoon_briefing", etc.
```

### Celery Beat Scheduler Initialization

**File:** `src/crypto_news_aggregator/tasks/beat_schedule.py:1-102`

Beat schedule configuration:

```python
from celery.schedules import crontab

beat_schedule = {
    "generate_morning_briefing": {
        "task": "generate_morning_briefing",           # Line 48
        "schedule": crontab(hour=8, minute=0),        # Line 49 (8 AM EST)
        "kwargs": {"force": False},                   # Line 50
        "options": {"expires": 3600}                  # Line 51
    },
    "generate_afternoon_briefing": {
        "task": "generate_afternoon_briefing",         # Line 64
        "schedule": crontab(hour=14, minute=0),       # Line 65 (2 PM EST)
        "kwargs": {"force": False},
        "options": {"expires": 3600}
    },
    "generate_evening_briefing": {
        "task": "generate_evening_briefing",           # Line 77
        "schedule": crontab(hour=20, minute=0),       # Line 78 (8 PM EST)
        "kwargs": {"force": False},
        "options": {"expires": 3600}
    }
}
```

**Integration with Celery app:**
- **File:** `src/crypto_news_aggregator/tasks/__init__.py:25`
- **Application:** `celery_app.conf.beat_schedule = beat_schedule`

**Launch command:**
```bash
celery -A crypto_news_aggregator.tasks beat --loglevel=info
```

**Verification:**
```bash
# View scheduled tasks at runtime
celery -A crypto_news_aggregator.tasks inspect scheduled
# Output: Lists all pending scheduled tasks with next run times
```

### CLI Commands & Scripts

**Script:** `src/crypto_news_aggregator/cli.py` (if exists)

Common CLI entry points:

1. **Backfill narratives** (development):
```bash
python scripts/backfill_narratives.py
# File: scripts/backfill_narratives.py:20-50
# Sets sys.path, imports services, runs narrative detection on historical articles
```

2. **Trigger manual briefing**:
```bash
curl -X POST "http://localhost:8000/admin/trigger-briefing?briefing_type=morning&force=true"
# File: src/crypto_news_aggregator/api/admin.py:415-490
# Direct HTTP endpoint (preferred over CLI)
```

3. **Trigger manual RSS fetch** (added BUG-054):
```bash
curl -X POST "http://localhost:8000/admin/trigger-fetch"
# File: src/crypto_news_aggregator/api/admin.py:504
# Manually triggers RSS ingestion outside the beat schedule
```

4. **Database health check**:
```bash
python -c "
import asyncio
from crypto_news_aggregator.db.mongodb import get_database
db = asyncio.run(get_database())
stats = asyncio.run(db.db.command('serverStatus'))
print('MongoDB status:', stats['ok'])
"
```

### Configuration Loading

**File:** `src/crypto_news_aggregator/core/config.py:1-100`

Settings initialization via Pydantic:

```python
class Settings(BaseSettings):
    # API
    API_TITLE: str = "Crypto News Aggregator"          # Line 10
    API_V1_STR: str = "/api/v1"                        # Line 11

    # Database
    MONGODB_URI: str = Field(..., env="MONGODB_URI")   # Line 15 (required)

    # LLM
    ANTHROPIC_API_KEY: str = Field(..., env="ANTHROPIC_API_KEY")  # Line 20
    ANTHROPIC_DEFAULT_MODEL: str = "claude-haiku-4-5-20251001"    # Line 21

    # Celery
    CELERY_BROKER_URL: str = Field(..., env="CELERY_BROKER_URL")  # Line 25
    CELERY_RESULT_BACKEND: str = Field(..., env="CELERY_RESULT_BACKEND")  # Line 26

    class Config:
        env_file = ".env"                              # Line 35
        env_file_encoding = "utf-8"
        case_sensitive = True

def get_settings() -> Settings:
    return Settings()                                  # Line 40
```

**Configuration sources** (priority):
1. Environment variables (production)
2. `.env` file (development)
3. Hardcoded defaults (fallback)

**Required environment variables:**
```bash
MONGODB_URI=${MONGODB_URI}  # Set via environment or .env
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

**Health check:**
```bash
# Verify all configuration is loaded
python -c "
from crypto_news_aggregator.core.config import get_settings
settings = get_settings()
print('✓ API title:', settings.API_TITLE)
print('✓ MongoDB URI:', 'configured' if settings.MONGODB_URI else 'missing')
print('✓ API key:', 'configured' if settings.ANTHROPIC_API_KEY else 'missing')
"
```

## Operational Checks

### Health Verification

**Check 1: FastAPI server starts**
```bash
# Terminal 1
uvicorn src/crypto_news_aggregator/main:app --port 8000 --reload
# Should print: "Uvicorn running on http://0.0.0.0:8000"
```

**Check 2: API is responsive**
```bash
curl http://localhost:8000/api/v1/health
# Should return: {"status": "ok"}
```

**Check 3: Celery worker starts**
```bash
# Terminal 2
celery -A crypto_news_aggregator.tasks worker --loglevel=info
# Should print: "[*] Ready to accept tasks"
```

**Check 4: Celery Beat scheduler starts**
```bash
# Terminal 3
celery -A crypto_news_aggregator.tasks beat --loglevel=info
# Should print: "[*] Scheduler: Startup"
```

### Startup Sequence Verification

Full healthy startup should show:
1. Configuration loaded from `.env` or environment
2. MongoDB connection established (no connection errors)
3. FastAPI app initialized with routes
4. Celery workers ready
5. Beat scheduler tracking cron jobs

**Debugging startup failures:**

| Issue | Verification | Fix |
|-------|--------------|-----|
| MongoDB connection fails | Check `MONGODB_URI` in `.env` | Verify credentials and network access |
| Celery can't connect to Redis | Check `CELERY_BROKER_URL` | Start Redis: `redis-server` |
| Missing environment variables | Run config check above | Add to `.env` or export |
| API port already in use | `lsof -i :8000` | Kill process: `kill -9 <PID>` or use different port |
| LLM API key invalid | Try: `curl -H "x-api-key: $ANTHROPIC_API_KEY" https://api.anthropic.com/v1/messages` | Update API key in `.env` |

## Relevant Files

### Core Entry Points
- `src/crypto_news_aggregator/main.py` - FastAPI app initialization
- `src/crypto_news_aggregator/worker.py` - Celery worker launcher
- `src/crypto_news_aggregator/tasks/__init__.py` - Celery app setup
- `src/crypto_news_aggregator/tasks/beat_schedule.py` - Beat schedule definition

### Configuration
- `src/crypto_news_aggregator/core/config.py` - Settings loading
- `.env` - Environment variables (development)

### Database
- `src/crypto_news_aggregator/db/mongodb.py:1-80` - MongoDB client init
- `src/crypto_news_aggregator/db/operations/` - CRUD operations

### API Routes
- `src/crypto_news_aggregator/api/v1/__init__.py` - Router registration
- `src/crypto_news_aggregator/api/v1/endpoints/health.py` - Health check endpoint

## Related Documentation
- **[20-scheduling.md](#scheduling-task-dispatch)** - How scheduled tasks are configured
- **[60-llm.md](#llm-integration-generation)** - LLM provider initialization
- **[50-data-model.md](#data-model-mongodb)** - MongoDB collections and indexing

---
*Last updated: 2026-04-25* | *Generated from: 01-entrypoints.txt, 02-celery-registration.txt, 03-celery-beat.txt, 04-mongo-init.txt, 12-config.txt* | *Anchor: application-entrypoints*