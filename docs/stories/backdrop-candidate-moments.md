# Backdrop Candidate Moments — Crypto News Aggregator (Backdrop)

**Status:** Candidate list for Backdrop submission  
**Date:** 2026-07-22  
**Source:** Sprint 014–021 analysis

---

## How to Use This List

Each entry below is a **candidate moment** for Backdrop's six categories:
- A meaningful success
- A difficult problem or challenge
- A product decision or tradeoff
- A customer or user insight
- A failure, mistake, or lesson
- A leadership or influence example

**Next step:** Choose 1–2 moments per category, then expand using `product-story-template.md`.

---

## MEANINGFUL SUCCESSES

### S1: Observable Multi-Model Routing Infrastructure (Sprint 016)
- **Span:** Moved from opaque `_OPERATION_MODEL_ROUTING` dict to explicit `RoutingStrategy` class
- **Metrics:** 39 gateway tests, 15 Gemini provider tests, 3 decision records (MSD-001/002/003), 100% deterministic A/B bucketing via MD5
- **Impact:** Model routing now visible in gateway logs; swappable without code changes; prevents silent cost escalation
- **Why it matters:** Foundation for multi-model evaluation; enables future provider swaps (Perplexity, xAI, local models)

### S2: Cost Optimization: $2.50–5.00/day → $0.54/day (Sprints 012–016)
- **Span:** 89% cost reduction through systematic optimization
- **Levers:** Tier classification before enrichment (only ~70 of 300 articles/day enriched), 100% Haiku routing (eliminated Sonnet leak), prompt compression (1,700 → 900 tokens), request/response caching
- **Metrics:** Daily baseline $0.54 (validated post-Sprint-15), monthly ~$16
- **Impact:** Enabled production viability; daily hard limit ($1.00) now has 46% safety margin; monthly ($30) has 47% margin
- **Why it matters:** Cost discipline is foundational for margins; model routing visible at every step

### S3: Fresh-Start Narrative Trust Layer (Sprint 019)
- **Span:** 7 tickets completed, zero regressions, 341 legacy narratives preserved
- **What shipped:**
  - Prevented invalid briefings from publishing (BUG-099: JSON validation, confidence thresholds, empty-insight checks)
  - Grounded refinement prompts with source context (BUG-100: replaced counts-only with full narrative/signal details)
  - Article-cluster fallback display for untrusted narratives (FEATURE-062: deterministic copy, no LLM calls)
  - Display mode API fields (FEATURE-061: distinguishes summary vs. article_cluster rendering)
  - Trusted summary eligibility filter (FEATURE-060: cutoff-based, read-only)
- **Metrics:** 4 invalid briefings pre-deploy → 0 post-deploy; 5 untrusted narratives ready for fallback display; 28 tests added to BUG-099 alone
- **Impact:** Briefings are now gated on quality; narratives page remains populated even when summaries stale; no mass mutation of legacy data

### S4: BugOps Signal Intake Foundation (Sprint 018)
- **Span:** 84 tests, deterministic alert-to-case, one-way Slack webhooks
- **What shipped:**
  - Cost-runaway detection from `llm_traces` (5-min threshold + projected hourly)
  - Hourly deduplication with exact `dedupe_key` bucketing
  - Slack webhook on new case only (no duplicate sends for repeated alerts in same hour)
  - Deterministic report generation (stored data only, no LLM calls)
- **Metrics:** 8 test files, 84 passing tests, zero regressions; 3 production bugfixes post-sprint (BUG-096, BUG-097, BUG-098)
- **Impact:** Minimal signal infrastructure in place (llm_traces source only); runway logs placeheld for future; no autonomous remediation; ready for multi-source correlation engine (Sprint 19+)

---

## DIFFICULT PROBLEMS / CHALLENGES

### C1: Zero Trusted Narratives Immediately Post-Deploy (Sprint 019, TASK-096)
- **Problem:** Fresh-start cutoff (2026-05-10 00:00:00Z) was deployment boundary itself; production had zero narratives meeting any trust condition
- **Why hard:** Appeared to be regression but required understanding narrative lifecycle (`first_seen`, `last_summary_generated_at`, `_fresh_start_validated_at` fields) and timestamp comparison logic
- **Root cause:** Most recent narrative activity was 2026-05-08 23:30:12 (2+ days before cutoff); fail-safe behavior, not a bug
- **Resolution:** Documented timeline for first scheduled narrative refresh to populate trusted pool; created BUG-101 for investigation record
- **Lesson:** Deployment boundaries are rigid; consider sliding windows or relative-freshness for scale

### C2: Narrative Cache Investigation — Why Caching Couldn't Help (TASK-075)
- **Problem:** Explored whether semantic caching could reduce narrative generation cost
- **Why hard:** Superficially looks like low-hanging fruit (cache + reuse = savings), but requires deep understanding of one-pass processing model
- **Root cause:** Each article produces unique (article_id, narrative_id) pair; no retry repetition that would benefit from cache hits; semantic caching trades 500ms+ latency cost for zero benefit
- **Resolution:** Accepted as structural constraint; no cache opportunity exists; Tier 2 Flash evals can proceed without cache changes
- **Lesson:** Validate assumptions before optimization; constraints are sometimes honest limits, not gaps

### C3: Refresh Flag Clearing Without Timestamp (BUG-102, discovered mid-Sprint-019)
- **Problem:** 3 narratives had `needs_summary_update` flag cleared but no `last_summary_generated_at` timestamp set; silently hidden from future refresh runs
- **Why hard:** Required tracing through `narrative_refresh.py` failure paths, checking `llm_traces` to verify zero LLM calls were made, querying narrative lifecycle in MongoDB
- **Root cause:** Failure paths (article hydration empty, no article_ids, LLM returns None) were calling `update_one()` to clear flag without checking success-only condition
- **Resolution:** Fixed by removing all `update_one` calls from failure paths; only success path can clear flag; added 9 regression tests
- **Lesson:** Failure paths should not mutate state—only success paths should advance lifecycle flags; may exist elsewhere in codebase

### C4: Atlas M0 Sort/Memory Limits (BUG-036, BUG-037, BUG-038)
- **Problem:** Unbounded `$group` stages on large mention collections exceeded M0 memory (100MB limit)
- **Why hard:** Required replicating MongoDB's sort logic in Python post-grouping; validated correctness against original pipeline behavior
- **Resolution:** Moved sorting out of MongoDB pipeline; applied in Python after grouping
- **Impact:** Articles endpoint: 45s+ → 1–3s; entities endpoint: similar improvement

---

## PRODUCT DECISIONS / TRADEOFFS

### D1: Fresh-Start vs. Mass-Refresh of 341 Legacy Narratives (Sprint 019)
- **Options considered:**
  - **Option A (Mass-refresh):** Mutate all 341 legacy narratives to mark trusted; cost $3–5, operational risk
  - **Option B (Fresh-start):** Keep old data, only new narratives trusted; article-cluster fallback for display; $0 cost
- **Decision:** Chose B
- **Rationale:** Zero cost, preserves user experience, keeps old data for optional later repair, fail-safe (untrusted → fallback)
- **Outcome:** 7 tickets shipped; article-cluster fallback never needed to display because narrative refresh populates pool quickly
- **Tradeoff:** Users see deterministic fallback copy (not generated summary) for untrusted narratives; acceptable given speed/cost

### D2: Quality Regression Threshold (>5% = HALT, not force) (Sprint 016)
- **Context:** Tier 1 Flash evaluations on entity_extraction, sentiment_analysis, theme_extraction
- **Findings:** All 3 ops flagged >5% regression on Flash (expected for extraction tasks with strict F1 scoring)
- **Options considered:**
  - **Option A (Force swap):** Cost savings justify adoption despite regression
  - **Option B (Evidence-based halt):** Document regression, STAY Haiku, no swap
- **Decision:** Chose B
- **Rationale:** Quality is non-negotiable for mission-critical extraction; regression on rare entity types not worth cost savings
- **Outcome:** 3 decision records (MSD-001/002/003) with full analysis; zero production model swaps
- **Lesson:** Evidence-based outcomes (STAY when data says so) beats optimization pressure; defensible in interviews

### D3: Hourly Deduplication for BugOps Alerts (vs. per-incident bucketing)
- **Problem:** Same cost-runaway can occur 2–3x per hour (different article batches hitting entity_extraction in parallel)
- **Options considered:**
  - **Option A (Per-incident):** Separate case for each spike; accurate but alert fatigue
  - **Option B (Hourly bucketing):** Single case per hour, all alerts attached; users get 1 Slack notification
- **Decision:** Chose B
- **Rationale:** Prevents alert fatigue; incident window grouped by hour is reasonable for operational response
- **Tradeoff:** Lose per-incident granularity; users don't see "3 spikes in this hour"
- **Known limitation:** Documented for future multi-source correlation engine (Sprint 19+); can be refined with cost-tier bucketing

---

## CUSTOMER / USER INSIGHTS

### I1: Cost Spikes Recur Multiple Times Per Hour (BugOps context)
- **Finding:** Tier 1 operations (entity_extraction, sentiment_analysis) see 2–3 independent cost spikes per hour from different article batches
- **Why it matters:** Users expect granular incident awareness; hourly bucketing hides recurrence
- **Impact on design:** Led to decision for hourly deduplication (tradeoff: alert fatigue vs. incident granularity)
- **Future implication:** Multi-source correlation engine can offer cost-tier bucketing (critical >$1, warning 0.25–1.00 in same hour → separate alerts)

### I2: Article-Cluster Fallback Needed for Untrusted Narrative Display
- **Finding:** Fresh-start approach left 355+ narratives untrusted post-deploy; users needed something visible on narratives page
- **Why it matters:** Empty/sparse narratives page is worse UX than article-cluster fallback
- **Solution:** Deterministic fallback copy: primary entity → theme → "Recent Coverage"; scans up to 3 clean article titles (filters stale/untrusted/needs-refresh)
- **Impact:** Narratives page remains populated even when generated summaries unavailable; never exposes internal system-state language

---

## FAILURES / MISTAKES / LESSONS

### L1: Failure Paths Shouldn't Mutate State (BUG-102 lesson)
- **What happened:** `narrative_refresh.py` cleared `needs_summary_update` flag in failure paths (article hydration empty, no article_ids, LLM returns None)
- **Impact:** 3 narratives silently hidden from future refresh runs; required post-hoc re-flagging and retry
- **Lesson:** Only success paths should advance lifecycle flags; failure paths should log + continue without mutation
- **Audit recommendation:** Search codebase for similar patterns (failure paths with `update_one` calls)

### L2: Scoring Harness Hardcoded Field Names (BUG-060)
- **What happened:** Copy-paste error when extending eval harness from Flash to DeepSeek/Qwen; all Phase 3/4 output had `flash_label` instead of model-specific fields
- **Impact:** Accuracy totals unaffected; per-class data mislabeled
- **Lesson:** Post-hoc bug fixes break eval infrastructure; must be caught before running next eval pass
- **Prevention:** Code review for model-specific field names before executing evals

### L3: Opaque Routing Unmaintainable (BUG-090)
- **What happened:** `_OPERATION_MODEL_ROUTING` dict was source of truth but invisible in logs; accidentally routed operations to expensive models
- **Impact:** Cost escalation without visibility; operations team didn't know why costs spiked
- **Lesson:** Make routing explicit and observable; every decision must appear in logs
- **Resolution:** Introduced `RoutingStrategy` class; all overrides logged with operation + requested + actual

---

## LEADERSHIP / INFLUENCE

### L1: Established Decision-Record Discipline for Model Selection (Sprint 016)
- **What I did:** Wrote generalizable model-selection rubric (5 decision dimensions, 4 tier levels, explicit criteria)
- **Why it matters:** Reproducible framework applicable to any future model choice (Perplexity, xAI, local models)
- **Outcome:** 3 evidence-based decision records (MSD-001/002/003); used as interview material; framework extends beyond this product
- **Influence:** Established that >5% regression = HALT (not optimization pressure); prevents "close enough" drift
- **Constraint:** Framework is defensible but may erode under deadline pressure; culture-dependent

### L2: Evidence-Based Thinking Over Optimization Pressure
- **What I did:** When all 3 Tier 1 Flash evals flagged >5% regression, documented as expected outcome (not failure)
- **Why it matters:** Prevents false urgency; decisions grounded in data, not pressure
- **Outcome:** STAY Haiku decisions widely understood; zero regret (quality is working fine)
- **Leadership moment:** "Here's how we think about tradeoffs. Here's what the data says. Here's what we chose and why." This is interview-ready rigor.

### L3: Tier Discipline Prevents Scope Creep (Sprint 016)
- **What I did:** Set explicit "Tier 1 ONLY, 3 ops" boundary; explicitly deferred Tier 2 despite being unblocked
- **Why it matters:** Scope discipline keeps teams predictable; prevents "just one more" scope creep
- **Outcome:** Sprint 016 shipped on schedule; Tier 2 unblocked for future sprints without delay
- **Lesson:** Boundaries are features, not constraints; saying "no" to unblocked work is leadership

---

## INFRASTRUCTURE / SCALE MOMENTS

### I1: Cost Tracking Centralization (llm_traces as Single Source of Truth)
- **Problem:** `api_costs` + `llm_usage` collections existed alongside `llm_traces`; entity_extraction costs ($0.177/day) were invisible to enforcement layer
- **Resolution:** Moved all spend cap enforcement to read exclusively from `llm_traces`; deprecated legacy collections
- **Impact:** Daily spend visibility complete; no silent leaks; BUG-079 (hidden costs) prevented future regressions
- **Lesson:** One source of truth for money is non-negotiable; audit query implementations against authoritative collection

### I2: Observable Gateway Model Routing (BUG-077)
- **What:** Every variant assignment logged with operation + requested + actual + cost
- **Why:** Prevents silent cost escalation; enables debugging "why did cost spike?"
- **Impact:** 100% Haiku routing verified post-deployment; zero accidental Opus/Sonnet charges
- **Lesson:** Observability at every lever point; costs are visible in logs

### I3: Market Event Detection Disabled Gracefully (BUG-083)
- **Problem:** Original implementation had loose keyword matching (OR logic), fabricated figures ($50B+ liquidations)
- **Resolution:** Disabled, return empty list, documented limitation, briefings fall back to article-sourced signals + narratives
- **Why it matters:** Better to disable + be honest than ship broken; fallback path works fine
- **Lesson:** Acknowledge limitations; don't hide broken features

---

## DATA QUALITY MOMENTS

### DQ1: Duplicate Article Assignment Under Signals (BUG-032)
### DQ2: Narrative Articles Missing Time-Bound Cutoff (BUG-045: 45s latency fix)
### DQ3: Articles Batch N+1 Query (BUG-040: 45s+ → 1–3s)
### DQ4: Invalid Briefing Output Publishing (BUG-099: validation + confidence thresholds)

*For expansion: each of these has metrics + architectural rationale*

---

## SYSTEM DESIGN MOMENTS

### SD1: Celery + Beat for Distributed Task Processing (vs. direct FastAPI)
### SD2: Semantic Similarity for Narrative Detection (vs. keyword matching)
### SD3: NoSQL (MongoDB) for Flexible Schema (vs. PostgreSQL ACID)
### SD4: Soft Spend Limit $22.50 (non-functional, known issue) + Hard Limits $1/day, $30/month

*For expansion: each of these has tradeoff analysis + operational impact*

---

## NEXT STEPS

1. **Choose 1–2 moments per Backdrop category** above
2. **Expand chosen moments** using `product-story-template.md`
3. **Verify metrics** are defensible (DEFENSIBLE vs. APPROXIMATE)
4. **Link to decision records** or "none yet"
5. **Mark for publication** (Y/Maybe/No)

---

**Last updated:** 2026-07-22
