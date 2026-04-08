---
id: TASK-039
type: feature
status: backlog
priority: medium
complexity: low
created: 2026-04-08
updated: 2026-04-08
---

# Wire health.py Through LLM Gateway

## Problem/Opportunity

`api/v1/health.py` `check_llm()` (lines 68-91) makes a direct `httpx.AsyncClient` call to `api.anthropic.com` with its own headers and API key. It's unmetered — every UptimeRobot ping fires an LLM call that bypasses the spend cap. While each call is cheap (max_tokens=1), it's a bypass hole and contributes noise to attribution data.

## Proposed Solution

Replace the direct httpx call with a gateway `call()`. On spend cap hit, return `{"status": "degraded", "reason": "spend_cap"}` instead of erroring — this tells UptimeRobot the system is alive but cost-limited, which is operationally correct.

## Acceptance Criteria

- [ ] `import httpx` removed from `health.py` (no longer needed for LLM check; still used by other checks — verify before removing)
- [ ] `check_llm()` no longer constructs its own headers, payload, or httpx client
- [ ] `check_llm()` calls `gateway.call()` with `operation="health_check"`, `model=settings.ANTHROPIC_DEFAULT_MODEL`, `max_tokens=1`
- [ ] On `LLMError` with `error_type="spend_limit"`, returns `{"status": "degraded", "reason": "spend_cap", "latency_ms": ...}` (not "error")
- [ ] On other `LLMError` types, returns `{"status": "error", ...}` as before
- [ ] `"health_check"` added to `is_critical_operation()` in `cost_tracker.py` as NON-critical (blocked during soft limit — health pings are not worth spending budget on)
- [ ] Unit test: mock gateway, verify operation="health_check" passed
- [ ] Unit test: mock gateway raising spend_limit LLMError, verify "degraded" status returned (not "error")

## Dependencies

- TASK-036 (gateway must exist)

## Implementation Notes

### Replace `check_llm()` in `api/v1/health.py`

```python
# BEFORE (lines 68-91): direct httpx call
# AFTER:
from ...llm.gateway import get_gateway
from ...llm.exceptions import LLMError

async def check_llm() -> dict:
    """Minimal LLM ping via gateway. max_tokens=1."""
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        return {"status": "error", "error": "ANTHROPIC_API_KEY not set"}

    model = settings.ANTHROPIC_DEFAULT_MODEL
    start = time.monotonic()
    try:
        gateway = get_gateway()
        response = await gateway.call(
            messages=[{"role": "user", "content": "ok"}],
            model=model,
            operation="health_check",
            max_tokens=1,
            temperature=0.0,
        )
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {"status": "ok", "model": model, "latency_ms": latency_ms}
    except LLMError as e:
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        if e.error_type == "spend_limit":
            return {"status": "degraded", "reason": "spend_cap", "model": model, "latency_ms": latency_ms}
        logger.error("Health check: LLM ping failed", exc_info=True)
        return {"status": "error", "model": model, "latency_ms": latency_ms, "error": str(e)[:100]}
    except Exception as e:
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        logger.error("Health check: LLM ping failed", exc_info=True)
        return {"status": "error", "model": model, "latency_ms": latency_ms, "error": str(e)[:100]}
```

### Verify httpx import

`health.py` does NOT use httpx for any other check (database uses mongo_manager, redis uses redis_client, data_freshness uses mongo). So `import httpx` can be removed entirely.

### Test file: `tests/test_health_gateway.py`

1. `test_health_check_calls_gateway` — mock gateway.call, assert called with operation="health_check", max_tokens=1
2. `test_health_check_spend_cap_returns_degraded` — mock gateway raising LLMError(spend_limit), assert response has status="degraded"
3. `test_health_check_api_error_returns_error` — mock gateway raising LLMError(server_error), assert response has status="error"

## Open Questions

- None

## Completion Summary
- Actual complexity:
- Key decisions made:
- Deviations from plan: