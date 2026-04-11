---
ticket_id: TASK-063
title: Switch briefing generation model from Sonnet to Haiku (cost optimization)
priority: P1
severity: HIGH
status: COMPLETE
date_created: 2026-04-10
date_completed: 2026-04-10
branch: cost-optimization/tier-1-only
effort_estimate: 15 minutes
actual_effort: 0.1h
---

# TASK-063: Switch briefing generation model from Sonnet to Haiku

## Problem Statement

Briefing generation currently uses Claude Sonnet 4.5 ($5/$15 per 1M input/output tokens) as the primary model. For cost optimization (10x cheaper), we need to test Haiku's capability on briefing generation quality while maintaining accuracy.

Current state: Sonnet primary → Haiku fallback (~$0.05/briefing)
Target state: Haiku primary (testing) → Sonnet fallback (safety net) (~$0.005/briefing)

Gateway is already integrated and enforces spend caps. Cost tracking is working. Need to:
1. Swap model in briefing_agent.py
2. Fix undefined DEFAULT_MODEL reference
3. Trigger manual briefing and verify output quality

---

## Task

### 1. Fix Model Configuration in briefing_agent.py

**File:** `src/crypto_news_aggregator/services/briefing_agent.py`

**Lines 53-54 (current):**
```python
BRIEFING_PRIMARY_MODEL = "claude-sonnet-4-5-20250929"
BRIEFING_FALLBACK_MODEL = "claude-haiku-4-5-20251001"
```

**Change to:**
```python
BRIEFING_PRIMARY_MODEL = "claude-haiku-4-5-20251001"
BRIEFING_FALLBACK_MODEL = "claude-sonnet-4-5-20250929"
```

**Rationale:** Haiku becomes primary (cost test), Sonnet remains as safety fallback. Gateway.call() at line 850 will automatically use new model list.

---

### 2. Fix DEFAULT_MODEL NameError

**File:** `src/crypto_news_aggregator/services/briefing_agent.py`

**Line 921 (current):**
```python
"model": DEFAULT_MODEL,
```

**Change to:**
```python
"model": BRIEFING_PRIMARY_MODEL,
```

**Rationale:** `DEFAULT_MODEL` is undefined. Should reference the actual primary model in use. This metadata field is logged in the briefing document for tracing which model generated it.

---

### 3. Manual Test: Trigger Briefing via Admin Endpoint

**Endpoint:** `POST /admin/trigger-briefing`

**Test parameters:**
- `briefing_type=morning` (explicit type, no auto-detect)
- `is_smoke=true` (smoke test, doesn't publish, easier cleanup)
- `force=true` (default; bypass duplicate check)

**cURL command:**
```bash
curl -X POST "http://localhost:8000/admin/trigger-briefing?briefing_type=morning&is_smoke=true&force=true" \
  -H "Content-Type: application/json"
```

**Expected response (202 Accepted):**
```json
{
  "task_id": "abc123def456...",
  "task_name": "generate_morning_briefing_task",
  "kwargs": {"force": true, "is_smoke": true},
  "message": "✅ Morning briefing task queued (force=true). Check celery-worker logs for task_id=abc123def456..."
}
```

**Next step:** Monitor Celery worker logs for the task_id. Expected to see:
- `Starting morning briefing generation` (line 126 in briefing_agent.py)
- LLM calls using model `claude-haiku-4-5-20251001` (lines 824-867 via gateway)
- Trace records written to `llm_traces` collection
- Cost tracked in `llm_usage` collection (should be ~$0.005-0.01)

---

## Verification

### Unit/Integration Testing

1. **Verify model assignment (no execution required):**
   ```python
   from crypto_news_aggregator.services.briefing_agent import BRIEFING_PRIMARY_MODEL, BRIEFING_FALLBACK_MODEL
   assert BRIEFING_PRIMARY_MODEL == "claude-haiku-4-5-20251001"
   assert BRIEFING_FALLBACK_MODEL == "claude-sonnet-4-5-20250929"
   ```

2. **Test model list in _call_llm():**
   - Code at line 846 builds `models = [BRIEFING_PRIMARY_MODEL, BRIEFING_FALLBACK_MODEL]`
   - Verify it matches the constants defined at lines 53-54
   - No code change needed; this is automatic

3. **Test DEFAULT_MODEL fix:**
   - Trigger a briefing and check MongoDB `daily_briefings` collection
   - Verify `metadata.model` field is set to `"claude-haiku-4-5-20251001"`
   - NOT undefined, NOT null

### Manual Smoke Test (Production-like)

1. **Start Celery worker and FastAPI server:**
   ```bash
   # Terminal 1: FastAPI
   uvicorn crypto_news_aggregator.main:app --port 8000 --reload
   
   # Terminal 2: Celery worker
   celery -A crypto_news_aggregator.tasks.celery_app worker -l info
   ```

2. **Trigger briefing:**
   ```bash
   curl -X POST "http://localhost:8000/admin/trigger-briefing?briefing_type=morning&is_smoke=true"
   ```

3. **Check logs for success markers:**
   - Celery worker log: `Starting morning briefing generation`
   - Celery worker log: `Successfully generated morning briefing`
   - No `NameError: name 'DEFAULT_MODEL' is not defined` errors

4. **Verify cost tracking:**
   ```bash
   # Connect to MongoDB
   db.llm_traces.findOne({"operation": "briefing_generate"}, {sort: {timestamp: -1}})
   
   # Expected: 
   # {
   #   "model": "claude-haiku-4-5-20251001",
   #   "operation": "briefing_generate",
   #   "input_tokens": 3500-4500 (context varies),
   #   "output_tokens": 800-1200,
   #   "cost": 0.003-0.01,
   #   "timestamp": ...
   # }
   ```

5. **Check briefing metadata:**
   ```bash
   # MongoDB console
   db.daily_briefings.findOne({is_smoke: true}, {sort: {generated_at: -1}})
   
   # Expected `metadata.model` field:
   # "model": "claude-haiku-4-5-20251001"
   ```

6. **Verify briefing quality manually:**
   - Check `content.narrative` is not empty (Haiku should generate full briefing)
   - Check `content.key_insights` has 3-5 items
   - Check `content.recommendations` has 2-3 items
   - Check `confidence_score` (expected 0.7-0.9; <0.6 = refinement failed)

---

## Acceptance Criteria

- [x] BRIEFING_PRIMARY_MODEL changed to `"claude-haiku-4-5-20251001"` (line 53) — DONE
- [x] BRIEFING_FALLBACK_MODEL changed to `"claude-sonnet-4-5-20250929"` (line 54) — DONE
- [x] Line 921: `DEFAULT_MODEL` reference replaced with `BRIEFING_PRIMARY_MODEL` — DONE
- [ ] Manual smoke test triggered via `/admin/trigger-briefing?briefing_type=morning&is_smoke=true` — (pending)
- [ ] Celery worker logs show no `NameError` or model initialization failures — (pending)
- [ ] LLM trace shows `model: "claude-haiku-4-5-20251001"` — (pending)
- [ ] Briefing document saved with `metadata.model: "claude-haiku-4-5-20251001"` — (pending)
- [ ] Cost tracked in `llm_traces` collection (expected ~$0.005-0.01 per briefing) — (pending)
- [ ] Briefing narrative, insights, and recommendations populated (not empty/null) — (pending)
- [ ] Confidence score >= 0.6 (quality check passed) — (pending)

---

## Impact

**Cost reduction:**
- Before: ~$0.05 per briefing (Sonnet primary)
- After: ~$0.005-0.01 per briefing (Haiku primary)
- **Savings: 80-90% per briefing generation**
- For 3 briefings/day: ~$0.15/day → ~$0.03/day (~$90/month saved)

**Quality risk:**
- Haiku is tested on entity extraction (already in use). Briefing narrative generation is new.
- Fallback to Sonnet available if quality issues detected (via gateway fallback at line 857-866)
- Smoke test required before production rollout

**Timeline impact:**
- None. Gateway abstracts model selection; no frontend/backend breaking changes

---

## Related Tickets

- TASK-039: Disabled Sonnet fallback for entity extraction to prevent cost escalation
- TASK-041: Unified LLM gateway with cost attribution (COMPLETED - Sprint 13)
- Sprint 13 Briefing: Mid-sprint gap discovery on LLM call sites; gateway integration validates all calls go through single entry point

---

## Implementation Checklist for Claude Code

### Files to Modify
- [ ] `src/crypto_news_aggregator/services/briefing_agent.py`
  - [ ] Line 53: Change `BRIEFING_PRIMARY_MODEL` value
  - [ ] Line 54: Change `BRIEFING_FALLBACK_MODEL` value
  - [ ] Line 921: Change `DEFAULT_MODEL` to `BRIEFING_PRIMARY_MODEL`

### Testing Sequence
1. [ ] Make code changes
2. [ ] Run unit test: Import models and assert values
3. [ ] Start FastAPI + Celery worker (see Verification section)
4. [ ] Execute cURL command to trigger briefing
5. [ ] Monitor Celery logs for `Successfully generated morning briefing`
6. [ ] Query MongoDB for trace and briefing metadata
7. [ ] Verify model field and cost in traces
8. [ ] Verify briefing content (narrative, insights, recommendations)
9. [ ] Confirm no NameError, no undefined variables

### No Additional Files or Dependencies
- Gateway already integrated and working
- Cost tracking already in place
- Admin endpoint already exists
- No new imports, no new dependencies required

---

*Created: 2026-04-10* | *Branch: feature/haiku-briefings* | *Assignee: Claude Code*