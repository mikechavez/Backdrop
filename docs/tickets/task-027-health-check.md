# TASK-027: Health Check & Site Status

**Status:** In Progress — Backend Complete, Frontend Pending
**Branch:** `feature/task-027-health-check`
**Estimated:** 2 hours
**Dependencies:** TASK-025 (merged), TASK-026 (merged)

---

## Implementation Progress

### Step 1: Backend Health Endpoint ✅ COMPLETE
- **File:** `src/crypto_news_aggregator/api/v1/health.py`
- **Status:** Fully implemented and tested
- **Tests:** 20/20 passing (16 unit + 4 integration)

**What was implemented:**
- `check_database()` — MongoDB ping with latency tracking
- `check_redis()` — Upstash Redis ping via REST client
- `check_llm()` — Anthropic API ping with `max_tokens=1` (near-zero cost)
- `check_data_freshness()` — Latest article age check (24h threshold)
- `health_check()` endpoint — Orchestrates all checks, returns healthy/degraded/unhealthy

**Key features:**
- All checks are async (non-blocking)
- Proper error handling with error message truncation
- Latency tracking on each subsystem
- No authentication required (ops endpoint)
- Returns structured JSON with timestamp and individual check results

### Step 2: Frontend Status Indicator 🚧 PENDING
- `context-owl-ui/src/components/StatusIndicator.tsx` — Create new
- `context-owl-ui/src/components/Layout.tsx` — Add StatusIndicator to nav bar
- Tests will verify component renders and fetches health status

### Step 3: Tests ✅ COMPLETE (Backend)
- `tests/unit/test_health_endpoint.py` — 16/16 passing
- `tests/integration/test_health_integration.py` — 4/4 passing

---

## Overview

Expand the existing `/api/v1/health` stub into a comprehensive health check that tests all subsystems (database, Redis, LLM, data freshness). Add a frontend status indicator (green/yellow/red dot) in the nav bar. The endpoint is unauthenticated and designed for both ops monitoring and hiring-manager-facing visibility.

---

## File Changes Summary

| Action | File | Description |
|--------|------|-------------|
| MODIFY | `src/crypto_news_aggregator/api/v1/health.py` | Replace stub with full subsystem checks |
| CREATE | `context-owl-ui/src/components/StatusIndicator.tsx` | Frontend status dot component |
| MODIFY | `context-owl-ui/src/components/Layout.tsx` | Add StatusIndicator to nav bar |
| CREATE | `tests/unit/test_health_endpoint.py` | Unit tests for health logic |
| CREATE | `tests/integration/test_health_integration.py` | Integration tests for endpoint |

**No router registration changes needed** -- `health.py` is already wired up in `api/v1/`.

---

## Step 1: Replace the Health Endpoint Stub

**File:** `src/crypto_news_aggregator/api/v1/health.py`

Replace the entire file contents with:

```python
"""
Health check endpoint for system monitoring.

Returns status of all subsystems: database, redis, LLM, data freshness.
No authentication required -- this is an ops/status endpoint.
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

import httpx
from fastapi import APIRouter

from ...db.mongodb import mongo_manager
from ...core.redis_rest_client import redis_client
from ...core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Individual health checks ---


async def check_database() -> dict:
    """Check MongoDB connectivity via admin ping."""
    start = time.monotonic()
    try:
        db = await mongo_manager.get_async_database()
        await db.command("ping")
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {"status": "ok", "latency_ms": latency_ms}
    except Exception as e:
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        logger.error("Health check: database failed", exc_info=True)
        return {"status": "error", "latency_ms": latency_ms, "error": str(e)[:100]}


async def check_redis() -> dict:
    """Check Redis (Upstash) connectivity via PING."""
    start = time.monotonic()
    try:
        pong = redis_client.ping()
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        if pong:
            return {"status": "ok", "latency_ms": latency_ms}
        return {"status": "error", "latency_ms": latency_ms, "error": "PING returned False"}
    except Exception as e:
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        logger.error("Health check: redis failed", exc_info=True)
        return {"status": "error", "latency_ms": latency_ms, "error": str(e)[:100]}


async def check_llm() -> dict:
    """Minimal LLM ping: cheapest model, max_tokens=1, no retry.

    Cost: ~0.0001 cents per check (1 input token + 1 output token on Haiku).
    """
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        return {"status": "error", "error": "ANTHROPIC_API_KEY not set"}

    model = settings.ANTHROPIC_DEFAULT_MODEL
    start = time.monotonic()
    try:
        headers = {
            "x-api-key": settings.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "ok"}],
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {"status": "ok", "model": model, "latency_ms": latency_ms}
    except Exception as e:
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        logger.error("Health check: LLM ping failed", exc_info=True)
        return {"status": "error", "model": model, "latency_ms": latency_ms, "error": str(e)[:100]}


async def check_data_freshness() -> dict:
    """Check if most recent article was ingested within 24 hours."""
    try:
        db = await mongo_manager.get_async_database()
        collection = db["articles"]
        latest = await collection.find_one(
            sort=[("published_at", -1)],
            projection={"published_at": 1, "title": 1},
        )
        if not latest:
            return {"status": "warning", "error": "No articles found in database"}

        published = latest.get("published_at")
        if not published:
            return {"status": "warning", "error": "Latest article has no published_at timestamp"}

        # Ensure timezone-aware comparison
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)

        age = datetime.now(timezone.utc) - published
        age_hours = round(age.total_seconds() / 3600, 1)

        if age > timedelta(hours=24):
            return {
                "status": "warning",
                "latest_article_age_hours": age_hours,
                "latest_article_title": latest.get("title", "unknown")[:80],
            }

        return {
            "status": "ok",
            "latest_article_age_hours": age_hours,
            "latest_article_title": latest.get("title", "unknown")[:80],
        }
    except Exception as e:
        logger.error("Health check: data freshness failed", exc_info=True)
        return {"status": "error", "error": str(e)[:100]}


# --- Main endpoint ---

# Critical checks: if these fail, system is unhealthy
CRITICAL_CHECKS = {"database", "llm"}


@router.get("/health", response_model=Dict[str, Any], tags=["Health"])
async def health_check() -> Dict[str, Any]:
    """Comprehensive health check for all Backdrop subsystems.

    Returns:
        - **healthy**: All checks pass
        - **degraded**: Non-critical checks failing (redis, data_freshness)
        - **unhealthy**: Critical checks failing (database, llm)

    No authentication required.
    """
    checks = {
        "database": await check_database(),
        "redis": await check_redis(),
        "llm": await check_llm(),
        "data_freshness": await check_data_freshness(),
    }

    critical_failed = any(
        checks[name]["status"] == "error"
        for name in CRITICAL_CHECKS
        if name in checks
    )
    any_issue = any(
        checks[name]["status"] in ("error", "warning")
        for name in checks
    )

    if critical_failed:
        overall = "unhealthy"
    elif any_issue:
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
```

**Key design notes for CC:**
- Import path is `...db.mongodb` (2 dots up from `api/v1/`) and `...core.redis_rest_client` -- matches existing stub import depth
- `check_llm()` uses async `httpx.AsyncClient` instead of the sync `AnthropicProvider` to avoid blocking the event loop
- `max_tokens=1` and prompt `"ok"` -- effectively zero cost per ping
- Each check is a standalone async function for testability
- `check_data_freshness` uses `"warning"` (not `"error"`) for stale data since the pipeline still works

---

## Step 2: Frontend Status Indicator

### 2a. Create the StatusIndicator Component

**File:** `context-owl-ui/src/components/StatusIndicator.tsx`

```tsx
import { useState, useEffect } from 'react';
import { cn } from '../lib/cn';

type HealthStatus = 'healthy' | 'degraded' | 'unhealthy' | 'unknown';

interface HealthResponse {
  status: HealthStatus;
  timestamp: string;
  checks: Record<string, { status: string }>;
}

const STATUS_CONFIG: Record<HealthStatus, { color: string; label: string }> = {
  healthy:   { color: 'bg-green-500',  label: 'All systems live' },
  degraded:  { color: 'bg-yellow-500', label: 'Degraded' },
  unhealthy: { color: 'bg-red-500',    label: 'Issues detected' },
  unknown:   { color: 'bg-gray-400',   label: 'Status unknown' },
};

export function StatusIndicator() {
  const [status, setStatus] = useState<HealthStatus>('unknown');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const apiUrl = import.meta.env.VITE_API_URL;
    if (!apiUrl) {
      setLoading(false);
      return;
    }

    fetch(`${apiUrl}/health`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: HealthResponse) => {
        setStatus(data.status);
      })
      .catch(() => {
        setStatus('unknown');
      })
      .finally(() => {
        setLoading(false);
      });
  }, []); // Poll once on mount -- not continuously

  const config = STATUS_CONFIG[status];

  if (loading) {
    return (
      <div className="flex items-center gap-1.5" title="Checking system status...">
        <span className="w-2 h-2 rounded-full bg-gray-300 dark:bg-gray-600 animate-pulse" />
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1.5" title={config.label}>
      <span
        className={cn(
          'w-2 h-2 rounded-full',
          config.color,
          status === 'healthy' && 'animate-[pulse_3s_ease-in-out_infinite]'
        )}
      />
      <span className="text-xs text-gray-500 dark:text-gray-400 hidden sm:inline">
        {status === 'healthy' ? 'Live' : config.label}
      </span>
    </div>
  );
}
```

**Design notes for CC:**
- Uses raw `fetch()` instead of `apiClient` to avoid the API key requirement (health is unauthenticated)
- Single poll on mount (empty dependency array) -- not continuous polling per ticket spec
- Grey dot while loading, maps to grey/unknown on network failure
- `cn()` utility already exists in the project (used by `Layout.tsx`)
- Gentle pulse animation only on green/healthy -- not distracting

### 2b. Add StatusIndicator to Layout

**File:** `context-owl-ui/src/components/Layout.tsx`

Two changes:

**Change 1 -- Add import** at top, alongside existing imports:
```tsx
import { StatusIndicator } from './StatusIndicator';
```

**Change 2 -- Add component in nav bar.** Find this block:
```tsx
<div className="flex items-center gap-3">
  {/* Story page CTA — amber pill, visually distinct from blue product nav */}
  <a
    href="/story.html"
```

Insert `<StatusIndicator />` as the first child:
```tsx
<div className="flex items-center gap-3">
  <StatusIndicator />
  {/* Story page CTA — amber pill, visually distinct from blue product nav */}
  <a
    href="/story.html"
```

That is the only Layout change -- one import, one line inserted.

---

## Step 3: Unit Tests

**File:** `tests/unit/test_health_endpoint.py`

```python
"""Unit tests for health endpoint logic."""

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta


# --- Overall status logic tests ---


class TestHealthStatusLogic:
    """Test the overall status determination: healthy / degraded / unhealthy."""

    def _compute_status(self, checks: dict) -> str:
        """Mirror the logic from the health endpoint."""
        CRITICAL = {"database", "llm"}
        critical_failed = any(
            checks[name]["status"] == "error"
            for name in CRITICAL
            if name in checks
        )
        any_issue = any(
            checks[name]["status"] in ("error", "warning")
            for name in checks
        )
        if critical_failed:
            return "unhealthy"
        elif any_issue:
            return "degraded"
        return "healthy"

    def test_all_ok_returns_healthy(self):
        checks = {
            "database": {"status": "ok"},
            "redis": {"status": "ok"},
            "llm": {"status": "ok"},
            "data_freshness": {"status": "ok"},
        }
        assert self._compute_status(checks) == "healthy"

    def test_redis_error_returns_degraded(self):
        checks = {
            "database": {"status": "ok"},
            "redis": {"status": "error"},
            "llm": {"status": "ok"},
            "data_freshness": {"status": "ok"},
        }
        assert self._compute_status(checks) == "degraded"

    def test_data_freshness_warning_returns_degraded(self):
        checks = {
            "database": {"status": "ok"},
            "redis": {"status": "ok"},
            "llm": {"status": "ok"},
            "data_freshness": {"status": "warning"},
        }
        assert self._compute_status(checks) == "degraded"

    def test_database_error_returns_unhealthy(self):
        checks = {
            "database": {"status": "error"},
            "redis": {"status": "ok"},
            "llm": {"status": "ok"},
            "data_freshness": {"status": "ok"},
        }
        assert self._compute_status(checks) == "unhealthy"

    def test_llm_error_returns_unhealthy(self):
        checks = {
            "database": {"status": "ok"},
            "redis": {"status": "ok"},
            "llm": {"status": "error"},
            "data_freshness": {"status": "ok"},
        }
        assert self._compute_status(checks) == "unhealthy"

    def test_both_critical_fail_returns_unhealthy(self):
        checks = {
            "database": {"status": "error"},
            "redis": {"status": "error"},
            "llm": {"status": "error"},
            "data_freshness": {"status": "error"},
        }
        assert self._compute_status(checks) == "unhealthy"


# --- Individual check tests ---


class TestCheckDatabase:
    """Test database health check handles success and failure."""

    @pytest.mark.asyncio
    async def test_database_ok(self):
        from crypto_news_aggregator.api.v1.health import check_database

        mock_db = AsyncMock()
        mock_db.command = AsyncMock(return_value={"ok": 1})

        with patch(
            "crypto_news_aggregator.api.v1.health.mongo_manager"
        ) as mock_mm:
            mock_mm.get_async_database = AsyncMock(return_value=mock_db)
            result = await check_database()

        assert result["status"] == "ok"
        assert "latency_ms" in result

    @pytest.mark.asyncio
    async def test_database_error(self):
        from crypto_news_aggregator.api.v1.health import check_database

        with patch(
            "crypto_news_aggregator.api.v1.health.mongo_manager"
        ) as mock_mm:
            mock_mm.get_async_database = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            result = await check_database()

        assert result["status"] == "error"
        assert "error" in result


class TestCheckRedis:
    """Test Redis health check handles success and failure."""

    @pytest.mark.asyncio
    async def test_redis_ok(self):
        from crypto_news_aggregator.api.v1.health import check_redis

        with patch(
            "crypto_news_aggregator.api.v1.health.redis_client"
        ) as mock_redis:
            mock_redis.ping.return_value = True
            result = await check_redis()

        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_redis_error(self):
        from crypto_news_aggregator.api.v1.health import check_redis

        with patch(
            "crypto_news_aggregator.api.v1.health.redis_client"
        ) as mock_redis:
            mock_redis.ping.side_effect = Exception("Connection refused")
            result = await check_redis()

        assert result["status"] == "error"


class TestCheckLLM:
    """Test LLM health check uses cheap model and handles failure."""

    @pytest.mark.asyncio
    async def test_llm_ok(self):
        from crypto_news_aggregator.api.v1.health import check_llm

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200

        with patch(
            "crypto_news_aggregator.api.v1.health.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await check_llm()

        assert result["status"] == "ok"
        assert result["model"] == "claude-haiku-4-5-20251001"

        # Verify max_tokens=1 (cost control)
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["max_tokens"] == 1

    @pytest.mark.asyncio
    async def test_llm_no_api_key(self):
        from crypto_news_aggregator.api.v1.health import check_llm

        with patch(
            "crypto_news_aggregator.api.v1.health.get_settings"
        ) as mock_settings:
            mock_s = MagicMock()
            mock_s.ANTHROPIC_API_KEY = ""
            mock_settings.return_value = mock_s

            result = await check_llm()

        assert result["status"] == "error"
        assert "not set" in result["error"]

    @pytest.mark.asyncio
    async def test_llm_timeout(self):
        from crypto_news_aggregator.api.v1.health import check_llm

        with patch(
            "crypto_news_aggregator.api.v1.health.httpx.AsyncClient"
        ) as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=httpx.TimeoutException("timeout")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await check_llm()

        assert result["status"] == "error"


class TestCheckDataFreshness:
    """Test data freshness check handles various states."""

    @pytest.mark.asyncio
    async def test_fresh_data(self):
        from crypto_news_aggregator.api.v1.health import check_data_freshness

        recent_time = datetime.now(timezone.utc) - timedelta(hours=2)
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(
            return_value={"published_at": recent_time, "title": "Test Article"}
        )
        mock_db = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch(
            "crypto_news_aggregator.api.v1.health.mongo_manager"
        ) as mock_mm:
            mock_mm.get_async_database = AsyncMock(return_value=mock_db)
            result = await check_data_freshness()

        assert result["status"] == "ok"
        assert result["latest_article_age_hours"] < 24

    @pytest.mark.asyncio
    async def test_stale_data(self):
        from crypto_news_aggregator.api.v1.health import check_data_freshness

        old_time = datetime.now(timezone.utc) - timedelta(hours=48)
        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(
            return_value={"published_at": old_time, "title": "Old Article"}
        )
        mock_db = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch(
            "crypto_news_aggregator.api.v1.health.mongo_manager"
        ) as mock_mm:
            mock_mm.get_async_database = AsyncMock(return_value=mock_db)
            result = await check_data_freshness()

        assert result["status"] == "warning"
        assert result["latest_article_age_hours"] > 24

    @pytest.mark.asyncio
    async def test_no_articles(self):
        from crypto_news_aggregator.api.v1.health import check_data_freshness

        mock_collection = AsyncMock()
        mock_collection.find_one = AsyncMock(return_value=None)
        mock_db = AsyncMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        with patch(
            "crypto_news_aggregator.api.v1.health.mongo_manager"
        ) as mock_mm:
            mock_mm.get_async_database = AsyncMock(return_value=mock_db)
            result = await check_data_freshness()

        assert result["status"] == "warning"
```

**Test notes for CC:**
- All patches target `crypto_news_aggregator.api.v1.health.*` (the module where the checks are defined)
- Tests verify both behavior AND cost controls (max_tokens=1)
- Total: 16 unit tests

---

## Step 4: Integration Tests

**File:** `tests/integration/test_health_integration.py`

```python
"""Integration tests for the /api/v1/health endpoint."""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def mock_all_healthy():
    """Patch all subsystem checks to return healthy."""
    with patch(
        "crypto_news_aggregator.api.v1.health.check_database",
        new_callable=AsyncMock,
        return_value={"status": "ok", "latency_ms": 5.0},
    ), patch(
        "crypto_news_aggregator.api.v1.health.check_redis",
        new_callable=AsyncMock,
        return_value={"status": "ok", "latency_ms": 2.0},
    ), patch(
        "crypto_news_aggregator.api.v1.health.check_llm",
        new_callable=AsyncMock,
        return_value={"status": "ok", "model": "claude-haiku-4-5-20251001", "latency_ms": 800.0},
    ), patch(
        "crypto_news_aggregator.api.v1.health.check_data_freshness",
        new_callable=AsyncMock,
        return_value={"status": "ok", "latest_article_age_hours": 1.5},
    ):
        yield


@pytest.fixture
def mock_database_down():
    """Patch database check to fail, others healthy."""
    with patch(
        "crypto_news_aggregator.api.v1.health.check_database",
        new_callable=AsyncMock,
        return_value={"status": "error", "latency_ms": 5000.0, "error": "Connection refused"},
    ), patch(
        "crypto_news_aggregator.api.v1.health.check_redis",
        new_callable=AsyncMock,
        return_value={"status": "ok", "latency_ms": 2.0},
    ), patch(
        "crypto_news_aggregator.api.v1.health.check_llm",
        new_callable=AsyncMock,
        return_value={"status": "ok", "model": "claude-haiku-4-5-20251001", "latency_ms": 800.0},
    ), patch(
        "crypto_news_aggregator.api.v1.health.check_data_freshness",
        new_callable=AsyncMock,
        return_value={"status": "ok", "latest_article_age_hours": 1.5},
    ):
        yield


@pytest.fixture
def mock_redis_down():
    """Patch redis to fail, others healthy -- should produce degraded."""
    with patch(
        "crypto_news_aggregator.api.v1.health.check_database",
        new_callable=AsyncMock,
        return_value={"status": "ok", "latency_ms": 5.0},
    ), patch(
        "crypto_news_aggregator.api.v1.health.check_redis",
        new_callable=AsyncMock,
        return_value={"status": "error", "latency_ms": 5000.0, "error": "Connection refused"},
    ), patch(
        "crypto_news_aggregator.api.v1.health.check_llm",
        new_callable=AsyncMock,
        return_value={"status": "ok", "model": "claude-haiku-4-5-20251001", "latency_ms": 800.0},
    ), patch(
        "crypto_news_aggregator.api.v1.health.check_data_freshness",
        new_callable=AsyncMock,
        return_value={"status": "ok", "latest_article_age_hours": 1.5},
    ):
        yield


class TestHealthEndpoint:
    """Integration tests for GET /api/v1/health."""

    @pytest.mark.asyncio
    async def test_healthy_response_structure(self, mock_all_healthy):
        from crypto_news_aggregator.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "checks" in data
        assert set(data["checks"].keys()) == {
            "database", "redis", "llm", "data_freshness"
        }

    @pytest.mark.asyncio
    async def test_unhealthy_when_database_down(self, mock_database_down):
        from crypto_news_aggregator.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["database"]["status"] == "error"

    @pytest.mark.asyncio
    async def test_degraded_when_redis_down(self, mock_redis_down):
        from crypto_news_aggregator.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["checks"]["redis"]["status"] == "error"

    @pytest.mark.asyncio
    async def test_no_auth_required(self, mock_all_healthy):
        """Health endpoint must work without any API key header."""
        from crypto_news_aggregator.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Deliberately no X-API-Key header
            response = await client.get("/api/v1/health")

        assert response.status_code == 200
```

**Test notes for CC:**
- Patches target the module-level functions, not internal implementation
- All tests return HTTP 200 even for unhealthy (status is in body, not HTTP code -- standard for health endpoints)
- Total: 4 integration tests

---

## Verification Checklist (for CC to run)

```bash
# Run unit tests
pytest tests/unit/test_health_endpoint.py -v

# Run integration tests
pytest tests/integration/test_health_integration.py -v

# Quick manual smoke test (if running locally)
curl http://localhost:8000/api/v1/health | python -m json.tool
```

Expected: 20 tests passing (16 unit + 4 integration).

---

## Commit Message

```
feat(health): Comprehensive health check with frontend status indicator (TASK-027)

- Expand /api/v1/health stub to check database, redis, LLM, data freshness
- Add StatusIndicator component to frontend nav bar (green/yellow/red dot)
- LLM ping uses cheapest model with max_tokens=1 for zero-cost checks
- Overall status: healthy/degraded/unhealthy based on critical vs non-critical checks
- 20 tests (16 unit, 4 integration)
```