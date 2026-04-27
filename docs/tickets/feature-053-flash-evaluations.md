---
id: FEATURE-053
type: feature
status: backlog
priority: critical
complexity: high
created: 2026-04-27
updated: 2026-04-27
---

# FEATURE-053: Flash Evaluations — Tier 1 Testing Against Golden Set

## Problem/Opportunity

Currently, all 14 LLM operations route to claude-haiku-4-5-20251001. Gemini 2.5 Flash offers potential cost savings (est. 60% cheaper) with comparable quality for certain operation types. We need rigorous evaluation on production data to decide: which operations can safely swap to Flash?

This feature produces decision records (MSD-001, MSD-002, etc.) that become both operational guides and interview artifacts demonstrating cost-quality reasoning.

**SPRINT 16 SCOPE:** Tier 1 operations ONLY (3 operations: entity_extraction, sentiment_analysis, theme_extraction). Phases 1-2 only. 2-3 decision records.

---

## Proposed Solution

1. **Phase 1: Extract Golden Set** — Load historical call data from MongoDB (briefing_drafts collection) as input/output pairs
2. **Phase 2: Baseline from Existing Haiku Outputs** — Use existing `haiku_output` from golden set if available; only re-run if missing/inconsistent
3. **Phase 3: Run Flash Evaluations** — Execute same inputs on Gemini 2.5 Flash (variant_ratio=1.0 routing)
4. **Phase 4: Compare & Score** — Build comparison table (model, quality, cost, latency)
5. **Phase 5: Produce Decision Records** — Write MSD-001, MSD-002, etc. with decision (data-driven, no forced outcomes)

**Scope:** Tier 1 Operations ONLY (3 operations for Sprint 16)
- **Tier 1 (High Confidence):** entity_extraction, sentiment_analysis, theme_extraction

**Explicitly NOT in Sprint 16:**
- Tier 2 operations (narrative_generate, narrative_theme_extract, cluster_narrative_gen, narrative_polish, insight_generation)
- Full rollout decisions
- Production swaps

**Note on Tier 1 Classification:**
The full Tier 1 classification (per TASK-079) includes 5 operations: entity_extraction, sentiment_analysis, theme_extraction, actor_tension_extract, relevance_scoring. Sprint 16 evaluates a subset (3 ops) due to time constraints. Tier 2 and later phases are deferred to Sprint 17+.

---

## User Story

As a **PM making model selection decisions**, I want **rigorous evaluation data on Haiku vs. Flash for Tier 1 operations** so that **I can confidently decide which extraction operations swap without sacrificing quality or user experience**.

---

## Acceptance Criteria

- [ ] Golden set extracted: 50-100 samples per Tier 1 operation (3 ops total)
- [ ] **Phase 2 optimization:** Existing haiku_output used if available; only re-run if missing/inconsistent
- [ ] Flash variant run: same metrics collected on Gemini 2.5 Flash
- [ ] Comparison table: Model | Quality | Cost/1k | p50ms | p95ms (for each operation)
- [ ] Quality regression detected: any >5% drop flagged visually
- [ ] Decision records written: MSD-001, MSD-002, MSD-003 (minimum)
- [ ] Each decision record includes: operation, metrics, **data-driven decision** (not forced outcome), override conditions, rollout plan
- [ ] Eval runs are reproducible: golden set definition documented, same trace_ids used

---

## Dependencies

**Must Be Completed First:**
- [ ] BUG-090 (model routing observable)
- [ ] TASK-076 (RoutingStrategy implementation)
- [ ] TASK-077 (GeminiProvider available)
- [ ] TASK-078 (Model Selection Rubric)
- [ ] TASK-079 (Operation Tier Mapping)

**Also Recommended (not blocking):**
- [ ] TASK-074 (Helicone setup) — useful for trace visibility, not required
- [ ] TASK-075 (Narrative cache investigation) — runs parallel, gates Tier 2 decisions only

---

## Open Questions

- [ ] **Quality Scoring Details:** Will manual 1-5 rating be done by you, or automated?
  - *Proposed:* Automated exact-match for Tier 1, no manual review needed (deterministic operations)
- [ ] **Golden Set Sampling:** Random or stratified (by date, content length)?
  - *Proposed:* Random, last 7-14 days, at least 50 samples per operation
- [ ] **Cost Projection:** Should decision record include annual savings estimate?
  - *Proposed:* Yes, include "if swapped for this op: ~$X/year savings"

---

## Implementation Notes

### Phase 1: Golden Set Extraction

**MongoDB Query:**
```python
# For each Tier 1/2 operation, extract from briefing_drafts collection
db.briefing_drafts.find({
    "operation": "entity_extraction",
    "timestamp": {"$gte": datetime.now() - timedelta(days=14)}
}).limit(100)
```

**Golden Set Schema:**
```python
{
    "operation": "entity_extraction",
    "input_id": "trace_123abc",  # Stable identifier for reproducibility
    "input_text": "...",  # Article or content
    "articles": [...],  # Supporting articles (if any)
    "timestamp": "2026-04-20T10:30:00Z",
    "haiku_output": {...},  # Existing Haiku response (ground truth)
}
```

**Selection Criteria:**
- 50-100 samples per Tier 1 operation (3 ops = 150-300 samples total)
- Cover last 7-14 days
- Include edge cases (long inputs, multiple articles, high-volume clusters)

---

### Phase 2: Baseline from Existing Haiku Outputs (OPTIMIZED)

**Key Optimization:**

The golden set already contains `haiku_output{}` from historical calls. Use this as baseline instead of re-running:

```python
# For each sample in golden set:
for sample in golden_set:
    # OPTIMIZATION: Use existing haiku_output if present and valid
    if sample.get("haiku_output") and _is_valid_response(sample["haiku_output"]):
        # Use cached output
        baseline_metrics[sample["input_id"]] = {
            "operation": sample["operation"],
            "model": "anthropic:claude-haiku-4-5-20251001",
            "input_tokens": sample["haiku_output"].get("input_tokens"),
            "output_tokens": sample["haiku_output"].get("output_tokens"),
            "cost": sample["haiku_output"].get("cost"),
            "latency_ms": sample["haiku_output"].get("latency_ms"),
            "output": sample["haiku_output"].get("text"),
            "source": "historical"  # Track that we used cached output
        }
    else:
        # Only re-run if missing or invalid
        start = time.time()
        response = gateway.call(
            operation=sample["operation"],
            prompt=sample["input_text"],
            routing_key=sample["input_id"],  # Stable key for reproducibility
        )
        latency_ms = (time.time() - start) * 1000
        
        baseline_metrics[sample["input_id"]] = {
            "operation": sample["operation"],
            "model": response.actual_model,
            "latency_ms": latency_ms,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "cost": response.cost,
            "output": response.text,
            "source": "recomputed"  # Track that we re-ran it
        }
```

**Why This Matters:**
- Saves ~3-4 hours of API calls (recomputing 150-300 samples)
- Uses same ground truth (haiku_output was generated by same code path historically)
- Avoids drift (historical data is fixed reference point)
- Makes evaluation faster + cheaper

---

### Phase 3: Flash Variant Run

**Process:**
Same as Phase 2 baseline, but with Flash routing:

```python
# Activate Flash for this operation
strategy = _OPERATION_ROUTING[operation]
strategy.variant = "gemini:gemini-2.5-flash"
strategy.variant_ratio = 1.0  # 100% Flash (not A/B split)

# Run same golden set
for sample in golden_set:
    start = time.time()
    response = gateway.call(
        operation=sample["operation"],
        prompt=sample["input_text"],
        routing_key=sample["input_id"],  # Same key → same routing path
    )
    latency_ms = (time.time() - start) * 1000
    
    # Store Flash metrics
    flash_metrics[sample["input_id"]] = {
        "operation": sample["operation"],
        "model": response.actual_model,
        "latency_ms": latency_ms,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "cost": response.cost,
        "output": response.text,
    }
```

**Note:** If GeminiProvider.call() raises NotImplementedError, substitute with deterministic mock that matches response contract.

---

### Phase 4: Quality Scoring

**Tier 1 Operations (Extraction - Deterministic):**

For extraction operations, quality is measurable via exact match or overlap:

```python
def score_extraction(haiku_output, flash_output):
    """
    Exact match or overlap score.
    0 = completely different
    100 = identical
    
    For entity_extraction: check if key entities match
    For sentiment_analysis: check if sentiment classification matches
    For theme_extraction: check if themes overlap
    """
    # Simple approach: exact string match
    if haiku_output == flash_output:
        return 100
    
    # Or: semantic overlap (if outputs are JSON, compare keys)
    try:
        haiku_json = json.loads(haiku_output)
        flash_json = json.loads(flash_output)
        
        # Compare keys/structure (operation-specific)
        overlap = len(set(haiku_json.keys()) & set(flash_json.keys())) / len(set(haiku_json.keys()) | set(flash_json.keys()))
        return int(overlap * 100)
    except:
        # Fallback: character-level overlap
        common = sum(1 for a, b in zip(haiku_output, flash_output) if a == b)
        return int((common / len(haiku_output)) * 100) if haiku_output else 0
```

**Regression Threshold:**
- Tier 1: >5% of samples show quality regression (score drop >10 points)
- Flag any operation where regression exceeds threshold

---

### Phase 5: Comparison Table

For each operation evaluated, produce:

```
| Metric | Haiku | Flash | Delta |
|--------|-------|-------|-------|
| Avg Quality Score | 95.2% | 94.1% | -1.1% ✓ |
| Cost/1k tokens | $0.0034 | $0.00136 | -60% ✓ |
| p50 Latency (ms) | 245 | 380 | +55% ⚠️ |
| p95 Latency (ms) | 520 | 890 | +71% ⚠️ |
| Cost Savings (annual) | — | ~$8.2K | +savings |
```

---

### Phase 6: Data-Driven Decision Records

Create one decision record (MSD-XXX) per operation evaluated. **Decisions must be data-driven; no forced outcomes.**

Example structure:

**File:** `docs/decisions/MSD-001-entity_extraction.md`

```markdown
# MSD-001: entity_extraction — Haiku vs. Gemini 2.5 Flash

## Operation
- Name: entity_extraction
- Type: Extraction (Tier 1)
- Volume: ~100 calls/day
- Cost Impact: $0.152/day

## Evaluation Details
- Date Range: 2026-04-20 to 2026-04-27
- Golden Set Size: 100 samples
- Baseline: claude-haiku-4-5-20251001 (from historical haiku_output)
- Variant: gemini-2.5-flash

## Metrics

| Metric | Haiku | Flash | Regression |
|--------|-------|-------|-----------|
| Quality Score | 96.3% | 95.8% | -0.5% ✓ |
| Cost/1k | $0.0034 | $0.00136 | -60% |
| p50 Latency (ms) | 230 | 310 | +35% |
| p95 Latency (ms) | 480 | 750 | +56% |

## Decision (Data-Driven)

**SWAP to Flash** — IF the following conditions hold:
- Quality regression is minimal (< 5% threshold): ✓ (-0.5%)
- Cost savings justify latency increase for non-critical operation: ✓
- High-volume operation (100/day) amplifies annual savings (~$8.2K)

If any threshold is violated, decision would be STAY or CONDITIONAL.

## Rationale
- Quality regression is minimal and well below threshold
- Cost savings are significant (60% reduction)
- Tier 1 operation: low failure cost supports conservative experimentation
- Latency increase is acceptable for batch processing (not real-time)

## Override Conditions
Revert to Haiku if:
- Quality regression > 5% detected in production
- Latency p95 > 1000ms impacts downstream batch processing
- Flash API becomes unreliable (>1% error rate)

## Rollout Plan
1. Set variant_ratio = 0.1 (10% to Flash, 90% to Haiku) for 3 days
2. Monitor Sentry / cost dashboard for errors and quality regression
3. If no issues, increase to variant_ratio = 1.0 (100% Flash)
4. Set reminder to re-evaluate in 2 weeks

## Date Approved
2026-04-28
```

---

## Completion Summary

**After All Phases Complete (Sprint 16):**

- [ ] All Tier 1 operations evaluated (3 ops for Sprint 16)
- [ ] Decision records written: MSD-001 through MSD-003
- [ ] Comparison tables included in each record
- [ ] **Decisions are data-driven (no forced "SWAP" outcomes)**
- [ ] Quality regression analysis complete: flag any ops exceeding >5% threshold
- [ ] Golden set documented: schema, sampling criteria, reproducibility
- [ ] Eval methodology documented: quality scoring rules, regression threshold
- [ ] **Phase 2 optimization noted:** baseline computed from existing haiku_output where available
- [ ] Ready for interview: "Here's how we evaluated Haiku vs. Flash on production data"

**NOT in Sprint 16 (Deferred to Sprint 17+):**
- Tier 2 operations (narrative_generate, narrative_theme_extract, cluster_narrative_gen, narrative_polish, insight_generation)
- Full rollout decisions
- Production swaps

---

## Related Tickets

- BUG-090 (model routing must be observable)
- TASK-074 (Helicone proxy for trace visibility)
- TASK-075 (narrative_generate cache decision gates Tier 2 scope)
- TASK-076 (RoutingStrategy enables A/B control)
- TASK-077 (GeminiProvider must be available)
- TASK-078 (Model Selection Rubric frames decisions)
- TASK-079 (Operation Tier Mapping determines priority)