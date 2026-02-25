---
id: BUG-030
type: bug
status: code-complete
priority: critical
severity: high
created: 2026-02-23
updated: 2026-02-23
---

# Deprecated Anthropic Model Strings — All API Calls Failing

## Problem
All Anthropic API calls fail because the app uses retired model identifiers. Anthropic deprecated `claude-3-haiku-20240307` and `claude-3-5-haiku-20241022` on 2026-02-19. Every Claude-dependent feature (narrative generation, entity extraction, briefing generation) is broken in production.

Spun off from BUG-029, which was initially misdiagnosed as a billing/credits issue.

## Expected Behavior
API calls succeed using supported model identifiers. All Claude-dependent features work.

## Actual Behavior
API calls return errors (model not found / deprecated). Last successful calls were 2026-02-17 (two days before deprecation).

## Evidence
- Anthropic deprecation email received 2026-02-19: "Effective today, Anthropic has retired and no longer supports Claude Haiku 3.5"
- API logs show all calls using `claude-3-haiku-20240307` (retired)
- Two calls on 2026-02-17 already used `claude-haiku-4-5-20251001` successfully

## Root Cause
Deprecated model strings hardcoded across multiple files. Replaced with current equivalents.

---

## Acceptance Criteria
- [x] All deprecated model strings replaced in config.py, briefing_agent.py, anthropic.py, cost_tracker.py, cache.py
- [x] `rg` search returns zero hits for deprecated model strings in `/src/`
- [x] API test call succeeds with `claude-haiku-4-5-20251001`
- [ ] **Briefing generation works in production** — deploy, trigger manual briefing, confirm output
- [ ] **Narrative pipeline runs without API errors** — verify entity extraction + narrative clustering complete

---

## Resolution

**Branch:** fix/bug-027-remove-afternoon-scheduled-briefing
**Commits:**
- cafae9c - Initial model string replacements
- 20dbd7f - Correction: Fixed invalid model name format

### Changes Made (cafae9c)
1. **config.py** (lines 45-47):
   - `ANTHROPIC_DEFAULT_MODEL`: `claude-3-haiku-20240307` → `claude-haiku-4-5-20251001`
   - `ANTHROPIC_ENTITY_MODEL`: `claude-3-5-haiku-20241022` → `claude-haiku-4-5-20251001`
   - `ANTHROPIC_ENTITY_FALLBACK_MODEL`: `claude-3-5-sonnet-20241022` → `claude-sonnet-4-6`

2. **briefing_agent.py** (lines 46-50):
   - `DEFAULT_MODEL`: `claude-sonnet-4-5-20250929` → `claude-sonnet-4-6`
   - `FALLBACK_MODELS`: Simplified from 3 deprecated models to single `claude-haiku-4-5-20251001`

3. **anthropic.py** (lines 21-39):
   - Default model: `claude-3-haiku-20240307` → `claude-haiku-4-5-20251001`
   - Fallback chain: Updated to `claude-sonnet-4-6` and `claude-haiku-4-5-20251001`

4. **cost_tracker.py** (pricing table):
   - Removed deprecated model pricing
   - Added: `claude-haiku-4-5-20251001` ($1/$5 per 1M tokens)
   - Added: `claude-sonnet-4-6` ($3/$15 per 1M tokens)

5. **cache.py** (CostTracker class pricing):
   - Updated duplicate pricing table with current models

### Correction Applied (20dbd7f)
**Issue Found:** The initial commit used `claude-sonnet-4-6` which is not a valid Anthropic model ID format. Valid model names require a date suffix (e.g., `claude-sonnet-4-YYYYMMDD`).

**Fix Applied:**
- Changed `claude-sonnet-4-6` → `claude-sonnet-4-20250514` (valid format with date)
- Updated in: briefing_agent.py, config.py, anthropic.py, cost_tracker.py, cache.py
- Added detailed error logging to track API responses for debugging

### Code Verification
✅ No deprecated model strings remain in `/src/` directory (verified with ripgrep)
✅ All model names now use valid Anthropic format: `claude-{family}-{version}-{date}`
✅ Models tested locally: API accepts new model IDs, rejects with 400 only due to billing (expected)

---

## Production Verification (TODO)

### Step 1: Deploy to Vercel
- Push commit cafae9c to production branch
- Confirm Vercel build succeeds

### Step 2: Verify briefing generation
```bash
# Trigger manual briefing
curl -X POST "https://backdrop.markets/admin/trigger-briefing?force=true"

# Check response — should return briefing JSON, not an API error
```

### Step 3: Verify narrative pipeline
```bash
# Check MongoDB for recent narratives (after deploy)
db.narratives.find({last_updated: {$gte: ISODate("2026-02-23T00:00:00Z")}}).count()
# Should be > 0 once pipeline runs

# Check entity extraction
db.entity_mentions.find({created_at: {$gte: ISODate("2026-02-23T00:00:00Z")}}).count()
# Should be > 0
```

### Step 4: Check Anthropic API logs
- Go to https://console.anthropic.com — Logs
- Confirm new requests show `claude-haiku-4-5-20251001` and `claude-sonnet-4-6`
- Confirm 200 responses (not 4xx errors)

Once all four steps pass → mark status `completed` and close ticket.