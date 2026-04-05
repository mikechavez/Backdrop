---
id: BUG-059
type: bug
status: backlog
priority: critical
severity: critical
created: 2026-04-04
updated: 2026-04-04
---

# Cost Tracking Silently Fails + Spend Cap Never Enforces — $3/day Uncontrolled LLM Spend

## Problem

The BUG-056 spend cap ($0.25 soft / $0.33 hard) is correctly coded but never triggers. Actual Anthropic spend is ~$3/day while `db.api_costs` shows ~$0.15/day. The $0.15 comes only from `briefing_agent.py` (which has correct cost tracking). All other LLM callers have broken cost tracking, which means the budget cache always reads near $0, so the spend cap always passes.

Two root causes, three files affected:

1. **`anthropic.py`** — Wrong import path in all 5 cost tracking blocks (`db.mongo_manager` should be `db.mongodb`). Import fails silently inside try/except. API calls succeed and charge real money, but spend is never written to `db.api_costs`.

2. **`optimized_anthropic.py`** — Zero budget checks on any of its 3 API-calling methods. Also uses `asyncio.create_task()` for cost tracking (same fire-and-forget bug fixed in briefing_agent.py Session 14). This client is the RSS fetcher's primary LLM path for entity extraction and narrative elements.

Combined effect: the budget cache reads from `db.api_costs`, which is mostly empty because costs aren't being written. The spend cap sees ~$0 and allows everything.

## Expected Behavior

- All LLM API calls write cost records to `db.api_costs`
- Budget cache reflects actual daily spend
- Spend cap enforces: soft limit ($0.25) blocks non-critical ops, hard limit ($0.33) blocks all ops
- Daily LLM spend stays under $0.33 (~$10/month)

## Actual Behavior

- `anthropic.py` cost tracking silently fails on every call (ImportError caught by try/except)
- `optimized_anthropic.py` has no budget checks — processes unlimited articles per cycle
- Budget cache shows ~$0 → spend cap never triggers
- Actual spend: ~$3/day (~$90/month), 9x over target

## Steps to Reproduce

1. Check Anthropic dashboard: ~$3 consumed in last 24 hours
2. Query `db.api_costs` aggregation for same period: shows ~$0.15
3. Check Railway worker logs for: `Failed to track cost` or `Failed to track entity extraction cost` warnings (these are the silent ImportError catches)
4. Grep for the wrong import: `grep -rn "db.mongo_manager" src/` — should return hits in `anthropic.py`

## Environment

- Environment: production (Railway)
- User impact: high — uncontrolled spend, BUG-056 spend cap ineffective

---

## Resolution

**Status:** ✅ FIXED
**Fixed:** 2026-04-05 (Session 25)
**Branch:** `fix/bug-058-briefing-generation-skips` (includes BUG-058 + BUG-059 fixes)
**Commit:** `586e99e` - fix(llm): Fix cost tracking and add budget enforcement (BUG-059)

### Root Cause

**Root Cause 1: Wrong import path in `anthropic.py`**

Five cost tracking blocks (lines 443-444, 662-663, 758-759, 836-837, 914-915) all import:

```python
from crypto_news_aggregator.db.mongo_manager import mongo_manager  # WRONG
```

The correct module name is `mongodb`, not `mongo_manager`:

```python
from crypto_news_aggregator.db.mongodb import mongo_manager  # CORRECT
```

Every other file in the codebase uses the correct path (`briefing_agent.py:25`, `signal_service.py:21`, `cost_tracker.py:288`). The wrong import throws `ModuleNotFoundError`, caught by the surrounding `try/except Exception`, which logs a warning and continues. The API call already completed and charged real money.

**Root Cause 2: `optimized_anthropic.py` has no spend controls**

The `OptimizedAnthropicLLM` class is used by the RSS fetcher (`rss_fetcher.py:410`) for entity extraction and narrative element extraction. Three methods make API calls with zero budget checks:

- `extract_entities_batch()` — called per-article during RSS enrichment
- `extract_narrative_elements()` — called per-article for narrative processing
- `generate_narrative_summary()` — called for narrative clustering

None of these call `check_llm_budget()`. There is no backlog throttle (`ENRICHMENT_MAX_ARTICLES_PER_CYCLE` is only enforced in `anthropic.py`'s `enrich_articles_batch`). When 100+ articles queue up, all 100 get processed in a single cycle.

Additionally, all three methods use `asyncio.create_task()` for cost tracking, which is the fire-and-forget pattern already identified and fixed in `briefing_agent.py` (Session 14). In Celery workers, the event loop may close before the task completes, silently dropping the cost record.

### Changes Made

---

#### File 1: `src/crypto_news_aggregator/llm/anthropic.py`

**Change 1a: Fix import path in `extract_entities_batch` cost tracking (around line 443-444)**

Find (appears once, in the cost tracking block inside `extract_entities_batch`):
```python
from crypto_news_aggregator.services.cost_tracker import CostTracker
from crypto_news_aggregator.db.mongo_manager import mongo_manager
```

Replace with:
```python
from crypto_news_aggregator.services.cost_tracker import CostTracker
from crypto_news_aggregator.db.mongodb import mongo_manager
```

**Change 1b: Fix import path in `enrich_articles_batch` cost tracking (around line 662-663)**

Same fix — find and replace `db.mongo_manager` → `db.mongodb`.

**Change 1c: Fix import path in `score_relevance_tracked` cost tracking (around line 758-759)**

Same fix — find and replace `db.mongo_manager` → `db.mongodb`.

**Change 1d: Fix import path in `analyze_sentiment_tracked` cost tracking (around line 836-837)**

Same fix — find and replace `db.mongo_manager` → `db.mongodb`.

**Change 1e: Fix import path in `extract_themes_tracked` cost tracking (around line 914-915)**

Same fix — find and replace `db.mongo_manager` → `db.mongodb`.

**Shortcut for Claude Code:** There are exactly 5 occurrences. Run:
```bash
sed -i 's/from crypto_news_aggregator.db.mongo_manager import mongo_manager/from crypto_news_aggregator.db.mongodb import mongo_manager/g' src/crypto_news_aggregator/llm/anthropic.py
```

Then verify: `grep -n "mongo_manager" src/crypto_news_aggregator/llm/anthropic.py` should return zero hits for `db.mongo_manager`.

---

#### File 2: `src/crypto_news_aggregator/llm/optimized_anthropic.py`

**Change 2a: Add budget check imports (top of file, after existing imports)**

Add after the existing imports (around line 14):

```python
from ..services.cost_tracker import check_llm_budget, refresh_budget_if_stale
```

**Change 2b: Add budget check to `_make_api_call` (beginning of method, around line 56)**

This is the single chokepoint — all three API methods call `_make_api_call`. Adding the check here guards all paths.

Add `operation` parameter and budget check at the top of `_make_api_call`:

```python
def _make_api_call(self, prompt: str, model: str, max_tokens: int = 1000, temperature: float = 0.3, operation: str = "") -> Dict[str, Any]:
    """
    Make synchronous API call to Anthropic

    Returns:
        Dict with 'content' (text response), 'input_tokens', and 'output_tokens'
    """
    # --- SPEND CAP CHECK ---
    allowed, reason = check_llm_budget(operation)
    if not allowed:
        logger.warning(f"LLM call blocked by spend cap ({reason}) for '{operation}'")
        raise RuntimeError(f"Daily spend limit reached ({reason})")
    # --- END SPEND CAP CHECK ---

    headers = {
```

**Change 2c: Pass operation name from each calling method**

In `extract_entities_batch`, change the `_make_api_call` call (around line 127):
```python
api_response = self._make_api_call(
    prompt=prompt,
    model=self.HAIKU_MODEL,
    max_tokens=1000,
    temperature=0.3,
    operation="entity_extraction"
)
```

In `extract_narrative_elements`, change the `_make_api_call` call (around line 237):
```python
api_response = self._make_api_call(
    prompt=prompt,
    model=self.HAIKU_MODEL,
    max_tokens=800,
    temperature=0.3,
    operation="narrative_extraction"
)
```

In `generate_narrative_summary`, change the `_make_api_call` call (around line 300):
```python
api_response = self._make_api_call(
    prompt=prompt,
    model=self.SONNET_MODEL,
    max_tokens=500,
    temperature=0.7,
    operation="narrative_summary"
)
```

**Change 2d: Fix fire-and-forget cost tracking — switch `asyncio.create_task()` to `await`**

There are 6 instances of `asyncio.create_task(tracker.track_call(...))` in this file (2 in `extract_entities_batch`, 2 in `extract_narrative_elements`, 2 in `generate_narrative_summary` — one for cache hits, one for API calls in each method).

Replace every instance of:
```python
asyncio.create_task(
    tracker.track_call(
        ...
    )
)
```

With:
```python
await tracker.track_call(
    ...
)
```

This matches the fix already applied in `briefing_agent.py` (Session 14, commit f119256).

---

#### File 3: `src/crypto_news_aggregator/llm/anthropic.py` (additional fix)

**Change 3: Fix fire-and-forget cost tracking in tracked methods**

Same `asyncio.create_task` issue exists in 4 locations in `anthropic.py`:

- `enrich_articles_batch` (around line 669)
- `score_relevance_tracked` (around line 765)
- `analyze_sentiment_tracked` (around line 843)
- `extract_themes_tracked` (around line 921)

Replace each `asyncio.create_task(tracker.track_call(...))` with `await tracker.track_call(...)`.

Also replace the pattern:
```python
import asyncio
asyncio.create_task(
```
with just calling `await` directly. Remove the `import asyncio` lines inside these blocks since they're no longer needed.

The `extract_entities_batch` method (around line 458-469) is synchronous so it can't use `await`. For this one, keep the existing thread-based approach but fix the import path (Change 1a already handles this).

---

### Testing

**Verify import fix:**
```bash
# Should return zero hits
grep -n "db.mongo_manager" src/crypto_news_aggregator/llm/anthropic.py

# Should return hits in cost tracking blocks
grep -n "db.mongodb" src/crypto_news_aggregator/llm/anthropic.py
```

**Verify budget checks in optimized client:**
```bash
grep -n "check_llm_budget" src/crypto_news_aggregator/llm/optimized_anthropic.py
# Should return at least 1 hit (in _make_api_call)
```

**Verify no remaining create_task in cost tracking:**
```bash
grep -n "create_task" src/crypto_news_aggregator/llm/optimized_anthropic.py
# Should return zero hits

grep -n "create_task.*track_call" src/crypto_news_aggregator/llm/anthropic.py
# Should return zero hits (except the sync extract_entities_batch which uses threading)
```

**Production verification (post-deploy):**

1. Add $5 Anthropic credits
2. Deploy to Railway
3. Trigger RSS fetch: `curl -X POST https://context-owl-production.up.railway.app/admin/trigger-fetch`
4. After enrichment completes, check:
   - `db.api_costs.countDocuments({timestamp: {$gte: new Date(Date.now() - 3600000)}})` — should show new records
   - Worker logs should NOT show `Failed to track cost` warnings
   - After spend reaches $0.25: non-critical ops (sentiment, themes) should log `blocked by spend cap`
   - After spend reaches $0.33: all ops should log `blocked by spend cap`
5. Monitor Anthropic dashboard over 24 hours — daily spend should stay under $0.33

**Unit tests to add:**
- Test that `OptimizedAnthropicLLM._make_api_call` raises `RuntimeError` when `check_llm_budget` returns `(False, "hard_limit")`
- Test that cost records are written to `db.api_costs` after `optimized_anthropic` API calls (mock the HTTP call, verify `track_call` is awaited)

### Files Changed

- `src/crypto_news_aggregator/llm/anthropic.py` — Fix 5 import paths (`db.mongo_manager` → `db.mongodb`), replace 4 `create_task` with `await` in tracked methods
- `src/crypto_news_aggregator/llm/optimized_anthropic.py` — Add budget check import + check in `_make_api_call`, pass operation names from 3 calling methods, replace 6 `create_task` with `await`