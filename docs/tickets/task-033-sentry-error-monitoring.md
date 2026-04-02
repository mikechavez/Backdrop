---
id: TASK-033
type: feature
status: backlog
priority: high
complexity: small
created: 2026-04-02
updated: 2026-04-02
---

# Add Sentry Error Monitoring to Backdrop

## Problem/Opportunity
BUG-055 ran silently for 11+ days, burning ~480 wasted API calls/day against a full MongoDB. Every 3-minute cycle threw `OperationFailure: you are over your space quota` -- a real exception that was logged and swallowed. If Sentry had been wired in, we'd have gotten an alert on the first occurrence.

Sentry catches errors that happen. It covers: MongoDB failures, LLM API errors, Celery task exceptions, event loop bugs, and any unhandled FastAPI exceptions. Free tier gives 5K events/month -- more than enough for Backdrop's volume.

## Proposed Solution
Install `sentry-sdk[fastapi,celery]`, initialize in both the FastAPI app and the Celery worker, and add `SENTRY_DSN` as a Railway env var. Sentry's Python SDK auto-instruments FastAPI request errors and Celery task failures with zero custom code beyond the init call.

## User Story
As a solo operator, I want real-time alerts when Backdrop throws exceptions in production so that I catch failures within minutes instead of discovering them days later by manually combing logs.

## Acceptance Criteria
- [ ] Sentry SDK initialized in FastAPI app (catches unhandled request errors)
- [ ] Sentry SDK initialized in Celery worker (catches task failures)
- [ ] `SENTRY_DSN` added as Railway env var on all three services (web, celery-worker, celery-beat)
- [ ] Sentry alerts configured (email notification on first occurrence of new error)
- [ ] Test: trigger a deliberate error and confirm it appears in Sentry dashboard within 60 seconds
- [ ] No performance impact: `traces_sample_rate` set to 0.1 or lower

## Dependencies
- Sentry account created (free tier, see Manual Steps below)
- Independent of TASK-034 and TASK-035

## Manual Steps (before code deploy)
1. **Create Sentry account:** Go to https://sentry.io/signup/ -- sign up with GitHub
2. **Create project:** Select platform "Python" -- name it "backdrop" -- select framework "FastAPI"
3. **Copy DSN:** Settings > Projects > backdrop > Client Keys (DSN) > copy the DSN string
4. **Add to Railway:** Add `SENTRY_DSN=<your-dsn>` env var to all three services: `crypto-news-aggregator`, `celery-worker`, `celery-beat`
5. **Alert rules:** Sentry auto-creates a default alert rule (email on first occurrence). Verify this is active under Alerts > Rules.

## Implementation Notes

### File Changes

**1. Add dependency**

File: `requirements.txt` (or `pyproject.toml` -- whichever manages deps)
```
sentry-sdk[fastapi,celery]>=2.0.0
```

**2. Add config setting**

File: `src/crypto_news_aggregator/core/config.py`

Add to the `Settings` class alongside existing env var fields:
```python
# Monitoring
SENTRY_DSN: str | None = Field(default=None, env="SENTRY_DSN")
```

**3. Initialize Sentry in FastAPI app**

File: `src/crypto_news_aggregator/main.py`

Add near the top, BEFORE the `FastAPI()` instantiation:
```python
import sentry_sdk
from crypto_news_aggregator.core.config import get_settings

settings = get_settings()
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=0.1,
        environment="production",
    )
```

The `sentry-sdk[fastapi]` extra auto-detects and instruments FastAPI. No middleware needed -- the SDK patches FastAPI internally when `init()` is called before the app is created.

**4. Initialize Sentry in Celery worker**

File: `src/crypto_news_aggregator/tasks/__init__.py`

Add near the top, BEFORE the Celery app is created:
```python
import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from crypto_news_aggregator.core.config import get_settings

settings = get_settings()
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=[CeleryIntegration()],
        traces_sample_rate=0.1,
        environment="production",
    )
```

The `CeleryIntegration` auto-captures: task failures, task retries, task timeouts. It attaches task name + task_id to every Sentry event.

**5. Verification**

After deploying:
```bash
# Confirm integration with a test message
python -c "
import sentry_sdk
sentry_sdk.init(dsn='<your-dsn>')
sentry_sdk.capture_message('Backdrop Sentry test - delete me')
"
# Should appear in Sentry dashboard within 60 seconds
```

### What Sentry Catches vs. What It Misses
| Failure mode | Example | Caught by Sentry? |
|---|---|---|
| MongoDB errors | `OperationFailure: over space quota` (BUG-055) | Yes |
| Event loop bugs | `RuntimeError: Event loop is closed` (BUG-055) | Yes |
| LLM API failures | Timeout, auth error, rate limit | Yes |
| Celery task crashes | Unhandled exception in any task | Yes |
| Silent absence | fetch_news not scheduled (BUG-054) | **No -- needs TASK-034** |
| Pipeline stall | Articles stop flowing, no error thrown | **No -- needs TASK-034** |

### Estimated Effort
- Code changes: 15 min (4 files, ~20 lines total)
- Manual setup (Sentry account + Railway env vars): 10 min
- Verification: 5 min
- **Total: ~30 min**

## Open Questions
- [ ] None -- straightforward integration

## Completion Summary
- Actual complexity:
- Key decisions made:
- Deviations from plan: