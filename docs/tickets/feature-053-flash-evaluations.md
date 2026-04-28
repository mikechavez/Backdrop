---
id: FEATURE-053
type: feature
status: in-progress
priority: critical
complexity: high
created: 2026-04-27
updated: 2026-04-28
sprint: 16
---

# FEATURE-053: Flash Evaluations — Tier 1 Testing Against Golden Set

## Status

**Phase 2 & 3 COMPLETE (2026-04-28):** Baseline extraction (300 Haiku samples) and challenger model runs (900 API calls, 99.8% success rate) finished via OpenRouter. Phase 4 (normalization) and Phase 5-6 (scoring + decision records) deferred to future sessions.

---

## What Claude Code Must and Must Not Do

**Must:**
- Load golden set from the files specified below
- Strip HTML from input text before any model call
- Use production prompts from the exact file paths specified below — do not rewrite or paraphrase them
- Apply the scoring logic defined in EVAL-001-evaluation-contract.md exactly
- Apply the output normalization layer before scoring (see below)
- Produce comparison tables and MSD files in the format specified
- Use OpenRouter for all model calls
- Use only the locked model variants listed below

**Must not:**
- Choose, change, or substitute model variants
- Modify prompts in any way
- Interpret or adjust scoring rules
- Change matching logic
- Hardcode file paths — accept golden set path as a parameter
- Make any assumptions not covered by this ticket or the eval contract

---

## Evaluation Contract

All scoring logic, thresholds, and failure taxonomies are locked in:

```
docs/decisions/EVAL-001-evaluation-contract.md
```

**Read this document before writing any Phase 4 scoring code.** The Phase 4 section in this ticket is a summary only. The contract is authoritative. Do not deviate from it.

---

## Infrastructure — OpenRouter

All model calls go through OpenRouter. Do not use direct provider SDKs.

**Why:** Single HTTP client, OpenAI-compatible request format, model swapping via model string only. Eliminates per-provider SDK complexity.

**Base URL:** `https://openrouter.ai/api/v1`

**Auth:** `Authorization: Bearer ${process.env.OPENROUTER_API_KEY}`

**Key loading:**
```bash
source /Users/mc/dev-projects/crypto-news-aggregator/scripts/load_keys.sh
```

**Environment variable:** `process.env.OPENROUTER_API_KEY`

**Run command:**
```bash
source /Users/mc/dev-projects/crypto-news-aggregator/scripts/load_keys.sh && npx tsx <entry_file>.ts
```

---

## Locked Model Variants

These are fixed. Claude Code does not choose, substitute, or update these strings.

| Role | Model String |
|---|---|
| Baseline (Haiku) | `anthropic/claude-haiku-4-5-20251001` |
| Primary target | `google/gemini-2.5-flash` |
| Challenger A | `deepseek/deepseek-chat` |
| Challenger B | `qwen/qwen-plus` |

All four run against the same golden set. Haiku baseline is extracted from golden set fields (not re-called via API) — see Phase 2.

---

## Production Prompt Locations

Claude Code must extract and reuse these prompts exactly. Do not rewrite, summarize, or paraphrase them.

| Operation | File | Entry Point |
|---|---|---|
| entity_extraction | `./src/crypto_news_aggregator/llm/optimized_anthropic.py` | `_build_entity_extraction_prompt()` — line 127 |
| sentiment_analysis | `./src/crypto_news_aggregator/llm/anthropic.py` | prompt passed to `_get_completion()` — line 127 |
| theme_extraction | `./src/crypto_news_aggregator/llm/anthropic.py` | prompt passed to `_get_completion()` — line 146 |

If a prompt references article fields beyond `text` (e.g. `title`, `source`), include those fields from the golden set document. Do not strip context the production prompt expects.

---

## Golden Set — Source and Files

**Source collection:** `db.articles` (not `briefing_drafts` — original ticket was incorrect)

**Pre-extracted files:**
```
/Users/mc/entity_extraction_golden.json
/Users/mc/sentiment_analysis_golden.json
/Users/mc/theme_extraction_golden.json
```

Format: JSONL — one MongoDB article document per line.

**Field mapping:**

| Operation | Input Field | Haiku Output Field |
|---|---|---|
| entity_extraction | `text` | `entities` (array of objects) |
| sentiment_analysis | `text` | `sentiment.label` (string: positive/negative/neutral) |
| theme_extraction | `text` | `themes` (array of strings) |

**Entity object schema:**
```json
{
  "name": "Bitcoin",
  "type": "cryptocurrency",
  "ticker": null,
  "confidence": 0.95,
  "is_primary": true
}
```

**Sentiment object schema:**
```json
{
  "score": 0.7,
  "magnitude": 0.7,
  "label": "positive",
  "provider": "claude-haiku-4-5-20251001",
  "updated_at": "2026-04-14T05:35:06.307Z"
}
```

**Golden set stats:**

| Operation | Samples | Avg Text Length | Notes |
|---|---|---|---|
| entity_extraction | 100 | 432 chars | 39 short (<200 chars), 31 multi-entity (>3) |
| sentiment_analysis | 100 | 435 chars | 50 positive / 26 negative / 24 neutral |
| theme_extraction | 100 | 435 chars | avg 5.4 themes per article |

---

## Manual Validation Findings

Completed before implementation. Must be cited in each MSD file under "Manual Validation Caveat."

| Operation | Agreement | Status |
|---|---|---|
| entity_extraction | 30% | 🔴 Red flag — proceed with caveat |
| sentiment_analysis | 80% | 🟡 Normal variance — proceed with caveat |
| theme_extraction | 10% | 🔴 Red flag — proceed with caveat |

**entity_extraction caveat:** Disagreements concentrated around extraction granularity. Reviewer labeled at conceptual level; Haiku labels at mention level. Haiku is internally consistent. Parity scores measure whether challengers match Haiku's mention-level philosophy. Prompt refinement deferred to Sprint 17.

**sentiment_analysis caveat:** Two mismatches on neutral/negative boundary on genuinely ambiguous articles. Label-level agreement is reliable. Baseline is trustworthy.

**theme_extraction caveat:** Systematic philosophy gap — Haiku includes entity names as themes; reviewer labeled only conceptual themes. Haiku is internally consistent. Interpret parity scores conservatively for this operation. Prompt refinement deferred to Sprint 17.

---

## Phases

### Phase 2 — Baseline Extraction ✅ COMPLETE

✅ **Completed 2026-04-28**

Load each golden set JSONL file. For each document extract:
- `_id` as stable sample identifier
- `title` and `text` as input (HTML-stripped — see normalization below)
- Haiku output from the field mapping above (do not re-call Haiku API)
- Track source as `"historical"` in output

**Implementation:**
- ✅ Created `scripts/phase_2_baseline_extraction.py` (127 lines)
- ✅ Loaded all 3 golden sets (100 samples each)
- ✅ Extracted Haiku baselines from `entities`, `sentiment`, `themes` fields
- ✅ HTML-stripped all input text (production-compliant)
- ✅ Output: 3 JSONL files + metadata JSON per operation
- ✅ All outputs written to `/docs/decisions/msd-flash/runs/2026-04-28/`

**Results:**
- `baseline-entity_extraction.jsonl`: 100 samples
- `baseline-sentiment_analysis.jsonl`: 100 samples
- `baseline-theme_extraction.jsonl`: 100 samples

### Phase 3 — Model Variant Runs ✅ COMPLETE

✅ **Completed 2026-04-28**

Run the three non-Haiku model variants (Gemini Flash, DeepSeek, Qwen) against the same HTML-stripped input text for each operation.

- ✅ Use production prompts from the file paths above — extracted and reused exactly
- ✅ Use OpenRouter for all calls
- ✅ Use only the locked model strings above
- ✅ Collect per sample: model string, input tokens, output tokens, cost, latency (ms), raw output
- ✅ Write outputs to a dated output directory
- ✅ Harness is modular — adding a model variant requires only a new model string

**Implementation:**
- ✅ Created `scripts/phase_3_challenger_models.py` (220 lines)
- ✅ Updated `scripts/load_keys.sh` to load only `OPENROUTER_API_KEY`
- ✅ Used `urllib` for HTTP calls (no external dependencies)
- ✅ Extracted production prompts exactly from codebase (no rewrites)
- ✅ Rate limiting: 0.5s between calls for stability

**Results:**
- ✅ Total API calls: 900 (300 samples × 3 models)
- ✅ Successful: 898/900 (99.8% success rate)
  - entity_extraction: 300/300 successful
  - sentiment_analysis: 299/300 (flash: 1 error)
  - theme_extraction: 299/300 (deepseek: 1 error)
- ✅ Output: 9 JSONL files (3 operations × 3 models)
  - `challenger-entity_extraction-{flash,deepseek,qwen}.jsonl`
  - `challenger-sentiment_analysis-{flash,deepseek,qwen}.jsonl`
  - `challenger-theme_extraction-{flash,deepseek,qwen}.jsonl`

### Phase 4 — Output Normalization ⏳ PENDING

**Apply before any scoring.** Without this, formatting differences produce fake regressions.

**Deferred to future session.** When implementing:

For all operations:
- Strip HTML tags
- Strip leading/trailing whitespace
- Lowercase all strings
- Remove punctuation (except hyphens within words)

For array outputs (entity names, theme strings):
- Deduplicate
- Sort alphabetically (for deterministic comparison)

For entity extraction specifically:
- Extract `name` field from entity objects before scoring (do not compare full objects)

### Phase 5 — Scoring Harness ⏳ PENDING

**Read EVAL-001-evaluation-contract.md before writing any scoring code.** The following is a summary only.

**Deferred to future session.** When implementing:

**entity_extraction:**
- Score: F1 (precision + recall harmonic mean) × 100
- Match: normalized string + alias normalization
- Alias table: build from golden set scan before scoring, document and version-control it
- Sample regression flag: F1 < 0.85
- Operation flag: >5% of samples flagged

**sentiment_analysis:**
- Score: binary label match — 100 if match, 0 if not
- Match: exact class only (positive / negative / neutral)
- Log adjacent mismatches separately as diagnostic (does not affect score)
- Sample regression flag: any mismatch
- Operation flag: >5% of samples flagged

**theme_extraction:**
- Score: adjusted F1 × 100, two-pass
- Pass 1: normalized string match F1
- Pass 2: if ≥50% token overlap between a challenger theme and a Haiku theme, count as match
- Pass 2 adjusts score upward, capped at 100
- Sample regression flag: adjusted F1 < 0.80
- Operation flag: >5% of samples flagged

After scoring: apply failure mode taxonomy from eval contract to worst 10 samples per operation before writing decision records.

### Phase 6 — Comparison Tables and Decision Records ⏳ PENDING

Produce one decision record per operation:

```
docs/decisions/MSD-001-entity_extraction.md
docs/decisions/MSD-002-sentiment_analysis.md
docs/decisions/MSD-003-theme_extraction.md
```

**Deferred to future session.** When implementing, each record must include:

1. Operation metadata (name, type, volume, cost impact)
2. Evaluation details (date range, golden set size, baseline, variants run)
3. Quality metrics table — one column per model variant
4. Latency table — p50 and p95 per model
5. Cost table — cost/1k tokens, avg input/output tokens, est cost/day, est annual savings
6. Failure mode breakdown — worst 10 samples tagged per taxonomy from eval contract
7. Data-driven decision: SWAP / STAY / CONDITIONAL — one decision per challenger model
8. Rationale
9. Override conditions (when to revert)
10. Rollout plan (if SWAP or CONDITIONAL)
11. Manual validation caveat for this operation (copy from findings above)

**Decision vocabulary:**
- SWAP — quality threshold met, cost savings justify latency increase
- STAY — quality threshold not met, or risk does not justify savings
- CONDITIONAL — threshold met under specific conditions only (e.g. batch ok, real-time not ok)

Decisions must emerge from data. No outcome is assumed in advance.

---

## Known Data Quality Issue

The `text` field on some articles contains raw HTML (img tags, p tags, anchor tags). Strip HTML before passing to any model. Apply to both Haiku baseline extraction and all challenger model calls — normalization must be consistent.

---

## Reproducibility Requirements

- Golden set files are fixed inputs — do not re-query MongoDB
- Same sample `_id` values used for all model runs
- Alias table version-controlled alongside scoring code
- All scripts accept golden set path as input parameter — no hardcoded paths
- All outputs written to a dated output directory (e.g. `docs/decisions/msd-flash/runs/2026-04-28/`)

---

## Acceptance Criteria

- [x] Golden set loaded correctly — 100 samples per operation confirmed
- [x] HTML stripped from input text before all model calls
- [x] Haiku baseline extracted from golden set fields — Haiku API not re-called
- [x] All three challenger models run (Gemini Flash, DeepSeek, Qwen)
- [x] Production prompts reused exactly from specified file paths
- [ ] Output normalization applied before scoring (Phase 4, future session)
- [ ] Alias table built, documented, and version-controlled (Phase 5, future session)
- [ ] Scoring harness matches eval contract exactly (Phase 5, future session)
- [ ] Regression flags applied per sample and per operation (Phase 5, future session)
- [ ] Failure mode taxonomy applied to worst 10 samples per operation (Phase 5, future session)
- [ ] Comparison tables produced for all 3 operations, all 4 models (Phase 6, future session)
- [ ] MSD-001, MSD-002, MSD-003 written with all required sections (Phase 6, future session)
- [ ] Manual validation caveats included in each MSD file (Phase 6, future session)
- [x] All outputs written to dated output directory
- [x] Scripts written and functional (phase_2 and phase_3)

---

## Out of Scope — Sprint 16

- Tier 2 operations (narrative_generate, narrative_theme_extract, cluster_narrative_gen, narrative_polish, insight_generation)
- Production routing changes
- Haiku prompt improvements (flagged for Sprint 17 based on manual validation findings)
- Helicone trace visibility (TASK-074, non-blocking)

---

## Dependencies

**Required before Phase 3:**
- [ ] OpenRouter API key loaded via `scripts/load_keys.sh`
- [ ] Golden set files present at `/Users/mc/*.json`

**Non-blocking:**
- [ ] TASK-074 (Helicone) — useful for trace visibility, not required
- [ ] TASK-075 (narrative cache) — gates Tier 2 only

---

## Related Artifacts

| Artifact | Location | Status |
|---|---|---|
| Evaluation contract | `docs/decisions/EVAL-001-evaluation-contract.md` | Locked |
| Golden set — entity | `/Users/mc/entity_extraction_golden.json` | Ready |
| Golden set — sentiment | `/Users/mc/sentiment_analysis_golden.json` | Ready |
| Golden set — theme | `/Users/mc/theme_extraction_golden.json` | Ready |
| EVAL-001 meta-doc | `docs/decisions/EVAL-001-model-selection-flash-evaluations.md` | To write after eval runs |
| MSD-001 | `docs/decisions/MSD-001-entity_extraction.md` | To write after eval runs |
| MSD-002 | `docs/decisions/MSD-002-sentiment_analysis.md` | To write after eval runs |
| MSD-003 | `docs/decisions/MSD-003-theme_extraction.md` | To write after eval runs |
| Model Selection Rubric | TASK-078 | Reference |
| Operation Tier Mapping | TASK-079 | Reference |