---
id: FEATURE-062
type: feature
status: complete
priority: high
complexity: medium
created: 2026-05-10
updated: 2026-05-10
branch: feature/062-deterministic-article-cluster-fallback
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
- [x] Locate the narratives page and narrative card component.
- [x] Read `display_mode`, `display_title`, `display_summary`, and `recent_article_count` from the narratives API response.
- [x] Render normal generated-summary card when `display_mode="summary"`.
- [x] Render article-cluster fallback card when `display_mode="article_cluster"`.
- [x] Preserve recent article list display.
- [x] Ensure no internal system-state language appears in public UI.
- [x] Add/update frontend tests if the project has frontend test coverage (no test framework exists).

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

- [x] Fresh trusted summaries render normally.
- [x] Article-cluster mode renders user-facing activity fallback.
- [x] Article-cluster mode does not show stale generated title/summary when display fields are provided.
- [x] Article-cluster mode still shows the recent article list.
- [x] Public UI does not display stale, missing, untrusted, needs refresh, or summary status.
- [x] No LLM calls are introduced.
- [x] Existing narratives page layout remains recognizable and not redesigned.

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

- **Status:** ✅ COMPLETE
- **Actual complexity:** Medium (straightforward rendering logic, display mode branching)
- **Branch:** `feature/062-deterministic-article-cluster-fallback`
- **Commit:** `61724d5`

### Key Decisions Made

1. **Display Field Preference:** Frontend prefers display fields from FEATURE-061 API for both summary and article-cluster modes. Legacy title/summary fields used only for backward compatibility.

2. **Article-Cluster Layout:** Clean, minimal layout showing only display_title, recent_article_count, and display_summary. Entity tags excluded from article-cluster mode (no internal metadata).

3. **Article List Preservation:** Articles section placed outside the display_mode conditional, ensuring both modes support expandable article lists and pagination.

4. **No Trust Computation:** Frontend never computes trust from timestamps. Trust determination is backend responsibility (FEATURE-061).

### Deviations from Plan

None. Ticket requirements met exactly.

### Tests Run

- ✅ TypeScript compilation: 0 errors
- ✅ Production build: 2148 modules, 145KB gzipped
- ✅ Code audit: Verified article-cluster mode does not render legacy title/summary when display fields present
- ✅ Backward compatibility: Summary mode works with and without display fields

No automated test framework exists in frontend (no jest/vitest). Ready for manual verification on dev/staging once FEATURE-061 deployed.

### Manual Verification

Pending deployment of FEATURE-061 to dev/staging. Test plan:
1. Mock or use Bitcoin stale-case narrative with display_mode="article_cluster"
2. Verify UI renders: "Bitcoin" → "8 recent articles" → "Latest coverage includes..."
3. Verify UI does NOT show: "Bitcoin Holds $75K...", "Old stale generated summary", entity tags
4. Verify article list expandable and pagination functional
5. Verify no internal status words in UI

### Implementation Details

**Files Modified:**
- `context-owl-ui/src/types/index.ts` — Extended Narrative interface
- `context-owl-ui/src/pages/Narratives.tsx` — Added display mode rendering logic

**Type Extensions:**
```typescript
display_mode?: "summary" | "article_cluster";
display_title?: string;
display_summary?: string | null;
recent_article_count?: number;
```

**Display Mode Computation (Lines 136-151):**
- cardTitle: prefers display_title → title → theme
- cardSummary: uses display_summary if defined, else summary/story
- displayMode: defaults to "summary" if not provided
- displayArticleCount: uses recent_article_count in article_cluster mode

**Rendering Logic (Lines 343-373):**
- article_cluster: renders {cardTitle}, {displayArticleCount} recent article(s), {cardSummary}
- summary: renders {cardTitle}, {cardSummary}, entity tags (preserved)
- Both modes: article list section remains unchanged (lines 375+)

**Backend Safety:**
- No backend files modified
- No data mutations
- No LLM calls added
