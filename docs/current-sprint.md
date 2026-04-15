# Sprint 15 — Cost Stability + Enforcement

**Status:** IN PROGRESS
**Target Start:** 2026-04-14
**Target End:** 2026-04-21
**Sprint Goal:** Fix budget enforcement blind spot so the hard limit enforces against true spend, close model routing enforcement gap, label all cost operations correctly, complete RSS fingerprint coverage, and establish a reliable cost baseline for feature development.

---

## Context from Sprint 14

Infrastructure is stable and scheduled briefings are working. The blocker was cost enforcement: the hard limit was silent because the enforcement system read from `api_costs` while entity_extraction costs only wrote to `llm_traces`. BUG-079 fixed this by making `llm_traces` the single source of truth.

**Note:** The $1.134/day figure cited at sprint start was inflated by BUG-066's rolling 24hr window (fixed in Session 19). True baseline spend confirmed in Session 30 post-fix validation: **~$0.54/day**. System is already under the $1.00 hard limit — TASK-071 threshold relief is useful but not urgent.

---

## Priority 1 — Cost Stability + Briefing Quality (required before feature work)

### BUG-079: Budget enforcement blind to entity_extraction costs ✅ FIXED
- **Status:** ✅ RESOLVED — 2026-04-14 18:55:00 UTC
- **Code fix deployed:** 2026-04-14 (commits 533cbce, 50255cf)
- **Decision:** Option B — Use `llm_traces` as single source of truth for budget enforcement
- **Changes:** Updated `get_daily_cost()`, `get_monthly_cost()`, `get_cost_by_operation()`, `get_cost_by_model()` to query `llm_traces` instead of `api_costs`
- **Removed fragile code:** Eliminated manual async cost tracking task from `extract_entities_batch()` (110 lines removed)
- **Testing:** All 50 cost-related tests pass; verified entity_extraction costs now visible
- **ADR:** Created ADR-079 documenting the decision and rationale
- **Production validation (Session 30):**
  - `llm_traces` field name confirmed as `cost` (not `cost_usd`) — `get_daily_cost()` aggregates `"$cost"` correctly ✅
  - `entity_extraction` visible at $0.145/day, 174 calls ✅
  - True daily spend confirmed ~$0.54 — system is under $1.00 hard limit ✅
  - All LLM calls confirmed routing through gateway; no direct httpx bypass paths ✅

### BUG-077: Model routing warns but does not enforce ✅ FIXED
- **Status:** ✅ RESOLVED — 2026-04-14 18:30:00 UTC
- **Code fix deployed:** 2026-04-14 (commit c05404e)
- **Changes:** `_validate_model_routing()` now returns corrected model string; both `call()` and `call_sync()` use return value
- **Enforcement:** Silently overrides wrong models and logs warning; 5 missing operations added to routing table
- **Testing:** All 22 gateway tests pass; enforcement verified with manual validation
- **Cost impact:** Prevents Opus ($0.039/call) from bypassing enforcement, protects against 25× cost multiplier
- **Note:** `article_enrichment_batch` is not yet in `_OPERATION_MODEL_ROUTING` — will log a routing warning post BUG-078 fix. Low priority since calls use Haiku regardless; add in next routing table pass.

### BUG-078: RSS enrichment calls have no operation name ✅ FIXED
- **Status:** ✅ RESOLVED — 2026-04-14 19:15:00 UTC (second fix; first fix 94dc5fb was incorrect)
- **Code fix deployed:** 2026-04-14 (commit 6448289)
- **Root cause (corrected in Session 30):** Original fix (94dc5fb) patched the four sync methods (`analyze_sentiment`, `extract_themes`, `score_relevance`, `generate_insight`) which were already passing correct operation names. The actual broken call sites were the async `_tracked` wrapper methods and `enrich_articles_batch` — all calling `_get_completion_with_usage(prompt)` without passing the `operation` argument that was already in scope.
- **Changes (correct fix):** Passed operation names to `_get_completion_with_usage()` in four async methods:
  - `enrich_articles_batch` line 550: hardcoded `operation="article_enrichment_batch"`
  - `score_relevance_tracked` line 633: `operation=operation` (parameter pass-through)
  - `analyze_sentiment_tracked` line 695: `operation=operation` (parameter pass-through)
  - `extract_themes_tracked` line 758: `operation=operation` (parameter pass-through)
- **Production validation (Session 30):**
  - Last `provider_fallback` trace timestamp: 2026-04-15T01:40:22 UTC (15 min before deploy at 01:55 UTC) ✅
  - `article_enrichment_batch` appeared in operation breakdown post-deploy with 8 calls ✅
  - No new `provider_fallback` entries generated after deploy ✅

### BUG-076: RSS ingest path does not generate article fingerprints ✅ FIXED
- **Status:** ✅ RESOLVED — Migration completed 2026-04-14 18:07:45 UTC
- **Code fix deployed:** 2026-04-13 (commit 28f65db)
- **Backfill:** 1,766 articles fingerprinted, 4 duplicates identified
- Deduplication by fingerprint now working for RSS ingest path
- **Verification needed:** Manual review of 4 tagged duplicates before deletion

### BUG-080: Briefing date mismatch — prompt says April 15, header says April 14 ✅ FIXED
- **Status:** ✅ RESOLVED — 2026-04-15
- **Code fix deployed:** 2026-04-15 (commit 13d0ecc)
- **Root cause:** `_build_generation_prompt()` formatted UTC timestamp directly; frontend displays in local timezone (CST/CDT). Evening briefing at 6 PM CST = midnight UTC next day → prompt dated April 15 while header showed April 14.
- **Changes:**
  - Added `ZoneInfo` import for timezone conversion
  - Defined `BRIEFING_DISPLAY_TZ = ZoneInfo("America/Chicago")` constant to match frontend
  - Convert `generated_at` from UTC to display timezone before formatting for LLM prompt
- **Testing:** 
  - Unit test: midnight UTC (2026-04-15 00:00 UTC) → "Tuesday, April 14, 2026" ✅
  - Unit test: 2 PM UTC (2026-04-15 14:00 UTC) → "Wednesday, April 15, 2026" ✅
  - All 5 briefing prompt tests pass ✅
- **Branch:** `fix/bug-080-briefing-date-mismatch` (ready for PR)

---

## Priority 2 — Observability

### TASK-069: Cost dashboard + Slack alerts
- Build dashboard reading from `llm_traces` (confirmed single source of truth)
- Aggregate on `cost` field (not `cost_usd`)
- Add Slack alerts at soft limit ($0.80) and hard limit ($1.00, or revised per TASK-071)
- **Unblocked:** BUG-079 complete and validated

---

## Priority 3 — Narrative cost investigation

### TASK-070: Investigate narrative_generate volume
- Current (Session 30 confirmed): 51 calls today, $0.125 — tracking toward ~$0.30–0.40/day
- Previously cited 186 calls/$0.59 figure was inflated by rolling window bug
- Hourly trace data shows concentration in early UTC hours — likely a batch job
- Investigate what triggers that batch and whether it is necessary at current volume
- BUG-072 cache is wired but cache hit rate is unknown — query `db.llm_cache` to check
- Target: narrative costs under $0.30/day

---

## Priority 4 — Threshold recalibration

### TASK-071: Recalibrate spend thresholds
- **Context updated:** True spend is ~$0.54/day — already under $1.00 hard limit. No emergency relief needed.
- Still worth recalibrating to set meaningful soft/hard limits that reflect actual baseline
- Suggested targets: soft limit $0.70, hard limit $1.00
- Revisit after TASK-070 to see if narrative costs come down further
- Target end state: $0.50–0.70/day with correct enforcement

---

## Confirmed Cost Baseline (Session 30, 2026-04-15)

| Operation | Calls/day | Cost/day |
|---|---|---|
| provider_fallback (pre-fix, fading) | ~180 | $0.168 |
| entity_extraction | ~174 | $0.152 |
| narrative_generate | ~51 | $0.125 |
| briefing_refine | ~4 | $0.032 |
| briefing_critique | ~4 | $0.023 |
| briefing_generate | ~2 | $0.020 |
| article_enrichment_batch (post-fix) | growing | — |
| cluster_narrative_gen | ~6 | $0.006 |
| narrative_polish | ~6 | $0.003 |
| **Total** | | **~$0.54** |

`provider_fallback` will collapse to near zero by end of day as pre-fix traces age and post-fix cycles accumulate under correct operation names.

---

## Success Criteria

- [x] BUG-079 resolved: `get_daily_cost()` returns true spend matching `llm_traces` aggregate total (2026-04-14)
- [x] BUG-077 resolved: no Opus calls reach the API from production code paths (2026-04-14)
- [x] BUG-078 resolved: zero `provider_fallback` entries in `llm_traces` from enrichment operations — verified post-deploy 2026-04-15 01:55 UTC
- [x] BUG-076 resolved: Migration backfilled 1,762 articles; 4 duplicates tagged for review (2026-04-14)
- [ ] TASK-071 complete: enforcement thresholds recalibrated to reflect true baseline
- [ ] TASK-069 complete: cost dashboard live, Slack alerts wired
- [ ] Daily cost trending toward $0.50–0.70 target

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| `article_enrichment_batch` not in routing table logs warnings | High | Low | Add to `_OPERATION_MODEL_ROUTING` in next routing pass; no cost impact since Haiku is used regardless |
| Narrative batch job volume higher than expected | Low | Medium | Investigate before disabling; check cache hit rate first |
| BUG-077 enforcement change breaks test suite | Low | Low | Tests already updated to Haiku in Sprint 14; run full gateway test suite after change |

---

## Open Tickets

| ID | Title | Priority | Status |
|---|---|---|---|
| BUG-079 | Budget enforcement blind to entity_extraction costs | P1 | ✅ COMPLETE + VALIDATED (2026-04-15) |
| BUG-077 | `_validate_model_routing` warns but does not enforce | P1 | ✅ COMPLETE (2026-04-14) |
| BUG-078 | RSS enrichment calls have no operation name | P1 | ✅ COMPLETE + VALIDATED (2026-04-15) |
| BUG-076 | RSS ingest path does not generate article fingerprints | P1 | ✅ COMPLETE (2026-04-14) |
| BUG-080 | Briefing date mismatch in LLM prompt | P2 | ✅ COMPLETE (2026-04-15) |
| TASK-069 | Cost dashboard + Slack alerts | P2 | Ready |
| TASK-070 | Narrative cost investigation | P3 | Backlog |
| TASK-071 | Spend threshold recalibration | P4 | Ready (lower urgency — spend already under limit) |