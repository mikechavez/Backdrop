---
id: FEATURE-061
type: feature
status: backlog
priority: high
complexity: medium
created: 2026-05-10
updated: 2026-05-10
branch: feature/narrative-display-mode-api
---

# FEATURE-061: Add Narrative Display Mode API Fields

## Problem/Opportunity

The narratives page should stay populated by recent article activity even when generated narrative summaries are stale or missing. However, the frontend should not need to infer summary trust from raw timestamps, and public users should not see internal labels like stale, missing, untrusted, or needs refresh.

The API should provide product-oriented display fields that let the frontend render either a normal generated-summary card or a deterministic article-cluster card.

---

## Proposed Solution

Add backend/API display fields for public narrative responses:

```json
{
  "display_mode": "summary",
  "display_title": "Generated narrative title",
  "display_summary": "Generated narrative summary",
  "recent_article_count": 8
}
```

or:

```json
{
  "display_mode": "article_cluster",
  "display_title": "Bitcoin",
  "display_summary": "Latest coverage includes Bitcoin holding near $80K, ETF outflows, options positioning, and Fed inflation concerns.",
  "recent_article_count": 8
}
```

The API may compute internal summary status, but public-facing API fields should support polished product rendering.

---

## User Story

As a user viewing the narratives page, I want recent article clusters to remain visible even when generated summaries are not trusted, so that I can still see what is currently being covered without seeing stale generated text.

---

## Implementation Scope

### In Scope
- [ ] Locate public narratives API endpoint and response formatting.
- [ ] Add `display_mode` to narrative API responses.
- [ ] Add `display_title` to narrative API responses.
- [ ] Add `display_summary` to narrative API responses.
- [ ] Add `recent_article_count` to narrative API responses if not already present.
- [ ] Compute display mode based on summary trust and recent activity.
- [ ] Keep the narratives page activity-based using recent `last_updated` narratives.
- [ ] Do not expose internal user-facing copy such as stale, missing, untrusted, or needs refresh.

### Out of Scope
- [ ] Do not modify frontend rendering in this ticket.
- [ ] Do not generate fallback copy with an LLM.
- [ ] Do not refresh old narratives.
- [ ] Do not delete or mutate narrative records.
- [ ] Do not change briefing narrative selection in this ticket.

---

## Files to Create

Test file, if no suitable existing test file exists:

```text
tests/**/test_narrative_display_mode_api.py
```

---

## Files to Modify

Exact endpoint files must be located by implementation agent. Start with:

```text
src/crypto_news_aggregator/api/v1/endpoints/
src/crypto_news_aggregator/db/operations/narratives.py
src/crypto_news_aggregator/services/narrative_service.py
```

Do not search unrelated areas unless these do not contain the public narratives endpoint.

---

## Do Not Modify

```text
src/crypto_news_aggregator/tasks/narrative_refresh.py
src/crypto_news_aggregator/tasks/beat_schedule.py
src/crypto_news_aggregator/services/briefing_agent.py
context-owl-ui/
```

Do not modify production data.

---

## Exact Implementation Requirements

1. Locate the API endpoint used by the public narratives page.
2. Locate the response formatter/model for narrative cards.
3. Add a backend helper similar to:

```python
def get_narrative_display_mode(narrative: dict[str, Any], cutoff: datetime) -> str:
    """Return 'summary' or 'article_cluster'."""
```

4. Use `display_mode="summary"` only when the generated summary is trusted.
5. Use `display_mode="article_cluster"` when the generated summary is not trusted but the narrative has recent article activity.
6. Summary trust should use the same cutoff semantics as FEATURE-060:

```text
first_seen >= cutoff
OR last_summary_generated_at >= cutoff
OR _fresh_start_validated_at >= cutoff
```

7. For `display_mode="summary"`:

```text
display_title = existing generated narrative title
display_summary = existing generated summary or description field
```

8. For `display_mode="article_cluster"`:

```text
display_title = deterministic primary topic/entity, not stale generated title
display_summary = deterministic article-activity sentence, no LLM
```

9. Do not expose the words stale, missing, untrusted, or needs refresh in public display fields.
10. If internal/debug fields are added, keep them separate from public user-facing copy.
11. Ensure old narratives with recent `last_updated` can still appear in the public narratives API as article clusters.

### Required Interfaces / Schemas

Add fields to the narrative response schema, using existing model style:

```python
display_mode: Literal["summary", "article_cluster"]
display_title: str
display_summary: str | None
recent_article_count: int
```

Optional internal/debug fields only if useful:

```python
summary_status: Literal["fresh", "stale", "missing"] | None
summary_status_reason: str | None
```

If added, these fields must not be used as public copy in frontend.

---

## Acceptance Criteria

- [ ] Narrative API returns `display_mode` for each public narrative.
- [ ] Narrative API returns `display_title` for each public narrative.
- [ ] Narrative API returns `display_summary` for each public narrative or `null` only if fallback sentence cannot be built.
- [ ] Trusted summaries use existing generated title/summary.
- [ ] Untrusted summaries use article-cluster display mode.
- [ ] Untrusted article-cluster mode does not return stale generated title as `display_title`.
- [ ] Public display fields do not include words like stale, missing, untrusted, or needs refresh.
- [ ] Old narratives with recent articles remain eligible for the narratives page.
- [ ] No LLM calls are added.

---

## Test Plan

### Automated Tests

```bash
pytest tests -k "narrative and display and api"
```

Required test coverage:

- [ ] Fresh trusted narrative returns `display_mode="summary"`.
- [ ] Old narrative missing `last_summary_generated_at` but with recent articles returns `display_mode="article_cluster"`.
- [ ] Article-cluster mode uses deterministic topic/entity for `display_title`.
- [ ] Article-cluster mode does not expose stale generated summary as `display_summary`.
- [ ] Public display fields do not include internal system-state words.
- [ ] No LLM provider is called in display-mode formatting tests.

### Manual Verification

Use the Bitcoin stale narrative as a model case:

```text
Generated title: Bitcoin Holds $75K Amid Geopolitical Tensions and Strong ETF Inflows
Recent articles: BTC around $80K
Expected display_mode: article_cluster
Expected display_title: Bitcoin
Expected display_summary: article-activity sentence based on latest article titles
```

---

## Dependencies

- FEATURE-060 defines trusted-summary cutoff semantics. Use the same config/helper if possible.

---

## Open Questions

- [ ] Locate exact public narratives endpoint and schema.
- [ ] Confirm whether the existing narrative schema uses `summary` or `description` for generated summary text.

---

## Rollback Plan

- [ ] Revert API schema/formatter additions.
- [ ] Frontend can continue using existing narrative title/summary fields until FEATURE-062 is deployed.
- [ ] Since no production data is mutated, rollback is code only.

---

## Completion Summary

- Actual complexity:
- Branch:
- Commit:
- Key decisions made:
- Deviations from plan:
- Tests run:
- Manual verification:
