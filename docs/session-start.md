---
session_date: 2026-02-23
project: Backdrop (Context Owl)
current_sprint: Sprint 11 — 48-Hour Launch
session_focus: Ship Substack + Interactive Site + Distribution
---

# Session Context: Sprint 11 — 48-Hour Launch

## Sprint Overview

**Goal:** Fix production, ship Substack article + Cognitive Debt Simulator interactive site, maximize distribution across X, LinkedIn, Reddit, HN

**Duration:** 2026-02-23 to 2026-02-25 (48 hours)
**Deadline:** Hard — launch window is time-sensitive

---

## Current Status

### Sprint 10 Status
- ✅ BUG-027 (afternoon briefing removal) — completed & verified
- ✅ BUG-028 (stale briefing query) — completed & verified
- ✅ Sprint 9 documentation infrastructure complete (2,526 lines, 8 modules)
- ✅ BUG-029 (API credits exhausted) — CLOSED, misdiagnosed as billing issue
- 🟡 BUG-030 (deprecated model strings) — CODE COMPLETE (commit cafae9c), awaiting production verification

### BUG-030 Status
- ✅ Code changes merged across 5 files (config.py, briefing_agent.py, anthropic.py, cost_tracker.py, cache.py)
- ✅ All deprecated model strings replaced, verified with ripgrep
- ✅ Models upgraded: Haiku → 4.5 (`claude-haiku-4-5-20251001`), Sonnet → 4 (`claude-sonnet-4-20250514`)
- ✅ Correction applied: Fixed invalid model name format `claude-sonnet-4-6` → `claude-sonnet-4-20250514`
- ✅ Local verification: API calls use correct model format, fail only on billing (expected without credits)
- **Status:** Code-complete, awaiting production verification and API credits for full test
- Once production verified → close BUG-030 and move to TASK-001

---

## What to Work On Next

**Priority 1**: [BUG-030] Production verification — deploy + test LLM features
- Status: 🟡 Code complete, needs production verification
- Tool: Manual (deploy, trigger briefing, check logs)
- Estimated effort: 15-30 min
- Steps:
  1. Deploy commit cafae9c to Vercel
  2. Trigger manual briefing: `curl -X POST "https://backdrop.markets/admin/trigger-briefing?force=true"`
  3. Verify narrative pipeline: check MongoDB for new narratives/entity mentions
  4. Check Anthropic console logs for 200 responses with new model strings
- Once verified → mark BUG-030 completed

**Priority 2**: [TASK-001] Replace placeholder URLs + add OG/Twitter meta tags
- Status: Ready to implement (after BUG-030 verified)
- Tool: Claude Code
- Estimated effort: 30 min
- Files to update:
  - `cognitive-debt-simulator-v5.html` (6 instances of `YOUR_SUBSTACK_URL_HERE`)
  - Add `og:image` meta tag
  - Add Twitter card meta tags
- Blocker: None (use temp Substack URL, replace after publish)

**Priority 3**: [FEATURE-045] Add share mechanics to interactive site
- Status: Ready to implement
- Tool: Claude Code
- Estimated effort: 1–2 hours
- Blocker: None

**Priority 4**: [FEATURE-046] Add email capture / Substack embed
- Status: Ready to implement
- Tool: Claude Code
- Estimated effort: 30 min
- Blocker: None

**Priority 5**: [TASK-002] Mobile/desktop QA + fix broken animations
- Status: Blocked by TASK-001, FEATURE-045, FEATURE-046
- Tool: Claude Code
- Estimated effort: 1 hour

**Priority 6**: [TASK-003] Deploy interactive site to backdrop.markets
- Status: Blocked by TASK-002
- Tool: Claude Code
- Estimated effort: 30 min–1 hour

**Priority 7**: [TASK-004] Create OG image / social card
- Status: Ready (Claude Web)
- Tool: Claude Web
- Estimated effort: 30 min

**Priority 8**: [TASK-005] Final polish Substack draft
- Status: Ready (Claude Web)
- Tool: Claude Web
- Estimated effort: 1–2 hours

**Priority 9**: [TASK-006] Adapt article for LinkedIn (native post)
- Status: Blocked by TASK-005
- Tool: Claude Web
- Estimated effort: 1 hour

**Priority 10**: [TASK-007] Adapt article for X (native article or thread)
- Status: Blocked by TASK-005
- Tool: Claude Web
- Estimated effort: 1 hour

**Priority 11**: [TASK-008] Write all launch distribution copy
- Status: Blocked by TASK-005
- Tool: Claude Web
- Estimated effort: 1–2 hours

**Priority 12**: [TASK-009] Warm-up phase (T-36 to T-24)
- Status: Blocked by all dev + content work
- Tool: Manual
- Estimated effort: 1 hour spread across day

**Priority 13**: [TASK-010] Launch day execution
- Status: Final step
- Tool: Manual

---

## Task Routing

| Ticket | Type | Tool | Model |
|--------|------|------|-------|
| BUG-030 (verify in prod) | Bug | Manual | — |
| TASK-001 (placeholders + meta) | Task | Claude Code | Sonnet |
| FEATURE-045 (share buttons) | Feature | Claude Code | Sonnet |
| FEATURE-046 (email capture) | Feature | Claude Code | Sonnet |
| TASK-002 (QA) | Task | Claude Code | Sonnet |
| TASK-003 (deploy) | Task | Claude Code | Sonnet |
| TASK-004 (OG image) | Task | Claude Web | — |
| TASK-005 (Substack polish) | Task | Claude Web | — |
| TASK-006 (LinkedIn version) | Task | Claude Web | — |
| TASK-007 (X article) | Task | Claude Web | — |
| TASK-008 (launch copy) | Task | Claude Web | — |
| TASK-009 (warm-up) | Task | Manual | — |
| TASK-010 (launch execution) | Task | Manual | — |

---

## Key Assets
- Substack draft: `Full_Draft_-_revised-3.md`
- Interactive site: `cognitive-debt-simulator-v5.html`
- Hosting: Vercel — same domain as Backdrop (backdrop.markets)
- LinkedIn: https://www.linkedin.com/in/mikechavez3/

## Known Issues in Interactive Site
- 6 instances of `YOUR_SUBSTACK_URL_HERE` (lines 382, 483, 540, 586, 611, 629)
- No `og:image` meta tag
- No Twitter card meta tags
- No share/tweet buttons
- No email capture
- No score-sharing after routing mini-game
- Mobile untested

---

## Recently Completed
- ✅ BUG-029 closed (misdiagnosed — was not billing, was deprecated models)
- ✅ BUG-030 code changes merged (commit cafae9c) — 5 files updated, all deprecated model strings removed

---

## Quick Reference

### Verify BUG-030 in production
```bash
# 1. Trigger manual briefing
curl -X POST "https://backdrop.markets/admin/trigger-briefing?force=true"

# 2. Test Haiku directly
curl -s https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-haiku-4-5-20251001","max_tokens":10,"messages":[{"role":"user","content":"ping"}]}' \
  | jq '.content[0].text'

# 3. Confirm no stale strings (run from project root)
rg -n "claude-3-haiku-20240307|claude-3-5-haiku-20241022|claude-3-5-sonnet-20241022" --type py .
```

### Test Substack OG tags
```
https://cards-dev.twitter.com/validator
```