#!/usr/bin/env python3
"""
TASK-098 Phase 2: Proposed Bounded Refresh Plan

KEY FINDING: The existing refresh mechanism (refresh_flagged_narratives) only
processes narratives with needs_summary_update=True. However, the top 10 active
UI narratives ALL have needs_summary_update=False, so they won't be picked up
by the scheduled refresh task.

This phase proposes a solution.
"""

print("=" * 80)
print("TASK-098 PHASE 2: PROPOSED BOUNDED REFRESH PLAN")
print("=" * 80)

print("""
[PROBLEM SUMMARY]
---------
1. Top 10 active UI narratives are ALL untrusted (no last_summary_generated_at >= 2026-05-10)
2. Existing refresh_flagged_narratives only processes needs_summary_update=True
3. The top UI narratives have needs_summary_update=False
4. Therefore: scheduled refresh will NOT pick them up
5. We need a way to refresh specific narrative IDs directly

[EXISTING REFRESH MECHANISM ANALYSIS]
---------
File: src/crypto_news_aggregator/tasks/narrative_refresh.py

Function: _refresh_flagged_narratives_async()
- Query: {"needs_summary_update": True, "lifecycle_state": {"$ne": "dormant"}}
- Takes: Candidates sorted by lifecycle priority + last_updated
- Limit: MAX_REFRESH_PER_RUN = 20 per run
- Process:
  1. Fetch articles for narrative (article_ids → MongoDB articles)
  2. Call generate_narrative_from_cluster(articles)
  3. Update narrative with new title, summary, last_summary_generated_at
  4. Clear needs_summary_update flag
- Safety: Budget-aware via check_llm_budget("narrative_generate")

Limitation: Only targets needs_summary_update=True
  → Won't process our untrusted-but-not-flagged narratives

[PROPOSED SOLUTIONS]
---------

Option A: Set needs_summary_update=True, then run refresh_flagged_narratives
  Pros:
    - Uses existing code path (safe, tested)
    - Respects budget limits
    - Sets last_summary_generated_at correctly
  Cons:
    - Requires DB mutation before approval (violates ticket rules)

Option B: Create temp script that calls generate_narrative_from_cluster directly
  Pros:
    - No DB mutations until approval
    - Reuses existing narrative generation logic
    - Can target specific IDs
  Cons:
    - Bypasses budget tracking (needs to call check_llm_budget)
    - Not part of standard refresh pipeline
    - Requires Python script in repo

Option C: Create bounded refresh endpoint in backend
  Pros:
    - Proper API layer
    - Standard deployment
  Cons:
    - Requires backend code change
    - Out of scope for this ticket

[RECOMMENDATION: Option A]
---------
The safest path is to:

1. Request approval to set needs_summary_update=True for top 5 UI narratives
2. Run existing refresh_flagged_narratives task
3. This will:
   - Process them with budget checks
   - Generate fresh summaries
   - Set last_summary_generated_at = now
   - Clear the flag
4. Post-refresh, verify they become trusted

Bounded Refresh Plan - TOP 5 UI NARRATIVES
---------

Refresh candidates (sorted by last_updated):
1. 695eb4b3ce758d67abd6e8f4 | Senate Banking Committee Advances Crypto Regulation Efforts
2. 698baa105278ec9e19bf2a19 | LayerZero Admits Mistakes in $292M Kelp DAO Exploit
3. 68f32d197082f49df56956c6 | Bitcoin Holds $75K Amid Geopolitical Tensions and Strong ETF Inflows
4. 68f03343bc9ab7390ca7af71 | SEC Signals New Regulatory Framework for Onchain Markets
5. 68f03350bc9ab7390ca7af78 | Coinbase Navigates Infrastructure Crisis Amid Market Recovery

Expected mutations:
  - 5 × narratives.updateOne(needs_summary_update: True)
  - Then: 5 × refresh_flagged_narratives runs generate_narrative_from_cluster
  - 5 × narratives.updateOne(title, summary, last_summary_generated_at, needs_summary_update: False)

Expected cost:
  - ~5 × narrative_generate LLM calls (0.002 each est. ~$0.01 total)

Success criteria:
  - After refresh: all 5 have last_summary_generated_at >= 2026-05-10T00:00:00Z
  - Trusted narrative count increases from 0 → 5
  - Smoke briefing can proceed with real trusted summaries

Next steps:
  - Waiting for explicit approval to proceed to Phase 3 (approval gate)
""")

print("=" * 80)
print("PHASE 2 PROPOSAL COMPLETE - AWAITING APPROVAL")
print("=" * 80)
