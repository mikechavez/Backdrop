# Sprint 15 — Cost Stability + Enforcement

**Status:** IN PROGRESS
**Target Start:** 2026-04-14
**Target End:** 2026-04-21
**Sprint Goal:** Fix budget enforcement blind spot so the hard limit enforces against true spend, close model routing enforcement gap, label all cost operations correctly, complete RSS fingerprint coverage, and establish a reliable cost baseline for feature development.

---

## Context from Sprint 14

Infrastructure is stable and scheduled briefings are working. The blocker is cost: actual daily spend is $1.134 against a $1.00 hard limit that isn't triggering. The hard limit is silent because the enforcement system reads from `api_costs` while $0.177/day of real spend only writes to `llm_traces`. Until BUG-079 is fixed, no cost number reported by the system is trustworthy. All other cost work this sprint depends on BUG-079 landing first.

---

## Priority 1 — Cost Stability (required before feature work)

### BUG-079: Budget enforcement blind to entity_extraction costs
- Hard limit not enforcing against true daily spend ($1.134 vs $1.00 threshold)
- Fix: unify cost write path so enforcement reads complete spend
- **Must land first.** All other cost tickets depend on this being correct.

### BUG-077: Model routing warns but does not enforce
- Opus can slip through unchecked; $0.039 already appeared from a test session
- Fix: `_validate_model_routing()` returns corrected model string; call sites use return value
- Depends on: nothing. Can run in parallel with BUG-079.

### BUG-078: RSS enrichment calls have no operation name
- 261 calls/day ($0.26) routed as `provider_fallback` in traces, `article_enrichment_batch` in api_costs
- Cannot be correlated across collections without cross-referencing both
- Fix: pass explicit operation names to the four sync methods in AnthropicProvider
- Depends on: BUG-079 ADR decision (determines which collection becomes source of truth before operation names are standardized)

### BUG-076: RSS ingest path does not generate article fingerprints ✅ FIXED
- **Status:** ✅ RESOLVED — Migration completed 2026-04-14 18:07:45 UTC
- **Code fix deployed:** 2026-04-13 (commit 28f65db)
- **Backfill:** 1,766 articles fingerprinted, 4 duplicates identified
- Deduplication by fingerprint now working for RSS ingest path
- **Verification needed:** Manual review of 4 tagged duplicates before deletion

---

## Priority 2 — Observability

### TASK-069: Cost dashboard + Slack alerts
- Build dashboard reading from whichever collection BUG-079 establishes as source of truth
- Add Slack alerts at soft limit ($0.80) and hard limit ($1.20)
- **Do not start until BUG-079 is resolved.** Dashboard built on the wrong collection will show wrong numbers.

---

## Priority 3 — Narrative cost investigation

### TASK-070: Investigate narrative_generate volume
- Current: 186 calls/day, $0.59/day — still the largest line item
- BUG-070 tier filter is working but call volume is higher than the 70/day projection
- Hourly trace data shows 164 calls concentrated in the 1 AM UTC hour — likely a batch job
- Investigate what triggers that batch and whether it is necessary at current volume
- BUG-072 cache is wired but cache hit rate is unknown — query `db.llm_cache` to check
- Target: narrative costs under $0.30/day

---

## Priority 4 — Threshold recalibration

### TASK-071: Recalibrate spend thresholds
- After BUG-079 is fixed, enforcement will see true spend for the first time
- Current true spend: $1.134/day — already over the $1.00 hard limit
- Set temporary relief thresholds: soft limit $0.80, hard limit $1.20
- Revisit after TASK-070 brings narrative costs down
- Target end state: $0.50–0.70/day with correct enforcement

---

## Success Criteria

- [ ] BUG-079 resolved: `get_daily_cost()` returns true spend matching `llm_traces` aggregate total
- [ ] BUG-077 resolved: no Opus calls reach the API from production code paths
- [ ] BUG-078 resolved: zero `provider_fallback` entries in `llm_traces` from enrichment operations
- [x] BUG-076 resolved: Migration backfilled 1,762 articles; 4 duplicates tagged for review (2026-04-14)
- [ ] TASK-071 complete: enforcement thresholds updated; system no longer over hard limit
- [ ] Daily cost trending toward $0.50–0.70 target

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| BUG-079 Option B (llm_traces as truth) breaks budget refresh flow | Medium | High | Test refresh_budget_cache() against llm_traces before deploying; keep api_costs writes in place until verified |
| Narrative batch job at 1 AM is load-bearing | Low | Medium | Investigate before disabling; check if it backfills articles created during the day |
| BUG-077 enforcement change breaks test suite | Low | Low | Tests already updated to Haiku in Sprint 14; run full gateway test suite after change |
| Spend spikes during BUG-079 fix deploy window | Low | Medium | Manually watch Railway logs during deploy; can revert enforcement changes independently |

---

## Open Tickets

| ID | Title | Priority | Status |
|---|---|---|---|
| BUG-079 | Budget enforcement blind to entity_extraction costs | P1 | Backlog |
| BUG-077 | `_validate_model_routing` warns but does not enforce | P1 | Backlog |
| BUG-078 | RSS enrichment calls have no operation name | P1 | Backlog |
| BUG-076 | RSS ingest path does not generate article fingerprints | P1 | ✅ COMPLETE (2026-04-14) |
| TASK-069 | Cost dashboard + Slack alerts | P2 | Blocked on BUG-079 |
| TASK-070 | Narrative cost investigation | P3 | Backlog |
| TASK-071 | Spend threshold recalibration | P4 | Blocked on BUG-079 |