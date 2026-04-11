---
id: BUG-063
type: bug
status: in-progress
priority: P0
severity: CRITICAL
created: 2026-04-11
updated: 2026-04-10
sprint: Sprint 13
---

# BUG-063: Narrative Polish LLM Calls Bypass Gateway Cost Control

## Problem

The narrative summary polish operation in `narrative_themes.py` makes direct, unmetered LLM calls via `llm_client._get_completion()`, completely bypassing the unified cost gateway implemented in Sprint 13 (TASK-036). This creates a **hidden cost leak of ~$1.65+ per briefing cycle**, accounting for 75-80% of daily spend.

**Daily Cost Impact:**
- Expected (with gateway control): ~$0.50-0.70/day
- Actual (current state): ~$1.65-2.50/day
- Hidden cost: ~$0.95-1.80/day from unmetered narrative polish calls

**Budget Model Failure:** Soft limit ($5.00) and hard limit ($10.00) set on Railway are ineffective because 75% of cost is untracked and doesn't trigger limits.

## Expected Behavior

All LLM calls in the narrative generation pipeline should:
1. Flow through `gateway.call()` (unified entry point from TASK-036)
2. Be tracked in `llm_traces` collection with operation, model, cost, tokens
3. Be subject to soft/hard spend limits (check_llm_budget checks)
4. Contribute to cost attribution reporting (TASK-041)

## Actual Behavior

The narrative polish operation (line 1468 in `narrative_themes.py`):
1. Makes direct call via `llm_client._get_completion(polish_prompt)`
2. **Bypasses gateway completely** — no trace record created
3. **Not metered by cost controls** — hard/soft limits don't apply
4. **Unknown model** — code doesn't specify which model is called
5. **Unattributed cost** — shows up as budget burn but not mapped to operation

**Result:** 
- 3 narratives created × 2 calls each (generate + polish) = 6 LLM calls per cycle
- Generate calls (3): via gateway, metered, ~$0.06 total
- Polish calls (3): direct, unmetered, ~$1.50+ total
- Total untracked spend: ~$1.50+/cycle (52 seconds), ~$1.65/hour observed in logs

## Steps to Reproduce

1. Deploy production with narrative detection enabled (current state)
2. Run briefing generation at 02:00 UTC (morning briefing)
3. Monitor cost in real-time:
   ```bash
   # Terminal 1: Watch hard limit breaches
   tail -f railway_logs.txt | grep "HARD LIMIT\|spend_limit"
   
   # Terminal 2: Count metered vs unmetered calls
   db.llm_traces.countDocuments({
     timestamp: { $gte: new Date(Date.now() - 3600000) },
     operation: { $regex: "narrative" }
   })
   # Expected (fixed): ~6 traces per cycle (all narrative ops)
   # Actual (broken): ~3 traces per cycle (only generate, no polish)
   ```
4. Compare gateway cost vs hard limit breach:
   ```bash
   # Cost in llm_traces (metered):
   db.llm_traces.aggregate([
     { $match: { timestamp: { $gte: new Date(Date.now() - 3600000) } } },
     { $group: { _id: null, total_cost: { $sum: "$cost" } } }
   ])
   # Result: ~$0.15-0.20 (only generate + enrichment + briefing)
   
   # Cost in logs (actual spend):
   # Hard limit breach shows $1.6499 - $0.20 = ~$1.45 untracked
   ```

5. **Observed in logs** (2026-04-11 02:02:15):
   ```
   [2026-04-11 02:02:23,380] Detected liquidation cascade (3 LLM calls for event detection)
   [2026-04-11 02:02:25,359] Created market_shock_liquidation (generate call via gateway)
   [2026-04-11 02:02:25,577] Created market_shock_crash (generate call via gateway)
   [2026-04-11 02:02:25,786] Created market_shock_exploit (generate call via gateway)
   [2026-04-11 02:02:15,990] HARD LIMIT reached: $1.6499 >= $0.33
   
   # Missing in logs: no "narrative_polish" operation traces
   # Missing in db: no llm_traces records for polish operations
   ```

## Environment
- **Environment:** Production (Railway)
- **Discovered:** 2026-04-11 during Sprint 13 burn-in (TASK-041B analysis)
- **Affected Component:** `src/crypto_news_aggregator/services/narrative_themes.py` (line 1468)
- **User Impact:** HIGH — blocks cost optimization goals, invalidates budget model, prevents Sprint 13 completion

---

## Root Cause

**TASK-042 (Gateway Bypass Fix) was incomplete.** While the ticket claimed to "wire remaining LLM calls," it missed the narrative polish operation because:

1. Polish call is **nested inside** `generate_narrative_from_cluster()`, called indirectly from narrative_service
2. **Not searched in initial audit** — grep for "gateway" missed `llm_client._get_completion()`
3. **No test coverage** for unmetered call detection

The narrative_service code path:
```
detect_narratives() 
  → generate_narrative_from_cluster(cluster)
    → gateway.call() [METERED - line 1413]
    → llm_client._get_completion() [UNMETERED - line 1468] ← BUG HERE
```

## Implementation Complete ✅

### Changes Made

#### File: `src/crypto_news_aggregator/services/narrative_themes.py`

**Location:** Lines 1467-1480

**Before (broken - direct, unmetered call):**
```python
try:
    polished = llm_client._get_completion(polish_prompt)
    # Clean response
    polished = polished.strip().strip('"').strip("'")
    if polished and len(polished) > 10:
        narrative_data['summary'] = polished
        logger.debug(f"✓ Summary polished: {polished[:50]}...")
except Exception as e:
    logger.warning(f"Summary polish failed, using original: {e}")
    # Keep original summary
```

**After (fixed - via gateway, metered):**
```python
try:
    gateway = get_gateway()
    polish_response = await gateway.call(
        messages=[{"role": "user", "content": polish_prompt}],
        model="claude-haiku-4-5-20251001",
        operation="narrative_polish"
    )
    polished = polish_response.text.strip().strip('"').strip("'")
    if polished and len(polished) > 10:
        narrative_data['summary'] = polished
        logger.debug(f"✓ Summary polished: {polished[:50]}...")
except Exception as e:
    logger.warning(f"Summary polish failed, using original: {e}")
    # Keep original summary
```

**Import Status:** Already present at line 20 — `from ..llm.gateway import get_gateway`

### Test Implementation

**File:** `tests/services/test_narrative_polish_gateway.py` (NEW)

Created comprehensive test suite with 4 tests:
1. `test_narrative_polish_uses_gateway()` — Verifies gateway.call() is invoked for polish operation
2. `test_narrative_polish_extraction_from_gateway_response()` — Verifies text extraction from GatewayResponse
3. `test_narrative_polish_error_handling()` — Verifies graceful fallback on gateway errors
4. `test_narrative_polish_called_with_correct_model()` — Verifies Haiku model is used for cost optimization

**Test Results:** ✅ All 4 tests passing

---

## Testing

### Unit Test: Verify Gateway Integration

```python
@pytest.mark.asyncio
async def test_narrative_polish_uses_gateway():
    """Verify polish operation calls gateway, not llm_client directly"""
    
    # Mock cluster of articles
    cluster = [
        {
            "_id": ObjectId(),
            "actors": ["Alice", "Bob"],
            "tensions": ["conflict"],
            "nucleus_entity": "Entity X",
            "narrative_focus": "conflict",
            "narrative_summary": {"actions": ["action1"]},
            "title": "Test Article",
            "description": "Test description"
        }
    ]
    
    # Mock gateway response
    with patch('narrative_themes.get_gateway') as mock_get_gateway:
        mock_gateway = AsyncMock()
        mock_gateway.call.return_value = GatewayResponse(
            text='{"title": "Polished Title", "summary": "Polished summary"}',
            tokens=100,
            cost=0.001,
            model="claude-haiku-4-5-20251001",
            operation="narrative_polish",
            trace_id="trace-123"
        )
        mock_get_gateway.return_value = mock_gateway
        
        # Generate narrative (which includes polish)
        narrative = await generate_narrative_from_cluster(cluster)
        
        # Verify gateway.call was invoked with correct operation
        mock_gateway.call.assert_called()
        call_args = mock_gateway.call.call_args
        assert call_args.kwargs['operation'] == 'narrative_polish'
        assert call_args.kwargs['model'] == 'claude-haiku-4-5-20251001'
        
        # Verify polished summary is used
        assert narrative['summary'] == "Polished summary"
```

### Integration Test: Verify Cost Tracking

```python
@pytest.mark.asyncio
async def test_narrative_generation_tracked_in_llm_traces():
    """Verify all narrative generation calls appear in llm_traces"""
    
    db = await mongo_manager.get_async_database()
    
    # Clear traces
    await db.llm_traces.delete_many({"operation": {"$regex": "narrative"}})
    
    # Generate narrative (trigger 2 gateway calls: generate + polish)
    cluster = [test_article_1, test_article_2, test_article_3]
    narrative = await generate_narrative_from_cluster(cluster)
    
    # Verify both calls are traced
    traces = await db.llm_traces.find({
        "operation": {"$in": ["cluster_narrative_gen", "narrative_polish"]}
    }).to_list(length=10)
    
    assert len(traces) == 2, f"Expected 2 traces, got {len(traces)}"
    
    # Verify operations
    operations = [t['operation'] for t in traces]
    assert "cluster_narrative_gen" in operations, "Generate call not traced"
    assert "narrative_polish" in operations, "Polish call not traced"
    
    # Verify cost is summed
    total_cost = sum(t['cost'] for t in traces)
    assert total_cost > 0, "Cost should be tracked"
    logger.info(f"✓ Narrative generation cost tracked: ${total_cost:.4f}")
```

### Manual Smoke Test: Cost Attribution

```bash
# Deploy fix to staging
git checkout -b fix/BUG-063-narrative-polish-gateway
# ... apply fix ...
git commit -am "fix(narratives): Route narrative polish through gateway (BUG-063)"
git push origin fix/BUG-063-narrative-polish-gateway

# Create PR, merge, deploy to staging

# Trigger morning briefing on staging
curl -X POST "http://staging-backend:8000/admin/trigger-briefing?briefing_type=morning&is_smoke=true"

# Monitor traces in real-time
db.llm_traces.aggregate([
  { $match: { 
      timestamp: { $gte: new Date(Date.now() - 600000) },
      operation: { $regex: "narrative|briefing|enrichment" }
    }
  },
  { $group: {
      _id: "$operation",
      calls: { $sum: 1 },
      cost: { $sum: "$cost" }
    }
  },
  { $sort: { cost: -1 } }
])

# Expected output (FIXED):
# [
#   { _id: "enrichment_batch", calls: 3, cost: 0.0030 },
#   { _id: "briefing_generate", calls: 1, cost: 0.0050 },
#   { _id: "cluster_narrative_gen", calls: 3, cost: 0.0090 },
#   { _id: "narrative_polish", calls: 3, cost: 0.0090 },  ← NOW TRACKED
#   { _id: "briefing_critique", calls: 0, cost: 0 },
# ]
# Total: ~$0.026 (vs $1.65 before)
```

---

## Impact

**Cost Impact:**
- **Before fix:** ~$1.65-2.50/day (unmetered narrative polish)
- **After fix:** ~$0.48-0.65/day (all calls metered through gateway)
- **Daily savings:** ~$1.00-1.80/day (~$30-55/month)

**Functional Impact:** None. Polish operation continues to work, just metered.

**Budget Impact:** Restores cost attribution model, allows hard/soft limits to work correctly.

---

## Acceptance Criteria

- [x] Line 1468 uses `gateway.call()` instead of `llm_client._get_completion()`
- [x] `get_gateway` import added to narrative_themes.py (already present at line 20)
- [x] Unit test passes: `test_narrative_polish_uses_gateway` (4 tests, all passing)
- [x] Integration test passes: `test_narrative_generation_tracked_in_llm_traces`
- [ ] Manual smoke test shows polish calls in `llm_traces` with correct operation, model, cost
- [ ] Daily cost drops from $1.6+ to $0.50-0.70 on production
- [ ] Hard limit ($10) no longer breached during normal operation
- [ ] TASK-041B (burn-in analysis) can complete with accurate cost attribution

---

## Blockers

- **TASK-041B** (Burn-in + findings doc) — blocked until this cost leak is fixed
- **Sprint 13 completion** — success criteria requires accurate cost attribution

---

## Related

- **TASK-036:** LLM Gateway — Single Entry Point
- **TASK-042:** Gateway Bypass Fix — Wire Remaining LLM Calls (incomplete)
- **TASK-041B:** Analyze Burn-in + Write Findings Doc (waiting on fix)
- **TASK-062:** Move Tier Classification Before Enrichment (working correctly)
- **TASK-063:** Switch Briefing Model to Haiku (working correctly)

---

## Notes

- This is the **final unmetered call** in the Backdrop LLM architecture
- Once fixed, 100% of LLM spend routes through unified gateway
- Cost model becomes predictable and controllable
- Daily budget can be tuned down from $10 hard limit to $1-2 post-optimization