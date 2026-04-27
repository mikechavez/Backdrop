hard-limit-enforcement-blocks-48-hour-burn-in

---
id: BUG-058
type: bug
status: in-progress
priority: critical
severity: critical
created: 2026-04-08
updated: 2026-04-08
---

# Hard Spend Limit Enforcement Kills Burn-in Within Minutes

## Problem

Sprint 13 burn-in measurement terminated after ~5 minutes when gateway enforced `LLM_DAILY_HARD_LIMIT` ($0.33). System reached hard cap before completing a single full briefing cycle, blocking all 48-hour cost attribution measurement. Sentry reports two `LLMError: Daily spend limit reached (hard_limit)` events on `cluster_narrative_gen` and `narrative_generate` operations.

**Impact:** Burn-in data collection incomplete. Cannot measure cost attribution by operation. Sprint 13 success criteria unreachable.

## Expected Behavior

- Gateway should enforce soft limit ($0.25) with monitoring/alerting
- Burn-in measurement should run uninterrupted for full 48 hours to capture realistic cost distribution
- Cost attribution data should reflect actual pipeline spend without cap-enforcement truncation

## Actual Behavior

- Gateway hard limit ($0.33) is triggered within 5 minutes of pipeline startup
- `_check_budget()` raises `LLMError` before API call completes
- Briefing generation aborts midway through narrative enrichment phase
- llm_traces collection shows incomplete operation sequence (missing refine loops, full narrative cycles)
- Measurement window truncated, cost attribution skewed toward early operations

## Steps to Reproduce

1. Set `LLM_DAILY_HARD_LIMIT=0.33` in Railway config
2. Deploy Backdrop to production
3. Trigger briefing generation on a typical article batch
4. Monitor llm_traces collection and Sentry
5. Observe: Hard cap breach occurs ~5 minutes in, blocking narrative_generate and cluster_narrative_gen operations

## Environment

- Environment: production (Railway)
- User impact: high (blocks Sprint 13 completion)
- Sentry alerts: 2 new `LLMError` events (first seen 2026-04-08 ~XX:XX UTC)

## Screenshots/Logs

```
[2026-04-08T~XX:XXZ] Sentry Alert: LLMError in crypto_news_aggregator.llm.gateway._check_budget
Daily spend limit reached (hard_limit)

[2026-04-08T~XX:XXZ] Sentry Alert: Unexpected error for article 69d523f0...: 
LLMError: Daily spend limit reached (hard_limit)
```

MongoDB trace sample (first 5 minutes):
- briefing_generate: 1 record, $0.04
- briefing_critique: 1 record, $0.06
- narrative_theme_extract: 4 records, $0.08
- narrative_generate: 2 records (FAILED), $0.10
- cluster_narrative_gen: 1 record (FAILED), $0.05
- **Cumulative: $0.33 in <5 min → hard cap breach**

---

## Resolution

**Status:** In Progress (implementation complete, awaiting redeploy)
**Fixed:** Code implementation done (line 142 in config.py)
**Branch:** `feat/task-041-burn-in-setup`
**Commit:** Pending

### Root Cause

**Primary:** `LLM_DAILY_HARD_LIMIT` of $0.33 is too aggressive for production cost tracking with fully instrumented narrative enrichment pipeline.

**Secondary:** Narrative enrichment operations (`narrative_generate`, `cluster_narrative_gen`, `actor_tension_extract`) were previously invisible (bypass in TASK-042). Now metered, their true cost is visible:
- Theme extraction + narrative generation: ~$0.08–0.10 per article
- Cluster narrative generation: ~$0.05 per cluster
- Refine loops (not reached in current run): estimated $0.06–0.12 per cycle

**Combined cost per briefing cycle:** Estimated $0.25–0.35, exceeding hard limit on first full cycle.

### Fix Approach

**Immediate (unblock burn-in):**
1. Increase `LLM_DAILY_HARD_LIMIT` to $5.00 in Railway production config
2. Keep `LLM_DAILY_SOFT_LIMIT` at $0.25 (monitoring threshold)
3. Redeploy to production
4. Restart 48-hour burn-in measurement from clean `llm_traces` collection
5. Document in sprint notes: "Temporary hard limit lift required for full burn-in visibility"

**Sprint 14+ (optimize):**
1. Analyze cost attribution data from burn-in (TASK-041B findings)
2. Identify top 2–3 cost drivers by operation
3. Implement targeted optimizations:
   - Downgrade narrative_generate to Haiku (if quality unaffected)
   - Reduce critique iterations or refine loop depth
   - Skip theme extraction for low-salience articles
4. Re-establish hard limit at data-driven target (estimated $0.50–0.75/day)

### Changes Made

*Implementation:*
- [x] Update `LLM_DAILY_HARD_LIMIT` in `src/crypto_news_aggregator/core/config.py`: `0.33` → `5.00` (line 142)
- [ ] Redeploy Backdrop to production (Railway)
- [ ] Clear `llm_traces` collection and restart burn-in
- [ ] Update `/docs/sprint-13-burn-in-status.md` with hard limit note

### Testing

1. **Pre-fix verification:**
   - Query llm_traces: `db.llm_traces.countDocuments({})` should return 0
   - Check Sentry: no new `LLMError: Daily spend limit` alerts after hard limit increase
   
2. **Burn-in validation (2026-04-10):**
   - Run `poetry run python scripts/analyze_burn_in.py` after 48 hours
   - Verify complete operation sequences: generate → critique → refine + all narrative phases
   - Confirm zero hard limit breaches in production logs
   - Cost attribution report includes all 8 operations with nonzero spend

3. **Hard limit re-establishment (Sprint 14):**
   - Review findings doc cost breakdown
   - Calculate sustainable hard limit based on optimization choices
   - Re-lower limit incrementally with monitoring

### Files Changed

- `railway.toml` (or equivalent): `LLM_DAILY_HARD_LIMIT` env var
- `/docs/sprint-13-burn-in-status.md`: Document hard limit lift and rationale

---

## Related Tickets

- **TASK-041A:** Restart 48-hour burn-in (currently blocked by this bug)
- **TASK-041B:** Analyze burn-in + write findings (unblocked once fix deployed)
- **TASK-042:** Gateway bypass fix (successful; this bug is consequence, not fault)

## Notes

This is **not a gateway bug** — the hard limit enforcement is working correctly. The bug is a **measurement design issue**: the hard limit is set too low for a production system running the full narrative enrichment pipeline. The fix is temporary (for measurement only) and should trigger Sprint 14 optimization work on the actual cost drivers identified by the burn-in data.