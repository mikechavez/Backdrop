# Session Start

**Date:** 2026-04-15 (Session 37, Sprint 15)
**Status:** All BUGs complete (BUG-080, BUG-081, BUG-082, BUG-084 briefing quality; BUG-083 Part 1). TASK-073 (zombie narrative auto-dormancy) complete.
**Branches Ready:** fix/bug-080-briefing-date-mismatch, fix/bug-081-briefing-separate-stories, fix/bug-082-narrative-implausible-figures, fix/bug-083-market-event-detector-phantom-narratives, fix/bug-084-narrative-summary-fabrication, feat/task-073-auto-dormant-narratives
**Next:** Part 2 of BUG-083 (MongoDB cleanup), create PRs for all bugs + TASK-073, then TASK-069 (cost dashboard + Slack alerts)

---

## Current Session Context

### What was completed in Session 37

**TASK-073 COMPLETE: Auto-dormant zombies narratives when all source articles are purged**

Implemented automated detection and dormancy marking for zombie narratives (narratives with zero surviving source articles). Two-part implementation: one-time cleanup query and periodic automated check.

**Implementation deployed (commit c8e8e5b):**
- **Part 1 — One-time cleanup script:** Created `scripts/cleanup_zombie_narratives.py`
  - MongoDB aggregation identifies hot narratives with zero surviving articles
  - Supports `--dry-run` mode for safe preview
  - Marks identified narratives dormant with `_disabled_by: "TASK-073-zombie-cleanup"`
  - Tested against production: found 10 zombie narratives from prior sessions
- **Part 2 — Periodic automated check:** Integrated into worker.py
  - New function `auto_dormant_zombie_narratives()` in `tasks/narrative_cleanup.py`
  - Runs every 1 hour via worker scheduler
  - Automatically catches zombies post-article-purge
  - Logs warnings when narratives auto-dormanted for Railway visibility
- **Testing:** 6 comprehensive unit tests covering detection, dormanting, edge cases; all pass ✅
- **Impact:** Prevents fabricated/un-verifiable narratives from appearing in briefings without manual audits

**Branch:** feat/task-073-auto-dormant-narratives (ready for PR)

---

### What was completed in Session 36

**BUG-084 FIXED: Narrative summary generator fabricates events not present in source articles**

The narrative summary generator was producing summaries describing events not in source articles. Three root causes: (1) prompt encouraged "synthesizing" coherence without grounding, (2) only 300 chars of article text provided insufficient context for LLM to distinguish signal from noise, (3) used Sonnet instead of Haiku contradicting project standardization.

**Fix deployed (commit 3edbf48):**
- Increased article text context from 300 to 800 characters in `_build_summary_prompt()`
- Replaced "synthesize into cohesive narrative" prompt with explicit grounding constraint: "only events explicitly stated in provided articles"
- Added CRITICAL instruction block warning against inferring or speculating events not in source text
- Switched from Sonnet to Haiku model to reduce cost while improving instruction adherence
- Reduced temperature from 0.7 to 0.5 to limit creative drift under tighter grounding constraints
- Fixed cache key mismatch: use HAIKU_MODEL consistently (was using SONNET_MODEL on cache.set)

**Branch:** fix/bug-084-narrative-summary-fabrication (ready for PR)

---

### What was completed in Session 35

**BUG-083 PART 1: Disable market event detector creating phantom narratives**

The market event detector was creating fictional narratives like "Major Market Liquidation Event - $5.0B Cascade" by matching 23 unrelated articles and summing unrelated dollar amounts. Six compounding failures: OR keyword matching, no relevance validation, blind volume extraction, low thresholds, missing narrative metadata, and force-boosted ranking.

**Fix deployed (commit 6850efb):**
- Modified `detect_market_events()` to return empty list immediately with info log
- Preserved original implementation as disabled code with detailed BUG-083 notes
- Detector no longer creates phantom narratives

**Status:** Part 1 complete. Part 2 (MongoDB cleanup of existing phantom narratives) pending approval.
**Branch:** `fix/bug-082-narrative-implausible-figures` (same branch, Part 1 added)

---

### What was completed in Session 34

**BUG-082 FIXED: Narrative summary pipeline validation for implausible financial figures**

Defense-in-depth validation added to `generate_narrative_summary()` to catch implausible figures that slip past BUG-081 briefing-level critique checks.

**Fix deployed (commit 1d633f8):**
- Added `import re` for regex pattern matching
- Updated `_build_summary_prompt()` with figure verification instruction (rule 4) to instruct LLM to verify financial figures are consistent across articles
- Added post-generation figure plausibility check that logs warnings for figures exceeding $50B threshold
- Created comprehensive test suite: 15 unit tests covering all regex formats, threshold logic, and caching behavior; all pass ✅
- Verified no regressions: all 9 LLM cost tracking tests pass ✅

**Branch:** `fix/bug-082-narrative-implausible-figures` — ready for PR

---

### What was completed in Session 33

**BUG-081 FIXED: Briefing quality guardrails for duplicate events, unnamed entities, and implausible figures**

April 14 evening briefing had three issues: (1) Polkadot/Hyperbridge bridge exploit presented as two separate stories, (2) "two platforms" mentioned but only one named (Kraken), (3) "$204.7B liquidations" (~7-10% of entire market cap) passed critique unchallenged.

**Fix deployed (commits bd2a8c7, 891d073):**
- Added system prompt rules 9-11: consolidate duplicate events, prevent unnamed entities, verify figure plausibility
- Added critique checks 8-10: detect duplicate events, unnamed entities, implausible figures
- Created comprehensive test suite: 7 new tests covering all three rules, all pass ✅
- Verified no regressions: all 5 existing briefing prompt tests pass ✅

**Branch:** `fix/bug-081-briefing-separate-stories` — ready for PR

---

### What was completed in Session 32

**BUG-080 FIXED: Briefing date mismatch in LLM prompt**

Evening briefings at 6 PM CST (= midnight UTC) had narratives dated April 15 while the frontend header showed April 14. Root cause: `_build_generation_prompt()` was formatting the UTC timestamp directly, but the frontend displays dates in local timezone (CST/CDT).

**Fix deployed (commit 13d0ecc):**
- Added `ZoneInfo` import for timezone-aware conversion
- Defined `BRIEFING_DISPLAY_TZ = ZoneInfo("America/Chicago")` constant
- Convert `generated_at` from UTC to display timezone before formatting for LLM prompt
- Added 2 unit tests: midnight UTC → correct date conversion, daytime UTC dates unaffected
- All 5 briefing prompt tests pass ✅

**Branch:** `fix/bug-080-briefing-date-mismatch` — ready for PR

---

### What was completed in Session 30

**Full cost tracking validation** — confirmed the entire LLM call → trace → enforcement pipeline is working correctly end-to-end:

- `llm_traces` field is `cost` (not `cost_usd`) — `get_daily_cost()` confirmed reading correct field ✅
- All LLM calls route through `gateway.py` — no direct httpx bypass paths in `anthropic.py` or `optimized_anthropic.py` ✅
- Gateway writes trace on every exit path: cache hit, HTTP error, exception, and success ✅
- True daily spend confirmed: **~$0.54/day** (not the $1.134 cited at sprint start — that was inflated by BUG-066's rolling window)

**BUG-078 re-investigation and correct fix deployed:**
- Original fix (94dc5fb) patched the wrong layer — sync methods were already correct
- Real broken call sites: async `_tracked` methods + `enrich_articles_batch` dropping `operation` at `_get_completion_with_usage()` call
- Correct fix (commit 6448289) deployed at 01:55 UTC
- Validated: last `provider_fallback` trace at 01:40 UTC (pre-deploy); `article_enrichment_batch` appearing post-deploy ✅

---

## Confirmed Cost Baseline (2026-04-15, partial day)

| Operation | Calls | Cost |
|---|---|---|
| provider_fallback (pre-fix, fading) | 180 | $0.169 |
| entity_extraction | 174 | $0.152 |
| narrative_generate | 51 | $0.125 |
| briefing_refine | 4 | $0.032 |
| briefing_critique | 4 | $0.023 |
| briefing_generate | 2 | $0.020 |
| article_enrichment_batch (post-fix) | 8 | $0.007 |
| cluster_narrative_gen | 6 | $0.006 |
| narrative_polish | 6 | $0.003 |
| **Total** | | **~$0.54** |

`provider_fallback` will be near zero by end of day as pre-fix traces age out.

---

## Known Minor Issues

- `article_enrichment_batch` not in `_OPERATION_MODEL_ROUTING` in `gateway.py` — logs a routing warning per call, no cost impact (Haiku used regardless). Add to routing table in next pass.
- BUG-076: 4 duplicate articles tagged, pending manual review before deletion.

---

## Open Sprint Tickets

| ID | Title | Priority | Status |
|---|---|---|---|
| TASK-069 | Cost dashboard + Slack alerts | P2 | Ready |
| TASK-070 | Narrative cost investigation | P3 | Backlog |
| TASK-071 | Spend threshold recalibration | P4 | Ready (lower urgency — spend already under $1.00 limit) |

---

## What Happened Before (Sessions 1–29)

**Sessions 26–29 (Sprint 15 start):**
- BUG-077 FIXED: model routing now enforces (not just warns); 5 missing operations added to routing table
- BUG-076 FIXED: RSS fingerprint backfill — 1,766 articles fingerprinted, 4 duplicates tagged
- BUG-079 FIXED: budget enforcement now reads `llm_traces` as single source of truth; entity_extraction ($0.177/day) now visible to enforcement; 110 lines of manual tracking removed

**Sessions 14–25 (Sprint 14):**
- Built unified LLM Gateway (TASK-036–042) with async/sync modes, budget enforcement, tracing
- Fixed BUG-066 (rolling window daily cost), BUG-067 (Motor truthiness), BUG-068 (double cost tracking)
- Fixed BUG-064 (memory leak + retry storm), BUG-065 (briefing soft limit incorrectly triggered)
- TASK-063: Swapped briefing model to Haiku primary, Sonnet fallback (80-90% cost reduction per briefing)
- Tier 1 enrichment filter: only ~17% of articles receive full LLM enrichment, saving ~75% on enrichment costs

**Sessions 1–13 (Sprint 12–13):**
- Built complete Backdrop platform: FastAPI + Celery + MongoDB + Redis + Railway
- Narrative fingerprinting/deduplication (89.1% match rate)
- Entity extraction with tier classification
- Twice-daily LLM-generated briefings (morning/evening)
- Cost optimization from $90+/month to under $10/month