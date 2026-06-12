# BugOps Sprint 020 Alignment Investigation

## Context

We are planning Sprint 020 for BugOps. Sprint 018 built the foundation.
Sprint 020 will add outcome freshness detectors, the DependencyGraph,
cascade suppression, and idempotency on top of that foundation.

Before writing Sprint 020 implementation tickets, we need to understand
three specific alignment gaps between the Sprint 018 implementation and
the Sprint 020 design. This is an investigation task only — no code
changes yet.

---

## What to find

### 1. Dedupe key format

Sprint 018 implemented hourly bucketed dedupe keys in the format:

```
llm_traces:cost_runaway:YYYY-MM-DD:HH
```

Sprint 020 defines dedupe keys in the format:

```
detector_type:root_subsystem
```

Examples: `article_freshness:articles`, `signal_freshness:signals`

**Find:**
- The exact file and line(s) where dedupe_key is constructed in the
  current implementation
- The exact file and line(s) where dedupe_key is used for lookup
  (finding an existing open case)
- Whether dedupe_key has a unique index in MongoDB or is just a query
  field
- Any other places in the codebase that construct or reference
  dedupe_key format directly

Show the relevant code snippets.

---

### 2. BugAlertEvent layer

Sprint 018 normalizes signals into a `BugAlertEvent` first, then creates
or attaches to a `BugCase`. The flow is:

```
SignalSource → BugAlertEvent → BugCase
```

Sprint 020 freshness detectors need to create or attach to a BugCase
directly. The question is whether `BugAlertEvent` should remain as
internal plumbing or be bypassed for freshness detectors.

**Find:**
- The full `BugAlertEvent` model definition (file, line, all fields)
- The full `BugCase` model definition (file, line, all fields)
- The `process_alert_event()` method or equivalent — wherever the
  BugAlertEvent → BugCase creation logic lives (file, line, full
  implementation)
- Whether BugAlertEvent is required by the store layer or optional —
  i.e., is there any path to create a BugCase without a BugAlertEvent?

Show the relevant code snippets.

---

### 3. BugCase data model fields

Sprint 020 requires these fields on BugCase that may not exist yet:

```
root_subsystem          string
affected_subsystems     list of strings
blast_radius            list of strings
recovery_candidate_at   timestamp | null
observation_count       integer
resolution_type         string | null
confidence              float | null
correlation_reason      string | null
```

Sprint 018 BugCase currently has at minimum:
`severity`, `status`, `dedupe_key`

**Find:**
- The complete current BugCase model with every field, type, and
  default value
- Any MongoDB collection indexes defined on bug_cases (in store.py
  or any migration/init file)
- Whether `observation_count` exists already or if it is tracked a
  different way (e.g., by counting attached BugAlertEvents)
- Whether there is any existing `last_seen_at` or `first_seen_at`
  tracking on BugCase

Show the relevant code snippets.

---

## Deliverable

For each of the three areas above, provide:

1. File path(s) and line number(s)
2. The relevant code snippet(s) — full method or model definitions,
   not just the line in isolation
3. A one-paragraph summary of what exists, what is missing, and
   whether the gap is additive (new fields/methods needed) or
   conflicting (existing behavior needs to change)

Do not make any code changes. Investigation only.

---

## Files likely to be relevant

Based on the Sprint 018 summary, start here:

```
src/crypto_news_aggregator/bugops/models.py
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/bugops/signal_sources/base.py
src/crypto_news_aggregator/bugops/signal_sources/llm_traces.py
```

But search the full bugops/ directory for any other relevant files.
