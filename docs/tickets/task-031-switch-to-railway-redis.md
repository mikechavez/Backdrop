---
ticket_id: TASK-031
title: Switch Redis from Upstash REST to Railway Redis (redis-py)
priority: critical
severity: high
status: OPEN
date_created: 2026-04-02
branch: feature/task-031-railway-redis
effort_estimate: 1 hr
---

# TASK-031: Switch Redis from Upstash REST to Railway Redis (redis-py)

## Problem Statement

The app's rate limiter and circuit breaker depend on Redis via an Upstash REST client (`redis_rest_client.py`). The Upstash database was deleted, and attempts to reconnect with a new Upstash instance have failed despite correct credentials (unknown env/client interaction issue). Meanwhile, a working Railway-hosted Redis instance already exists at `redis://default:...@redis.railway.internal:6379` and is successfully used by Celery for task brokering.

**Without working Redis, the rate limiter and circuit breaker are silently disabled.** All LLM calls pass through unchecked, which means adding Anthropic credits risks another budget blowout. This is the #1 blocker for getting Backdrop back online safely.

---

## Task

Replace the Upstash REST client with a standard `redis-py` client that connects to the Railway Redis instance. The interface (method signatures) must stay identical so that `rate_limiter.py`, `circuit_breaker.py`, and `health.py` require zero changes.

### Step 1: Install redis-py

Add `redis` package to project dependencies:
```bash
poetry add redis
```

### Step 2: Rewrite `src/crypto_news_aggregator/core/redis_rest_client.py`

Replace the entire file. The new implementation must:

- Connect using the `REDIS_URL` environment variable (already set on Railway for both services: `redis://default:...@redis.railway.internal:6379`)
- Fall back to `redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}` from config for local dev
- Preserve the `self.enabled` pattern — if no Redis URL is available, all methods return safe defaults (fail-open)
- Expose **exactly the same public interface** as the current client:

| Method | Signature | Returns |
|--------|-----------|---------|
| `get(key)` | `(str) -> Optional[Any]` | Value or None |
| `set(key, value, ex=None)` | `(str, Any, Optional[int]) -> bool` | True on success |
| `delete(*keys)` | `(*str) -> int` | Number of keys deleted |
| `exists(key)` | `(str) -> bool` | True if key exists |
| `expire(key, seconds)` | `(str, int) -> bool` | True on success |
| `ttl(key)` | `(str) -> int` | TTL in seconds |
| `incr(key)` | `(str) -> int` | New value after increment |
| `ping()` | `() -> bool` | True if PONG received |

**Important implementation notes:**
- All methods are **synchronous** (the current client is sync, and both `rate_limiter.py` and `circuit_breaker.py` call them synchronously)
- `get()` should decode bytes to str (redis-py returns bytes by default — use `decode_responses=True` in the client constructor)
- `set()` must handle the `ex` parameter for TTL (redis-py's `set()` natively supports this)
- `incr()` must return `0` if `self.enabled` is False (matches current behavior)
- `ping()` must catch exceptions and return False (matches current behavior)
- The module-level singleton `redis_client = RedisRESTClient()` must be preserved as `redis_client = RedisClient()` (same variable name, since it's imported everywhere)

**Current file for reference (`redis_rest_client.py`):**
```python
import json
from typing import Any, Optional, Dict, Union, List
import requests
from .config import get_settings


class RedisRESTClient:
    def __init__(self, base_url: str = None, token: str = None):
        settings = get_settings()
        self.base_url = (base_url or settings.UPSTASH_REDIS_REST_URL).rstrip("/")
        self.token = token or settings.UPSTASH_REDIS_TOKEN
        self.enabled = bool(self.base_url and self.token)
        if self.enabled:
            self.headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
        else:
            self.headers = {}

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Any:
        if not self.enabled:
            return {"result": None}
        url = f"{self.base_url}/{endpoint}"
        response = requests.request(method, url, headers=self.headers, **kwargs)
        response.raise_for_status()
        return response.json()

    def get(self, key: str) -> Optional[Any]:
        try:
            response = self._make_request("GET", f"get/{key}")
            return response.get("result")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        if not isinstance(value, (str, int, float, bool)):
            value = json.dumps(value)
        endpoint = f"set/{key}/{value}"
        if ex is not None:
            endpoint += f"?ex={ex}"
        response = self._make_request("POST", endpoint)
        return response.get("result") == "OK"

    def delete(self, *keys: str) -> int:
        key_param = "/".join(keys)
        response = self._make_request("POST", f"del/{key_param}")
        return response.get("result", 0)

    def exists(self, key: str) -> bool:
        response = self._make_request("GET", f"exists/{key}")
        return bool(response.get("result", 0))

    def expire(self, key: str, seconds: int) -> bool:
        response = self._make_request("POST", f"expire/{key}/{seconds}")
        return bool(response.get("result", 0))

    def ttl(self, key: str) -> int:
        response = self._make_request("GET", f"ttl/{key}")
        return response.get("result", -2)

    def incr(self, key: str) -> int:
        response = self._make_request("POST", f"incr/{key}")
        result = response.get("result")
        return int(result) if result is not None else 0

    def ping(self) -> bool:
        try:
            response = self._make_request("GET", "ping")
            return response.get("result") == "PONG"
        except requests.exceptions.RequestException:
            return False

redis_client = RedisRESTClient()
```

### Step 3: Update `config.py`

Add a `REDIS_URL` field (for Railway's injected variable):
```python
# Add this near the existing Redis settings section
REDIS_URL: str = ""  # Full Redis URL (e.g., redis://default:pass@host:6379/0)
```

The existing `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB` fields should remain for local dev fallback.

The `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_TOKEN` fields can be removed.

### Step 4: Update health check Redis ping

**File:** `src/crypto_news_aggregator/api/v1/health.py`

The `check_redis()` function should work unchanged since it calls `redis_client.ping()` and the interface is identical. Verify this — no code change expected, just confirmation.

### Step 5: Update tests

**Existing test files to update (if they exist):**
- `tests/services/test_rate_limiter.py` — uses a `MockRedis` class. Should still work since interface is identical. Verify.
- `tests/services/test_circuit_breaker.py` — same pattern. Verify.

**New test file to create:**
- `tests/unit/test_redis_client.py` — basic tests for the new client:
  - `test_ping_returns_true_when_connected`
  - `test_ping_returns_false_when_disabled`
  - `test_get_set_roundtrip`
  - `test_incr_increments`
  - `test_delete_removes_key`
  - `test_expire_sets_ttl`
  - `test_exists_checks_key`
  - `test_disabled_client_returns_defaults` (no URL configured)

### Step 6: Clean up Railway env vars

After deployment is confirmed working:
- Remove `UPSTASH_REDIS_REST_URL` from crypto-news-aggregator
- Remove `UPSTASH_REDIS_TOKEN` from crypto-news-aggregator
- Remove same from celery-worker if present
- Verify `REDIS_URL` is already available to both services (Railway may auto-inject it from the Redis service, or it may need to be added as a shared variable)

### Step 7: Verify end-to-end

After deploying:
1. Hit `https://context-owl-production.up.railway.app/api/v1/health`
2. Confirm Redis check shows `"status": "ok"` with reasonable latency (5-50ms)
3. Confirm rate limiter is functional: check Railway logs for rate limit key creation on next LLM call

---

## Consumers of `redis_client` (DO NOT MODIFY these files — interface stays the same)

| File | Import | Usage |
|------|--------|-------|
| `services/rate_limiter.py` | `from crypto_news_aggregator.core.redis_rest_client import redis_client` | `get()`, `incr()`, `expire()`, `delete()` |
| `services/circuit_breaker.py` | `from crypto_news_aggregator.core.redis_rest_client import redis_client` | `get()`, `set()`, `incr()`, `expire()`, `delete()` |
| `api/v1/health.py` | `from ...core.redis_rest_client import redis_client` | `ping()` |

Both `rate_limiter.py` and `circuit_breaker.py` also accept a `redis` parameter for dependency injection in tests, so test mocks should continue to work unchanged.

---

## Verification

- [ ] `redis_client.ping()` returns True when connected to Railway Redis
- [ ] `redis_client.ping()` returns False when Redis unavailable (fail-open)
- [ ] All 8 public methods work with redis-py backend
- [ ] Rate limiter tests pass (`tests/services/test_rate_limiter.py`)
- [ ] Circuit breaker tests pass (`tests/services/test_circuit_breaker.py`)
- [ ] Health endpoint tests pass (`tests/unit/test_health_endpoint.py`, `tests/integration/test_health_integration.py`)
- [ ] New Redis client unit tests pass
- [ ] Health endpoint returns Redis status "ok" in production
- [ ] No changes needed in rate_limiter.py, circuit_breaker.py, or health.py

---

## Acceptance Criteria

- [ ] App uses Railway Redis (`REDIS_URL`) instead of Upstash REST API
- [ ] All existing Redis-dependent features work (rate limiting, circuit breaker, health check)
- [ ] Fail-open behavior preserved when Redis unavailable
- [ ] Upstash config removed from `config.py`
- [ ] Upstash env vars removed from Railway
- [ ] All tests pass

---

## Impact

**Unblocks adding Anthropic credits safely.** With Redis working, rate limiting and circuit breakers are active, preventing another LLM budget blowout. This is the final prerequisite before starting the TASK-028 burn-in validation.

---

## Related Tickets

- TASK-025: Implement Cost Controls (created the rate limiter and circuit breaker that depend on Redis)
- TASK-027: Health Check & Site Status (Redis health check)
- TASK-028: Burn-in Validation (blocked by this ticket)
- BUG-053: Remove hardcoded SMTP password from config.py