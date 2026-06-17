# Sprint 020: Outcome Freshness Design

---

## Purpose

This document is the implementation blueprint for Sprint 020. It covers
the four freshness detectors, cascade suppression mechanics, idempotency,
time authority application, recovery model implementation, auto-resolution,
notification routing, detector isolation, deploy suppression, retention
defaults, and success criteria.

This document does not define new architecture. All decisions referenced
here are locked in 00-core-system-architecture.md.

---

## Scope

Sprint 020 implements:

- Four outcome freshness detectors
- DependencyGraph (first version)
- Cascade suppression
- Idempotency and dedupe
- Auto-resolution with Recovery Window
- Recovery Window repeated-failure handling (replaces dedicated flapping protection)
- Notification routing rules
- Detector isolation
- Deploy suppression
- Suppression expiry summary

Sprint 020 does not implement:

- Evidence Pack collection
- Investigation generation
- Ticket drafting or export
- Retroactive case merging or absorption
- External heartbeat
- resolution_type population (field exists, not required this sprint)

---

## Freshness Detectors

Each detector implements the five-part definition required by the
Idle vs Broken architecture principle. Absence of output is only a
failure when output was expected.

---

### ArticleFreshness

Detects stalled article ingestion.

**Last successful output**
The most recent Article record with a `created_at` timestamp within
the configured freshness window. `created_at` is authoritative.
`published_at` is not used for freshness evaluation.

**Expected input or activity**
At least one RSS fetch attempt has completed within the current polling
cycle, and at least one source historically produces articles during this
time-of-day window. A fetch completing with zero new items is not
independently a failure.

**Failure condition**
No Article has been inserted within the freshness window AND at least one
source has produced articles during this time-of-day window in recent
history. Both conditions must be true.

**Legitimate idle condition**
All monitored RSS sources have published no new content in recent history
for this time-of-day window. Weekends, holidays, and low-activity periods
are legitimate idle. Detection must account for source publishing patterns
before raising a BugCase.

**Recovery condition**
At least one new Article is inserted with `created_at` within the
freshness window, on a source that was previously stalled.

**Severity:** High
**Dedupe key:** `article_freshness:articles`

---

### SignalFreshness

Detects stalled signal generation.

**Last successful output**
The most recent Signal record with a `last_updated` timestamp within the
configured freshness window.

**Expected input or activity**
At least one Article has been inserted recently enough that signal
generation should have run. If no articles are present, signal generation
has no input and cannot be expected to produce output.

**Failure condition**
Articles exist with `created_at` within the freshness window AND no new
Signals have been generated within the freshness window.

**Legitimate idle condition**
No articles have been inserted recently. Signal generation has no input
and is correctly idle.

**Recovery condition**
At least one new Signal is generated with `last_updated` within the
freshness window, corresponding to article input that was previously
not producing signals.

**Severity:** High
**Dedupe key:** `signal_freshness:signals`

---

### NarrativeFreshness

Detects stale narrative refresh.

**Last successful output**
The most recent Narrative record with a `last_summary_generated_at`
timestamp within the configured freshness window.

**Expected input or activity**
Sufficient signals exist to trigger narrative refresh.

**Failure condition**
Signals exist within the freshness window AND no Narrative has been
updated or inserted within the freshness window.

Job cadence tracking is deferred unless already available through
existing metadata.

**Legitimate idle condition**
No signals have been generated recently. Narrative refresh has no
meaningful input and is correctly idle.

**Recovery condition**
At least one Narrative is updated or inserted with a timestamp within
the freshness window after the stall period.

**Severity:** High
**Dedupe key:** `narrative_freshness:narratives`

---

### BriefingFreshness

Detects missing briefings.

**Last successful output**
The most recent Briefing record with a `generated_at` timestamp within
the configured freshness window. Briefings are expected on a known
schedule. The freshness window is calibrated to that schedule.

**Expected input or activity**
The briefing generation window has elapsed. Narratives exist that are
fresh enough to produce a briefing.

**Failure condition**
The briefing generation window has elapsed AND no Briefing has been
inserted within the expected window AND fresh narratives exist as input.
Briefing timestamps are corroborated against the known schedule before
raising a BugCase.

**Legitimate idle condition**
The briefing generation window has not yet elapsed since the last
successful briefing. Or no sufficiently fresh narratives exist to
produce a briefing.

**Recovery condition**
A new Briefing is inserted with `generated_at` within the expected
window following the stall period.

**Severity:** High
**Dedupe key:** `briefing_freshness:briefings`

---

## DependencyGraph — First Version

The DependencyGraph is a hand-maintained, version-controlled artifact.
It represents operational outcome dependencies.

```
scheduler → ingestion → articles → signals → narratives → briefings
```

Each node corresponds to a subsystem. Each edge represents a dependency:
the downstream node's output requires the upstream node to be functioning.

The graph supports two traversal directions:

**Upstream traversal (cascade suppression)**
Walk from a detector's root_subsystem toward the root of the graph.
Check for open BugCases at each upstream node. Stop at first match.

**Downstream traversal (blast radius)**
Walk from a BugCase's root_subsystem toward the leaves. All reachable
nodes are candidates for affected_subsystems.

The graph is not inferred dynamically. It does not represent every
internal service, queue, or collection — only operational outcome
dependencies relevant to freshness detection and cascade suppression.

Version: 1.0. Changes require deliberate versioning.

---

## Cascade Suppression

Processing order is deterministic and must not be varied:

```
1. Check for open upstream BugCase (DependencyGraph upstream traversal)
   → If found: attach signal, update affected_subsystems, update
     last_seen_at and observation_count. No new BugCase. No notification.
     Stop.

2. Check for open BugCase with same dedupe_key
   → If found: attach signal, update last_seen_at and observation_count.
     No new BugCase. No notification. Stop.

3. Create new BugCase. Notify.
```

Upstream-wins is unconditional. A downstream detector does not create
a new BugCase if any upstream node has an open BugCase, regardless of
whether the downstream detector's condition appears independently severe.

Sprint 020 does not implement retroactive merging. If an upstream BugCase
is created after a downstream BugCase already exists, those cases remain
separate. Retroactive merge is deferred.

---

## Idempotency

**Dedupe key format:** `detector_type:root_subsystem`

Examples:
- `article_freshness:articles`
- `signal_freshness:signals`
- `narrative_freshness:narratives`
- `briefing_freshness:briefings`

**Dedupe scope:** open BugCases only. A resolved or closed BugCase with
the same dedupe_key does not suppress a new case.

**Attachment behavior on match:**
- Increment `observation_count`
- Update `last_seen_at`
- Do not send a new notification
- Do not change severity unless escalation rules apply (see Notification
  Routing)

---

## Time Authority

All freshness comparisons use `inserted_at` as the primary timestamp.

`published_at` is never used for freshness decisions. It is an external
timestamp and cannot be trusted.

`fetched_at` may appear in diagnostic context attached to a BugCase but
is not authoritative for freshness.

`detected_at` records when BugOps observed a condition. It populates
BugCase metadata. It is not used for source freshness decisions.

**60-second tolerance buffer**
All freshness window comparisons apply a configurable 60-second tolerance
buffer before evaluating. This prevents boundary-condition false positives
where an artifact arrives slightly after a strict deadline due to
processing latency.

**BriefingFreshness corroboration**
Briefing freshness uses the known briefing schedule as a secondary
corroboration signal. A briefing is only considered overdue if both:
- `inserted_at` of the last briefing is outside the freshness window, AND
- the scheduled generation window has elapsed according to the known
  schedule plus the tolerance buffer.

---

## Recovery Model

Recovery is defined as outcome recovery, not component health.

**Recovery candidate entry**
When a freshness detector runs and finds that the expected artifact is
now being produced again (recovery condition met), `recovery_candidate_at`
is set to the timestamp of the first healthy observation.

`recovery_candidate_at` is internal metadata. It is not an
operator-facing status.

**Recovery Window**
The BugCase must remain in healthy state for the full duration of the
Recovery Window before automatic resolution. The Recovery Window is
configurable. Default: 10 minutes.

If the failure condition is re-observed before the Recovery Window
elapses, `recovery_candidate_at` is cleared and the BugCase returns
to active failure state.

**Resolution unit**
BugCase resolves as a unit. Partial resolution is not supported.
Individual affected_subsystems may recover at different times; this
is recorded in metadata but does not close the case. The case closes
when the root_subsystem's recovery condition is met and the Recovery
Window elapses.

**Recovery Window units**
Minutes. Configurable per environment. Defaults:
- Production: 10 minutes
- Development/test: 1 minute

---

## Auto-Resolution

Auto-resolution triggers when:
- The BugCase's root_subsystem recovery condition is met, AND
- `recovery_candidate_at` is set, AND
- The elapsed time since `recovery_candidate_at` is greater than or
  equal to the Recovery Window

Auto-resolution is blocked only when:
- The recovery condition is re-violated before the Recovery Window
  elapses (see Recovery Window repeated-failure handling, below)
- The BugCase has been manually closed by an operator

Auto-resolution still applies to BugCases with active mute or snooze
flags. Mute and snooze affect notification behavior only. A muted or
snoozed BugCase that meets recovery conditions resolves normally.

**Recovery Window repeated-failure handling**
If a BugCase is in recovery countdown and the failure recurs:
- Clear `recovery_candidate_at` timestamp
- BugCase remains open
- Do NOT send a new notification
- Do NOT create a new BugCase
- Countdown resets on next recovery observation

This mechanism naturally handles failure oscillation: if a failure
keeps recurring within the recovery window, the case stays open and
operators remain aware. Once recovery is stable for the full window,
the case auto-resolves. No separate flapping detection is required.

---

## Notification Routing

Notifications are driven by BugCase state changes, not raw detector
observations.

**Routing rules by severity:**

| Severity | Trigger             | Channel | Behavior  |
|----------|---------------------|---------|-----------|
| Critical | BugCase created     | Slack   | Immediate |
| Critical | Severity escalation | Slack   | Immediate |
| High     | BugCase created     | Slack   | Immediate |
| High     | Severity escalation | Slack   | Immediate |
| Medium   | BugCase created     | Digest  | Batched   |
| Low      | BugCase created     | Stored  | None      |

**Deduplication**
No new notification is sent for repeated observations against an open
BugCase with the same dedupe_key, unless:
- Severity increases
- A new subsystem joins affected_subsystems
- The BugCase reopens after resolution

**Throttle**
Notifications for the same BugCase are throttled to at most once per
configurable throttle window, except for severity escalation events,
which always notify immediately.

**Reopen notification**
When a resolved BugCase reopens, a new notification is sent at the
BugCase's current severity regardless of throttle state.

---

## Detector Isolation

Each detector runs inside an independent try/catch block within the
BugOps polling loop.

A failure in any single detector:
- Logs a structured error
- Does not halt the polling loop
- Does not prevent other detectors from running

**Observability**
Detector runs are observable through structured logs. Persisted run
records are optional in Sprint 020 if implementation cost is low.
If persisted, the run record schema is:

```
detector_name       string
run_started_at      timestamp
run_completed_at    timestamp
status              enum: success | failure | skipped
error_type          string | null
error_message       string | null
duration_ms         integer
```

Detector run records are not operator-facing alerts.

---

## Deploy Suppression

BugOps supports a maintenance mode for deploy suppression windows.

**Suppression behavior:**
- Notifications are suppressed during the suppression window
- BugCases continue to be created and recorded
- BugCases remain visible to operators
- Detection, case creation, and auto-resolution logic are unaffected

**Mute and snooze flags**
BugCases may carry `muted_until` or `snoozed_until` timestamps.
These are flags, not lifecycle statuses. They affect notification
behavior only and do not block auto-resolution or case progression.

**Suppression expiry**
Suppression windows have a configurable duration and expire
automatically. Manual deactivation is also supported.

If implemented in Sprint 020, suppression expiry should send a summary
notification for unresolved Critical/High BugCases that would have
notified during the window.

**Suppression scope**
Sprint 020 implements suppression at the global level. Per-subsystem
suppression is deferred.

---

## Retention Policy

Default retention for artifacts created in Sprint 020:

| Artifact                  | Retention            |
|---------------------------|----------------------|
| BugCases                  | Permanent            |
| Detector run logs/records | 30 days if persisted |

These values are configurable and not immutable architecture.

---

## Sprint 020 Success Criteria

- All four freshness detectors run in the BugOps polling loop without
  requiring changes to the monitor process structure
- Each detector correctly distinguishes legitimate idle from broken
  using the five-part definition
- Cascade suppression correctly attaches downstream signals to upstream
  BugCases rather than creating new ones
- Idempotency correctly suppresses duplicate BugCases for repeated
  observations of the same condition
- A BugCase auto-resolves after the Recovery Window elapses without
  re-violation
- A BugCase does not auto-resolve if the failure condition recurs
  during the Recovery Window
- A detector failure does not halt the polling loop or prevent other
  detectors from running
- Notifications route correctly by severity and are not re-sent for
  repeated observations against the same open BugCase
- BugCases with active mute or snooze flags resolve normally when
  recovery conditions are met
- Deploy suppression prevents notifications without suppressing case
  creation or auto-resolution
- Detector runs are observable through structured logs
