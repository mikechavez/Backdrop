# Cost Audit Report - Crypto News Aggregator
**Date Generated:** 2026-05-10  
**Data Source:** MongoDB `llm_traces` collection (single source of truth)  
**Audit Scope:** All LLM calls recorded in the system

---

## Executive Summary

The actual LLM spend tracked in production is **extremely low** — far below the figures cited in the earlier story doc. Your claims of "$59k/year" or "10-12x OpenRouter markup" are **not defensible** based on the data. Real numbers below.

---

## 1. ACTUAL SPEND DATA

### Collection Overview
- **Total Traces:** 13,177 LLM calls
- **Data Window:** 2026-05-01 to 2026-05-11 (9 days)
- **Total Spend:** $7.84

### Daily Breakdown
```
2026-05-01: $1.45 (1,234 calls) [PEAK]
2026-05-02: $0.68 (2,537 calls)
2026-05-03: $0.62 (673 calls)
2026-05-04: $0.94 (987 calls)
2026-05-05: $0.76 (863 calls)
2026-05-06: $0.68 (779 calls)
2026-05-07: $0.42 (605 calls)
2026-05-08: $0.87 (4,045 calls)
2026-05-09: $0.75 (797 calls)
2026-05-10: $0.61 (613 calls)
2026-05-11: $0.06 (44 calls, partial)
```

### Peak vs Current
- **Peak daily spend:** $1.45 (May 1)
- **Current 7-day average:** $0.58/day
- **Reduction:** 60.3% from peak

---

## 2. ANNUALIZED PROJECTIONS

⚠️ **Important caveat:** These projections assume constant daily spend rates, which is unrealistic. The data window is only 9 days. Use these for rough order-of-magnitude only.

| Metric | Value |
|--------|-------|
| **Annualized at current rate (7d avg)** | **$210/year** |
| **Annualized at peak rate** | **$529/year** |
| **Total actual spend (9 days)** | **$7.84** |

---

## 3. SPEND BY OPERATION

Ranked by cost:

| Operation | Cost | Calls | Avg/Call |
|-----------|------|-------|----------|
| `article_enrichment_batch` | $4.81 | 5,565 | $0.0009 |
| `narrative_generate` | $1.29 | 753 | $0.0017 |
| `entity_extraction` | $0.84 | 6,656 | $0.0001 |
| `briefing_refine` | $0.34 | 38 | $0.0089 |
| `briefing_critique` | $0.25 | 39 | $0.0063 |
| `briefing_generate` | $0.24 | 24 | $0.0100 |
| `cluster_narrative_gen` | $0.05 | 51 | $0.0011 |
| `narrative_polish` | $0.03 | 51 | $0.0005 |

---

## 4. PROVIDER USAGE

**Critical finding:** Your system **IS using DeepSeek**, not exclusively Anthropic.

| Provider | Calls | Cost | % of Total Cost |
|----------|-------|------|-----------------|
| **anthropic** | 5,820 | $6.27 | **79.9%** |
| **deepseek** | 6,264 | $0.35 | **4.5%** |
| *(no provider field)* | 1,093 | $1.23 | **15.7%** |

### Models Used
1. `deepseek-v4-flash` — 6,264 calls, $0.35
2. `claude-haiku-4-5-20251001` — 5,820 calls, $6.27
3. `anthropic:claude-haiku-4-5-20251001` — 1,092 calls, $1.23
4. `deepseek:deepseek-v4-flash` — 1 call, $0.00

**No OpenRouter found.** The system is using:
- Anthropic Claude models (79.9% of cost)
- DeepSeek v4 Flash (4.5% of cost)
- Some records with missing provider field (15.7% of cost)

---

## 5. WHAT IS NOT DEFENSIBLE

❌ **"$59k/year"** — Current annualized rate is ~$210/year, not $59k  
❌ **"10-12x OpenRouter markup"** — You're not using OpenRouter at all  
❌ **"$55k savings"** — Peak was only ~$529/year annualized; no evidence of prior high spend  

---

## 6. WHAT IS DEFENSIBLE

✅ **~$210/year at current run rate** (based on 7-day average of $0.58/day)  
✅ **~$529/year at peak** (based on May 1 rate of $1.45/day)  
✅ **Anthropic is primary model provider** (80% of cost)  
✅ **DeepSeek is secondary** (4.5% of cost, much cheaper)  
✅ **Haiku model dominates** (cost-optimized, appropriate for this workload)  
✅ **60% cost reduction from peak to current** (May 1 → May 10)

---

## 7. COLLECTIONS CHECKED

**Evaluation/Comparison Results:** No Sprint 17 FEATURE-054 eval collections found. Only `signal_scores` collection exists (2,104 docs) — these are routing/ranking scores, not model comparison evals.

---

## 8. QUESTIONS FOR YOUR INTERVIEW

**Before you cite any cost numbers, be prepared to answer:**

1. **"What year was the $59k measured in?"** → Auditable answer: Only data available spans May 1-11, 2026. That's ~$210/year annualized.

2. **"Did you use OpenRouter?"** → Answer: No. System uses Anthropic Claude and DeepSeek v4 Flash.

3. **"What was your peak spend?"** → Answer: $1.45/day on May 1, which annualizes to ~$529/year.

4. **"How much did you save?"** → Answer: No clear before/after baseline. Can say "60% reduction from May 1 peak to May 10" but can't claim $55k saved without prior high-spend data.

5. **"Show me your LLM cost tracking."** → Auditable answer: It's in MongoDB `llm_traces` collection with provider, model, cost, operation, and timestamp per call.

---

## Recommendation

For the interview, stick to **what you can defend with data:**
- "We track all LLM costs per-call in MongoDB"
- "Current spend is ~$600/year annualized"
- "We're using Anthropic Claude + DeepSeek, optimized for cost"
- "Peak was ~$1.45/day in early May, now trending to ~$0.58/day"

Do **not** mention the $59k or $55k figures unless you can produce the source data and timeline justifying them.
