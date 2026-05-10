---
id: FEATURE-060
type: feature
status: backlog
priority: high
complexity: medium
created: 2026-05-10
updated: 2026-05-10
branch: feature/trusted-summary-briefing-eligibility
---

# FEATURE-060: Add Trusted Summary Eligibility for Briefings

## Problem/Opportunity

Briefings currently consume active narratives even when their generated summaries may be stale or missing freshness metadata. TASK-095 found 341 active narratives missing `last_summary_generated_at`, while only 4 were flagged for refresh.

The May 10 bad briefing was likely downstream of contradictory or stale narrative inputs combined with a refinement validation gap. Sprint 019 adopts a fresh-start trust boundary: briefings should synthesize only from trusted narrative summaries.

---

## Proposed Solution

Add trusted-summary eligibility logic to the briefing input path. The briefing agent should exclude narratives whose generated summary/title is not trusted.

A narrative is trusted for briefing synthesis if any of the following is true:

1. `first_seen >= FRESH_START_CUTOFF`
2. `last_summary_generated_at >= FRESH_START_CUTOFF`
3. `_fresh_start_validated_at >= FRESH_START_CUTOFF`

The initial cutoff should be configurable and default to `2026-05-10T00:00:00Z` if not configured.

Old narratives should not be deleted or modified. They are simply excluded from briefing synthesis unless they meet eligibility.

---

## User Story

As a reader of the crypto briefing, I want briefings to be generated only from trusted and current narrative summaries so that the briefing does not synthesize stale or contradictory narrative state.

---

## Implementation Scope

### In Scope
- [ ] Add a trusted-summary eligibility helper for narratives used by briefing generation.
- [ ] Apply the eligibility helper inside briefing input gathering before selecting the top active narratives.
- [ ] Add a configurable fresh-start cutoff date.
- [ ] Log how many narratives were excluded from briefing inputs due to untrusted summaries.
- [ ] Ensure the briefing can still generate with fewer than 15 narratives.
- [ ] Add tests for old missing-timestamp narratives being excluded.

### Out of Scope
- [ ] Do not change the public narratives page behavior in this ticket.
- [ ] Do not refresh old narratives.
- [ ] Do not delete old narratives.
- [ ] Do not mark narratives dormant.
- [ ] Do not change narrative clustering or matching.
- [ ] Do not add LLM calls.

---

## Files to Create

Test file, if no suitable existing test file exists:

```text
tests/**/test_briefing_narrative_eligibility.py
```

---

## Files to Modify

```text
src/crypto_news_aggregator/services/briefing_agent.py
src/crypto_news_aggregator/core/config.py
```

Potentially, if narrative query logic lives elsewhere:

```text
src/crypto_news_aggregator/db/operations/narratives.py
```

---

## Do Not Modify

```text
src/crypto_news_aggregator/tasks/narrative_refresh.py
src/crypto_news_aggregator/tasks/beat_schedule.py
context-owl-ui/
```

Do not modify production data.

---

## Exact Implementation Requirements

1. Locate the briefing narrative input gathering path. TASK-095 identified `briefing_agent.py` as the relevant file and noted article hydration in `briefing_agent.py:322`.
2. Add a helper similar to:

```python
def _is_narrative_summary_trusted(narrative: dict[str, Any], cutoff: datetime) -> bool:
    """Return True if this narrative summary is trusted for briefing synthesis."""
```

3. The helper must return `True` if:

```text
first_seen >= cutoff
OR last_summary_generated_at >= cutoff
OR _fresh_start_validated_at >= cutoff
```

4. The helper must return `False` for active legacy narratives where:

```text
first_seen < cutoff
last_summary_generated_at missing
_fresh_start_validated_at missing
```

5. Apply this helper before passing narratives into prompt construction.
6. Preserve existing sorting/ranking among eligible narratives.
7. Do not mutate narrative records.
8. Log counts:

```text
active_narratives_considered
trusted_narratives_selected
untrusted_narratives_excluded
```

9. If fewer than 15 trusted narratives exist, continue with the available trusted narratives. Do not backfill with untrusted narratives.
10. Ensure prompt language tolerates fewer narratives.
11. Add config setting:

```text
FRESH_START_CUTOFF=2026-05-10T00:00:00Z
```

If the project uses a different config naming style, use the existing convention but keep the setting explicit.

### Required Interfaces / Schemas

Suggested config field:

```python
FRESH_START_CUTOFF: str = "2026-05-10T00:00:00Z"
```

Suggested parsed helper:

```python
def get_fresh_start_cutoff() -> datetime:
    ...
```

---

## Acceptance Criteria

- [ ] Briefing input gathering excludes active legacy narratives missing `last_summary_generated_at` when `first_seen` is before the cutoff.
- [ ] Briefing input gathering includes narratives with `first_seen >= cutoff`.
- [ ] Briefing input gathering includes old narratives with `last_summary_generated_at >= cutoff`.
- [ ] Briefing input gathering includes old narratives with `_fresh_start_validated_at >= cutoff`.
- [ ] The system can generate a briefing with fewer than 15 trusted narratives.
- [ ] The code logs how many narratives were excluded.
- [ ] No narrative documents are modified.
- [ ] No LLM calls are added.

---

## Test Plan

### Automated Tests

```bash
pytest tests -k "trusted and narrative and briefing"
```

Required test coverage:

- [ ] Old active narrative with missing `last_summary_generated_at` is excluded.
- [ ] Old active narrative with `last_summary_generated_at` after cutoff is included.
- [ ] New narrative with `first_seen` after cutoff is included.
- [ ] Old narrative with `_fresh_start_validated_at` after cutoff is included.
- [ ] Missing or malformed timestamp fails closed, meaning excluded from briefing synthesis.
- [ ] Fewer than 15 eligible narratives does not crash prompt construction.

### Manual Verification

Run a read-only query before and after local implementation to compare eligible counts.

```javascript
const cutoff = ISODate("2026-05-10T00:00:00Z");
db.narratives.countDocuments({
  lifecycle_state: { $in: ["emerging", "rising", "hot", "reactivated"] },
  $or: [
    { first_seen: { $gte: cutoff } },
    { last_summary_generated_at: { $gte: cutoff } },
    { _fresh_start_validated_at: { $gte: cutoff } }
  ]
})
```

Expected: this count represents narratives eligible for briefing synthesis.

---

## Dependencies

- BUG-099 should be completed first so invalid briefings fail closed even if trusted inputs are sparse.

---

## Open Questions

- [ ] Confirm whether `first_seen`, `last_summary_generated_at`, and `_fresh_start_validated_at` are all stored as Mongo dates when present.
- [ ] Confirm final environment variable naming convention.

---

## Rollback Plan

- [ ] Disable the fresh-start cutoff by setting the cutoff to an old date before all narratives, for example `1970-01-01T00:00:00Z`.
- [ ] Revert the helper and filtering changes if needed.
- [ ] Since no production data is mutated, rollback is code/config only.

---

## Completion Summary

- Actual complexity:
- Branch:
- Commit:
- Key decisions made:
- Deviations from plan:
- Tests run:
- Manual verification:
