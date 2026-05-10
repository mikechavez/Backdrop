---
id: BUG-099
type: bug
status: backlog
priority: high
severity: high
created: 2026-05-10
updated: 2026-05-10
branch: fix/prevent-invalid-briefings-publishing
---

# BUG-099: Prevent Invalid Briefings From Publishing

## Problem

A production morning briefing published invalid model meta-output instead of a valid briefing. The saved `content.narrative` asked for narrative titles, summaries, and entity names.

TASK-095 confirmed that `_parse_briefing_response()` can fall back to raw LLM text as `narrative` when JSON parsing fails, assigning `confidence_score=0.3`. `_save_briefing()` then publishes non-smoke briefings without validating confidence, empty insights, parse failure, or model meta-output.

---

## Expected Behavior

Malformed, low-confidence, empty, or model-meta briefing output must not be published to public users.

If a briefing generation/refinement result is invalid, the system should either:

1. not save it, or
2. save it as an unpublished failure/debug record with metadata indicating why it was rejected.

The public briefing API should continue returning the latest valid published briefing.

---

## Actual Behavior

A bad briefing was saved with:

```text
confidence_score: 0.3
key_insights: []
content.narrative: request for missing narrative data
published: true
```

The public briefing page then displayed it until it was manually unpublished.

---

## Impact

- Environment: production
- User impact: high
- Operational impact: public briefing page can show model meta-output instead of a briefing
- Cost/performance/data impact: no direct cost increase, but failed generations can still consume LLM budget and produce unusable artifacts

---

## Evidence

### Logs / Trace IDs / Screenshots

```text
Bad briefing:
_id: 6a00734544c1c6f85c7266f1
type: morning
generated_at: 2026-05-10T12:00:00.512Z
task_id: 9ec83c1e-5dd7-423c-a70e-831b10a2375f
metadata.confidence_score: 0.3
metadata.refinement_iterations: 1
content.key_insights: []
content.narrative: asks user to provide narrative titles, summaries, and entity names
```

TASK-095 findings:

```text
briefing_agent.py:831-890: _parse_briefing_response() accepts raw text on JSON decode failure.
briefing_agent.py:940-1012: _save_briefing() publishes non-smoke briefings without quality validation.
db/operations/briefing.py:63-76: public latest briefing query filters published/smoke only, not quality.
api/v1/endpoints/briefing.py:229-260: public endpoint returns latest production briefing without validity filtering.
```

### Known Facts

- [ ] JSON parse failure currently returns `GeneratedBriefing(narrative=response_text[:2000], key_insights=[], confidence_score=0.3)`.
- [ ] `_save_briefing()` sets `published = not is_smoke`.
- [ ] Public briefing filtering only checks production/smoke fields.
- [ ] Bad briefing was manually unpublished after discovery.

### Hypotheses

- [ ] Some tests may currently expect the raw-text fallback behavior and will need updates.

---

## Steps to Reproduce

1. Mock `_call_llm()` or `_generate_with_llm()` to return plain text instead of valid JSON.
2. Ensure the text contains a request for missing data, for example `Please provide the active narrative data`.
3. Run the briefing parse/save flow for a non-smoke briefing.
4. Observe that the current code can save and publish the raw text as `content.narrative`.

---

## Files to Inspect

```text
src/crypto_news_aggregator/services/briefing_agent.py
src/crypto_news_aggregator/db/operations/briefing.py
src/crypto_news_aggregator/api/v1/endpoints/briefing.py
```

---

## Files to Modify

```text
src/crypto_news_aggregator/services/briefing_agent.py
src/crypto_news_aggregator/db/operations/briefing.py
src/crypto_news_aggregator/api/v1/endpoints/briefing.py
```

Test files to locate or create:

```text
tests/**/test_briefing_agent*.py
tests/**/test_briefing*.py
```

---

## Do Not Modify

```text
src/crypto_news_aggregator/services/narrative_service.py
src/crypto_news_aggregator/tasks/narrative_refresh.py
src/crypto_news_aggregator/tasks/beat_schedule.py
context-owl-ui/
```

Do not modify production data. Do not trigger briefing generation against production.

---

## Fix Requirements

- [ ] Add explicit parse-failure tracking to `GeneratedBriefing` or an equivalent internal result structure.
- [ ] Do not treat arbitrary non-JSON LLM output as valid publishable briefing content.
- [ ] Add a publishability validation step before inserting a public briefing.
- [ ] Reject publishable status when `confidence_score < 0.5`.
- [ ] Reject publishable status when `key_insights` is empty.
- [ ] Reject publishable status when `narrative` is empty or whitespace.
- [ ] Reject publishable status when narrative contains model-meta or missing-data request language.
- [ ] Suggested phrase patterns include:
  - `I need the actual narrative data`
  - `please provide`
  - `I don't have access`
  - `AVAILABLE DATA`
  - `Could you provide`
  - `I'm ready to execute`
  - `before I can generate`
- [ ] Invalid outputs must not be returned by the public latest briefing API.
- [ ] Log rejected briefing output with `briefing_type`, `task_id`, confidence score, and rejection reason.
- [ ] If saving invalid output for debugging, save with `published=false` and metadata such as:

```python
{
    "invalid_output": True,
    "invalid_reason": "parse_failed_or_model_meta_output",
    "invalidated_at": datetime.now(timezone.utc),
}
```

### Required Interfaces / Schemas

Prefer a small helper in `briefing_agent.py`:

```python
def _validate_briefing_publishable(generated: GeneratedBriefing) -> tuple[bool, str | None]:
    """Return whether a generated briefing is safe to publish and a rejection reason if not."""
```

If `GeneratedBriefing` is a dataclass, add optional fields only if needed:

```python
parse_failed: bool = False
raw_response_excerpt: str | None = None
```

---

## Verification Plan

### Automated Tests

```bash
pytest tests -k "briefing and (parse or publish or invalid)"
```

Required cases:

- [ ] Plain text LLM response does not produce a published briefing.
- [ ] JSON parse failure marks briefing invalid or returns unpublished failure.
- [ ] `confidence_score < 0.5` is rejected for publication.
- [ ] Empty `key_insights` is rejected for publication.
- [ ] Empty narrative is rejected for publication.
- [ ] Narrative containing missing-data request language is rejected for publication.
- [ ] Valid JSON briefing with confidence >= 0.5 and non-empty insights can publish.

### Manual Verification

1. Query latest public briefing after tests or local smoke flow.
2. Expected result: latest public briefing never contains phrases like `please provide`, `I don't have access`, or `AVAILABLE DATA`.
3. Confirm the manually invalidated May 10 briefing remains unpublished.

Mongo check:

```javascript
db.daily_briefings.find(
  {
    published: true,
    "content.narrative": /please provide|I don't have access|AVAILABLE DATA|I need the actual narrative data|before I can generate/i
  },
  { type: 1, generated_at: 1, "content.narrative": 1, metadata: 1 }
)
```

Expected: no results.

---

## Regression Risk

- Risk level: medium
- Areas to watch:
  - Briefings may fail closed and users may see the previous valid briefing.
  - Existing tests may assume parse fallback returns a minimal briefing.
  - If validation is too strict, valid briefings could be rejected.

Mitigation:

- Keep validation rules explicit and test-backed.
- Log rejected outputs with reason.
- Do not delete invalid generations unless explicitly decided.

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
