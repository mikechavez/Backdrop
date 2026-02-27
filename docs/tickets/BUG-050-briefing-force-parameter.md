---
id: BUG-050
type: bug
status: fixed
priority: medium
severity: medium
created: 2026-02-26
updated: 2026-02-26
---

# BUG-050: Briefing Generation Endpoint Force Parameter Not Providing Clear Feedback

## Problem
The `/api/v1/briefing/generate` endpoint with `force=true` was returning generic "may already exist today" error messages, making it impossible to distinguish between:
- A briefing actually existing (force=false case)
- A generation failure that needs server log investigation (force=true case)

## Expected Behavior
When `force=true` is specified, the endpoint should:
1. Always attempt generation, even if one exists
2. If generation fails, provide clear error details indicating a generation error occurred
3. Log the force parameter and generation outcome for debugging

## Actual Behavior
The endpoint returned "Briefing generation returned no result (may already exist today)" regardless of the force value, with no indication whether:
- The force parameter was actually being used
- A generation error occurred during processing
- An existence check was skipped

## Steps to Reproduce
1. Call `POST /api/v1/briefing/generate` with `{"type": "evening", "force": true}`
2. Observe generic error message that provides no actionable information
3. No way to debug without checking server logs manually

## Environment
- Environment: production
- Impact: medium (affects admin ability to trigger briefing regeneration)

---

## Resolution

**Status:** Fixed
**Fixed:** 2026-02-26
**Branch:** docs/task-005-published-substack-url
**Commit:** (pending)

### Root Cause
The endpoint was catching all exceptions silently and returning None, then responding with a generic message that didn't account for the force parameter value. The error response didn't differentiate between:
1. Expected behavior (force=false, briefing exists)
2. Error condition (force=true, generation failed)

### Changes Made
**File:** `src/crypto_news_aggregator/api/v1/endpoints/briefing.py`

1. **Added logging** (line 431):
   - Log the briefing type and force parameter at start of generation
   - Log warning when generation returns None (line 443)

2. **Improved error messages** (lines 452-463):
   - If `force=true` and generation fails: "Briefing generation failed (check server logs for details)"
   - If `force=false` and generation fails: "Briefing generation returned no result (may already exist today)"
   - This differentiates between expected vs error conditions

3. **Better exception handling** (lines 465-475):
   - HTTPExceptions re-raised as-is (for 400 validation errors)
   - Other exceptions now return error response instead of 500 status
   - Error message includes the actual exception details for debugging

### Testing
Manual testing with curl:
```bash
# Before fix: generic message regardless of force value
curl -X POST https://context-owl-production.up.railway.app/api/v1/briefing/generate \
  -H "Content-Type: application/json" \
  -d '{"type": "evening", "force": true}'
# Response: "Briefing generation returned no result (may already exist today)"

# After fix: different message when force=true
# Response: "Briefing generation failed (check server logs for details)"
```

### Files Changed
- `src/crypto_news_aggregator/api/v1/endpoints/briefing.py` (lines 430-475)

---

## Next Steps
1. Commit this fix
2. Deploy to production
3. When next briefing generation issue occurs, the error message will now indicate whether to check logs (force=true case) or if a briefing already exists (force=false case)
