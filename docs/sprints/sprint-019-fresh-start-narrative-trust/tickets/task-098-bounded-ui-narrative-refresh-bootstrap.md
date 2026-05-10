---
ticket_id: TASK-098
title: Bounded UI Narrative Refresh Bootstrap
priority: high
severity: medium
status: IN PROGRESS - BLOCKED ON CELERY WORKER
date_created: 2026-05-10
date_last_updated: 2026-05-10
branch: task/bounded-ui-narrative-refresh-bootstrap
effort_estimate: small-to-medium
blocker: Celery worker not running in Railway production environment
---

# TASK-098: Bounded UI Narrative Refresh Bootstrap

## Problem Statement

After Sprint 019 deployment, the system is safer but not yet fully briefing-ready.

Post-deploy verification showed:

- BUG-099 containment is working: invalid post-deploy briefing output was saved unpublished.
- FEATURE-060 trust filtering is working: trusted narrative count is currently 0.
- The public narratives page has recent active narratives, but those narratives are legacy/untrusted because they do not yet have `last_summary_generated_at >= 2026-05-10T00:00:00Z`.
- The current public UI appears to show generated narrative titles/summaries for active narratives, including examples such as:
  - `Senate Banking Committee Advances Crypto Regulation Efforts`
  - `LayerZero Admits Mistakes in $292M Kelp DAO Exploit`
  - `Bitcoin Holds $75K Amid Geopolitical Tensions and Strong ETF Inflows`
  - `SEC Signals New Regulatory Framework for Onchain Markets`
  - `Coinbase Navigates Infrastructure Crisis Amid Market Recovery`

This creates two operational questions:

1. Are FEATURE-061/062 display-mode fields actually being returned and consumed by the public narratives UI?
2. Can we safely bootstrap trusted narrative summaries by refreshing only the narratives currently visible on the public Active Narratives page, instead of waiting for scheduled refresh or mass-refreshing legacy narratives?

This task is a controlled post-deploy operational bootstrap. It is not a general legacy repair.

---

## Goal

Verify the display-mode behavior for the narratives currently visible on the public UI, then prepare and, if explicitly approved, run a bounded refresh for the top public UI narratives so that a small, relevant set becomes trusted for briefing synthesis.

A narrative becomes trusted for briefing synthesis if:

```text
first_seen >= 2026-05-10T00:00:00Z
OR last_summary_generated_at >= 2026-05-10T00:00:00Z
OR _fresh_start_validated_at >= 2026-05-10T00:00:00Z
```

The preferred outcome is:

```text
current top UI narratives refreshed
→ last_summary_generated_at >= cutoff
→ trusted_narratives > 0
→ smoke briefing has real trusted summaries
→ scheduled production briefing can resume with useful inputs
```

---

## Scope

### In Scope

- Identify the exact narratives currently displayed on the public Active Narratives page.
- Compare UI narratives against MongoDB records.
- Verify whether those narratives are trusted or untrusted under the FEATURE-060 rule.
- Verify public API display fields for those narratives:
  - `display_mode`
  - `display_title`
  - `display_summary`
  - `recent_article_count`
- Determine why the UI may still be showing generated title/summary for untrusted narratives.
- Locate the safest existing mechanism for refreshing specific narrative summaries.
- Prepare a bounded refresh plan for the top 5 current UI narratives.
- Run the bounded refresh only after explicit approval.
- Verify refreshed narratives become trusted.
- Recommend whether to run a smoke briefing after refresh.

### Out of Scope

- Do not mass-refresh all legacy narratives.
- Do not refresh all 341 missing-timestamp narratives.
- Do not change `FRESH_START_CUTOFF`.
- Do not manually set `last_summary_generated_at`.
- Do not mutate data before explicit approval.
- Do not run production briefing generation in this ticket.
- Do not run scheduled or manual narrative refresh blindly.
- Do not change clustering/matching behavior.
- Do not modify frontend or backend code unless a separate bug is identified and approved.

---

## Safety Rules

Until explicit approval is given:

```text
READ-ONLY ONLY
```

Forbidden without approval:

```text
updateOne
updateMany
deleteOne
deleteMany
insertOne
insertMany
bulkWrite
findOneAndUpdate
aggregate pipelines with $out or $merge
manual timestamp edits
manual production briefing generation
manual mass narrative refresh
```

If a mutation appears necessary, stop and report the proposed action, scope, expected writes, and rollback plan.

---

## Current UI Narratives to Investigate

Use the public Active Narratives page/API ordering as the source of truth. The observed UI included the following narratives:

```text
Senate Banking Committee Advances Crypto Regulation Efforts
LayerZero Admits Mistakes in $292M Kelp DAO Exploit
Bitcoin Holds $75K Amid Geopolitical Tensions and Strong ETF Inflows
SEC Signals New Regulatory Framework for Onchain Markets
Coinbase Navigates Infrastructure Crisis Amid Market Recovery
Solv Protocol Migrates $700M Bitcoin Assets From LayerZero to Chainlink
TrustedVolumes Suffers $6.7M Exploit Amid Scope Disputes
Aave Fights Court Freeze of $71M Kelp DAO Recovery
Morgan Stanley Launches Crypto Trading on E*Trade Platform
Kraken Expands Regulated Trading and Global Cash Access
Haun Ventures Closes $1 Billion Fund for Crypto and AI
Drift Launches Token Recovery Plan After $295M Hack
Strategy Pauses Bitcoin Purchases Ahead of Q1 Earnings
Hut 8 Pivots to AI, Secures $9.8B Data Center Deal
Ripple Shares North Korean Threat Intelligence With Crypto Industry
DTCC Launches Tokenized Securities Pilot With 50+ Firms
World Liberty Financial and Justin Sun in Escalating Legal Battle
Binance Launches Withdrawal Protection Against Rising Wrench Attacks
FINRA Approves Securitize for Tokenized Securities Operations
GameStop Bids $55.5B for eBay Using Bitcoin Treasury
```

Do not assume this list is still current. Query the public API/page first and use the live top items.

---

## Implementation Plan

## Phase 1: Read-Only Discovery

### 1. Identify Current Top UI Narratives

Use the same endpoint/query the public Active Narratives page uses.

For the top 10 current UI narratives, report:

```text
_id
title
lifecycle_state
first_seen
last_updated
last_summary_generated_at
_fresh_start_validated_at
article_count
needs_summary_update
entities
theme
current trust status under FEATURE-060
whether it appears in public API
```

### 2. Verify Trust Status

For each top UI narrative, compute:

```text
trusted = (
  first_seen >= 2026-05-10T00:00:00Z
  OR last_summary_generated_at >= 2026-05-10T00:00:00Z
  OR _fresh_start_validated_at >= 2026-05-10T00:00:00Z
)
```

Expected before refresh:

```text
Most or all current UI narratives are untrusted.
```

### 3. Verify API Display Mode Behavior

Call the public narratives API and inspect those same narratives.

Report:

```text
display_mode
display_title
display_summary
recent_article_count
legacy title
legacy summary/story if present
```

Questions to answer:

```text
If a narrative is untrusted, does API return display_mode="article_cluster"?
If API returns article_cluster, is frontend consuming display_title/display_summary?
If UI still shows old generated title/summary, why?
```

Possible causes:

```text
backend display_mode is wrong
frontend build is not deployed
frontend ignores display fields
API response is cached
browser/CDN is serving old UI bundle
narrative is actually trusted for a reason missed earlier
```

### 4. Identify Safe Refresh Mechanism

Locate existing refresh code paths. Inspect only.

Look for:

```text
refresh_flagged_narratives
narrative_refresh.py
Celery task names
manual CLI/task invocation paths
functions that refresh a specific narrative ID
```

Report:

```text
function/task name
whether it accepts specific narrative IDs
whether it only processes needs_summary_update=true
whether it updates title
whether it updates summary
whether it sets last_summary_generated_at
whether it sets needs_summary_update=false
whether it calls LLM operation narrative_generate
whether it skips dormant narratives
estimated cost per narrative
expected writes per narrative
```

If no safe specific-ID refresh path exists, stop and propose options. Do not improvise a production mutation.

---

## Phase 2: Proposed Bounded Refresh Plan

After discovery, propose one of these plans.

### Preferred Plan: Top 5 UI Narratives

Refresh only the top 5 current public UI narratives.

Selection criteria:

```text
currently visible on public Active Narratives page
active lifecycle state
recent last_updated
article_count > 0
untrusted under FEATURE-060
not dormant
```

Expected cost:

```text
5 × estimated per-narrative refresh cost
```

Expected writes:

```text
title updated if generated title changes
summary updated
last_summary_generated_at set to now
needs_summary_update set false if successful
possibly metadata fields updated by existing refresh path
```

### Alternate Plan: Top 10 UI Narratives

Use only if top 5 is insufficient for briefing quality.

### Stop Conditions

Stop before refresh if:

```text
refresh path cannot target specific IDs
refresh path would process all legacy narratives
refresh path would process more than configured batch limit
refresh path only refreshes dormant narratives
estimated cost is abnormal
code path does not set last_summary_generated_at
code path bypasses existing summary generation safety
```

---

## Phase 3: Approval Gate

Do not run refresh until the operator explicitly approves.

Approval prompt should include:

```text
Narrative IDs to refresh
Titles to refresh
Expected writes
Expected cost
Command/task to run
Whether refresh is production-safe
How success will be verified
Rollback considerations
```

---

## Phase 4: Execute Bounded Refresh After Approval

If approved, run only the approved bounded refresh.

Rules:

```text
refresh only approved narrative IDs
do not refresh all legacy narratives
do not run briefing generation
do not manually set last_summary_generated_at
use existing narrative summary generation path
do not change MAX_REFRESH_PER_RUN
stop on unexpected errors or abnormal cost
```

---

## Phase 5: Post-Refresh Verification

After refresh, run read-only verification.

### 1. Refreshed Narratives

For each refreshed narrative, report:

```text
_id
old title
new title
new summary first 300 chars
last_summary_generated_at
needs_summary_update
article_count
lifecycle_state
```

### 2. Trusted Narrative Count

Run FEATURE-060 trusted count:

```text
first_seen >= cutoff
OR last_summary_generated_at >= cutoff
OR _fresh_start_validated_at >= cutoff
```

Expected:

```text
trusted_narratives >= number of refreshed active narratives
```

### 3. LLM Cost

Report:

```text
narrative_generate traces during refresh window
cost per narrative
total cost
errors, if any
```

### 4. Public API Display Mode

For refreshed narratives, verify:

```text
display_mode="summary"
display_title uses refreshed generated title
display_summary uses refreshed generated summary
recent_article_count present
```

For unrefreshed untrusted narratives, verify:

```text
display_mode="article_cluster"
display_title/display_summary do not expose stale generated summary as authoritative
```

---

## Phase 6: Briefing Readiness Decision

Use this decision rule:

```text
trusted_narratives = 0
→ Do not run briefing.

trusted_narratives = 1-4
→ Smoke briefing only. Expect thin output.

trusted_narratives >= 5
→ Run smoke briefing. If smoke passes, allow scheduled production briefing.

trusted_narratives >= 10
→ Better briefing readiness. Smoke still recommended before production.
```

Smoke briefing acceptance:

```text
published=false or is_smoke=true
confidence_score >= 0.5
key_insights count > 0
narrative length reasonable
no meta-output phrases
trusted_narratives_selected > 0
untrusted_narratives_excluded logged
LLM cost normal
```

---

## Acceptance Criteria

- [ ] Current top UI narratives are identified from live public API/page.
- [ ] Trust status is reported for top UI narratives.
- [ ] API display-mode behavior is verified for top UI narratives.
- [ ] Any mismatch between API display fields and UI rendering is explained.
- [ ] Safe refresh mechanism is identified and documented.
- [ ] Refresh plan targets only top 5 or explicitly approved top 10 UI narratives.
- [ ] No mass refresh is run.
- [ ] No production briefing generation is run in this ticket.
- [ ] No data mutation occurs before explicit approval.
- [ ] After approved refresh, refreshed narratives have `last_summary_generated_at >= 2026-05-10T00:00:00Z`.
- [ ] Trusted narrative count increases above 0.
- [ ] LLM cost is reported.
- [ ] Recommendation is given for smoke briefing readiness.

---

## Verification Commands / Query Patterns

Use the db-query skill where possible.

### Count trusted narratives

```bash
poetry run python3 scripts/db_query.py count narratives '{
  "$or": [
    {"first_seen": {"$gte": {"$date": "2026-05-10T00:00:00Z"}}},
    {"last_summary_generated_at": {"$gte": {"$date": "2026-05-10T00:00:00Z"}}},
    {"_fresh_start_validated_at": {"$gte": {"$date": "2026-05-10T00:00:00Z"}}}
  ]
}'
```

If the helper does not support extended JSON dates, use a small Python read-only script or the existing db-query skill date examples.

### Find recently active narratives

```bash
poetry run python3 scripts/db_query.py find narratives '{
  "lifecycle_state": {"$in": ["hot", "emerging", "rising", "reactivated"]}
}' '{
  "_id": 1,
  "title": 1,
  "lifecycle_state": 1,
  "first_seen": 1,
  "last_updated": 1,
  "last_summary_generated_at": 1,
  "article_count": 1,
  "needs_summary_update": 1
}' 10
```

### Narrative generate cost during refresh window

```bash
poetry run python3 scripts/db_query.py find llm_traces '{
  "operation": "narrative_generate"
}' '{
  "timestamp": 1,
  "operation": 1,
  "cost": 1,
  "model": 1,
  "error": 1
}' 50
```

---

## Risks

### Risk: Refresh path cannot target specific narratives

Mitigation:

```text
Stop. Do not run mass refresh. Create a separate ticket for specific-ID refresh support.
```

### Risk: UI still shows stale summary despite API display_mode="article_cluster"

Mitigation:

```text
Treat as frontend deployment/cache bug. Do not solve by refreshing everything.
```

### Risk: Refreshed summaries are low quality

Mitigation:

```text
Use smoke briefing and manual inspection before production briefing.
```

### Risk: LLM cost spikes

Mitigation:

```text
Limit to top 5 first. Stop on abnormal trace cost.
```

---

## Completion Summary

**Status:** 🔴 IN PROGRESS - Celery Execution Issue Detected

### Phase 0-2: COMPLETE ✅
- Current UI narratives inspected: 10 top active narratives queried
- Display-mode findings: All fields missing (display_mode, display_title, display_summary not set in DB)
- Refresh mechanism identified: `refresh_flagged_narratives` in `src/crypto_news_aggregator/tasks/narrative_refresh.py`
- Approved refresh scope: Top 5 narratives only

### Phase 4A: COMPLETE ✅
- 5 narratives manually flagged via mongosh updateMany
- All 5 had `needs_summary_update` set to `true`
- Verified via read-only query

### Phase 4B: ❌ PARTIAL FAILURE
- Celery task triggered: Task ID `9e93ad11-a4ff-4145-af78-e5567f5b8181`
- Task queued successfully BUT never executed
- **Root cause:** Celery worker not running in Railway environment
- **Evidence:** Zero `narrative_generate` LLM traces recorded
- **Result:** 3 of 5 narratives had flags cleared (but no timestamps set), 2 still flagged
- **Narratives refreshed:** 0/5 (no LLM calls made)
- **Trusted narrative count before:** 0
- **Trusted narrative count after:** 0 (unchanged - FAILURE)
- **LLM cost:** $0.00 (no execution)
- **Deviations from plan:** Celery worker unavailable in deployed environment

### Next Steps for New Session
1. Investigate Celery worker status in Railway deployment
2. Either: (A) Start worker manually, (B) Run refresh_flagged_narratives directly via Python sync execution, or (C) Check Railway configuration
3. Resume Phase 4B with guaranteed execution path
4. Complete Phase 5 verification
5. Proceed to smoke briefing if refresh succeeds
