---
date: 2026-06-20
task: TASK-114C
phase: Phase A Exit Gate — Tier 1 Historical Reconstruction
status: Phase 1 Complete — Reconstructed Cases Ready for Evidence Collection
---

# TASK-114C: Historical Reconstruction — Status Report

## Phase 1: Historical Case Reconstruction ✅ COMPLETE

Three documented incidents have been reconstructed as synthetic BugCases in the `bugops_gate_review` database. Each reconstruction clearly separates:
- **Documented historical facts**: from incident tickets, timelines, root cause analysis
- **Synthetic support data**: realistic but explicitly labeled (LLM traces, related cases, config)
- **What will be validated**: collector behavior when processing reconstructed incident data
- **What cannot be validated**: portions of production that were never captured (e.g., LLM output vs input comparison)

---

## Reconstruction Details

### BUG-064: Cost Control Failure / Briefing Generation Halt

**Classification:** Cost control / infrastructure failure (soft limit breach)

**Documented Historical Facts:**
- Failure start: 2026-04-13 00:00:10 UTC
- Failure duration: 70+ minutes (through 01:10 UTC)
- Soft limit: $0.25/day
- Actual spend at soft limit trigger: $0.2954
- Blocked operation: `briefing_generate`
- Root subsystem: briefing_generation (Celery worker)
- 4 retry cycles observed within window
- Healthy signals documented: MongoDB (12ms), Redis (4ms), FastAPI ok, workers active, no recent deployments

**Synthetic Support Data (Reconstructed):**
- **LLM Traces:** 4 failed `briefing_generate` operations (timestamps: 00:00:10, 00:05:10, 00:10:10, 00:15:10)
  - Cost progression: $0.0625 → $0.1163 → $0.1701 → $0.2239 (totals $0.2954)
  - Rationale: Realistic cost curve for 4 retries within soft limit window
- **Related Cases:** BUG-057-SYNTHETIC (prior briefing timeout on 2026-04-10)
  - Rationale: Tests related-case collector's subsystem correlation detection

**Ground Truth Reference:** 
- `docs/tickets/done/bug-064-memory-leak-retry-storm-soft-limit.md`
- `docs/sprints/sprint-021/golden-investigation-bug-064.md`

**What Will Be Validated:**
- ✅ Metrics collector detects cost totals and operation counts
- ✅ LLM trace collector aggregates costs, operations, and recent traces
- ✅ System state collector identifies healthy signals
- ✅ Related case collector surfaces prior briefing incidents

**What Cannot Be Validated From Reconstruction:**
- ❌ Raw Railway logs (log collector will not find production logs in gate review database)
- ❌ Actual Motor client recreation behavior (would require live Celery task retry)
- ❌ Memory heap statistics (requires live process inspection)

---

### BUG-073: Articles Missing Fingerprints / Deduplication Broken

**Classification:** Code path regression / RSS ingestion failure

**Documented Historical Facts:**
- First observed: 2026-04-14 02:00:00 UTC
- Impact: 100% of April 14 inserts had `fingerprint: null`
- Root subsystem: articles/ingestion (RSS pipeline)
- Root cause: Direct MongoDB insert_one() bypassed ArticleService.create_article()
- Related incidents explicitly documented: BUG-070, BUG-071, BUG-072
  - These three fixes were noted as ineffective without working fingerprints

**Synthetic Support Data (Reconstructed):**
- **Related Cases:** BUG-070-SYNTHETIC, BUG-071-SYNTHETIC, BUG-072-SYNTHETIC
  - BUG-070: Tier-1 filtering regression (2026-04-08)
  - BUG-071: Compressed system prompt issue (2026-04-09)
  - BUG-072: LLM cache wiring broken (2026-04-09)
  - Rationale: Tests related-case collector's multi-incident pattern detection

**Ground Truth Reference:**
- `docs/tickets/done/bug-073-articles-missing-fingerprints.md`

**What Will Be Validated:**
- ✅ Related case collector detects subsystem overlap across BUG-070/071/072
- ✅ Metrics collector reports article ingestion health
- ✅ System state collector identifies healthy other subsystems

**What Cannot Be Validated From Reconstruction:**
- ❌ Deploy context (Railway API deployment history for code change) — would require Railway credentials/access
- ❌ Actual fingerprint null count in articles (would require production article collection)
- ❌ Code diff analysis (Evidence Pack does not include git diffs)
- ❌ Deduplication impact metrics (would require article duplicate detection queries)

---

### BUG-084: Narrative Summary Fabrication

**Classification:** LLM output quality / content correctness issue

**Documented Historical Facts:**
- Incident timestamp: 2026-04-15 04:00:00 UTC (approx)
- Root subsystem: narrative_generation
- **Root cause 1:** Prompt encouraged synthesis into "cohesive narrative" even when articles share only entity, not story
- **Root cause 2:** Article text truncated to 300 characters (insufficient grounding)
- **Root cause 3:** Model choice: Sonnet (claude-sonnet-4-5-20250929) instead of standardized Haiku
- **Manifestation:** Narrative title "Kraken Faces Extortion Over Stolen Internal Data" (fabricated)
- **Source articles reality:** 3 articles about Kraken IPO filing, zero mention of extortion/breach

**Synthetic Support Data (Reconstructed):**
- **LLM Trace:** One narrative_generate operation
  - Model: Sonnet (contradicts standardization)
  - Cost: $0.0156
  - Rationale: Realistic cost for narrative operation with Sonnet model
- **Config Evidence:** (Synthetic but realistic)
  - ARTICLE_SUMMARY_TRUNCATE_CHARS: 300
  - NARRATIVE_GENERATION_MODEL: claude-sonnet-4-5-20250929

**Ground Truth Reference:**
- `docs/tickets/done/bug-084-narrative-summary-fabricated-events.md`

**⚠️ KNOWN LIMITATION (from TASK-114C spec lines 65-70):**

Evidence Pack **CANNOT** capture the root issue: "LLM output contradicts input."

The Evidence Pack sections include:
- Config evidence (model choice, truncation limit) ✅
- LLM traces (model, cost, operation) ✅
- System state (narrative service health) ✅

The Evidence Pack does **NOT** include:
- ❌ Narrative text itself (content)
- ❌ Source article text (grounding)
- ❌ Comparison of narrative vs sources (semantic analysis)

**Therefore:** Blind diagnosis for BUG-084 will likely be PARTIAL (identifies wrong model and insufficient grounding) or MISS (cannot identify fabrication without semantic analysis).

**This is a valid and valuable finding** about Evidence Pack coverage. It identifies a genuine gap: Evidence Pack is designed for infrastructure/system diagnostics, not content quality assurance. A PARTIAL or MISS score is the correct and useful outcome.

**What Will Be Validated:**
- ✅ Config evidence collector detects model choice and truncation limits
- ✅ LLM trace collector captures operation, cost, model
- ✅ System state collector reports narrative service health

**What Cannot Be Validated From Reconstruction:**
- ❌ Whether LLM output contradicts input (no semantic analysis in Evidence Pack)
- ❌ Narrative content correctness (out of scope)
- ❌ Source article comparison (out of scope)

---

## Database State

**Location:** `mongodb://localhost:27017/bugops_gate_review`

**Collections:**
- **bug_cases**: 7 documents
  - 3 reconstructed incidents (BUG-064, BUG-073, BUG-084)
  - 4 synthetic related cases (BUG-057, BUG-070, BUG-071, BUG-072)
- **llm_traces**: 5 documents
  - 4 traces for BUG-064 retries
  - 1 trace for BUG-084 narrative operation

**Database is isolated:** No production data, separate database name, safe for destructive testing.

---

## Phase 2: Evidence Collection (Next)

**Status:** Ready to proceed

**Process:**
1. For each reconstructed case, run real `EvidenceCollector.collect(bugcase)`
2. EvidenceCollector will:
   - Create EvidencePack in bugops_gate_review.evidence_packs
   - Register all 7 collectors (metrics, system_state, related_cases, deploy_context, config, llm_traces, logs)
   - Each collector runs independently; failures don't halt others
   - Pack marked COMPLETE or PARTIAL based on sections_missing
3. Capture each Evidence Pack as JSON for blind diagnosis

**Expected Outcomes:**
- **BUG-064:** COMPLETE Evidence Pack (all collectors should succeed)
- **BUG-073:** PARTIAL Evidence Pack (deploy_context and log collectors may not find Railway data in gate review)
- **BUG-084:** COMPLETE Evidence Pack (collectors work, but Evidence Pack lacks fabrication detection)

---

## Phase 3: Blind Diagnosis (After Collection)

**Process:**
1. For each Evidence Pack, write blind diagnosis (BEFORE reading ground truth)
2. Diagnosis answer: "Based solely on this Evidence Pack, what happened and why?"
3. Timestamp each diagnosis
4. Then compare against documented ground truth
5. Score: MATCH / PARTIAL / MISS

---

## Next Steps

1. **Evidence Collection:** Run EvidenceCollector on each reconstructed case
   - Output: 3 Evidence Packs stored in bugops_gate_review.evidence_packs
2. **Blind Diagnosis:** Write 3 diagnoses (one per pack) timestamped before comparison
3. **Scoring:** Compare diagnoses vs ground truth
4. **Report:** Single markdown file `TASK-114C-REPLAY-RESULTS.md` with:
   - Reconstruction summaries (fact/synthetic breakdown)
   - Evidence Packs metadata
   - Blind diagnoses (timestamped)
   - Ground truth comparison
   - Scores (MATCH/PARTIAL/MISS)
   - Exit gate criteria audit

---

## Reconstruction Harness

**Script:** `scripts/gate-review-reconstruction-simple.py`

- Pure Python, no Docker
- Creates documented BugCases + synthetic support data
- Prints fact/synthetic breakdown for review
- Persists to local MongoDB gate review database
- Can be re-run (clears and rebuilds database)

**Run:**
```bash
poetry run python scripts/gate-review-reconstruction-simple.py
```

---

## Files Modified/Created

- ✅ `scripts/gate-review-reconstruction-simple.py` — Reconstruction harness
- ✅ `docs/sprints/sprint-021/TASK-114C-EXECUTION-PLAN.md` — Original plan (superseded by this report)
- ✅ `docs/sprints/sprint-021/TASK-114C-RECONSTRUCTION-STATUS.md` — This status report (new)

---

## Exit Gate Criteria Status

| Criteria | Status | Notes |
|----------|--------|-------|
| 3 BugCases reconstructed | ✅ Complete | BUG-064, BUG-073, BUG-084 |
| Reconstructed BugCases persisted | ✅ Complete | bugops_gate_review database |
| Documented facts separated from synthetic | ✅ Complete | Clearly labeled in output |
| Collector validation plan documented | ✅ Complete | See "What Will Be Validated" sections |
| Evidence Collection ready to proceed | ✅ Ready | All reconstructed cases in database |
| BUG-084 limitation documented | ✅ Complete | Known gap: no semantic analysis in Evidence Pack |

---

## Key Decision Points

**Terminology:** This is **documented historical reconstruction**, not "full replay"
- Source data: documented facts + synthetic support
- Not dependent on production logs/metrics
- Validates collector behavior on reconstructed incident data
- Clear labeling of what's fact vs synthetic

**BUG-084 Handling:** No forced pass
- PARTIAL or MISS is acceptable and valuable
- Identifies genuine Evidence Pack coverage gap
- Invalid to fabricate signal that doesn't exist in Evidence Pack

**Database Isolation:** Complete separation from production
- Gate review database: bugops_gate_review
- Production database: crypto_news (untouched)
- Safe for destructive testing, full teardown after gate

