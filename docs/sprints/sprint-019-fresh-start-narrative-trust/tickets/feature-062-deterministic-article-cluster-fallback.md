---
id: FEATURE-062
type: feature
status: backlog
priority: high
complexity: medium
created: 2026-05-10
updated: 2026-05-10
branch: feature/deterministic-article-cluster-fallback
---

# FEATURE-062: Add Deterministic Article Cluster Fallback

## Problem/Opportunity

When generated narrative summaries are stale or missing, the public narratives page should not show the stale generated title/summary as authoritative. But it should still show useful recent article activity.

The fallback must be production-grade and user-facing. It must not show internal language like stale, missing, untrusted, or needs refresh. It must also not use an LLM.

---

## Proposed Solution

Update the narrative card UI to use the API display contract from FEATURE-061.

If `display_mode="summary"`, render the existing generated narrative card.

If `display_mode="article_cluster"`, render a deterministic activity card:

```text
Bitcoin
8 recent articles
Latest coverage includes Bitcoin holding near $80K, ETF outflows, options positioning, and Fed inflation concerns.
```

The copy should come from backend-provided `display_title`, `display_summary`, and `recent_article_count`. The frontend should not infer trust from timestamps.

---

## User Story

As a user viewing narratives, I want stale generated summaries to gracefully degrade into recent article activity so that I still understand what the cluster is about without seeing misleading old summary text.

---

## Implementation Scope

### In Scope
- [ ] Locate the narratives page and narrative card component.
- [ ] Read `display_mode`, `display_title`, `display_summary`, and `recent_article_count` from the narratives API response.
- [ ] Render normal generated-summary card when `display_mode="summary"`.
- [ ] Render article-cluster fallback card when `display_mode="article_cluster"`.
- [ ] Preserve recent article list display.
- [ ] Ensure no internal system-state language appears in public UI.
- [ ] Add/update frontend tests if the project has frontend test coverage.

### Out of Scope
- [ ] Do not change backend API in this ticket.
- [ ] Do not add an LLM call.
- [ ] Do not add refresh buttons or admin controls.
- [ ] Do not redesign the narratives page.
- [ ] Do not hide recent article clusters just because summary is untrusted.

---

## Files to Create

Only if no suitable frontend test file exists:

```text
context-owl-ui/**/__tests__/*Narrative*.test.*
```

---

## Files to Modify

Exact frontend files must be located by implementation agent. Start with:

```text
context-owl-ui/
```

Expected file types to locate:

```text
Narratives page component
Narrative card component
Narratives API client/types
```

Do not search backend files except to confirm response field names from FEATURE-061.

---

## Do Not Modify

```text
src/crypto_news_aggregator/services/briefing_agent.py
src/crypto_news_aggregator/services/narrative_service.py
src/crypto_news_aggregator/tasks/
src/crypto_news_aggregator/db/
```

Do not modify production data.

---

## Exact Implementation Requirements

1. Locate the frontend component that renders narrative cards.
2. Locate the API client/types used by the narratives page.
3. Extend the frontend type/interface to include:

```typescript
display_mode?: "summary" | "article_cluster";
display_title?: string;
display_summary?: string | null;
recent_article_count?: number;
```

4. Use `display_title` as the card title when present.
5. Use `display_summary` as the displayed summary when present.
6. For `display_mode="summary"`, preserve the existing card layout as much as possible.
7. For `display_mode="article_cluster"`, render:

```text
{display_title}
{recent_article_count} recent articles
{display_summary}
```

8. Continue rendering the existing recent articles list under the card.
9. Do not render the old generated `title` or `summary` in article-cluster mode if backend provided display fields.
10. Do not show labels or copy containing:

```text
stale
missing
untrusted
needs refresh
summary status
```

11. If the API does not yet provide display fields, fall back to current behavior temporarily but document that FEATURE-061 is required.
12. Do not add frontend logic that computes trust from raw timestamps.

### Required Interfaces / Schemas

Expected API shape from FEATURE-061:

```typescript
type NarrativeDisplayMode = "summary" | "article_cluster";

interface Narrative {
  display_mode?: NarrativeDisplayMode;
  display_title?: string;
  display_summary?: string | null;
  recent_article_count?: number;
  // existing fields remain
}
```

---

## Acceptance Criteria

- [ ] Fresh trusted summaries render normally.
- [ ] Article-cluster mode renders user-facing activity fallback.
- [ ] Article-cluster mode does not show stale generated title/summary when display fields are provided.
- [ ] Article-cluster mode still shows the recent article list.
- [ ] Public UI does not display stale, missing, untrusted, needs refresh, or summary status.
- [ ] No LLM calls are introduced.
- [ ] Existing narratives page layout remains recognizable and not redesigned.

---

## Test Plan

### Automated Tests

Run frontend tests according to project conventions. If unknown, inspect `context-owl-ui/package.json`.

Possible commands:

```bash
cd context-owl-ui
npm test
npm run test
npm run lint
```

Required test coverage if frontend tests exist:

- [ ] `display_mode="summary"` renders normal summary card.
- [ ] `display_mode="article_cluster"` renders display title, recent article count, and fallback summary.
- [ ] Article-cluster mode does not render stale generated title if different from display title.
- [ ] Internal status words are not present in rendered text.

### Manual Verification

1. Mock or use API response for Bitcoin stale case:

```json
{
  "display_mode": "article_cluster",
  "display_title": "Bitcoin",
  "display_summary": "Latest coverage includes Bitcoin holding near $80K, ETF outflows, options positioning, and Fed inflation concerns.",
  "recent_article_count": 8
}
```

2. Confirm UI shows:

```text
Bitcoin
8 recent articles
Latest coverage includes Bitcoin holding near $80K, ETF outflows, options positioning, and Fed inflation concerns.
```

3. Confirm UI does not show:

```text
Bitcoin Holds $75K Amid Geopolitical Tensions and Strong ETF Inflows
Summary needs refresh
Stale
Untrusted
Missing
```

---

## Dependencies

- FEATURE-061 should be completed first so the frontend has `display_mode` and display fields.

---

## Open Questions

- [ ] Locate exact frontend narrative page/card files.
- [ ] Confirm frontend package manager and test command.

---

## Rollback Plan

- [ ] Revert frontend rendering changes.
- [ ] Since backend fields are additive, rollback does not require backend data changes.

---

## Completion Summary

- Actual complexity:
- Branch:
- Commit:
- Key decisions made:
- Deviations from plan:
- Tests run:
- Manual verification:
