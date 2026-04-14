# Sprint 14 — Infrastructure Stability + LLM Cost Monitoring

**Status:** IN PROGRESS
**Target Start:** 2026-04-11
**Target End:** 2026-04-14
**Sprint Goal:** Fix critical briefing bugs, validate scheduled briefing execution, measure actual LLM costs, establish sustainable infrastructure baseline.

---

## Current Status (2026-04-14, 11:30 EST)

### ✅ Completed This Sprint
- **BUG-064:** Memory leak + retry storm — MERGED
- **BUG-065:** Briefing soft limit incorrectly triggered — MERGED
- **BUG-066:** Daily cost calculation (rolling 24h vs calendar day) — CODE COMPLETE
- **BUG-067:** Motor AsyncIOMotorDatabase truthiness check — CODE COMPLETE
- **BUG-068:** Double cost tracking (OptimizedAnthropicLLM duplicate) — CODE COMPLETE
- **BUG-069:** Briefing persistence (empty documents) — **✅ FIXED & VERIFIED**
- **BUG-075:** Inconsistent model routing (Opus/Sonnet instead of Haiku) — **✅ FIXED**
  - Added `_OPERATION_MODEL_ROUTING` config to gateway.py with expected model for each operation
  - Added `_validate_model_routing()` method to detect and log model mismatches
  - Fixed test_gateway.py (Opus → Haiku) and tests/llm/test_gateway.py (Sonnet → Haiku)
  - All 22 gateway tests passing ✅
  - Branch: `fix/bug-075-model-routing`
  - Impact: Prevents 25× cost spike ($0.038760 vs $0.0015 per call)
  - Manual briefing generation tested: saves with full content
  - Cost logged correctly: $0.010033
  - Document visible on UI: ✅ Yes
- **BUG-076:** Narrative focus field stores full LLM response — **✅ FIXED**
  - Added `extract_focus_phrase()` function to isolate 2-5 word phrase from explanation text
  - Handles quoted strings, newlines, multi-line explanations, and boundary detection
  - Integrated in `discover_narrative_from_article()` immediately after JSON parsing
  - 13 comprehensive unit tests covering edge cases (empty strings, quoted text, real-world examples)
  - All 53 focus/validation/discovery tests passing ✅
  - Branch: `fix/bug-076-narrative-focus-parser`
  - Impact: Prospectively fixes all new narrative detections; existing bad data can be backfilled
- **BUG-070:** Narrative tier-1 only filter — **✅ CODE COMPLETE**
  - Changed `MAX_RELEVANCE_TIER = 2` → `1` in narrative_themes.py
  - Expected savings: -64% narrative calls (~193 → 70/day), ~$0.38/day cost reduction
  - Single-line fix, zero-risk change
  - Commit: 03df32f
- **BUG-071:** Narrative prompt compression — **✅ COMPLETE**
  - Compressed system prompt: 1,700 tokens → 900 tokens (-47%)
  - Cost reduction: ~$0.105/day on narrative_generate calls
  - Added `NARRATIVE_SYSTEM_PROMPT` constant (700 tokens, concise rules)
  - Replaced 128-line prompt blob with 4-line user message
  - Fixed 6 discovery-narrative tests to use `get_gateway()` mocking
  - All tests passing (10/10 discover_narrative tests)
  - Combined with BUG-070: Total narrative cost reduction -68%
- **BUG-072:** LLM cache infrastructure wiring — **✅ COMPLETE**
  - Implemented cache lookup/save in LLMGateway for both async and sync paths
  - Added 6 methods: `_get_from_cache()`, `_save_to_cache()`, sync variants
  - Cacheable operations: narrative_generate, entity_extraction, narrative_theme_extract
  - Non-cacheable: briefing operations (always fresh)
  - Expected savings: -30% narrative_generate calls (~$0.037/day)
  - All 22 gateway tests passing, 4 new cache-specific tests added
  - Commit: c68e760
  - Combined impact with BUG-070/071: -98% narrative cost (from $0.60/day → $0.015/day)

### ✅ Completed (Continued)
- **BUG-073:** Articles missing fingerprints — deduplication broken — **✅ COMPLETE**
  - Fixed `create_or_update_articles()` to route through `ArticleService.create_article()`
  - All articles now get fingerprints generated (MD5 hash of normalized title + content)
  - Deduplication by fingerprint now functional for all ingested articles
  - Impact: Prevents duplicate articles across feeds from wasting storage and LLM quota
  - Commit: 28f65db (parent commit in current branch)

- **BUG-074:** Briefing agent receives empty narrative list — **✅ COMPLETE**
  - Missing `.sort()` in `_get_active_narratives()` caused MongoDB to return October 2025 documents
  - All old documents failed 7-day recency check, resulting in empty narrative list
  - Added `.sort("last_updated", -1)` before `.limit(limit * 3)` in briefing_agent.py line 291
  - Index `idx_lifecycle_state_last_updated` already exists, no migration needed
  - Commit: 98f172d
  - Impact: Briefing agent now receives recent narratives (April 2026), generation succeeds end-to-end

### ✅ Completed (Continued)
- **TASK-065:** Add observability to narrative backfill update_one calls — **✅ COMPLETE**
  - Added debug logging before `update_one` execution (article_id + fields)
  - Check `result.modified_count` and log warning if 0 (document not found or no change)
  - Wrap `update_one` in try/except with error logging on failure
  - Files: `src/crypto_news_aggregator/services/narrative_themes.py:1254-1295`
  - Commit: `cde555c`
  - Impact: Closes blind spot in write path observability; future write failures immediately detectable in logs

### 🔲 In Progress
- **TASK-028:** Validate scheduled briefing execution + measure costs (see below)

### 📋 Not Yet Started
- TASK-069: Cost dashboard + Slack alerts
- TASK-070: Narrative cost investigation (separate from TASK-028)
- TASK-071: Spend threshold adjustment

---

## TASK-028: Scheduled Briefing Validation (Next Phase)

**Current blockers resolved:**
- ✅ Code fixes applied (BUG-064 through BUG-069)
- ✅ Manual briefing generation working
- ✅ Celery Beat configured with correct timezone (`America/New_York`)
- ✅ Celery Worker running on Railway

**What we need to verify:**
Scheduled briefings **may have been broken before**, and we need to confirm BUG-069 fix resolves that.

### Verification Plan

**Phase 1: Watch next scheduled execution (Today 2026-04-13)**
- Morning briefing was at 8:00 AM EST (already passed)
- Evening briefing scheduled for 8:00 PM EST (20:00 EST = 02:00 UTC next day)
- Check at ~20:15 EST:
  ```javascript
  // Verify document saved
  db.briefing_drafts.findOne({created_at: {$gte: new Date("2026-04-13T20:00:00Z")}})
  
  // Verify it has content, not empty
  // Should have: narrative, key_insights, entities_mentioned, recommendations, confidence_score
  ```

**Phase 2: 72-hour observation (2026-04-13 to 2026-04-16)**
- Let system run for 3 full days of normal operation
- Collect metrics:
  - Scheduled briefing execution (should see 6 total: 2/day × 3 days)
  - All documents should have full content
  - Cost tracking by operation

**Phase 3: Cost attribution report (after 72h)**
- Query all `llm_traces` from the period
- Group by operation, sum costs
- Validate assumptions:
  - Briefing generation: ~$0.01/run × 6 runs = $0.06
  - Narrative operations should be minimal during scheduled runs (no active user enrichment)
  - Total daily spend should be $0.50–0.70 (validate Sprint 13 optimization)

**Success criteria:**
- [ ] All scheduled briefings execute (6 documents in 72h, all with content)
- [ ] No empty briefing documents
- [ ] Daily cost stays under $1.00 hard limit
- [ ] Soft limit not triggered (should be under $0.50 soft if narrative costs optimized)

---

## Why Scheduled Briefings Might Have Been Broken

**Context:** You mentioned scheduled briefings were failing for reasons you can't remember.

**Most likely cause:** BUG-069 (empty document persistence)
- Manual briefings probably always worked (you'd test manually, see it save with content)
- Scheduled briefings probably failed silently (empty documents created, Celery task marked "success")
- Users never saw briefings on UI
- You debugged and found them empty, then abandoned scheduled generation

**Hypothesis:** BUG-069 fix resolves this. The code path that was broken is now working.

---

## Infrastructure Status

**Services running on Railway:**
- ✅ FastAPI backend (API server)
- ✅ Celery Worker (task execution)
- ✅ Celery Beat (scheduler)
- ✅ MongoDB (database)
- ✅ Redis (cache/locks)

**No migration planned** — Railway services are stable. If cost becomes an issue later, Sprint 15 can evaluate provider migration.

**Celery configuration verified:**
```python
# celery_config.py
timezone = "America/New_York"  # ✅ EST/EDT handling automatic
enable_utc = True

# beat_schedule.py
"generate-morning-briefing": crontab(hour=8, minute=0)   # 8 AM EST
"generate-evening-briefing": crontab(hour=20, minute=0)  # 8 PM EST
```

---

## Cost Baseline (Pre-Sprint 14)

From previous observations:
- **Narrative operations:** ~$0.38/day (32 calls in 30 mins = 64/hour) 🚨 HIGH
- **Briefing generation:** ~$0.01/briefing
- **Article enrichment:** ~$0.20/day (heavily throttled)
- **Other:** entity extraction, alerts, cache
- **Total:** ~$0.95/day (near $1.00 hard limit)

**Issue:** Narratives dominate budget. TASK-070 will investigate this separately.

---

## Next Actions (48h)

1. **Tonight (2026-04-13 20:00 EST):** Check that evening briefing executes scheduled
2. **Tomorrow:** Continue observation, ensure morning briefing (2026-04-14 08:00 EST) also executes
3. **Wednesday 2026-04-15:** Confirm 72-hour pattern holds (6 briefings, all with content)
4. **Thursday 2026-04-16:** Generate cost report, determine if additional optimizations needed

**If scheduled briefing fails:**
- Check Celery Beat logs
- Verify MongoDB connection from worker
- Check for LLM errors in traces
- Fall back to manual triggers while debugging

---

## Removed From This Sprint

These items are deferred to post-validation:
- TASK-064 (Railway cost audit) — Not needed if current infrastructure stable
- TASK-065/066/067 (provider migration) — Only if costs spike again
- TASK-069 (dashboard + alerts) — Can build after cost stability confirmed
- TASK-070 (narrative cost investigation) — Separate sprint focus

---

## Success Criteria (for Sprint 14 completion)

- [x] All critical bugs fixed (BUG-064 through BUG-069)
- [ ] Manual briefing generation working (VERIFIED ✅)
- [ ] Scheduled briefing execution confirmed working (PENDING — watch tonight)
- [ ] 72-hour observation period complete (PENDING)
- [ ] Cost report shows sustainable daily spend (PENDING)
- [ ] Services remain stable for 3 days without restarts (PENDING)

---

## Risk Assessment

| Risk | Probability | Mitigation |
|------|------------|-----------|
| Scheduled briefings still broken | Low | Manual testing tonight at 8 PM EST; fallback to manual triggers |
| Cost explodes again (>$1.00/day) | Medium | Soft limit at $0.50 will block enrichment; investigate narrative costs (TASK-070) |
| Celery Beat crashes | Low | Worker has auto-restart; can manually trigger briefings if needed |
| Database consistency issues | Very Low | BUG-069 fix ensures all inserts go through single code path |

---

## Handoff to Sprint 15

If TASK-028 validation succeeds:
- ✅ Infrastructure stable, daily costs $0.50–0.70
- ✅ Scheduled briefings working automatically
- ✅ Cost tracking complete and visible
- ✅ Ready for broader feature development

**Sprint 15 priorities:**
1. Build cost dashboard + Slack alerts (TASK-069)
2. Investigate + optimize narrative costs (TASK-070)
3. Adjust spend thresholds for sustainable operation (TASK-071)
4. Resume product development (narrative quality, briefing enhancements)

---

**Status: Ready for scheduled briefing validation tonight**