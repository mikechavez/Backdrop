---
id: FEATURE-XXX
type: feature
status: backlog
priority: medium
complexity: medium
created: YYYY-MM-DD
updated: YYYY-MM-DD
branch: feature/[short-description]
---

# FEATURE-XXX: Title

## Problem/Opportunity

<!-- What problem does this solve or what opportunity does it create? -->

---

## Proposed Solution

<!-- High-level description of the approach. -->

---

## User Story

As a [role], I want [goal] so that [benefit].

---

## Implementation Scope

### In Scope
- [ ] [Concrete behavior/file/module]
- [ ] [Concrete behavior/file/module]

### Out of Scope
- [ ] [Explicit non-goal]
- [ ] [Explicit non-goal]

---

## Files to Create

<!-- Exact paths. Leave empty only if none. -->

```text
path/to/new_file.py
path/to/new_test.py
```

---

## Files to Modify

<!-- Exact paths. The implementation agent should not search for alternate files unless a blocker is documented. -->

```text
path/to/existing_file.py
path/to/existing_test.py
```

---

## Do Not Modify

<!-- Guardrails for unrelated or risky areas. -->

```text
path/to/protected_file.py
path/to/unrelated_area/
```

---

## Exact Implementation Requirements

<!-- Agent-ready instructions. Prefer explicit classes/functions/config names. -->

1. [Step 1]
2. [Step 2]
3. [Step 3]

### Required Interfaces / Schemas

```python
# Include function/class signatures or schema examples here when applicable.
```

### Configuration

```text
ENV_VAR_NAME=example
```

---

## Acceptance Criteria

- [ ] [Concrete, testable condition]
- [ ] [Concrete, testable condition]
- [ ] [Concrete, testable condition]

---

## Test Plan

### Automated Tests

```bash
pytest path/to/test_file.py
```

Required test coverage:
- [ ] [Case 1]
- [ ] [Case 2]

### Manual Verification

1. [Manual step]
2. [Expected result]

---

## Dependencies

- None

---

## Open Questions

- [ ] [Question or decision needed]

---

## Rollback Plan

<!-- How to safely revert or disable this feature. -->

- [ ] [Rollback step]

---

## Completion Summary

<!-- Fill in after completion. -->

- Actual complexity:
- Branch:
- Commit:
- Key decisions made:
- Deviations from plan:
- Tests run:
- Manual verification:
