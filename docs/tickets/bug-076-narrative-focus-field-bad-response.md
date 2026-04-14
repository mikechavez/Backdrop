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

**Status:** FIXED
**Fixed:** 2026-04-14
**Branch:** fix/bug-076-narrative-focus-parser
**Commit:** 41936ad

### Root Cause
The `narrative_focus` response parser reads the raw LLM output string without extracting just the focus phrase. The model wraps its answer in explanation text (e.g., `"defi ecosystem expansion"\n\nThis phrase captures...`) and the parser doesn't strip the explanation text.

### Changes Made
1. **Added `extract_focus_phrase()` function** (`narrative_themes.py` lines 436-488)
   - Extracts just the 2-5 word focus phrase from raw LLM response
   - Handles quoted strings, newlines, and multi-line explanations
   - Strips explanation text that follows the phrase
   - Normalizes whitespace

2. **Integrated extraction in `discover_narrative_from_article()`** (lines 860-868)
   - Calls `extract_focus_phrase()` immediately after JSON parsing
   - Only applies extraction if focus field has explanation text
   - Logs when extraction modifies the field

3. **Added comprehensive unit tests** (`test_narrative_themes.py`)
   - 13 test cases covering edge cases (empty strings, quoted text, multi-line explanations, etc.)
   - All tests passing

### Testing Results
✅ All 53 focus/validation/discovery tests passing:
- 13 new `TestExtractFocusPhrase` tests
- 23 `TestValidateNarrativeJson` tests (backward compatible)
- 10 `TestComputeFocusSimilarity` tests
- 3 `TestBuildDegradedNarrative` tests
- 2 `TestZeroRetryOnValidationFailure` tests

### Backfill Notes
Existing documents with bad `narrative_focus` values can be fixed later if needed. The fix applies prospectively to all new narrative detections.

### Files Changed
- `src/crypto_news_aggregator/services/narrative_themes.py` — Added `extract_focus_phrase()` and integrated it in `discover_narrative_from_article()`
- `tests/services/test_narrative_themes.py` — Added 13 new test cases