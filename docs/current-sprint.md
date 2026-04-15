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

### BUG-079: Budget enforcement blind to entity_extraction costs ✅ FIXED
- **Status:** ✅ RESOLVED — 2026-04-14 18:55:00 UTC
- **Code fix deployed:** 2026-04-14 (commits 533cbce, 50255cf)
- **Decision:** Option B — Use `llm_traces` as single source of truth for budget enforcement
- **Changes:** Updated `get_daily_cost()`, `get_monthly_cost()`, `get_cost_by_operation()`, `get_cost_by_model()` to query `llm_traces` instead of `api_costs`
- **Removed fragile code:** Eliminated manual async cost tracking task from `extract_entities_batch()` (110 lines removed)
- **Testing:** All 50 cost-related tests pass; verified entity_extraction costs now visible
- **Cost impact:** Hard limit now enforces against true spend ($1.134/day vs blind $0.957/day); entity_extraction ($0.177/day) now visible
- **ADR:** Created ADR-079 documenting the decision and rationale
- **Verification:** After deployment, check `llm_traces` aggregate matches `refresh_budget_cache()` output

### BUG-077: Model routing warns but does not enforce ✅ FIXED
- **Status:** ✅ RESOLVED — 2026-04-14 18:30:00 UTC
- **Code fix deployed:** 2026-04-14 (commit c05404e)
- **Changes:** `_validate_model_routing()` now returns corrected model string; both `call()` and `call_sync()` use return value
- **Enforcement:** Silently overrides wrong models and logs warning; 5 missing operations added to routing table
- **Testing:** All 22 gateway tests pass; enforcement verified with manual validation
- **Cost impact:** Prevents Opus ($0.039/call) from bypassing enforcement, protects against 25× cost multiplier

### BUG-078: RSS enrichment calls have no operation name ✅ FIXED
- **Status:** ✅ RESOLVED — 2026-04-14 18:45:00 UTC
- **Code fix deployed:** 2026-04-14 (commit 94dc5fb)
- **Changes:** Passed explicit operation names to four sync methods in AnthropicProvider:
  - `analyze_sentiment` → `operation="sentiment_analysis"`
  - `extract_themes` → `operation="theme_extraction"`
  - `generate_insight` → `operation="insight_generation"`
  - `score_relevance` → `operation="relevance_scoring"`
- Added warning log to `_get_completion` when operation is empty (future safeguard)
- **Cost impact:** ~261 enrichment calls/day ($0.26) now visible in operation-level breakdowns

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

- [x] BUG-079 resolved: `get_daily_cost()` returns true spend matching `llm_traces` aggregate total (2026-04-14)
- [x] BUG-077 resolved: no Opus calls reach the API from production code paths (2026-04-14)
- [x] BUG-078 resolved: zero `provider_fallback` entries in `llm_traces` from enrichment operations (2026-04-14)
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
| BUG-079 | Budget enforcement blind to entity_extraction costs | P1 | ✅ COMPLETE (2026-04-14) |
| BUG-077 | `_validate_model_routing` warns but does not enforce | P1 | ✅ COMPLETE (2026-04-14) |
| BUG-078 | RSS enrichment calls have no operation name | P1 | ✅ COMPLETE (2026-04-14) |
| BUG-076 | RSS ingest path does not generate article fingerprints | P1 | ✅ COMPLETE (2026-04-14) |
| TASK-069 | Cost dashboard + Slack alerts | P2 | Ready (BUG-079 complete) |
| TASK-070 | Narrative cost investigation | P3 | Backlog |
| TASK-071 | Spend threshold recalibration | P4 | Ready (BUG-079 complete) |