---
id: BUG-058
type: bug
status: backlog
priority: critical
severity: high
created: 2026-04-04
updated: 2026-04-04
---

# Briefing Generation Silently Skips — Queries Non-Existent `trending_signals` Collection

## Problem

Twice-daily briefings (8 AM / 8 PM) are not generating. The beat schedule fires correctly, but `BriefingAgent.generate_briefing()` silently returns `None` every time because it cannot find any signals.

## Expected Behavior

Briefing agent computes trending signals on-demand from `entity_mentions`, finds signals + narratives, and generates a briefing via the LLM.

## Actual Behavior

`_get_trending_signals()` queries a pre-computed `trending_signals` MongoDB collection that was never populated. The query returns an empty list. The empty-data guard (line 153) then skips generation with:

```
WARNING: Skipping morning briefing: insufficient data (signals=0, narratives=N)
```

No LLM call is ever made. No error is raised.

## Steps to Reproduce

1. Wait for scheduled briefing (8 AM or 8 PM) or trigger manually via `/admin/trigger-briefing`
2. Check worker logs for "Skipping ... briefing: insufficient data"
3. Confirm `db.trending_signals.countDocuments()` returns 0 in MongoDB

## Environment

- Environment: production (Railway)
- User impact: high — core product output is not generating

---

## Resolution

**Status:** Complete
**Fixed:** 2026-04-04
**Branch:** `fix/bug-058-briefing-generation-skips`
**Commit:** `b82df8d`

### Root Cause

`BriefingAgent._get_trending_signals()` (briefing_agent.py lines 255-269) queries `db.trending_signals`, a collection that was designed to hold pre-computed signal scores but was never populated by any scheduled task. This was diagnosed in Sprint 12 Session 18 but the fix was never merged to main.

The working alternative — `compute_trending_signals()` in `services/signal_service.py` — computes signals on-demand by aggregating `entity_mentions`. It is already used by the `/api/v1/signals` endpoint and does not require a pre-computed collection.

### Changes Made

**File: `src/crypto_news_aggregator/services/briefing_agent.py`**

**Change 1: Add import (after line 43)**

Add this import alongside the existing `heartbeat` import:

```python
from crypto_news_aggregator.services.signal_service import compute_trending_signals
```

**Change 2: Replace `_get_trending_signals` method (lines 255-269)**

Replace the entire method with:

```python
async def _get_trending_signals(self, limit: int = 20) -> List[Dict[str, Any]]:
    """Get top trending signals computed on-demand from entity_mentions.

    Previously queried a pre-computed 'trending_signals' collection that was
    never populated, causing briefings to always skip with 'insufficient data'.
    Fixed to use compute_trending_signals() which aggregates entity_mentions
    directly. See BUG-055 Session 18 diagnosis.
    """
    try:
        signals = await compute_trending_signals(
            timeframe="24h",
            limit=limit,
            min_score=0.0,
        )
        return signals
    except Exception as e:
        logger.error(f"Failed to compute trending signals: {e}")
        return []
```

### Testing

1. Deploy to production with Anthropic credits available ($3+ balance)
2. Trigger manual briefing: `curl -X POST https://context-owl-production.up.railway.app/admin/trigger-briefing`
3. Verify worker logs show `Retrieved N trending signals` with N > 0
4. Verify briefing document appears in `db.daily_briefings`
5. Verify briefing appears on frontend at https://backdropxyz.vercel.app/

**Automated test:** Mock `compute_trending_signals` in existing briefing agent tests and verify `_get_trending_signals` returns results (vs empty list with old code).

### Files Changed

- `src/crypto_news_aggregator/services/briefing_agent.py`