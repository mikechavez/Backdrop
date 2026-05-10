# TASK-098: Approval Request - Bounded UI Narrative Refresh (Top 20)

**Status:** ⏳ AWAITING APPROVAL FOR PHASE 4  
**Date:** 2026-05-10  
**Phase:** 3 (Approval Gate)

---

## Quick Summary

**What:** Refresh the 20 most active UI narratives by setting `needs_summary_update=True` and running the scheduled `refresh_flagged_narratives` task.

**Why:** All 20 are currently UNTRUSTED (no `last_summary_generated_at >= 2026-05-10`). After refresh, they become trusted and can be used for briefing synthesis.

**Cost:** ~$0.04 (20 × narrative_generate LLM calls)

**Risk:** Minimal. Uses existing production code path with budget safety checks.

---

## The 20 Narratives to Refresh

| # | Title | ID |
|---|-------|-----|
| 1 | Senate Banking Committee Advances Crypto Regulation Efforts | 695eb4b3ce758d67abd6e8f4 |
| 2 | LayerZero Admits Mistakes in $292M Kelp DAO Exploit | 698baa105278ec9e19bf2a19 |
| 3 | Bitcoin Holds $75K Amid Geopolitical Tensions and Strong ETF Inflows | 68f32d197082f49df56956c6 |
| 4 | SEC Signals New Regulatory Framework for Onchain Markets | 68f03343bc9ab7390ca7af71 |
| 5 | Coinbase Navigates Infrastructure Crisis Amid Market Recovery | 68f03350bc9ab7390ca7af78 |
| 6 | Solv Protocol Migrates $700M Bitcoin Assets From LayerZero to Chainlink | 69fe50dabd5313e9062754c7 |
| 7 | TrustedVolumes Suffers $6.7M Exploit Amid Scope Disputes | 69fd2d3a03dc7874df10099b |
| 8 | Aave Fights Court Freeze of $71M Kelp DAO Recovery | 68f7d591549ab51c11335648 |
| 9 | Morgan Stanley Launches Crypto Trading on E*Trade Platform | 68f132da6c15d3927e402274 |
| 10 | Kraken Expands Regulated Trading and Global Cash Access | 69e086dcf8bb33f93e1de49c |
| 11 | Haun Ventures Closes $1 Billion Fund for Crypto and AI | 69f9660a28dc2250fc100945 |
| 12 | Drift Launches Token Recovery Plan After $295M Hack | 69cec78faa731a71682e815e |
| 13 | Strategy Pauses Bitcoin Purchases Ahead of Q1 Earnings | 68f038166a64ae154ad352f5 |
| 14 | Hut 8 Pivots to AI, Secures $9.8B Data Center Deal | 6942c60a9eccade71afccfc2 |
| 15 | Ripple Shares North Korean Threat Intelligence With Crypto Industry | 68f03dd4a58523ef72254235 |
| 16 | DTCC Launches Tokenized Securities Pilot With 50+ Firms | 693bfb2b9eccade71afcc62f |
| 17 | World Liberty Financial and Justin Sun in Escalating Legal Battle | 6901de0db3b56c831a0a1550 |
| 18 | Binance Launches Withdrawal Protection Against Rising Wrench Attacks | 68ec0da42c74a4887b0b9d48 |
| 19 | FINRA Approves Securitize for Tokenized Securities Operations | 6900ea1ab3b56c831a0a0bc6 |
| 20 | GameStop Bids $55.5B for eBay Using Bitcoin Treasury | 6939da229eccade71afcc21c |

---

## What Happens on Approval

### Phase 4A: Flag Narratives
```javascript
db.narratives.updateMany(
  {"_id": {"$in": [ObjectId(...), ...]}},
  {"$set": {"needs_summary_update": true}}
)
```
Expected: 20 documents modified

### Phase 4B: Refresh Task Runs (Automated)
The scheduled `refresh_flagged_narratives` task will:
1. Fetch the 20 flagged narratives (sorted by lifecycle priority + recency)
2. For each: fetch articles, call LLM to generate fresh summary/title
3. Update: set `last_summary_generated_at = now`, clear `needs_summary_update` flag
4. Safety: respect `check_llm_budget` soft/hard limits

**Expected updates per narrative:**
```javascript
{
  "title": "<new generated title>",
  "summary": "<new generated summary>",
  "last_summary_generated_at": ISODate("2026-05-10T..."),
  "needs_summary_update": false
}
```

---

## Expected Outcome

**Before Refresh:**
```
Trusted narratives: 0
Display mode: article_cluster (untrusted, show article count only)
Briefing synthesis: No narratives available
```

**After Refresh:**
```
Trusted narratives: 20
Display mode: summary (trusted, show generated summaries)
Briefing synthesis: 20 trusted narratives available
```

---

## Cost & Budget

- **LLM cost:** 20 × narrative_generate ≈ $0.04
- **Budget limit:** $10/day (soft), $15/day (hard)
- **Current usage:** Not checked, but historical trend is $0.50-2.00/day
- **Impact:** Negligible

---

## Risk Assessment

### Safe Because:
- ✅ Uses existing production code path (`refresh_flagged_narratives`)
- ✅ Code is tested and deployed
- ✅ Respects budget safety checks (`check_llm_budget`)
- ✅ Bounded to 20 narratives (within MAX_REFRESH_PER_RUN=20)
- ✅ No manual timestamp edits (LLM code sets `last_summary_generated_at`)
- ✅ No mass mutations to legacy narratives (only these 20)

### Rollback Plan:
If refresh fails or produces poor quality:
1. Flag clears on error (narratives remain pre-refresh state)
2. No permanent data corruption
3. Can re-run if needed
4. Smoke briefing will reject low-confidence output

---

## Next Steps After Approval

### Phase 5: Post-Refresh Verification
```bash
poetry run python3 scripts/task_098_phase1_discovery.py
# Expected: All 20 narratives show last_summary_generated_at >= 2026-05-10T00:00:00Z
# Expected: Trusted narrative count = 20
```

### Phase 6: Briefing Readiness Decision
```text
trusted_narratives = 20
→ Smoke briefing STRONGLY RECOMMENDED
→ Expected: Substantial, meaningful content
→ Production briefing: Can resume if smoke passes
```

---

## Approval Checklist

**I confirm:**
- [ ] I approve setting `needs_summary_update=True` for these 20 narratives
- [ ] I approve running `refresh_flagged_narratives` task
- [ ] I understand cost is ~$0.04 (within budget)
- [ ] I understand this bounded refresh is production-safe

**If approved, next action:**
```bash
poetry run python3 scripts/task_098_phase4_execute_refresh.py
```

This script will:
1. Set flags for the 20 narratives
2. Monitor refresh progress
3. Report LLM cost
4. Verify successful refresh

---

## References

- **Findings:** `task-098-phase1-phase2-findings.md`
- **Refresh mechanism:** `src/crypto_news_aggregator/tasks/narrative_refresh.py`
- **Trust logic:** `src/crypto_news_aggregator/services/narrative_trust.py`
- **Approval request:** `scripts/task_098_approval_request_top20.py`
- **Execution script:** `scripts/task_098_phase4_execute_refresh.py`
