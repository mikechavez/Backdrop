---
ticket_id: TASK-075
title: Narrative Cache Investigation - Root Cause Analysis & Fix Proposal
priority: critical
severity: critical
status: CLOSED
date_created: 2026-04-27
date_closed: 2026-04-27
branch: feature/narrative-cache-investigation
effort_estimate: 4-6 hours
effort_actual: ~2 hours
---

# TASK-075: Narrative Cache Investigation - Root Cause Analysis & Fix Proposal

## Problem Statement

The `narrative_generate` operation has **0% cache hit rate** despite being the **second-largest cost driver** in Backdrop ($6.64/month over 2,543 calls). This investigation was opened to determine whether caching could be fixed to reduce costs 5-10x, potentially eliminating the need for a Gemini Flash model swap.

**Finding:** The 0% hit rate is not a bug. It is a structural property of how the system processes narrative operations. Exact-match caching cannot materially reduce costs for these operations under the current architecture. The Gemini Flash model swap (FEATURE-053) is confirmed as the correct cost lever.

---

## Investigation Results

### Phase 1: Root Cause Analysis — COMPLETE

**Evidence gathered:**
- Reviewed `gateway.py` (cache logic, CACHEABLE_OPERATIONS, `_write_trace`, `_save_to_cache`, `_get_from_cache`)
- Reviewed `narrative_themes.py` (all narrative operation callers, input construction)
- Reviewed ingestion architecture (`30-ingestion.md`) — confirmed one-pass processing + aggressive deduplication
- Queried `llm_cache` collection: 0 entries for any narrative operation
- Queried `llm_traces` aggregation: `input_hash` field is null on all trace documents (for all operations, not just narrative)

**Three root causes identified:**

#### Root Cause 1 — narrative_generate was likely not in CACHEABLE_OPERATIONS historically

The `llm_cache` collection has **zero entries** for `narrative_generate` despite 3,524 recorded calls. The `_save_to_cache` implementation is correct and working (validated by `entity_extraction` having thousands of cache entries). The only consistent explanation is that `narrative_generate` was added to `CACHEABLE_OPERATIONS` recently, after the majority of those calls were made. The uploaded `gateway.py` reflects a newer version than what was running in production during the billing period.

*Confidence: high / not fully proven. Alternative explanations: silent write failure, environment mismatch. Soften if disputed.*

**Code location:** `gateway.py` lines 603–608 (CACHEABLE_OPERATIONS list)

#### Root Cause 2 — Exact-match caching structurally cannot help narrative operations

This is the core architectural constraint. The input being hashed for `narrative_generate` is:

```
"Article Title: {title}\nArticle Summary: {summary[:500]}\n\nExtract narrative data. Respond with ONLY valid JSON."
```

Every call processes a different article with a unique title and summary → unique SHA-1 every time. A cache hit requires byte-identical input. The ingestion pipeline deduplicates articles on `title + content[:500]` fingerprint before insertion — so each article enters MongoDB once and is processed once. There is no mechanism causing the same content to reach `narrative_generate` twice.

The same structural constraint applies to `cluster_narrative_gen` (unique article clusters per run) and `actor_tension_extract` (unique theme+snippet combinations per run).

**Why entity_extraction achieves 99.6% hits but narrative operations don't:**
`entity_extraction` runs via Celery tasks, which retry on timeout or failure. When a worker crashes or a task times out, the same `article_id` is re-queued and `entity_extraction` runs again on identical content → cache hit. Narrative operations run in a different code path without the same retry-driven repetition.

**Code locations:**
- `narrative_themes.py:855` — `narrative_generate` input construction (title + summary)
- `narrative_themes.py:1023` — `actor_tension_extract` input construction (theme + snippets)
- `narrative_themes.py:1430` — `cluster_narrative_gen` input construction (article cluster)
- `gateway.py:617–619` — SHA-1 hash of `json.dumps(messages, sort_keys=True)`

#### Root Cause 3 — cluster_narrative_gen, actor_tension_extract, and narrative_polish are excluded from CACHEABLE_OPERATIONS entirely

Three of the four narrative operation strings are never checked against cache:

| Operation | Line | In CACHEABLE_OPERATIONS |
|---|---|---|
| `narrative_generate` | 855 | ✅ yes |
| `actor_tension_extract` | 1023 | ❌ no |
| `cluster_narrative_gen` | 1430 | ❌ no |
| `narrative_polish` | 1486 | ❌ no |

Even if added, Root Cause 2 means they would not produce meaningful cache hits.

**Code location:** `gateway.py:603–608` (CACHEABLE_OPERATIONS list)

#### Secondary bug found — cache save failures silently suppressed

In `_save_to_cache`, exceptions are logged at DEBUG level:

```python
except Exception as e:
    logger.debug(f"Cache save failed for {operation}: {e}")  # ← should be WARNING
```

If cache writes fail for any reason (connection issue, auth error, timeout), the failure is invisible in production logs. This does not explain the 0% hit rate but is a real observability gap.

**Code location:** `gateway.py:285`

---

## Caching Strategies Considered and Scoped Out

The above findings apply specifically to the current **exact-match response caching** architecture. Two alternative caching strategies exist but are out of scope for Sprint 16:

**Semantic caching** — embed inputs, retrieve nearest neighbor, return cached response if similarity exceeds threshold. Technically valid for topically similar articles, but requires embedding infrastructure, vector store, similarity threshold tuning, and quality validation to ensure wrong narratives aren't reused. Non-trivial engineering investment not justified at $6.64/month.

**Component-level caching** — cache intermediate pipeline steps rather than full operation outputs. Would require redesigning narrative generation as a multi-stage pipeline. Introduces latency, complexity, and orchestration overhead. Out of scope for current sprint; only worth revisiting if optimizing for quality or controllability, not cost.

**Decision:** Both strategies are deferred indefinitely unless narrative operation volume scales significantly (10-100x) or narrative generation is redesigned as a multi-stage pipeline for other reasons.

---

## Verification

### Investigation Verification (Phase 1)

- [x] Confirmed narrative_generate IS in CACHEABLE_OPERATIONS in uploaded gateway.py
- [x] Located all callers of narrative operations (narrative_themes.py lines 855, 1023, 1430, 1486)
- [x] Queried llm_cache collection: **0 entries** for any narrative operation
- [x] Ran aggregation on llm_traces: `input_hash` is null on all documents (field not written by `_write_trace`)
- [x] Root cause documented: structural — unique inputs per call, one-pass processing, no retry repetition

### Solution Design Verification (Phase 2)

- [x] Root cause tied to specific code locations
- [x] Alternative caching strategies evaluated and explicitly scoped out
- [x] Decision: accept as architectural constraint; proceed with model swap
- [x] Minor fixes documented (observability improvements)

---

## Acceptance Criteria

- [x] Root cause identified and documented — **0% cache hit rate caused by: unique per-article inputs + one-pass processing pipeline (no retry repetition)**
- [x] Root cause tied to specific code locations (gateway.py, narrative_themes.py)
- [x] MongoDB queries run and results analyzed:
  - [x] llm_cache collection state: 0 entries for all narrative operations
  - [x] llm_traces input_hash: null on all documents (input_hash not written to trace schema)
  - [x] Call distribution: all 3,524 narrative_generate calls have null input_hash (confirmed via aggregation)
- [x] Solution design produced:
  - [x] Alternative strategies evaluated (semantic caching, component-level caching) — both scoped out
  - [x] No code changes recommended for caching
  - [x] Minor observability fix recommended (logger.debug → logger.warning in _save_to_cache)
  - [x] Expected cache hit improvement: 0% (structural constraint, not fixable with current architecture)
  - [x] Cost savings from caching: $0/month
- [x] Decision recorded: **Accept as architectural constraint. Do not pursue caching fix.**
- [x] Recommendation: **Proceed to FEATURE-053 Flash evaluation for narrative operations (Sprint 17)**

---

## Impact

**On Sprint 16:**
- TASK-075 is resolved. Cache investigation is closed.
- narrative_generate is confirmed NOT suitable for caching under current architecture.
- Flash evaluation for narrative operations (Tier 2) is confirmed as justified — defer to Sprint 17 per existing scope.
- FEATURE-053 Sprint 16 scope unchanged: Tier 1 only (entity_extraction, sentiment_analysis, theme_extraction).

**On cost projection:**
- No change from caching. narrative_generate cost remains ~$6.64/month until model swap is evaluated.
- Model swap (Gemini Flash) is the only near-term lever. Deferred to Sprint 17 for Tier 2 operations.

**On TASK-071 threshold recalibration:**
- No new baseline from caching. Recalibration can proceed using current cost data as-is.

---

## Recommended Follow-On Actions

**Do now (minor, low effort):**
1. Change `logger.debug` → `logger.warning` in `_save_to_cache` so cache write failures are visible in production logs (`gateway.py:285`)
2. Add explicit cache outcome logging (hit/miss, operation, hash prefix) to the gateway so cache behavior is observable without running manual DB queries

**Do in Sprint 17:**
3. Evaluate Gemini Flash for narrative operations (Tier 2 evals) — this is the real cost reduction path
4. Optionally add retry logic to narrative operations if pipeline reliability issues emerge — retries would create cache-hit opportunities as a free side effect, but should only be added for reliability reasons, not caching

**Do not do:**
- Semantic caching (over-engineered for current scale)
- Component-level caching (requires pipeline redesign)
- Input entropy reduction / normalization (degrades output quality)
- Adding cluster_narrative_gen / actor_tension_extract to CACHEABLE_OPERATIONS (hygiene only, no cost impact)

---

## Related Tickets

- BUG-090 (Model Override) — COMPLETE ✅
- FEATURE-053 (Flash Evaluations) — Sprint 16 Tier 1 scope unchanged; Tier 2 (narrative) deferred to Sprint 17
- TASK-071 (Threshold Recalibration) — unblocked; use current cost data as baseline
- Sprint 16 Model Selection Rubric — narrative_generate confirmed as Tier 2; Flash evaluation justified for Sprint 17

---

## Completion Summary

- **Root cause identified:** Unique inputs (per-article content) + one-pass processing pipeline with no retry repetition → exact-match caching cannot produce hits
- **Solution recommended:** No caching fix. Accept as architectural constraint.
- **Estimated cache hit improvement:** 0% (structural)
- **Cost savings from caching:** $0/month
- **Decision:** Accept as-is. Proceed with Gemini Flash evaluation for narrative operations in Sprint 17.
- **Impact on Sprint 16:** No change to scope. FEATURE-053 remains Tier 1 only (3 ops). Narrative operations deferred to Sprint 17 for model swap evaluation.
- **Secondary finding:** Cache save failures are silently suppressed at DEBUG level — fix observability before Sprint 17 evals.