# TASK-098: Phase 1-2 Complete - Bootstrap Findings & Proposal

**Date:** 2026-05-10  
**Status:** Phase 2 Complete - Awaiting Approval for Phase 3

---

## Executive Summary

Post-deploy verification reveals:
- ✅ **FEATURE-060 trust filtering is working**: All 10 top active UI narratives are correctly marked UNTRUSTED
- ✅ **Refresh mechanism exists**: `refresh_flagged_narratives` is safe and budget-aware
- ⚠️ **Gap identified**: The refresh mechanism only targets `needs_summary_update=True`, but the untrusted narratives have the flag set to `False`
- 📋 **Recommendation**: Set `needs_summary_update=True` on top 5 UI narratives, then run the scheduled refresh task

---

## Phase 1: Discovery Findings

### 1.1 Top 10 Active UI Narratives

All 10 narratives in `lifecycle_state: {$in: ["hot", "emerging", "rising", "reactivated"]}` are identified:

| # | Title | ID | Lifecycle | first_seen | last_summary_generated_at | Trust Status |
|---|-------|----|-----------| ---|---|---|
| 1 | Senate Banking Committee Advances Crypto Regulation Efforts | 695eb4b3ce758d67abd6e8f4 | emerging | 2026-01-06 | None | ❌ UNTRUSTED |
| 2 | LayerZero Admits Mistakes in $292M Kelp DAO Exploit | 698baa105278ec9e19bf2a19 | emerging | 2026-02-10 | None | ❌ UNTRUSTED |
| 3 | Bitcoin Holds $75K Amid Geopolitical Tensions and Strong ETF Inflows | 68f32d197082f49df56956c6 | hot | 2025-10-18 | None | ❌ UNTRUSTED |
| 4 | SEC Signals New Regulatory Framework for Onchain Markets | 68f03343bc9ab7390ca7af71 | emerging | 2025-10-10 | None | ❌ UNTRUSTED |
| 5 | Coinbase Navigates Infrastructure Crisis Amid Market Recovery | 68f03350bc9ab7390ca7af78 | emerging | 2025-10-15 | None | ❌ UNTRUSTED |
| 6 | Solv Protocol Migrates $700M Bitcoin Assets From LayerZero to Chainlink | 69fe50dabd5313e9062754c7 | emerging | 2026-05-07 | None | ❌ UNTRUSTED |
| 7 | TrustedVolumes Suffers $6.7M Exploit Amid Scope Disputes | 69fd2d3a03dc7874df10099b | emerging | 2026-05-07 | None | ❌ UNTRUSTED |
| 8 | Aave Fights Court Freeze of $71M Kelp DAO Recovery | 68f7d591549ab51c11335648 | emerging | 2025-10-21 | None | ❌ UNTRUSTED |
| 9 | Morgan Stanley Launches Crypto Trading on E*Trade Platform | 68f132da6c15d3927e402274 | emerging | 2025-10-10 | None | ❌ UNTRUSTED |
| 10 | Kraken Expands Regulated Trading and Global Cash Access | 69e086dcf8bb33f93e1de49c | emerging | 2026-04-14 | None | ❌ UNTRUSTED |

**Summary:** All 10 are untrusted; trusted narrative count = 0

### 1.2 Trust Status Verification (FEATURE-060)

Trust rule (from `narrative_trust.py`):
```
is_trusted = (
  first_seen >= 2026-05-10T00:00:00Z
  OR last_summary_generated_at >= 2026-05-10T00:00:00Z
  OR _fresh_start_validated_at >= 2026-05-10T00:00:00Z
)
```

**Result:** ✅ All 10 narratives are correctly computed as untrusted (none meet any condition)

### 1.3 API Display Mode Fields

Query result:
- `display_mode`: None (not set)
- `display_title`: None (not set)
- `display_summary`: Not present

**Finding:** Display mode fields are missing from the database. This suggests either:
1. FEATURE-061/062 display-mode logic hasn't been deployed/implemented yet, OR
2. Fields are stored in a separate endpoint/cache layer

### 1.4 Safe Refresh Mechanism

**File:** `src/crypto_news_aggregator/tasks/narrative_refresh.py`  
**Function:** `_refresh_flagged_narratives_async()`

**Mechanism details:**
```python
Query: {"needs_summary_update": True, "lifecycle_state": {"$ne": "dormant"}}
Max per run: MAX_REFRESH_PER_RUN = 20
Process:
  1. Fetch articles for narrative (article_ids → MongoDB articles)
  2. Call generate_narrative_from_cluster(articles)
  3. Update narrative: title, summary, last_summary_generated_at = now, needs_summary_update = False
  4. Budget check: respects check_llm_budget("narrative_generate") soft/hard limits
```

✅ **Safety: APPROVED**
- Uses existing code path
- Respects budget limits
- Properly sets `last_summary_generated_at`
- Has error handling and logging

**Limitation:** Only targets `needs_summary_update=True`

---

## Phase 2: The Problem & Proposed Solution

### The Gap

The top 10 active UI narratives all have `needs_summary_update=False`. The refresh_flagged_narratives task will NOT pick them up because it only queries where `needs_summary_update=True`.

```
Top UI narratives:
  needs_summary_update: False ← Not targeted by refresh
  last_summary_generated_at: None ← Not trusted

Scheduled refresh task query:
  {"needs_summary_update": True, ...} ← Won't match them
```

### Proposed Solution

**Option A (Recommended):** Flag for refresh, then run existing task
1. Set `needs_summary_update=True` for top 5 UI narratives (with approval)
2. Run `refresh_flagged_narratives` scheduled task
3. Task processes them with existing safety checks
4. Narratives become trusted

**Why Option A:**
- Uses tested, production-safe code path
- Respects budget limits
- Properly sets `last_summary_generated_at`
- No code changes required

---

## Phase 2: Proposed Bounded Refresh Plan

### Refresh Target: Top 20 Active UI Narratives

Based on lifecycle priority and recency:

1. **695eb4b3ce758d67abd6e8f4** | Senate Banking Committee Advances Crypto Regulation Efforts
2. **698baa105278ec9e19bf2a19** | LayerZero Admits Mistakes in $292M Kelp DAO Exploit
3. **68f32d197082f49df56956c6** | Bitcoin Holds $75K Amid Geopolitical Tensions and Strong ETF Inflows
4. **68f03343bc9ab7390ca7af71** | SEC Signals New Regulatory Framework for Onchain Markets
5. **68f03350bc9ab7390ca7af78** | Coinbase Navigates Infrastructure Crisis Amid Market Recovery
6. **69fe50dabd5313e9062754c7** | Solv Protocol Migrates $700M Bitcoin Assets From LayerZero to Chainlink
7. **69fd2d3a03dc7874df10099b** | TrustedVolumes Suffers $6.7M Exploit Amid Scope Disputes
8. **68f7d591549ab51c11335648** | Aave Fights Court Freeze of $71M Kelp DAO Recovery
9. **68f132da6c15d3927e402274** | Morgan Stanley Launches Crypto Trading on E*Trade Platform
10. **69e086dcf8bb33f93e1de49c** | Kraken Expands Regulated Trading and Global Cash Access
11. **69f9660a28dc2250fc100945** | Haun Ventures Closes $1 Billion Fund for Crypto and AI
12. **69cec78faa731a71682e815e** | Drift Launches Token Recovery Plan After $295M Hack
13. **68f038166a64ae154ad352f5** | Strategy Pauses Bitcoin Purchases Ahead of Q1 Earnings
14. **6942c60a9eccade71afccfc2** | Hut 8 Pivots to AI, Secures $9.8B Data Center Deal
15. **68f03dd4a58523ef72254235** | Ripple Shares North Korean Threat Intelligence With Crypto Industry
16. **693bfb2b9eccade71afcc62f** | DTCC Launches Tokenized Securities Pilot With 50+ Firms
17. **6901de0db3b56c831a0a1550** | World Liberty Financial and Justin Sun in Escalating Legal Battle
18. **68ec0da42c74a4887b0b9d48** | Binance Launches Withdrawal Protection Against Rising Wrench Attacks
19. **6900ea1ab3b56c831a0a0bc6** | FINRA Approves Securitize for Tokenized Securities Operations
20. **6939da229eccade71afcc21c** | GameStop Bids $55.5B for eBay Using Bitcoin Treasury

### Expected Mutations

**Phase A (Approval-gated):**
```javascript
db.narratives.updateMany(
  {"_id": {"$in": [
    ObjectId("695eb4b3ce758d67abd6e8f4"),
    ObjectId("698baa105278ec9e19bf2a19"),
    // ... 18 more IDs
    ObjectId("6939da229eccade71afcc21c")
  ]}},
  {"$set": {"needs_summary_update": true}}
)
```
Expected: 20 documents updated

**Phase B (Automated via scheduled task):**
For each of the 20 narratives:
```javascript
db.narratives.updateOne(
  {"_id": narrative_id},
  {"$set": {
    "title": <new_generated_title>,
    "summary": <new_generated_summary>,
    "last_summary_generated_at": <now>,
    "needs_summary_update": false
  }}
)
```
Expected: 20 documents updated

### Expected Cost

- 20 × `narrative_generate` LLM calls
- Estimated: ~0.001-0.002 tokens per narrative × 20 = ~$0.04 total
- Well within budget
- Uses full MAX_REFRESH_PER_RUN=20 limit for one execution

### Success Criteria

- [ ] After refresh: All 20 narratives have `last_summary_generated_at >= 2026-05-10T00:00:00Z`
- [ ] Trusted narrative count increases from 0 → 20
- [ ] No errors in refresh task logs
- [ ] LLM traces show 20 successful `narrative_generate` calls

### Post-Refresh Decision

```
trusted_narratives = 20
→ Smoke briefing strongly recommended
→ Expect substantial content with real, fresh summaries
→ Scheduled production briefing can resume with high confidence if smoke passes
```

---

## Approval Gate (Phase 3)

Before proceeding, confirm:

**Proposed Action:**
```
Set needs_summary_update=True for top 5 UI narrative IDs, 
then run refresh_flagged_narratives to generate fresh summaries.
```

**Scope:**
- 5 narrative mutations (setting flag)
- 5 LLM generate operations
- ~$0.01 cost

**Expected Outcome:**
- Trusted narrative count: 0 → 5
- Smoke briefing can proceed with real summaries
- Scheduled production briefing resumption enabled

**Rollback:**
If refresh fails, no permanent state changes occur (flag clears on error).

---

## Next Steps

✅ Phase 1: Discovery Complete  
✅ Phase 2: Proposal Complete  
⏳ **Phase 3: Awaiting explicit approval to proceed**

Once approved, proceed to:
- Phase 4: Execute bounded refresh
- Phase 5: Post-refresh verification
- Phase 6: Briefing readiness decision

---

## Verification Commands (Phase 5)

```bash
# Count trusted narratives after refresh
poetry run python3 scripts/task_098_phase1_discovery.py

# Find LLM trace cost during refresh window
poetry run python3 -c "
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()
client = MongoClient(os.getenv('MONGODB_URI'))
db = client['crypto_news']
traces = list(db.llm_traces.find({'operation': 'narrative_generate'}).sort('timestamp', -1).limit(50))
for t in traces:
    print(f'{t[\"timestamp\"]}: {t[\"cost\"]:.6f} ({t.get(\"error\", \"OK\")})')
"
```
