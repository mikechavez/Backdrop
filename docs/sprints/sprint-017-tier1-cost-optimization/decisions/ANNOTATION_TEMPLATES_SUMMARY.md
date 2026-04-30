---
date: 2026-04-29
type: annotation-task
status: ready-for-annotation
---

# Annotation Templates Summary

Three stratified annotation templates have been generated for Phase 3 scoring validation. Use these to label additional samples before threshold-based scoring.

---

## Files Generated

| File | Samples | Stratification | Location |
|------|---------|-----------------|----------|
| **entity_extraction_annotation_template.md** | 27 | Quartile by entity count | `decisions/` |
| **sentiment_analysis_annotation_template.md** | 25 | Label distribution (pos/neu/neg) | `decisions/` |
| **theme_extraction_annotation_template.md** | 25 | Quartile by theme count | `decisions/` |

**Total to annotate:** 77 samples (representing complexity distribution)

---

## Sampling Strategy

### entity_extraction (27 samples)

Stratified by entity count per article:

```
Q1 (1-2 entities):   7 samples  (46 available)
Q2 (3 entities):     6 samples  (16 available)
Q3 (4 entities):     7 samples  (18 available)
Q4 (5+ entities):    7 samples  (10 available)
```

**Purpose:** Validate F1 scoring across complexity range. Tests both simple (single entity) and complex (multi-entity) extraction.

### sentiment_analysis (25 samples)

Stratified by sentiment label:

```
Positive:  9 samples  (45 available)
Neutral:   8 samples  (21 available)
Negative:  8 samples  (24 available)
```

**Purpose:** Validate accuracy scoring across sentiment distribution. Ensures balanced validation (not just positive bias).

### theme_extraction (25 samples)

Stratified by theme count per article:

```
Q1 (3-4 themes):   7 samples  (15 available)
Q2 (5 themes):     6 samples  (41 available)
Q3 (5-6 themes):   6 samples  (20 available)
Q4 (7-8 themes):   6 samples  (15 available)
```

**Purpose:** Validate adjusted F1 scoring across theme density. Tests both sparse and dense theme distributions.

---

## Excluded Articles

All 30 previously-labeled articles (from f053-validation-worksheet.md) have been excluded to ensure fresh annotations:

- **entity_extraction:** 10 articles excluded
- **sentiment_analysis:** 10 articles excluded
- **theme_extraction:** 10 articles excluded

This ensures Phase 4 spot-checks can use the new annotations independently.

---

## Annotation Format

Each template follows this structure:

```markdown
## Sample N
**TITLE:** [Article headline]

**TEXT:** [Article content with HTML stripped]

**YOUR LABEL:** [blank for annotation]

---
```

### How to Fill In

**entity_extraction:**
```
**YOUR LABEL:** Entity1, Entity2, Entity3
```
(Comma-separated list of named entities)

**sentiment_analysis:**
```
**YOUR LABEL:** positive (score: 0.7)
```
(Label + score from -1.0 to +1.0)

**theme_extraction:**
```
**YOUR LABEL:** Theme1, Theme2, Theme3, Theme4
```
(Comma-separated list of themes/topics)

---

## Next Steps

1. **Annotate:** Fill in `**YOUR LABEL:**` sections for all 77 samples
2. **Save:** Keep filenames as-is in `decisions/` directory
3. **Use in Phase 4:** These annotations will be used for spot-checking Phase 2 challenger outputs
4. **Validation:** Compare against challenger model outputs to assess quality

---

## Quality Notes

- Samples are stratified, not random, so expect some clustering by complexity
- Some articles appear in multiple templates if they fit multiple stratifications (e.g., positive sentiment + high entity count)
- HTML has been stripped but some markdown formatting preserved for readability
- Article text is truncated at [...] if very long; refer to golden set for full text if needed

---

## Files

- `entity_extraction_annotation_template.md` (10K)
- `sentiment_analysis_annotation_template.md` (11K)
- `theme_extraction_annotation_template.md` (9.4K)
