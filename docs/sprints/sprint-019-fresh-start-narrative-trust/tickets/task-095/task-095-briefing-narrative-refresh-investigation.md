---
ticket_id: TASK-095
title: Investigate Briefing Refinement Publication and Narrative Refresh Behavior
priority: high
severity: high
status: COMPLETE
date_created: 2026-05-10
date_completed: 2026-05-10
branch: task/investigate-briefing-narrative-refresh
effort_estimate: medium
actual_effort: 2.5 hours
---

# TASK-095: Investigate Briefing Refinement Publication and Narrative Refresh Behavior

## Problem Statement

A production morning briefing published invalid model meta-output instead of a valid crypto briefing. The published narrative asked the user to provide active narrative titles, summaries, and entity names.

This appears to be a downstream symptom of two possible system issues:

1. Briefing refinement can return non-briefing text and still be saved/published.
2. Active narratives may be stale because legacy narratives missing `last_summary_generated_at` are not being marked for summary refresh.

Before implementing any fixes, investigate the current code paths and answer how the system actually behaves. Do not modify code, run migrations, or change production data.

---

## Context

The bad briefing was already unpublished manually, so users now see the previous valid evening briefing.

Bad briefing evidence:

```text
_id: 6a00734544c1c6f85c7266f1
type: morning
generated_at: 2026-05-10T12:00:00.512Z
task_id: 9ec83c1e-5dd7-423c-a70e-831b10a2375f
metadata.confidence_score: 0.3
metadata.refinement_iterations: 1
content.key_insights: []
content.narrative: asks for narrative titles, summaries, and entity names
```

LLM trace evidence showed the briefing pipeline completed without technical errors:

```text
briefing_generate
briefing_critique
briefing_refine
briefing_critique
briefing_refine
```

All observed `llm_traces.error` values were null.

Narrative freshness evidence:

```text
active narratives missing last_summary_generated_at: 341
narratives with needs_summary_update=true: 4
```

Example stale active narrative:

```text
title: Bitcoin Holds $75K Amid Geopolitical Tensions and Strong ETF Inflows
first_seen: 2025-10-18
last_updated: 2026-05-10
lifecycle_state: hot
needs_summary_update: false
last_summary_generated_at: missing
```

The actual linked articles are current BTC-around-$80K articles, including:

```text
Bitcoin holds $80K into weekly close as traders say BTC price dip not yet over
Bitcoin Price Prospect: BTC Holds $80K While Momentum Starts Heating Up
Bitcoin price may dip toward $70K as Fed estimates hotter inflation print
Bitcoin briefly slips below $80,000, but options traders are betting the dip won’t last
Bitcoin stalls as BTC ETF outflows hit $268M
Bitcoin Bulls Defend $79,200 as $28.3M in Long Liquidations Resets Risk
```

Known likely data-type issue:

```text
narratives.article_ids appear to be stored as strings
articles._id are ObjectIds
```

This may matter if narrative refresh/source hydration queries articles without converting string IDs to ObjectId.

---

## Task

Perform a read-only investigation and produce a structured report answering the questions below.

Do not implement fixes. Do not modify code. Do not run migrations. Do not change production data.

1. Inspect briefing generation, refinement, parsing, saving, and public retrieval behavior.
2. Inspect narrative summary freshness and refresh task behavior.
3. Inspect article hydration behavior for string `article_ids` versus ObjectId `_id`.
4. Inspect LLM cost/budget behavior for narrative refresh.
5. Recommend a staged fix plan, but do not implement it.

---

## Files to Create

```text
docs/investigations/TASK-095-briefing-narrative-refresh-investigation.md
```

---

## Files to Modify

```text
None
```

---

## Do Not Modify

```text
src/crypto_news_aggregator/services/briefing_agent.py
src/crypto_news_aggregator/services/narrative_service.py
src/crypto_news_aggregator/tasks/
src/crypto_news_aggregator/db/operations/
src/crypto_news_aggregator/llm/
context-owl-ui/
```

Do not modify any application code, tests, migrations, database records, or environment configuration in this task.

---

## Implementation Requirements

This is an investigation-only task.

- [ ] Do not edit production code.
- [ ] Do not edit tests.
- [ ] Do not run migrations.
- [ ] Do not update MongoDB records.
- [ ] Do not trigger production briefing generation.
- [ ] Do not trigger narrative refresh jobs.
- [ ] Do not run any command that could consume LLM budget unless explicitly approved.
- [ ] Produce a written investigation report only.
- [ ] Include exact file paths and function/class names for every finding.
- [ ] Distinguish confirmed behavior from inferred behavior.
- [ ] Distinguish code findings from database observations.
- [ ] Include any unknowns or ambiguous code paths.

### Files to Inspect First

Start with these files. Follow imports/references as needed.

```text
src/crypto_news_aggregator/services/briefing_agent.py
src/crypto_news_aggregator/services/narrative_service.py
src/crypto_news_aggregator/tasks/
src/crypto_news_aggregator/tasks/beat_schedule.py
src/crypto_news_aggregator/db/operations/briefing.py
src/crypto_news_aggregator/db/operations/narratives.py
src/crypto_news_aggregator/llm/gateway.py
```

Also inspect any frontend/API code used by:

```text
briefings page
narratives page
public briefing API endpoint
public narratives API endpoint
admin briefing trigger endpoint
```

### Investigation Questions

#### A. Briefing Publication Behavior

Answer:

1. Where exactly is the final briefing saved?
2. What function constructs the final `daily_briefings` document?
3. Does the code validate whether generated/refined output is actually publishable?
4. Can a low-confidence briefing still be saved with `published=true`?
5. Can a briefing with empty `key_insights` still be saved with `published=true`?
6. Does `_parse_briefing_response` or equivalent fallback behavior allow arbitrary raw text to become `content.narrative`?
7. Does the public briefing API filter out invalid, failed, low-confidence, or empty-insight briefings?
8. What fields does the public briefing page use to decide which briefing to show?
9. Is there any existing concept of `invalid_output`, `failed_generation`, or similar metadata?

#### B. Briefing Refinement Behavior

Answer:

1. What exactly is included in the initial `briefing_generate` prompt?
2. What exactly is included in the `briefing_critique` prompt?
3. What exactly is included in the `briefing_refine` prompt?
4. Does the refinement prompt include the full active narrative source context?
5. Does the refinement prompt include active narrative titles?
6. Does the refinement prompt include narrative summaries/descriptions?
7. Does the refinement prompt include narrative entities?
8. Does the refinement prompt include article titles/sources attached to each narrative?
9. Is there any chance the refinement prompt references an `AVAILABLE DATA` section that is not actually included?
10. Does the refinement prompt explicitly require valid JSON only?
11. What happens if refinement returns plain text instead of JSON?
12. Is the final saved briefing always the last refinement output, even if it is lower quality than the original generation?

#### C. Narrative Freshness Behavior

Answer:

1. Where are `needs_summary_update` and `last_summary_generated_at` set?
2. Are these fields set when a narrative is first created?
3. Are these fields set when an article is appended to an existing narrative?
4. What happens if an existing narrative is missing `last_summary_generated_at`?
5. Does staleness logic treat missing `last_summary_generated_at` as stale?
6. What exact conditions set `needs_summary_update=true`?
7. Does lifecycle promotion set `needs_summary_update=true`?
8. Does 3+ new articles since last summary set `needs_summary_update=true`?
9. Does `last_updated > last_summary_generated_at + 24h` set `needs_summary_update=true`?
10. Are legacy narratives missing `last_summary_generated_at` excluded from refresh logic?
11. Are active narratives allowed to remain `hot`, `emerging`, `rising`, or `reactivated` with missing `last_summary_generated_at` and `needs_summary_update=false`?

#### D. Narrative Refresh Task Behavior

Answer:

1. Does `refresh_flagged_narratives` exist?
2. Where is it defined?
3. Is it scheduled automatically?
4. If scheduled, how often does it run?
5. Does it have a batch limit?
6. Does it respect LLM daily/monthly budget limits?
7. Does it process all `needs_summary_update=true` narratives in one run or bounded batches?
8. What operation name does it use for LLM traces?
9. Does it update `title`, `description`, or both?
10. Does it set `last_summary_generated_at=now` after refresh?
11. Does it clear `needs_summary_update=false` after successful refresh?
12. What happens on refresh failure?
13. Does it retry failed narratives?
14. Does it record refresh failure metadata?

#### E. Article Hydration / ObjectId Behavior

Answer:

1. What type is stored in `narratives.article_ids`: strings, ObjectIds, or mixed?
2. What type is used for `articles._id`?
3. Does narrative refresh logic convert string `article_ids` to ObjectId before querying `articles`?
4. Could refresh/source hydration silently return zero articles because of string/ObjectId mismatch?
5. Are there tests covering string article IDs?
6. Are there any helper functions for converting narrative article IDs into article ObjectIds?
7. Are those helpers used consistently in briefing and narrative refresh paths?

#### F. Cost and Budget Behavior

Answer:

1. What operation names correspond to narrative generation and narrative refresh in `llm_traces`?
2. What is the estimated average cost of one narrative refresh based on existing code and traces?
3. If 341 narratives were flagged for refresh, would the system try to refresh all immediately?
4. Could that exceed the $1/day hard budget?
5. Would budget exhaustion block later entity extraction, narrative generation, or briefing generation?
6. Is there a per-task or per-run refresh budget separate from the global LLM budget?
7. Is there a safe way in the current system to refresh only 10-20 narratives as a pilot?
8. Does the refresh path have cost-aware batching, throttling, or early stopping?

#### G. Recommended Safe Fix Plan

Based on findings, propose a minimal staged plan.

Include:

1. containment fix to prevent invalid briefings from publishing
2. refinement prompt/context fix
3. narrative freshness fix for missing `last_summary_generated_at`
4. small pilot refresh plan
5. batch backfill plan with cost controls
6. user-facing ramifications
7. cost ramifications
8. risks and rollback plan

Do not implement the plan.

### Configuration

No configuration changes required.

```text
N/A
```

### Commands to Run

Prefer static inspection commands only.

Allowed:

```bash
grep -R "refresh_flagged_narratives" -n src/
grep -R "needs_summary_update" -n src/
grep -R "last_summary_generated_at" -n src/
grep -R "briefing_refine" -n src/
grep -R "briefing_critique" -n src/
grep -R "published" -n src/ context-owl-ui/
grep -R "daily_briefings" -n src/
```

Allowed if needed:

```bash
pytest --collect-only
```

Do not run:

```bash
pytest
celery
python -m crypto_news_aggregator.tasks...
python -m crypto_news_aggregator.services...
```

unless explicitly approved, because some commands may trigger LLM calls, background jobs, or database writes.

---

## Verification

### Automated Verification

- [ ] No code files modified.
- [ ] No tests modified.
- [ ] No migrations created.
- [ ] Investigation report created at `docs/investigations/TASK-095-briefing-narrative-refresh-investigation.md`.
- [ ] Report includes file paths and function names for every finding.
- [ ] Report answers all questions in sections A-G or explicitly marks unanswered items as unknown.

### Manual Verification

- [ ] Review `git diff` and confirm only the investigation report was added.
- [ ] Confirm no production data was changed.
- [ ] Confirm no LLM-consuming commands were run.
- [ ] Confirm report distinguishes confirmed behavior from inferred behavior.
- [ ] Confirm report includes a recommended staged fix plan but no implementation.

---

## Acceptance Criteria

- [ ] The investigation identifies the exact code path that allowed invalid refinement output to become a published briefing.
- [ ] The investigation identifies whether low-confidence / empty-insight briefings can currently publish.
- [ ] The investigation identifies whether refinement prompts include sufficient narrative source context.
- [ ] The investigation identifies where `needs_summary_update` and `last_summary_generated_at` are set and whether missing timestamps are treated as stale.
- [ ] The investigation identifies whether `refresh_flagged_narratives` exists, whether it is scheduled, and whether it has batch/cost controls.
- [ ] The investigation identifies whether string `article_ids` are converted to ObjectId during article hydration.
- [ ] The investigation estimates cost ramifications of refreshing 10, 50, 100, and 341 narratives.
- [ ] The investigation proposes a safe staged fix order.
- [ ] No application code or production data is changed.

---

## Impact

This investigation reduces risk before implementing fixes.

Expected benefits:

- Prevents premature changes to production data.
- Clarifies whether the immediate user-facing bug is isolated to briefing publication validation or also requires prompt/context fixes.
- Clarifies whether narrative refresh can be safely backfilled without blowing through the daily LLM budget.
- Produces an implementation-ready plan for the next bug/fix tickets.

User-facing impact of the investigation itself:

- None. This task should not change runtime behavior.

Cost impact of the investigation itself:

- None expected. This task should not trigger LLM calls or refresh jobs.

Operational risk:

- Low, assuming no code, database, or runtime jobs are modified.

---

## Related Tickets

- Follow-up likely: `BUG-XXX: Prevent Invalid Briefing Refinement Output From Publishing`
- Follow-up likely: `BUG-XXX: Fix Narrative Summary Freshness for Legacy Active Narratives`
- Follow-up likely: `TASK-XXX: Batch Backfill Stale Active Narrative Summaries With Cost Controls`

---

## Completion Summary

**Status: COMPLETE** ✅

- **Branch:** `task/investigate-briefing-narrative-refresh`
- **Report Location:** `docs/investigations/TASK-095-briefing-narrative-refresh-investigation.md`
- **Changes Made:** Investigation report only (1,125 lines). No code modifications, no database changes, no LLM calls.
- **Tests Run:** N/A (read-only investigation)
- **Manual Verification:**
  - ✅ Confirmed no src/ files modified: `git diff src/` returns empty
  - ✅ Confirmed no test files modified
  - ✅ Confirmed investigation report created with all 7 sections (A-G)
  - ✅ Confirmed exact file paths and function names included throughout
  - ✅ Confirmed report distinguishes confirmed vs. inferred behavior
  - ✅ Confirmed staged fix plan included (5 stages with risks/rollback)
  - ✅ No production data changed
  - ✅ No LLM-consuming commands executed

**Deviations from Plan:** None. Completed exactly as specified.

---

## Key Investigation Findings (Summary)

### Root Cause Identified
**Briefing Publication Validation Gap:** The `_parse_briefing_response()` fallback handler (lines 878-890 in `briefing_agent.py`) accepts raw LLM text as valid briefing content when JSON parsing fails, setting `confidence_score=0.3`. No validation prevents publication of low-confidence or empty-insight briefings.

### Secondary Issues Identified
1. **Refinement Prompt Context Deficiency:** Refinement prompt references "AVAILABLE DATA" but includes no actual narrative details, summaries, entities, or articles — preventing effective refinement.
2. **Narrative Staleness Detection Failure:** 341 legacy narratives missing `last_summary_generated_at` are not flagged for refresh because staleness logic uses `last_updated` as fallback, making recent-but-stale narratives appear fresh.

### Confirmed (Not Root Cause)
- ✅ String/ObjectId conversion: Correctly handled in both `narrative_refresh.py:92` and `briefing_agent.py:322`
- ✅ Refresh task exists, scheduled, has batch limits (20/run), respects budget
- ✅ Cost estimates: $6.82-10.23 for 341 narratives; $0.50/day at 20/run

### Recommended Fix Stages
1. **Stage 1 (Containment):** Add briefing validation (reject low-confidence/empty)
2. **Stage 2 (Refinement):** Add narrative context to refinement prompt
3. **Stage 3 (Staleness):** Backfill missing timestamps + fix staleness detection
4. **Stage 4 (Backfill):** Batch refresh 341 narratives over 7-10 days
5. **Stage 5 (Monitoring):** Dashboard tracking

**Total Implementation Estimate:** ~15-20 hours (including staging validation)
**Cost Impact:** +$0.02-0.05/day for refinement prompts; ~$5-7 one-time for backfill
