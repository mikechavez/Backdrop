---
ticket_id: TASK-026
title: Fix Active LLM Failures (BUG-052 Resolution)
priority: critical
severity: critical
status: OPEN
date_created: 2026-03-31
branch: feature/task-026-fix-llm-failures
effort_estimate: 3 hr
---

# TASK-026: Fix Active LLM Failures (BUG-052 Resolution)

## Problem Statement

All LLM-dependent systems are non-functional: briefing generation, entity extraction, sentiment analysis. This has been a recurring pattern — systems go down silently and stay down until manually discovered. BUG-052 was created during Sprint 11 with an investigation guide, but the root cause was never identified. TASK-024 audit findings will likely pinpoint the issue.

**Previous known failures:**
- 2026-02-27: Insufficient Anthropic credits (resolved by adding credits)
- 2026-03-11: BUG-052 filed — all LLM systems down, credits ruled out
- Current: LLM spend burning through budget (possibly related)

---

## Root Cause Analysis (from Explore Agent)

Nine critical defects found across five files:

| # | Location | Defect | Severity |
|---|----------|--------|----------|
| 1 | `briefing_agent.py:163` | `return None` on all LLM failures — indistinguishable from "skipped" | Critical |
| 2 | `anthropic.py:78,81` | `_get_completion()` returns `""` on all errors — silent failure for sentiment/themes/relevance | Critical |
| 3 | `briefing_agent.py:794–799` | Bare `except:` swallows error body parsing | High |
| 4 | `anthropic.py:71–72,441–442` | Multiple bare `except: pass` swallow secondary exceptions | High |
| 5 | `briefing_tasks.py:117–120` | LLM failure logs as `"skipped"` (INFO) instead of error; task reports SUCCESS | High |
| 6 | `briefing.py:479–490` | API returns HTTP 200 `success=False` with no machine-readable error type | High |
| 7 | `anthropic.py:483` | `extract_entities_batch` returns `{"results": [], "usage": {}}` — empty = failure, indistinguishable from "no entities" | Medium |
| 8 | `briefing_agent.py:838` | `logger.error` without `exc_info=True` — stack trace lost | Medium |
| 9 | `briefing_agent.py:841` | `RuntimeError("All LLM models failed")` lacks structured context (which models, last error) | Medium |

**Key structural issue:** Every LLM exception is caught, logged, and converted to `None` or `""` at `briefing_agent.py:generate_briefing()`. This breaks the entire error chain — Celery tasks can't distinguish failure from skip; API can't return meaningful errors to frontend.

---

## Implementation Plan

### Step 1 — Create `LLMError` exception class

**New file:** `src/crypto_news_aggregator/llm/exceptions.py`

```python
class LLMError(Exception):
    """Structured exception for LLM API failures with error_type classification."""
    
    def __init__(
        self, 
        message: str, 
        *, 
        error_type: str, 
        model: str | None = None, 
        status_code: int | None = None
    ):
        super().__init__(message)
        self.error_type = error_type  # "auth_error", "rate_limit", "server_error", "timeout", "all_models_failed", "parse_error", "unexpected"
        self.model = model
        self.status_code = status_code
```

No changes to `llm/__init__.py` needed (import directly from `exceptions`).

---

### Step 2 — Fix `_get_completion()` and `_get_completion_with_usage()` in `anthropic.py`

**File:** `src/crypto_news_aggregator/llm/anthropic.py`

**Current behavior:** Both methods return `""` / `("", {})` on all errors. Callers treat empty string as valid response.

**Change `_get_completion()` (lines 60-81):**

Replace the two `except` blocks that return `""` with:

```python
except httpx.HTTPStatusError as e:
    status = e.response.status_code
    try:
        error_msg = e.response.json().get("error", {}).get("message", e.response.text[:200])
    except Exception:
        error_msg = e.response.text[:200]
    if status == 403:
        error_type = "auth_error"
    elif status == 429:
        error_type = "rate_limit"
    elif status >= 500:
        error_type = "server_error"
    else:
        error_type = "unexpected"
    logger.error(f"Anthropic API error {status} for model {model}: {error_msg}", exc_info=True)
    raise LLMError(error_msg, error_type=error_type, model=model, status_code=status)
except httpx.TimeoutException as e:
    logger.error(f"Anthropic API timeout for model {model}", exc_info=True)
    raise LLMError("Request timed out", error_type="timeout", model=model)
except Exception as e:
    logger.error(f"Unexpected error calling Anthropic API: {e}", exc_info=True)
    raise LLMError(str(e), error_type="unexpected", model=model)
```

**Apply identical pattern to `_get_completion_with_usage()` (lines 113-121).**

**Important:** `analyze_sentiment()`, `score_relevance()`, `extract_themes()` all call `_get_completion()`. They must catch `LLMError` and return their graceful-degraded defaults (0.0, empty string, []) rather than propagating:

```python
def analyze_sentiment(self, text: str) -> float:
    try:
        response = self._get_completion(prompt)
        ...parse float...
    except LLMError:
        logger.warning("analyze_sentiment: LLM unavailable, returning 0.0")
        return 0.0
```

Same for `score_relevance()` → return `0.0` and `extract_themes()` → return `[]`.

This preserves backward compatibility (callers still get 0.0/empty) while ensuring the error is logged at the call site.

---

### Step 3 — Fix `generate_briefing()` in `briefing_agent.py`

**File:** `src/crypto_news_aggregator/services/briefing_agent.py`

**Current behavior:** Lines 161-163 catch all exceptions and `return None`, making LLM failure indistinguishable from "briefing already exists."

**Change (lines 161-163):**

```python
except LLMError:
    raise   # propagate LLMError — caller must handle
except Exception as e:
    logger.exception(f"Failed to generate {briefing_type} briefing: {e}")
    return None   # non-LLM failures still return None (DB errors, etc.)
```

**Also fix bare `except:` at line 798 in `_call_llm()`:**

```python
try:
    error_data = response.json()
    logger.error(f"API error response: {error_data}")
except Exception:   # replace bare except:
    logger.error(f"API error body: {response.text[:500]}")
```

**Add `exc_info=True` to `logger.error(f"LLM call failed: {e}")` at line 838.**

---

### Step 4 — Fix `briefing_tasks.py` to distinguish skip from failure

**File:** `src/crypto_news_aggregator/tasks/briefing_tasks.py`

**Current behavior (lines 116-121):** `None` result from `generate_briefing()` always logs "skipped".

**Change:** Import `LLMError` and catch it explicitly before the generic `except`:

```python
except LLMError as exc:
    logger.error(
        f"Morning briefing LLM failure [error_type={exc.error_type}, model={exc.model}]: {exc}",
        exc_info=True,
    )
    raise self.retry(exc=exc)
except Exception as exc:
    logger.exception(f"Morning briefing generation failed: {exc}")
    raise self.retry(exc=exc)
```

The `None` path (lines 116-121) only runs when `generate_briefing()` returns `None` (clean skip) — LLM errors now raise `LLMError` and never reach this code.

**Apply the same change to `generate_evening_briefing_task` and `generate_afternoon_briefing_task`.**

---

### Step 5 — Fix API endpoint to return structured error

**File:** `src/crypto_news_aggregator/api/v1/endpoints/briefing.py`

**Add `error_type` field to `GenerateBriefingResponse` (line 406):**

```python
class GenerateBriefingResponse(BaseModel):
    success: bool
    message: str
    briefing_id: Optional[str] = None
    error_type: Optional[str] = None   # populated on LLM failure only
```

**Add `LLMError` catch block to `generate_briefing_endpoint()` (before generic `except Exception`):**

```python
_LLM_HTTP_CODES = {
    "auth_error": 502,
    "rate_limit": 503,
    "server_error": 503,
    "timeout": 503,
    "all_models_failed": 503,
    "parse_error": 502,
    "unexpected": 503,
}

except HTTPException:
    raise
except LLMError as e:
    status_code = _LLM_HTTP_CODES.get(e.error_type, 503)
    logger.error(f"LLM failure generating {briefing_type} briefing [error_type={e.error_type}]: {e}", exc_info=True)
    raise HTTPException(
        status_code=status_code,
        detail={"error_type": e.error_type, "message": str(e), "model": e.model},
    )
except Exception as e:
    ...existing handler...
```

---

### Step 6 — Write tests

**New test files:**

1. `tests/llm/test_llm_exceptions.py` — unit tests: LLMError fields, is-a Exception, raise/catch
2. `tests/llm/test_anthropic_error_handling.py` — pytest-httpx mocks:
   - 403 → raises LLMError(error_type="auth_error")
   - 429 → raises LLMError(error_type="rate_limit")
   - 500 → raises LLMError(error_type="server_error")
   - timeout → raises LLMError(error_type="timeout")
   - happy path → returns text (regression: no longer returns "")
   - Same coverage for `_get_completion_with_usage`
3. `tests/services/test_briefing_agent_error_handling.py` — AsyncMock:
   - `generate_briefing()` raises LLMError on LLM failure (doesn't return None)
   - `generate_briefing()` still returns None when briefing already exists
   - No "skipped" log line on LLM failure
4. `tests/api/test_briefing_generate_endpoint.py` — TestClient:
   - auth_error → HTTP 502 with `detail.error_type == "auth_error"`
   - rate_limit → HTTP 503
   - clean skip (None return) → HTTP 200 success=False, no error_type
   - happy path → HTTP 200 success=True with briefing_id

---

## Critical Files

| File | Change |
|------|--------|
| `src/crypto_news_aggregator/llm/exceptions.py` | NEW — LLMError class |
| `src/crypto_news_aggregator/llm/anthropic.py` | Raise LLMError; catch in analyze_sentiment/score_relevance/extract_themes |
| `src/crypto_news_aggregator/services/briefing_agent.py` | Re-raise LLMError; fix bare except |
| `src/crypto_news_aggregator/tasks/briefing_tasks.py` | Catch LLMError explicitly; add exc_info |
| `src/crypto_news_aggregator/api/v1/endpoints/briefing.py` | Map LLMError to HTTP codes; add error_type field |
| `tests/llm/test_llm_exceptions.py` | NEW |
| `tests/llm/test_anthropic_error_handling.py` | NEW |
| `tests/services/test_briefing_agent_error_handling.py` | NEW |
| `tests/api/test_briefing_generate_endpoint.py` | NEW |

---

## Deferred (out of scope for this task)

- `extract_entities_batch()` — still returns `{"results": [], "usage": {}}` on failure, but enhanced log message distinguishes failure from empty. Full propagation deferred until callers in `rss_fetcher.py` / `selective_processor.py` are hardened.

---

## Verification

1. `poetry run pytest tests/llm/ tests/services/test_briefing_agent_error_handling.py tests/api/test_briefing_generate_endpoint.py -v` — all new tests pass
2. `poetry run pytest tests/ -x --ignore=tests/integration` — full suite still passes
3. Manual: trigger briefing with invalid API key → API returns HTTP 502 with `{"error_type": "auth_error", ...}`
4. Manual: trigger briefing when one exists today → API returns HTTP 200 `success=False`, no `error_type`

---

## Acceptance Criteria

- [ ] Root cause identified and fixed (documented in completion summary)
- [ ] All three LLM systems operational and verified end-to-end
- [ ] No silent failures — every error logged with context
- [ ] Structured error responses propagate to API layer
- [ ] All error handling changes documented (before/after)
- [ ] Integration tests passing for all three systems (happy path + error path)

---

## Impact

Resolves BUG-052 and the recurring pattern of silent LLM failures. Combined with TASK-025 (cost controls), ensures systems stay up and failures are immediately visible.

---

## Related Tickets

- BUG-052: All LLM Systems Non-Functional (this ticket resolves BUG-052)
- TASK-024: LLM Spend Audit (blocks this ticket)
- TASK-025: Implement Cost Controls (parallel work)
- TASK-027: Health Check & Site Status (depends on this ticket)