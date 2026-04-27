---
id: BUG-081
type: bug
status: backlog
priority: medium
severity: medium
created: 2026-04-15
updated: 2026-04-15
---

# Briefing presents duplicate events as separate stories and references unnamed entities

## Problem
The April 14 evening briefing has three quality issues caused by missing guardrails in the system and critique prompts:

1. **Duplicate event coverage:** The Polkadot/Hyperbridge bridge exploit is presented as two separate stories — one paragraph about a "Polkadot bridge breach" minting $1.1B in unauthorized DOT, and a separate paragraph about a "Hyperbridge exploit" minting "over 1 billion fake DOT tokens." These are the same event from different source articles that were clustered into separate narratives upstream. The briefing should consolidate them.

2. **Unnamed entity references:** The briefing says "A major security incident affected two platforms" but only names Kraken. The second platform is never identified — the LLM confabulated a count from incomplete source data rather than limiting claims to what it could name.

3. **Implausible figures unchallenged:** The briefing cites "$204.7B" in liquidations within 24 hours. This would be ~7-10% of the entire crypto market cap and historically unprecedented. The critique/refine loop did not flag it.

## Expected Behavior
- When multiple narratives describe the same event, the briefing should synthesize them into one consolidated account.
- The briefing should never reference unnamed entities — if it can't name a platform, it shouldn't claim one exists.
- The critique pass should flag figures that are implausible relative to total crypto market cap.

## Actual Behavior
The system prompt has no rule about consolidating overlapping narratives, no rule about unnamed entities, and the critique prompt has no check for implausible figures. The LLM passes the self-refine loop without these issues being caught.

## Steps to Reproduce
1. Feed the briefing agent narratives that cover the same event from different angles
2. Include a narrative with incomplete entity details
3. Include a narrative with a suspiciously large financial figure
4. Observe that the generated briefing presents duplicates, references unnamed entities, and passes the implausible figure through critique unchallenged

## Environment
- Environment: production
- User impact: medium — degrades briefing quality and credibility

---

## Resolution

**Status:** ✅ COMPLETE — 2026-04-15

### Root Cause
The system prompt in `_get_system_prompt()` lacks rules for narrative consolidation and unnamed entity prevention. The critique prompt in `_build_critique_prompt()` lacks checks for duplicate events, unnamed entities, and figure plausibility.

### Changes Made

**File: `crypto_news_aggregator/services/briefing_agent.py`**

**Change 1 — Add rules 9, 10, 11 to system prompt in `_get_system_prompt()` (between rule 8 and GOOD EXAMPLE)**

Find:
```
   - NEVER suggest topics or narratives that weren't provided

GOOD EXAMPLE:
```

Replace with:
```
   - NEVER suggest topics or narratives that weren't provided

9. CONSOLIDATE DUPLICATE EVENTS
   - If multiple narratives clearly describe the same underlying event from different angles, synthesize them into a single coherent account
   - Do NOT present the same event twice with different framing
   - Look for overlapping entities, similar dollar amounts, or the same infrastructure/platform involved
   - Example: Two narratives about a Polkadot bridge exploit should become one consolidated paragraph, not two separate sections

10. NO UNNAMED ENTITIES
    - If you cannot name a specific platform, exchange, or entity from the provided narratives, do not reference it
    - NEVER use phrases like "two platforms", "multiple exchanges", or "several protocols" unless you can name each one explicitly
    - NEVER imply a count of affected parties you cannot enumerate by name
    - If a narrative lacks specific details, acknowledge the limitation rather than implying unnamed actors

11. VERIFY FIGURE PLAUSIBILITY
    - Before citing any financial figure, consider whether it is plausible given the total crypto market cap (~$2-3T)
    - A single-event liquidation exceeding $50B, a hack exceeding $10B, or similar extremes are almost certainly errors in the source data
    - If a figure seems implausible, flag the uncertainty: "reported figures suggest $X, though this would be historically unprecedented"
    - When source articles disagree on a figure, note the discrepancy rather than picking the most dramatic number

GOOD EXAMPLE:
```

**Change 2 — Add checks 8, 9, 10 to critique prompt in `_build_critique_prompt()` (between check 7 and "Respond with")**

Find:
```
7. ABRUPT TRANSITIONS: Does it switch topics mid-paragraph without logical connection?

Respond with:
```

Replace with:
```
7. ABRUPT TRANSITIONS: Does it switch topics mid-paragraph without logical connection?

8. DUPLICATE EVENTS: Does the briefing describe the same underlying event more than once with different framing? Look for overlapping entities, similar figures, or the same infrastructure involved. If two sections cover the same incident, this is a critical issue — they must be consolidated into one account.

9. UNNAMED ENTITIES: Does the briefing reference unnamed platforms, exchanges, or entities? Phrases like "two platforms", "multiple exchanges", or "several protocols" without naming each one are NOT acceptable. Every referenced entity must be explicitly named from the provided narratives.

10. IMPLAUSIBLE FIGURES: Are any cited figures implausible relative to the total crypto market (~$2-3T)? A single-event liquidation exceeding $50B, a hack exceeding $10B, or similar extremes would be historically unprecedented and likely an error. Flag any such figures.

Respond with:
```

### Testing
1. Trigger a test briefing with narratives known to overlap (e.g., two narratives about the same Polkadot exploit). Verify the output consolidates them into one section.
2. Provide a narrative with incomplete entity details and verify the briefing does not reference unnamed platforms.
3. Provide a narrative containing "$204.7B in liquidations" and verify the critique pass flags it as implausible, triggering a refinement that either corrects or hedges the figure.
4. Run existing briefing generation tests to confirm no regressions.

### Implementation Details

**System Prompt Rules 9-11 Added:**
- Rule 9: Consolidate duplicate events from different narrative angles into single coherent account
- Rule 10: Prevent unnamed entity references — every entity must be explicitly named
- Rule 11: Verify figure plausibility against ~$2-3T crypto market cap baseline

**Critique Prompt Checks 8-10 Added:**
- Check 8: Detect duplicate events with different framing — flag as critical
- Check 9: Detect unnamed entity references — require explicit names from narratives
- Check 10: Detect implausible figures — flag extremes ($50B+ liquidations, $10B+ hacks) as historically unprecedented

**Code Changes (commit bd2a8c7):**
- Lines 545-561: Added system prompt rules 9-11
- Lines 697-701: Added critique checks 8-10

**Test Coverage (commit 891d073):**
- Created `tests/services/test_bug_081_briefing_quality.py` with 7 comprehensive tests
- All 7 new tests pass ✅
- All 5 existing briefing prompt tests pass (no regressions) ✅

### Files Changed
- `src/crypto_news_aggregator/services/briefing_agent.py` — added system + critique rules
- `tests/services/test_bug_081_briefing_quality.py` — new test file (7 tests)