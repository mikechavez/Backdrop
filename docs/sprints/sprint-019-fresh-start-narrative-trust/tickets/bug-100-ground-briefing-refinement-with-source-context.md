---
id: BUG-100
type: bug
status: backlog
priority: medium
severity: medium
created: 2026-05-10
updated: 2026-05-10
branch: fix/ground-briefing-refinement-context
---

# BUG-100: Ground Briefing Refinement With Source Context

## Problem

The briefing refinement prompt references `AVAILABLE DATA` but only includes counts of signals, narratives, and patterns. It does not include actual narrative titles, summaries, entities, article titles, signal details, or pattern details.

When critique identified hallucinations and missing sources, the refinement model asked for the missing data instead of producing a corrected briefing.

---

## Expected Behavior

When self-refine runs, the refinement prompt should include enough source context for the model to correct the briefing without asking for more data.

The model should be instructed to return valid JSON only and remove unsupported claims rather than requesting additional data.

---

## Actual Behavior

TASK-095 found that `_build_refinement_prompt()` includes:

```text
AVAILABLE DATA:
- Signals: {count} trending entities
- Narratives: {count} active narratives
- Patterns: {count} detected patterns
```

But it does not include the actual available data.

---

## Impact

- Environment: production
- User impact: medium to high when refinement runs
- Operational impact: refinement can degrade output or ask for source material
- Cost/performance/data impact: minor token increase expected after fix

---

## Evidence

### Logs / Trace IDs / Screenshots

Bad briefing narrative included:

```text
I appreciate the detailed critique, but I need to pause and request the actual narrative data before I can generate a corrected briefing.
```

TASK-095 findings:

```text
briefing_agent.py:619-689: _build_generation_prompt() includes narrative details.
briefing_agent.py:691-758: _build_critique_prompt() includes briefing, key insights, available narrative titles, and entities.
briefing_agent.py:765-786: _build_refinement_prompt() includes original briefing, critique feedback, and counts only.
briefing_agent.py:393-501: _self_refine() saves the last refinement output regardless of quality unless other validation exists.
```

### Known Facts

- [ ] Generation prompt includes narrative titles and summaries.
- [ ] Critique prompt includes narrative titles and entities.
- [ ] Refinement prompt lacks actual source context.
- [ ] Refinement prompt says valid JSON only, but BUG-099 is needed to enforce this.

### Hypotheses

- [ ] Adding source context will reduce refinement refusals and missing-data requests.
- [ ] Prompt token count will increase modestly when refinement runs.

---

## Steps to Reproduce

1. Create or mock a briefing input with multiple narratives.
2. Build the generation prompt and observe narrative details are present.
3. Build the refinement prompt for the same input.
4. Observe that only counts are included under `AVAILABLE DATA`, not the actual narrative details.

---

## Files to Inspect

```text
src/crypto_news_aggregator/services/briefing_agent.py
```

---

## Files to Modify

```text
src/crypto_news_aggregator/services/briefing_agent.py
```

Test files to locate or create:

```text
tests/**/test_briefing_agent*.py
tests/**/test_briefing_refinement*.py
```

---

## Do Not Modify

```text
src/crypto_news_aggregator/services/narrative_service.py
src/crypto_news_aggregator/tasks/narrative_refresh.py
src/crypto_news_aggregator/tasks/beat_schedule.py
context-owl-ui/
```

Do not modify production data.

---

## Fix Requirements

- [ ] Update `_build_refinement_prompt()` to include actual source context.
- [ ] Include top narrative titles and summaries from `briefing_input.narratives`.
- [ ] Include narrative entities where available.
- [ ] Include article titles/sources where already available in `briefing_input` without adding new DB calls.
- [ ] Include signal details and pattern details if already present in `briefing_input`.
- [ ] Do not add new LLM calls.
- [ ] Do not add new database calls unless the existing input does not contain any needed context. If new DB calls are required, stop and document the blocker.
- [ ] Keep context bounded to avoid token explosion.
- [ ] Recommended limit: top 8 narratives, top 5 entities per narrative, top 3 article titles per narrative if available.
- [ ] Prompt must explicitly instruct:
  - return valid JSON only
  - do not ask for additional data
  - use only provided source context
  - if unsupported, remove the claim
  - if context is sparse, produce a conservative briefing
- [ ] Coordinate with BUG-099 so non-JSON output fails closed.

---

## Verification Plan

### Automated Tests

```bash
pytest tests -k "briefing and refine"
```

Required cases:

- [ ] Refinement prompt includes narrative titles.
- [ ] Refinement prompt includes narrative summaries/facts when available.
- [ ] Refinement prompt includes narrative entities when available.
- [ ] Refinement prompt includes instructions not to ask for additional data.
- [ ] Refinement prompt includes valid JSON only instruction.
- [ ] Refinement prompt does not include only counts under `AVAILABLE DATA`.
- [ ] Prompt size remains bounded for 15 narratives.

### Manual Verification

Create a sample refinement prompt locally and inspect it.

Expected:

```text
ORIGINAL BRIEFING: ...
CRITIQUE FEEDBACK: ...
AVAILABLE SOURCE CONTEXT:
Narrative 1: title, summary, entities
Narrative 2: title, summary, entities
...
Return ONLY valid JSON. Do not ask for additional data.
```

---

## Regression Risk

- Risk level: medium
- Areas to watch:
  - Prompt length and cost.
  - Model output format stability.
  - Refinement overfitting to source snippets.

Mitigation:

- Bound context.
- Add tests against prompt structure.
- Rely on BUG-099 publishability gate for fail-closed behavior.

---

## Resolution

**Status:** Open  
**Fixed:** YYYY-MM-DD  
**Branch:**  
**Commit:**

### Root Cause

<!-- Fill after fixing. -->

### Changes Made

<!-- Fill after fixing. -->

### Testing

<!-- Fill after fixing. -->

### Files Changed

<!-- Fill after fixing. -->
