---
ticket_id: BUG-060
title: Scoring Harness Hardcodes flash_label for All Challenger Models
priority: P2
severity: medium
status: OPEN
date_created: 2026-04-28
component: scripts/phase_5_scoring_harness.py
discovered_in: TASK-080
---

# BUG-060: Scoring Harness Hardcodes flash_label for All Challenger Models

## Problem

The Phase 5 scoring harness (`scripts/phase_5_scoring_harness.py`) hardcodes
`flash_label` as the challenger label field when writing scored output files.
All three scored challenger files — including DeepSeek and Qwen — contain a
`flash_label` field instead of model-specific field names (`deepseek_label`,
`qwen_label`).

**Discovered during:** TASK-080 post-hoc analysis via raw file inspection.

## Impact

**Accuracy totals are not affected.** The `match` field (used to derive accuracy
statistics) was written correctly. Headline accuracy numbers in MSD-001/002/003
are valid.

**Per-class breakdowns are valid but mislabeled.** The values in `flash_label`
for DeepSeek and Qwen scored files contain the correct label for that model —
the field name is wrong, not the data. Any downstream analysis that reads
`deepseek_label` or `qwen_label` directly will fail to find the field.

## Files Affected

```
docs/decisions/msd-flash/runs/2026-04-28/scored-entity_extraction-deepseek.jsonl
docs/decisions/msd-flash/runs/2026-04-28/scored-entity_extraction-qwen.jsonl
docs/decisions/msd-flash/runs/2026-04-28/scored-sentiment_analysis-deepseek.jsonl
docs/decisions/msd-flash/runs/2026-04-28/scored-sentiment_analysis-qwen.jsonl
docs/decisions/msd-flash/runs/2026-04-28/scored-theme_extraction-deepseek.jsonl
docs/decisions/msd-flash/runs/2026-04-28/scored-theme_extraction-qwen.jsonl
```

## Root Cause

Label field name is hardcoded in the scoring harness rather than derived from
the model name or passed as a parameter. Likely a copy-paste error when the
harness was extended from Flash to DeepSeek and Qwen.

## Fix

In `scripts/phase_5_scoring_harness.py`, replace the hardcoded `flash_label`
field name with a model-derived label field name. Pattern:

```python
# Before (wrong)
scored_record["flash_label"] = challenger_label

# After (correct)
label_field = f"{model_short_name}_label"  # e.g. deepseek_label, qwen_label
scored_record[label_field] = challenger_label
```

Ensure `model_short_name` is derived from the model string (e.g. strip
provider prefix: `google/gemini-2.5-flash` → `flash`, `deepseek/deepseek-chat`
→ `deepseek`, `qwen/qwen-plus` → `qwen`).

The existing scored files from the 2026-04-28 run do not need to be rewritten —
accuracy totals are correct and the per-class data is readable if the caller
knows to look for `flash_label`. However, if these files are used for any
downstream analysis that references `deepseek_label` or `qwen_label` by name,
the files should be patched or the analysis should be written to check both
field names.

## Acceptance Criteria

- [ ] `flash_label` hardcoding removed from scoring harness
- [ ] Label field name derived from model identifier
- [ ] Verified against all three model strings (flash, deepseek, qwen)
- [ ] Note added to 2026-04-28 run README or in EVAL-001 meta-doc (already
      documented in EVAL-001-model-selection-flash-evaluations.md)

## Blocking

Must be fixed before next eval run. Does not block Sprint 16 closeout.

## Related

- FEATURE-053: Flash Evaluations (parent eval feature)
- TASK-080: Post-Hoc Eval Analysis (discovery)
- EVAL-001: `docs/decisions/EVAL-001-model-selection-flash-evaluations.md`
  (documents this limitation)