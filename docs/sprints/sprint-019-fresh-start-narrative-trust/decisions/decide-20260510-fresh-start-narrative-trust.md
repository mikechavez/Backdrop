# Decision: Fresh-Start Narrative Trust Layer

**Date:** 2026-05-10  
**Status:** Accepted  
**Sprint:** 019  

---

## Decision

For Sprint 019, we will not mass-refresh or repair all legacy narratives. Instead, we will separate trusted generated summaries from recent article activity.

Briefings will only use narratives whose generated summaries are trusted. The narratives page will remain activity-based and show recent article clusters even when generated summaries are stale or missing.

For untrusted summaries, the public UI will render deterministic article-cluster fallback copy. It will not show stale generated summary text as authoritative, and it will not expose internal labels like stale, missing, untrusted, or needs refresh.

---

## Rationale

TASK-095 found 341 active narratives missing `last_summary_generated_at`, but only 4 narratives flagged with `needs_summary_update=true`. The refresh task works for flagged narratives, but legacy narratives missing the timestamp are not being selected for refresh.

Mass-refreshing all legacy narratives would add cost, consume daily LLM budget, and risk broad user-facing churn. However, ignoring recent article activity would make the narratives page sparse and hide useful information.

This decision preserves recent activity while avoiding stale generated summaries in high-risk synthesis paths.

---

## Consequences

### Positive

- Briefings stop synthesizing from untrusted summaries.
- The narratives page remains populated using recent article activity.
- No LLM spend is required for fallback card copy.
- Legacy narratives remain available for future repair.
- The sprint avoids broad data migration and mass refresh risk.

### Negative

- Historical narrative continuity is not fully repaired in Sprint 019.
- Some long-running narratives may be excluded from briefings until refreshed or validated.
- API and UI need a display-mode contract to avoid leaking internal freshness state.

---

## Non-Goals

- Do not delete legacy narratives.
- Do not mark all old narratives dormant.
- Do not refresh all 341 legacy narratives.
- Do not use LLM calls for fallback card copy.
- Do not change article-to-narrative matching behavior in this sprint.

---

## Follow-Up Options

- Selectively refresh high-value legacy narratives later.
- Add admin tooling to validate or reactivate selected legacy narratives.
- Add a controlled batch repair sprint when cost budget permits.
- Revisit article-to-narrative matching if old legacy narratives continue absorbing new articles in harmful ways.
