---
id: BUG-076
type: bug
status: backlog
priority: low
severity: low
created: 2026-04-14
updated: 2026-04-14
---

# BUG-076: `narrative_focus` field stores full LLM response instead of extracted focus phrase

## Problem
The `narrative_focus` field on narrative documents contains a full LLM explanation rather than just the extracted focus phrase. The response parser grabs the entire model output instead of isolating the target value. This predates Sprint 13 and is not currently blocking anything, but indicates the parser was fragile before BUG-071's prompt compression and could silently produce bad data downstream.

## Expected Behavior
`narrative_focus` should contain a short extracted phrase, e.g.: `"defi ecosystem expansion"`

## Actual Behavior
`narrative_focus` contains the full LLM prose response, e.g.:
```
"defi ecosystem expansion"\n\nThis phrase captures the active process...
```

## Steps to Reproduce
1. Query a narrative document: `db.narratives.findOne({}, { narrative_focus: 1 })`
2. Observe `narrative_focus` contains multi-sentence LLM explanation rather than a short phrase

## Environment
- Environment: production
- User impact: low — field is not currently driving any critical pipeline behavior

---

## Resolution

**Status:** Open
**Fixed:**
**Branch:** fix/bug-076-narrative-focus-parser
**Commit:**

### Root Cause
The `narrative_focus` response parser reads the raw LLM output string without extracting just the focus phrase. The model wraps its answer in explanation text and the parser doesn't strip it.

### Changes Made
- Find the `narrative_focus` parser (likely in the narrative generation or post-processing code)
- Add JSON extraction or regex to pull only the focus phrase (e.g., extract first quoted string, or prompt the model to return JSON)
- Optionally backfill existing documents with corrected values

### Testing
1. Trigger narrative generation for a new document
2. Query `narrative_focus` field — confirm it contains only the short phrase
3. Spot-check 5–10 existing documents if backfill is run

### Files Changed
TBD — narrative response parser, likely in `narrative_themes.py` or equivalent