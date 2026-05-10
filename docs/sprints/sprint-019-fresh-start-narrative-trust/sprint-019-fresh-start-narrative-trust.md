# Sprint 019 — Fresh-Start Narrative Trust Layer

**Status:** Planned  
**Started:** 2026-05-10  
**Target:** Protect user-facing briefings from untrusted narrative summaries while keeping the narratives page useful through deterministic article-activity fallbacks.

---

## Sprint Goal

Sprint 019 creates a trust boundary between generated narrative summaries and recent article activity. Briefings should only synthesize from trusted summaries, while the narratives page should remain populated by recent article clusters even when a generated summary is stale or missing.

The sprint also prevents malformed LLM refinement output from publishing and repairs the refinement prompt so it has actual source context when self-refine runs.

---

## Scope Boundary

### In Scope
- [ ] Prevent invalid, low-confidence, non-JSON, or model-meta briefing output from publishing.
- [ ] Add trusted-summary eligibility for briefing narrative inputs.
- [ ] Add backend narrative display-mode fields for public narrative cards.
- [ ] Add deterministic, zero-LLM article-cluster fallback display for untrusted summaries.
- [ ] Ground briefing refinement prompts with source context so refinement can repair rather than ask for missing data.
- [ ] Add Sprint 019 verification queries and runbook notes.

### Out of Scope / Non-Goals
- [ ] Do not refresh all 341 legacy narratives in this sprint.
- [ ] Do not delete old narratives.
- [ ] Do not mark old narratives dormant as part of this sprint.
- [ ] Do not expose internal labels like stale, missing, untrusted, or needs refresh to public users.
- [ ] Do not use LLM calls to generate narrative-card fallback copy.
- [ ] Do not change narrative clustering or article-to-narrative matching behavior.
- [ ] Do not increase narrative refresh batch size or LLM budget.

---

## Sprint Order

| # | Ticket | Title | Status | Est | Actual |
|---|--------|-------|--------|-----|--------|
| 0 | TASK-095 | Briefing and Narrative Refresh Investigation | ✅ COMPLETE | medium | |
| 1 | BUG-099 | Prevent Invalid Briefings From Publishing | ✅ COMPLETE | medium | |
| 2 | FEATURE-060 | Add Trusted Summary Eligibility for Briefings | 🔲 OPEN | medium | |
| 3 | FEATURE-061 | Add Narrative Display Mode API Fields | 🔲 OPEN | medium | |
| 4 | FEATURE-062 | Add Deterministic Article Cluster Fallback | 🔲 OPEN | medium | |
| 5 | BUG-100 | Ground Briefing Refinement With Source Context | 🔲 OPEN | medium | |
| 6 | TASK-096 | Add Sprint 019 Verification Queries | 🔲 OPEN | small | |

---

## Success Criteria

- [ ] A briefing with raw non-JSON model output cannot publish to the public briefing page.
- [ ] A briefing with `confidence_score < 0.5` cannot publish unless explicitly saved as an unpublished failure record.
- [ ] A briefing with empty `key_insights` cannot publish.
- [ ] Briefing generation uses only narratives with trusted summaries.
- [ ] The public narratives page remains populated by recent article activity, even when generated summaries are not trusted.
- [ ] Public users never see internal system-state language such as stale, missing, untrusted, or needs refresh.
- [ ] Untrusted narrative cards render deterministic fallback copy from recent article data without LLM calls.
- [ ] Briefing refinement prompt includes source context and cannot reference unavailable `AVAILABLE DATA`.
- [ ] No mass legacy narrative refresh is triggered by this sprint.
- [ ] LLM spend does not increase except for the small expected increase from refinement prompt context when refinement runs.

---

## Agent Safety Notes

These constraints apply to all implementation agents working this sprint:

- Do not modify production data.
- Do not introduce broad database, shell, or filesystem access when a narrow tool/API is sufficient.
- Do not change unrelated files.
- Do not add autonomous destructive actions.
- Keep implementation bounded to the ticket's listed files unless a blocker is documented.
- If the implementation requires a new file/path not listed in the ticket, stop and document why before proceeding.
- Do not trigger production briefing generation unless explicitly approved.
- Do not trigger narrative refresh jobs unless explicitly approved.
- Do not add LLM calls for narrative-card fallback display.
- Do not expose internal summary trust labels to public users.

---

## Implementation Notes

### Expected Branch Naming

```text
feature/[short-description]
task/[short-description]
fix/[short-description]
```

### Expected Commit Format

```text
feat(scope): description
fix(scope): description
task(scope): description
```

### Test Expectations

- Unit tests should be added or updated for every logic change.
- Integration/manual verification steps must be documented in the ticket completion summary.
- If a test cannot be automated, document the reason and provide a manual verification path.

---

## Key Decisions

| Date | Decision | Rationale | Impact |
|------|----------|-----------|--------|
| 2026-05-10 | Use fresh-start narrative trust instead of mass legacy repair. | 341 active legacy narratives are missing `last_summary_generated_at`; repairing all of them would cost money and add operational risk. | Briefings will only use trusted summaries. Old narratives stay in MongoDB for optional later repair. |
| 2026-05-10 | Keep the narratives page activity-based. | Recent article clusters remain useful even when generated summaries are stale. | The narratives page should not go sparse just because a summary is untrusted. |
| 2026-05-10 | Use deterministic article-cluster fallback copy. | Avoid LLM cost and avoid presenting stale generated summaries as authoritative. | Public users see polished article activity cards, not system-state labels. |
| 2026-05-10 | Do not change clustering/matching behavior in Sprint 019. | Matching changes could create duplicate narratives and are riskier than query/display fixes. | Matching behavior remains a future follow-up if needed. |

---

## Discovered Work

_Tickets created mid-sprint for issues found during implementation._

| Ticket | Title | Reason Created | Status |
|--------|-------|----------------|--------|
| | | | |

---

## Session Log

### Session 1 (2026-05-10) — TASK-095 & BUG-099 ✅
**Briefing and Narrative Refresh Investigation + Invalid Briefing Prevention**

**TASK-095:**
- Confirmed invalid briefing output was published because raw non-JSON LLM text can become `content.narrative` with `confidence_score=0.3`.
- Confirmed `_save_briefing()` publishes non-smoke briefings without confidence, empty-insight, parse-failure, or meta-output validation.
- Confirmed refinement prompt references `AVAILABLE DATA` but only includes counts, not the actual narrative context.
- Confirmed 341 active narratives are missing `last_summary_generated_at`, while only 4 were flagged for refresh.
- Confirmed narrative refresh task exists, is batched, and converts string article IDs to ObjectId correctly.

**BUG-099:**
- Implemented `_validate_briefing_publishable()` with 7 rejection criteria (parse_failed, low confidence, empty narrative/insights, model-meta phrases).
- Added `parse_failed` field to `GeneratedBriefing` to explicitly track JSON parse failures.
- Modified `_save_briefing()` to validate before publishing and save rejected briefings unpublished with rejection metadata.
- Hardened `_get_production_briefings_filter()` to exclude invalid briefings at query level.
- Implemented context-aware "available data" detection to avoid false positives on valid briefings.
- Added task_id to rejection logging for debugging/correlation.
- 28 comprehensive tests added, all passing (17 validation + 2 parse + 5 save + 3 available_data + 1 filter).
- Branch: `fix/bug-099-prevent-invalid-briefings-publishing` | Commits: 270d800, 5184d21
