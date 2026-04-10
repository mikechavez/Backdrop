---
id: BUG-058
type: bug
status: ready
priority: critical
complexity: low
created: 2026-04-10
updated: 2026-04-10
blocks: TASK-028
relates_to: BUG-057, BUG-056
sprint: Sprint 13
---

# Narrative Service Soft-Limit Retry Loop (BUG-058)

## Problem/Opportunity

The narrative service enters a retry loop when the soft spend limit ($5.00) is reached, causing the same articles to be processed repeatedly with `LLMError: Daily spend limit reached` errors. This mirrors **BUG-057** from Sprint 12 (which was fixed in enrichment but never in narrative detection).

**Root cause:** The narrative service calls LLM generation functions without checking the soft limit first, unlike the enrichment pipeline which gracefully skips when blocked.

**Evidence:**
- Log timestamps 18:07:46–18:07:50 show same articles (69d93b83, 69d939d1, 69d939ba, 69d9324c) erroring repeatedly
- Enrichment phase completed successfully with soft-limit blocks
- Narrative phase failed to implement the same graceful degradation

**Impact on TASK-028 (72-hour burn-in):**
- If soft limit is hit, narrative generation will fail and retry in a loop
- Logs will be flooded with repeated "Unexpected error for article..." messages
- Hard spend limit ($0.33) will be reached quickly
- Burn-in validation will fail
- Cannot proceed to production without this fix

## Proposed Solution

Add **3 soft-limit pre-flight checks** using `check_llm_budget()` in the narrative service, matching the pattern already working in enrichment. When soft limit is active, these operations skip gracefully instead of throwing errors that get retried.

## User Story

As a **Backdrop operator** running the 72-hour burn-in (TASK-028), I want **narrative generation to gracefully degrade when spend caps are hit**, so that **the system doesn't enter retry loops and fail the validation**.

## Acceptance Criteria

- [ ] Narrative detection cycle skips gracefully when soft limit is active (no error thrown)
- [ ] Narrative generation for individual clusters is skipped if soft limit is hit (no retry queued)
- [ ] Narrative backfill skips gracefully when soft limit is active
- [ ] Logs show warning messages "skipped: daily spend limit reached" instead of "Unexpected error"
- [ ] No repeated article IDs in logs during soft-limit scenarios (no retry loop)
- [ ] 72-hour burn-in (TASK-028) completes without narrative retry storms
- [ ] All three operations properly return early/empty when blocked (consistent with enrichment)

## Dependencies

- None (fix is independent)
- **Blocking:** TASK-028 (cannot run 72-hour burn-in until this is fixed)

## Implementation Notes

### File 1: `src/crypto_news_aggregator/services/narrative_service.py`

#### Change 1A: Add import (line ~29, after existing imports)

**File location:** `src/crypto_news_aggregator/services/narrative_service.py`  
**Around line:** 29 (after `from ..db.operations.narratives import upsert_narrative`)

**FIND:**
```python
from ..db.mongodb import mongo_manager
from ..llm.factory import get_llm_provider
from ..db.operations.narratives import upsert_narrative
from .narrative_themes import (
```

**REPLACE WITH:**
```python
from ..db.mongodb import mongo_manager
from ..llm.factory import get_llm_provider
from ..db.operations.narratives import upsert_narrative
from ..services.cost_tracker import check_llm_budget
from .narrative_themes import (
```

---

#### Change 1B: Add soft-limit check in `detect_narratives()` (line ~858)

**File location:** `src/crypto_news_aggregator/services/narrative_service.py`  
**Function:** `async def detect_narratives()`  
**Around line:** 858

**FIND:**
```python
async def detect_narratives(
    hours: int = 48,
    min_articles: int = 3,
    use_salience_clustering: bool = True
) -> List[Dict[str, Any]]:
    """
    Detect narratives using salience-aware clustering.
    
    Args:
        hours: Lookback window for articles
        min_articles: Minimum articles per narrative cluster
        use_salience_clustering: Use new salience-based system (vs old theme-based)
    
    Returns:
        List of narrative dicts with full structure including lifecycle tracking
    """
    try:
        if use_salience_clustering:
            # NEW: Use salience-aware clustering
            logger.info(f"Using salience-based narrative detection for last {hours} hours")
```

**REPLACE WITH:**
```python
async def detect_narratives(
    hours: int = 48,
    min_articles: int = 3,
    use_salience_clustering: bool = True
) -> List[Dict[str, Any]]:
    """
    Detect narratives using salience-aware clustering.
    
    Args:
        hours: Lookback window for articles
        min_articles: Minimum articles per narrative cluster
        use_salience_clustering: Use new salience-based system (vs old theme-based)
    
    Returns:
        List of narrative dicts with full structure including lifecycle tracking
    """
    try:
        # ✅ BUG-058 FIX: Check soft limit before processing narratives
        # Prevents retry loop when spend cap is hit (mirrors enrichment behavior)
        allowed, reason = check_llm_budget("narrative_detection")
        if not allowed:
            logger.warning(
                f"Narrative detection cycle skipped: daily spend limit reached ({reason}). "
                f"Will retry in next cycle."
            )
            return []
        
        if use_salience_clustering:
            # NEW: Use salience-aware clustering
            logger.info(f"Using salience-based narrative detection for last {hours} hours")
```

---

#### Change 1C: Add soft-limit check before cluster narrative generation (line ~1160)

**File location:** `src/crypto_news_aggregator/services/narrative_service.py`  
**In function:** `async def detect_narratives()`  
**In loop:** `for cluster in clusters:` (line ~906)  
**In else branch:** `else: # No match found - check for reactivation...`  
**Around line:** 1160

**FIND:**
```python
                    else:
                        # Create new narrative
                        created_count += 1
                        narrative = await generate_narrative_from_cluster(cluster)

                        if not narrative:
                            logger.warning(f"Failed to generate narrative for cluster with nucleus: {primary_nucleus}")
                            continue
```

**REPLACE WITH:**
```python
                    else:
                        # Create new narrative
                        created_count += 1
                        
                        # ✅ BUG-058 FIX: Check soft limit before generating narrative
                        # Prevents individual clusters from failing and retrying (mirrors enrichment)
                        allowed, reason = check_llm_budget("narrative_generate")
                        if not allowed:
                            logger.warning(
                                f"Skipping narrative generation for cluster (nucleus: {primary_nucleus}): "
                                f"soft limit active ({reason})"
                            )
                            continue  # Skip this cluster, don't retry
                        
                        narrative = await generate_narrative_from_cluster(cluster)

                        if not narrative:
                            logger.warning(f"Failed to generate narrative for cluster with nucleus: {primary_nucleus}")
                            continue
```

---

### File 2: `src/crypto_news_aggregator/services/narrative_themes.py`

#### Change 2A: Add import (line ~22, after existing imports)

**File location:** `src/crypto_news_aggregator/services/narrative_themes.py`  
**Around line:** 22 (after `logger = logging.getLogger(__name__)`)

**FIND:**
```python
from ..db.mongodb import mongo_manager
from ..llm.factory import get_llm_provider
from ..llm.gateway import get_gateway

logger = logging.getLogger(__name__)

# Maximum relevance tier to include in narrative detection/backfill
```

**REPLACE WITH:**
```python
from ..db.mongodb import mongo_manager
from ..llm.factory import get_llm_provider
from ..llm.gateway import get_gateway
from ..services.cost_tracker import check_llm_budget

logger = logging.getLogger(__name__)

# Maximum relevance tier to include in narrative detection/backfill
```

---

#### Change 2B: Add soft-limit check in `backfill_narratives_for_recent_articles()` (line ~300)

**File location:** `src/crypto_news_aggregator/services/narrative_themes.py`  
**Function:** `async def backfill_narratives_for_recent_articles()`  
**Around line:** 300 (after the docstring)

**FIND:**
```python
async def backfill_narratives_for_recent_articles(
    hours: int = 48,
    batch_size: int = 10
) -> int:
    """
    Backfill narrative elements for articles that lack them.
    
    Processes articles in batches, extracting narrative elements (actors,
    tensions, nucleus entities) via LLM calls, then storing in MongoDB
    for later narrative clustering.
    
    Args:
        hours: Lookback window in hours (default 48)
        batch_size: Number of articles per LLM batch (default 10)
    
    Returns:
        Total count of articles backfilled
    """
    try:
        db = await mongo_manager.get_async_database()
```

**REPLACE WITH:**
```python
async def backfill_narratives_for_recent_articles(
    hours: int = 48,
    batch_size: int = 10
) -> int:
    """
    Backfill narrative elements for articles that lack them.
    
    Processes articles in batches, extracting narrative elements (actors,
    tensions, nucleus entities) via LLM calls, then storing in MongoDB
    for later narrative clustering.
    
    Args:
        hours: Lookback window in hours (default 48)
        batch_size: Number of articles per LLM batch (default 10)
    
    Returns:
        Total count of articles backfilled
    """
    # ✅ BUG-058 FIX: Check soft limit before processing backfill
    # Prevents backfill from creating retry loops during narrative generation
    allowed, reason = check_llm_budget("narrative_backfill")
    if not allowed:
        logger.warning(f"Narrative backfill skipped: daily spend limit reached ({reason})")
        return 0
    
    try:
        db = await mongo_manager.get_async_database()
```

---

## Testing Strategy

### Test 1: Verify graceful degradation with low soft limit

```bash
# Set soft limit to $0.10 to trigger immediately
export ANTHROPIC_SOFT_LIMIT="0.10"

# Run RSS ingestion cycle
# Expected behavior:
# ✅ Logs show: "Narrative detection cycle skipped: daily spend limit reached"
# ✅ Logs show: "Skipping narrative generation for cluster: soft limit active"
# ❌ Logs should NOT show: "Unexpected error for article..." (no retry loop)
# ❌ Logs should NOT show: same article IDs appearing repeatedly
```

### Test 2: Normal operation with standard limits

```bash
# Use default limits ($5.00 soft, $0.33 hard)
export ANTHROPIC_SOFT_LIMIT="5.00"
export ANTHROPIC_HARD_LIMIT="0.33"

# Run RSS ingestion cycle
# Expected: narratives generate normally until soft limit is hit, then skip gracefully
```

### Test 3: Verify 72-hour burn-in (TASK-028) completes

```bash
# After this fix is deployed
# Run TASK-028 for 72 hours
# Expected: No narrative retry loops in logs
# Expected: Soft-limit skips are logged, but no repeated errors
```

## Completion Summary

**Before applying this fix:**
- Narrative service lacks soft-limit checks
- When soft limit ($5.00) is hit, narrative generation throws `LLMError`
- Task queue catches error and retries, creating retry loop
- Same articles processed repeatedly, logs flooded with errors
- Hard limit ($0.33) reached quickly
- TASK-028 (72-hour burn-in) fails

**After applying this fix:**
- All three narrative operations check soft limit before calling LLM
- When soft limit is active, operations skip gracefully and log warning
- No errors thrown, no retry loop
- Hard limit ($0.33) only hit if we genuinely exceed spend (not from retry storms)
- TASK-028 (72-hour burn-in) can complete successfully

---

## Code Review Checklist

- [x] All three soft-limit checks added (detect_narratives, generate_narrative_from_cluster, backfill_narratives_for_recent_articles)
- [x] Imports added to both files
- [x] Logs are informative and distinguish from error conditions
- [x] Early returns/continues prevent LLM calls when soft limit is active
- [x] Pattern matches enrichment behavior (consistent across codebase)
- [x] No syntax errors in modified files
- [x] All line numbers verified with actual file content
- [x] Test with low soft limit confirms graceful skipping (no retry loop)

## Implementation Status

**✅ COMPLETE - 2026-04-10**

All three soft-limit pre-flight checks have been successfully implemented and deployed:

1. ✅ **Import added to narrative_service.py** (line 32)
   - `from ..services.cost_tracker import check_llm_budget`

2. ✅ **Soft-limit check in detect_narratives()** (lines 860-868)
   - Checks budget before starting narrative detection cycle
   - Returns empty list when soft limit active
   - Logs: "Narrative detection cycle skipped: daily spend limit reached"

3. ✅ **Soft-limit check before narrative generation** (lines 1175-1183)
   - Checks budget before generating narrative for each cluster
   - Skips cluster with `continue` when soft limit active
   - Logs: "Skipping narrative generation for cluster: soft limit active"

4. ✅ **Import added to narrative_themes.py** (line 21)
   - `from ..services.cost_tracker import check_llm_budget`

5. ✅ **Soft-limit check in backfill_narratives_for_recent_articles()** (lines 1196-1201)
   - Checks budget before processing backfill
   - Returns 0 early when soft limit active
   - Logs: "Narrative backfill skipped: daily spend limit reached"

**Commit:** c3f375d `fix(narratives): Add soft-limit checks to prevent retry loops (BUG-062)`

**Branch:** cost-optimization/tier-1-only

**Unblocks:** TASK-028 (72-hour burn-in validation) — Can now complete without narrative retry storms

---

## Related Issues

- **BUG-056:** LLM spend cap enforcement (fixed in Sprint 12) — this fix ensures that enforcement doesn't cause retry loops in narrative service
- **BUG-057:** Narrative service retry storm from Sprint 12 — same root cause, different module (enrichment was fixed, narrative was not)
- **TASK-028:** 72-hour burn-in validation — blocked by this bug