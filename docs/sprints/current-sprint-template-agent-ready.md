# Sprint [N] — [Title]

**Status:** Planned / In Progress / Complete  
**Started:** YYYY-MM-DD  
**Target:** [one-line goal]

---

## Sprint Goal

_[2-3 sentence description of what this sprint achieves and why it matters.]_

---

## Scope Boundary

### In Scope
- [ ] [Concrete scope item]
- [ ] [Concrete scope item]

### Out of Scope / Non-Goals
- [ ] [Explicitly excluded work]
- [ ] [Explicitly excluded work]

---

## Sprint Order

| # | Ticket | Title | Status | Est | Actual |
|---|--------|-------|--------|-----|--------|
| 1 | | | 🔲 OPEN | | |

---

## Success Criteria

- [ ] [Measurable outcome 1]
- [ ] [Measurable outcome 2]

---

## Agent Safety Notes

These constraints apply to all implementation agents working this sprint:

- Do not modify production data.
- Do not introduce broad database, shell, or filesystem access when a narrow tool/API is sufficient.
- Do not change unrelated files.
- Do not add autonomous destructive actions.
- Keep implementation bounded to the ticket's listed files unless a blocker is documented.
- If the implementation requires a new file/path not listed in the ticket, stop and document why before proceeding.

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

_Decisions made during the sprint that affect scope, priority, architecture, or approach._

| Date | Decision | Rationale | Impact |
|------|----------|-----------|--------|
| YYYY-MM-DD | | | |

---

## Discovered Work

_Tickets created mid-sprint for issues found during implementation._

| Ticket | Title | Reason Created | Status |
|--------|-------|----------------|--------|
| | | | |

---

## Session Log

### Session 1 (YYYY-MM-DD) — [ticket] [status emoji]
**[Ticket title]**
- [What was done, 2-5 bullets]
- Branch: `[branch]` | Commit: `[hash]`
