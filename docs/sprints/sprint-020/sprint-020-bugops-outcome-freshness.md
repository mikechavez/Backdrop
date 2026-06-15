# Sprint 020 — Outcome Freshness & Failure Visibility

**Status:** Planned
**Started:** TBD
**Target:** Production failures surface as BugCases automatically, with no manual monitoring required

---

## Sprint Goal

Sprint 020 adds outcome freshness detection to BugOps. Four detectors monitor whether articles, signals, narratives, and briefings are being produced at the expected rate. When expected output stops appearing — including when BugOps starts while production is already broken — BugOps creates a BugCase and notifies the operator via Slack. Cascade suppression, idempotency, and auto-resolution with a Recovery Window ensure operators receive signal, not noise.

This sprint does not implement Evidence Packs, Investigations, Tickets, Railway log ingestion, or runtime exception monitoring. Those are Sprint 021 and Sprint 022 respectively. Sprint 020's contract to the next sprint is a reliable, low-noise stream of BugCases that accurately represent production failures.

---

## Scope Boundary

### In Scope
- [ ] Four outcome freshness detectors (articles, signals, narratives, briefings)
- [ ] Canonical subsystem enum
- [ ] Deterministic severity mapping for freshness detectors
- [ ] DependencyGraph v1 (`scheduler → ingestion → articles → signals → narratives → briefings`)
- [ ] Cascade suppression (upstream-wins, deterministic processing order)
- [ ] Idempotency and dedupe for open BugCases
- [ ] BugCase model extension with Sprint 020 fields
- [ ] MongoDB indexes for BugOps collections
- [ ] `create_case_direct()` and `attach_observation_to_case()` store methods
- [ ] Startup detection for active failures present when BugOps starts
- [ ] Auto-resolution with configurable Recovery Window
- [ ] Recovery Window repeated-failure handling
- [ ] Slack notification contract for BugCase state changes
- [ ] Notification attempt persistence
- [ ] Global deploy suppression
- [ ] Suppression expiry summary
- [ ] Detector isolation (independent try/catch per detector)
- [ ] Detector run observability via structured logs

### Out of Scope / Non-Goals
- [ ] Railway log ingestion
- [ ] RuntimeExceptionSignalSource
- [ ] Runtime exception monitoring from Railway logs
- [ ] Evidence Pack collection (Sprint 021)
- [ ] Investigation generation (Sprint 021)
- [ ] Ticket drafting or export (Sprint 022)
- [ ] Retroactive BugCase merging or absorption
- [ ] Per-subsystem suppression (global only this sprint)
- [ ] External heartbeat (deferred, see architecture doc)
- [ ] `resolution_type` population (field added, not required this sprint)
- [ ] Medium digest batching (routing decision implemented, actual batching stubbed)
- [ ] RuntimeError, WorkerFailure, SchedulerFailure, DatabaseFailure signal sources (separate sprint)
- [ ] Slack interactive UI, buttons, slash commands, or acknowledgement actions
- [ ] Dedicated flapping detection with manual escalation

---

## Sprint Order

| #  | Ticket    | Title                                                              | Status   | Est | Actual |
|----|-----------|--------------------------------------------------------------------|----------|-----|--------|
| 1  | TASK-100  | Extend BugCase model with Sprint 020 fields                        | ✅ DONE  | S   | S      |
| 2  | TASK-100A | Add canonical BugOps subsystem enum                                | ✅ DONE  | S   | S      |
| 3  | TASK-100B | Add deterministic severity mapping for Sprint 020 detectors        | ✅ DONE  | S   | S      |
| 4  | TASK-100C | Configure Slack webhook in Railway for BugOps                     | ✅ DONE  | XS  | XS     |
| 5  | TASK-101  | Add MongoDB indexes for BugOps collections                         | ✅ DONE  | S   | S      |
| 6  | TASK-102  | Add `create_case_direct()` and `attach_observation_to_case()`      | ✅ DONE  | S   | S      |
| 7  | TASK-103  | Implement DependencyGraph v1                                       | ✅ DONE  | S   | S      |
| 8  | TASK-104  | Implement ArticleFreshness detector                                | 🔲 OPEN  | M   |        |
| 9  | TASK-105  | Implement SignalFreshness detector                                 | 🔲 OPEN  | M   |        |
| 10 | TASK-106  | Implement NarrativeFreshness detector                              | 🔲 OPEN  | M   |        |
| 11 | TASK-107  | Implement BriefingFreshness detector                               | 🔲 OPEN  | M   |        |
| 12 | TASK-108  | Wire freshness detectors into monitor with cascade suppression     | 🔲 OPEN  | M   |        |
| 13 | TASK-108A | Implement startup detection semantics                              | 🔲 OPEN  | M   |        |
| 14 | TASK-109  | Implement auto-resolution with Recovery Window                     | 🔲 OPEN  | M   |        |
| 15 | TASK-111  | Implement Slack notification contract for BugCase state changes    | 🔲 OPEN  | M   |        |
| 16 | TASK-111A | Persist notification attempt records                               | 🔲 OPEN  | S   |        |
| 17 | TASK-112  | Implement global deploy suppression                                | 🔲 OPEN  | S   |        |
| 18 | TASK-112A | Send deploy suppression expiry summary                             | 🔲 OPEN  | S   |        |
| 19 | TASK-113  | Update Sprint 020 docs and success criteria                        | 🔲 OPEN  | S   |        |

**Sequencing:**

Phase 1 — Foundation (no behavior change):
TASK-100 → TASK-100A → TASK-100B → TASK-100C → TASK-101 → TASK-102

Phase 2 — New primitives (no dependencies on Phase 1):
TASK-103

Phase 3 — Detectors (depend on Phase 1 + 2, can run in parallel):
TASK-104, TASK-105, TASK-106, TASK-107

Phase 4 — Wiring and behavior (depend on Phase 1–3):
- TASK-108 (cascade suppression wiring, depends on TASK-103 + all detectors)
- TASK-108A (startup detection, depends on TASK-108)
- TASK-109 (auto-resolution, depends on all detectors)
- TASK-111 (Slack contract, depends on TASK-100, TASK-100A, TASK-100B)
- TASK-111A (notification attempt persistence, depends on TASK-111)
- TASK-112 (deploy suppression, depends on TASK-100)
- TASK-112A (suppression expiry summary, depends on TASK-112)

Phase 5 — Closeout:
- TASK-113 (docs and success criteria, depends on all above)

---

## Ticket Specifications

---

### TASK-100 — Extend BugCase model with Sprint 020 fields

Add the following fields to the BugCase model:

```
root_subsystem         string (canonical subsystem enum value)
affected_subsystems    list of strings (canonical subsystem enum values)
blast_radius           list of strings (canonical subsystem enum values)
first_seen_at          timestamp
last_seen_at           timestamp
observation_count      integer, default 1
recovery_candidate_at  timestamp | null
resolution_type        string | null (not required this sprint)
muted_until            timestamp | null
snoozed_until          timestamp | null
detection_type         enum: startup | runtime | reopen
reopen_count           integer, default 0
```

`detection_type` is required. It records how the BugCase was created.

`resolution_type` field exists but is not populated this sprint.

`muted_until` and `snoozed_until` are flags affecting notification behavior
only. They do not block auto-resolution or case progression.

---

### TASK-100A — Add canonical BugOps subsystem enum

Create a shared canonical subsystem enum used across detectors, BugCase
fields, DependencyGraph, and notification messages.

Canonical values:

```
scheduler
ingestion
articles
signals
narratives
briefings
worker
database
```

Acceptance criteria:

- Canonical subsystem values exist as a shared constant or enum
- Detectors use enum values for root_subsystem
- BugCase root_subsystem validates against enum
- BugCase affected_subsystems validates against enum
- Tests reject ad hoc subsystem strings not in the enum

---

### TASK-100B — Add deterministic severity mapping for Sprint 020 detectors

Define and enforce the Sprint 020 severity mapping:

```
ArticleFreshness:   High
SignalFreshness:    High
NarrativeFreshness: High
BriefingFreshness:  High
```

Severity is assigned deterministically at detection time.

Sprint 020 does not implement severity escalation except where explicitly
required by a ticket.

Acceptance criteria:

- Each freshness detector produces High severity BugCases
- Severity is not computed dynamically from observation count or
  blast radius in Sprint 020
- Notification routing depends on this severity mapping

---

### TASK-100C — Configure Slack webhook in Railway for BugOps

Configure deploy-time environment variables to enable BugOps Slack notifications in production.

**Acceptance criteria:**

- Slack incoming webhook created and URL recorded
- Three environment variables set in Railway:
  - `BUGOPS_ENABLED` = `true`
  - `BUGOPS_SLACK_ENABLED` = `true`
  - `BUGOPS_SLACK_WEBHOOK_URL` = `<webhook URL>`
- At least one successful Slack delivery confirmed
- Railway logs confirm `"BugOps monitor running"`

**Notes:**

- No code changes required. This is deploy configuration only.
- Do this ticket before or alongside TASK-111 implementation.
- Verify cost-runaway thresholds are acceptable before flipping in production:
  - `BUGOPS_COST_5MIN_THRESHOLD_USD` defaults to `0.25`
  - `BUGOPS_PROJECTED_HOURLY_THRESHOLD_USD` defaults to `1.00`
- At $0.54/day production spend these thresholds are safe.

---

### TASK-101 — Add MongoDB indexes for BugOps collections

Add indexes to support efficient BugOps query patterns:

- Open BugCase lookup by dedupe_key
- Open BugCase lookup by root_subsystem (for cascade suppression)
- BugCase lookup by status
- Notification attempt lookup by bugcase_id

---

### TASK-102 — Add `create_case_direct()` and `attach_observation_to_case()` to BugOpsStore

`create_case_direct()` creates a new BugCase directly from detector
output, bypassing the alert event layer used in Sprint 018.

`attach_observation_to_case()` attaches a new observation to an existing
open BugCase, incrementing `observation_count` and updating `last_seen_at`.

These methods support the Sprint 020 processing order:

```
1. Check for open upstream BugCase → attach if found
2. Check for open BugCase with same dedupe_key → attach if found
3. Create new BugCase
```

---

### TASK-103 — Implement DependencyGraph v1

Implement the hand-maintained, version-controlled DependencyGraph.

Graph (version 1.0):

```
scheduler → ingestion → articles → signals → narratives → briefings
```

The graph must support:

- Upstream traversal (cascade suppression): walk from a given subsystem
  toward the root, return first open BugCase found at any upstream node
- Downstream traversal (blast radius): walk from a given subsystem toward
  the leaves, return all reachable subsystem names

`worker` and `database` must exist in the canonical subsystem enum
(TASK-100A) but are not graph nodes in Sprint 020. They are reserved for
future detectors.

The graph is not inferred dynamically. Changes require deliberate
versioning.

Unit tests required for both traversal directions.

---

### TASK-104 — Implement ArticleFreshness detector

**Five-part definition:**

Last successful output: most recent Article with `created_at` within
freshness window.

Expected input or activity: at least one RSS fetch attempt completed
within the current polling cycle (via `fetched_at` on Article records —
no RSS fetch job collection exists).

Failure condition: no Article inserted within freshness window AND at
least one source has historically produced articles during this
time-of-day window.

Legitimate idle condition: all monitored RSS sources have published no
new content for this time-of-day window in recent history.

Recovery condition: at least one new Article inserted with `created_at`
within freshness window on a previously stalled source.

**Detector config:**

```
root_subsystem:        articles
severity:              High
detection_type:        runtime (startup if first poll)
dedupe_key:            article_freshness:articles
suggested_manual_check: Check RSS ingestion health, recent fetch
                        attempts, source availability, and whether
                        articles are being inserted with created_at
                        timestamps.
```

**Notes:**

- Uses `created_at` on `articles` collection
- Uses `fetched_at` on Article records as proxy for fetch attempt
  (no RSS fetch job collection exists)
- Startup detection: if failure condition is active on first poll,
  create BugCase with detection_type=startup

---

### TASK-105 — Implement SignalFreshness detector

**Five-part definition:**

Last successful output: most recent Signal with `last_updated` within
freshness window.

Expected input or activity: at least one Article inserted recently enough
that signal generation should have run.

Failure condition: Articles exist with `created_at` within freshness
window AND no Signals generated within freshness window.

Legitimate idle condition: no articles inserted recently; signal
generation has no input.

Recovery condition: at least one new Signal generated with `last_updated`
within freshness window corresponding to previously stalled article input.

**Detector config:**

```
root_subsystem:        signals
severity:              High
detection_type:        runtime (startup if first poll)
dedupe_key:            signal_freshness:signals
suggested_manual_check: Check signal generation worker health and
                        confirm recent articles are being processed
                        into signals.
```

**Notes:**

- Uses `last_updated` on `signal_scores` collection
- Startup detection: if failure condition is active on first poll,
  create BugCase with detection_type=startup

---

### TASK-106 — Implement NarrativeFreshness detector

**Five-part definition:**

Last successful output: most recent Narrative with
`last_summary_generated_at` within freshness window.

Expected input or activity: sufficient signals exist to trigger narrative
refresh.

Failure condition: Signals exist within freshness window AND no Narrative
updated or inserted within freshness window.

Legitimate idle condition: no signals generated recently; narrative
refresh has no meaningful input.

Recovery condition: at least one Narrative updated or inserted with
`last_summary_generated_at` within freshness window after stall period.

**Detector config:**

```
root_subsystem:        narratives
severity:              High
detection_type:        runtime (startup if first poll)
dedupe_key:            narrative_freshness:narratives
suggested_manual_check: Check narrative refresh job health and confirm
                        recent signals are available as input.
```

**Notes:**

- Uses `last_summary_generated_at` on `narratives` collection
- No formal Pydantic model; queries `db.narratives` directly
- Startup detection: if failure condition is active on first poll,
  create BugCase with detection_type=startup

---

### TASK-107 — Implement BriefingFreshness detector

**Five-part definition:**

Last successful output: most recent Briefing with `generated_at` within
the expected schedule window.

Expected input or activity: briefing generation window has elapsed.
Narratives exist that are fresh enough to produce a briefing.

Failure condition: briefing generation window has elapsed AND no Briefing
inserted within expected window AND fresh narratives exist as input.

Legitimate idle condition: briefing generation window has not yet elapsed
since last successful briefing. Or no sufficiently fresh narratives exist.

Recovery condition: new Briefing inserted with `generated_at` within
expected window following stall period.

**Detector config:**

```
root_subsystem:        briefings
severity:              High
detection_type:        runtime (startup if first poll)
dedupe_key:            briefing_freshness:briefings
suggested_manual_check: Check briefing generation schedule, recent
                        narrative freshness, and whether a briefing
                        insert was attempted.
```

**Notes:**

- Uses `generated_at` on `daily_briefings` collection
- Two schedule windows: 8AM EST and 8PM EST, each with 30-minute grace
  period. Single-window approach produces false positives.
- A briefing is overdue only if BOTH: `generated_at` of last briefing
  is outside the window AND the scheduled window has elapsed plus grace
  period
- Startup detection: if failure condition is active on first poll,
  create BugCase with detection_type=startup

---

### TASK-108 — Wire freshness detectors into monitor with cascade suppression

Wire all four freshness detectors into the BugOps polling loop with
deterministic cascade suppression.

**Processing order (must not vary):**

```
1. Detector observes failure condition
2. Check for open upstream BugCase (DependencyGraph upstream traversal)
   → If found: attach observation, update affected_subsystems,
     update last_seen_at and observation_count. No new BugCase.
     No notification. Stop.
3. Check for open BugCase with same dedupe_key
   → If found: attach observation, update last_seen_at and
     observation_count. No new BugCase. No notification. Stop.
4. Create new BugCase. Notify if routing rules require it.
```

Upstream-wins is unconditional regardless of downstream severity.

Each detector runs inside an independent try/catch block. A detector
failure logs a structured error and does not halt the polling loop or
prevent other detectors from running.

Unit tests required for cascade suppression processing order.

---

### TASK-108A — Implement startup detection semantics

Implement startup detection behavior in the monitor.

BugOps does not require observing a healthy-to-unhealthy transition before
creating a BugCase. If production is already broken when BugOps starts,
detectors create BugCases immediately.

**Behavior:**

```
BugOps starts
→ each freshness detector runs (first poll)
→ active failure conditions create BugCases with detection_type=startup
→ cascade suppression applies normally during startup
→ Critical and High startup BugCases notify Slack
```

**Acceptance criteria:**

- Active failure at first monitor poll creates a BugCase
- Startup-created BugCase has detection_type=startup
- Startup-created High BugCase sends Slack notification
- Downstream startup failures cascade-suppress into upstream startup
  BugCase when applicable
- No healthy baseline is required before a startup BugCase is created
- Subsequent polls use detection_type=runtime

---

### TASK-109 — Implement auto-resolution with Recovery Window

Implement auto-resolution based on outcome recovery, not component health.

**Recovery candidate entry:**
When a freshness detector observes its recovery condition is met, set
`recovery_candidate_at` to the timestamp of the first healthy observation.

`recovery_candidate_at` is internal metadata. It is not operator-facing.

**Recovery Window:**
The BugCase resolves only if the subsystem remains healthy for the full
Recovery Window duration.

Default Recovery Window:
- Production: 10 minutes
- Development/test: 1 minute

**Failure recurrence before Recovery Window elapses:**

```
clear recovery_candidate_at
BugCase remains open
no new BugCase created
no Slack notification sent
```

**Auto-resolution triggers when:**

```
recovery condition is met AND
recovery_candidate_at is set AND
elapsed time since recovery_candidate_at >= Recovery Window
```

**Auto-resolution is blocked when:**

```
BugCase has been manually closed by operator
```

Auto-resolution still applies to BugCases with active mute or snooze
flags. Those flags affect notification behavior only.

Auto-resolution does not send a Slack notification.

BugCase resolves as a unit. Partial resolution is not supported.

Unit tests required for Recovery Window timing, failure recurrence
clearing, and manual-close blocking.

---

### TASK-111 — Implement Slack notification contract for BugCase state changes

Implement the full Slack notification contract.

**Notify on:**

```
new Critical BugCase created
new High BugCase created
Critical or High BugCase reopened
severity escalation
deploy suppression expiry summary (see TASK-112A)
```

**Do not notify on:**

```
repeated observation attached to existing BugCase
cascade-suppressed downstream observation
observation_count increase
last_seen_at update
recovery_candidate_at set
recovery_candidate_at cleared
auto-resolution
manual close
Low severity BugCase creation
Medium severity BugCase creation
```

**Notification event types:**

```
bugcase_created
bugcase_reopened
severity_escalated
suppression_summary
```

**Deduplication:**
A BugCase creation notification is sent at most once per BugCase.
Reopen and severity escalation always notify immediately regardless of
throttle.

**Throttle:**
Maximum 1 Slack notification per BugCase per hour, except severity
escalation and reopen which are always immediate. Throttle may be
deferred if implementation cost is high — deduplication rules already
prevent most duplicate sends.

**Slack message fields (all notifications):**

```
event_type
severity
title
bugcase_id
status
root_subsystem
affected_subsystems
summary
first_seen_at
last_seen_at
observation_count
dedupe_key
detection_type
suggested_manual_check
suppression_status
```

**suppression_status values:**

```
sent
suppressed
not_applicable
```

**Message format — BugCase created:**

```
🚨 HIGH — Article Freshness Failure

Case:           bc_123
Detection:      startup
Root subsystem: articles
Affected:       signals, narratives, briefings
Summary:        No articles inserted for 42 minutes while article
                activity was expected.
First seen:     2026-06-11 19:21 UTC
Last seen:      2026-06-11 19:21 UTC
Observations:   1
Suggested check: Check RSS ingestion health and recent fetch attempts.
```

**Message format — Case reopened:**

```
🔄 CASE REOPENED

Case:         bc_123
Severity:     High
Root:         articles
Summary:      Article freshness recovered but failed again.
Reopen count: 1
```

**Slack message must not include:**

```
raw logs
stack traces
large JSON payloads
full database records
LLM-generated analysis
Evidence Pack contents
Investigation contents
```

---

### TASK-111A — Persist notification attempt records

Persist a record for every notification attempt, independent of BugCase
lifecycle.

**Schema:**

```
notification_id
bugcase_id
event_type
channel
status
attempted_at
error_type       | null
error_message    | null
suppressed_reason | null
```

**channel values:** `slack`

**status values:**

```
sent       — Slack webhook accepted the notification
failed     — Slack webhook failed, timed out, or raised an exception
suppressed — Deploy suppression was active
skipped    — Routing rules did not require notification
```

Sprint 020 does not need to persist `skipped` records unless
implementation cost is low.

**Failure behavior:**

```
Slack send fails
→ record status: failed
→ log error
→ BugCase remains created
→ monitor continues polling
```

Notification failure must not block BugCase creation, detection,
auto-resolution, or evidence collection.

---

### TASK-112 — Implement global deploy suppression

Implement deploy suppression via environment variable.

**Mechanism:**

```
BUGOPS_SUPPRESSED_UNTIL=<ISO-8601 timestamp>
```

If current time is before `BUGOPS_SUPPRESSED_UNTIL`, suppression is
active.

If the variable is empty, invalid, or in the past, suppression is
inactive.

**During suppression:**

```
BugCases are created normally
BugCases are updated normally
Slack notifications are not sent
notification attempts are recorded as suppressed
auto-resolution runs normally
reopen logic runs normally
```

**Mute and snooze flags:**
`muted_until` and `snoozed_until` fields exist on BugCase (added in
TASK-100). Sprint 020 respects these flags for notification routing
only. No Slack UI or operator actions are implemented to set them.

Suppression scope is global only. Per-subsystem suppression is deferred.

---

### TASK-112A — Send deploy suppression expiry summary

When suppression expires, send one Slack summary for unresolved Critical
and High BugCases that were active during the suppression window.

**Send summary only if:**

```
suppression was active
one or more Critical or High BugCases were created or updated during
suppression window
those BugCases remain unresolved when suppression expires
```

**Do not send summary if:**

```
all suppressed BugCases auto-resolved before suppression ended
```

**Summary format:**

```
Deploy suppression ended

2 unresolved BugCases were active during suppression:

- HIGH Article Freshness Failure — bc_123
- HIGH Briefing Freshness Failure — bc_124
```

The summary does not replay individual suppressed notifications.

---

### TASK-113 — Update Sprint 020 docs and success criteria

Update sprint doc, success criteria, and any inline documentation to
reflect final Sprint 020 scope.

Must reflect:

- Startup detection behavior and detection_type field
- Full Slack notification contract
- Notification attempt records
- Recovery Window replacing flapping detection
- Railway log ingestion explicitly out of scope
- RuntimeExceptionSignalSource explicitly out of scope
- Canonical subsystem enum
- Deterministic severity mapping

Remove from success criteria:

```
Flapping protection activates and notifies correctly under rapid
oscillation
```

Confirm present in success criteria:

```
A BugCase does not auto-resolve if the failure condition recurs during
the Recovery Window
```

---

## Success Criteria

- [ ] All four freshness detectors run in the BugOps polling loop without changes to monitor process structure
- [ ] Each detector correctly distinguishes legitimate idle from broken using the five-part definition
- [ ] Active failures present at BugOps startup create BugCases with detection_type=startup
- [ ] Startup-created Critical and High BugCases send Slack notifications
- [ ] Startup-created downstream failures are cascade-suppressed into upstream BugCases when applicable
- [ ] Cascade suppression attaches downstream signals to upstream BugCases instead of creating new ones
- [ ] Idempotency suppresses duplicate BugCases for repeated observations of the same open condition
- [ ] A BugCase auto-resolves after the Recovery Window elapses without re-violation
- [ ] A BugCase does not auto-resolve if the failure condition recurs during the Recovery Window
- [ ] A detector failure does not halt the polling loop or prevent other detectors from running
- [ ] Slack notifications are sent only for BugCase state changes, not repeated observations
- [ ] Slack messages include severity, root_subsystem, affected_subsystems, summary, first_seen_at, last_seen_at, observation_count, dedupe_key, detection_type, and suggested_manual_check
- [ ] Slack send failure records a failed notification attempt and does not block BugCase creation
- [ ] BugCases with active mute or snooze flags resolve normally when recovery conditions are met
- [ ] Deploy suppression suppresses notification delivery without suppressing BugCase creation or updates
- [ ] Suppression expiry sends one summary for unresolved Critical and High BugCases active during suppression
- [ ] Canonical subsystem names are used consistently across all components
- [ ] Railway log ingestion and runtime exception monitoring are not implemented in Sprint 020
- [ ] Detector runs are observable through structured logs

---

## Agent Safety Notes

These constraints apply to all implementation agents working this sprint:

- Do not modify production data.
- Do not introduce broad database, shell, or filesystem access when a narrow tool/API is sufficient.
- Do not change unrelated files.
- Do not add autonomous destructive actions.
- Keep implementation bounded to the ticket's listed files unless a blocker is documented.
- If the implementation requires a new file/path not listed in the ticket, stop and document why before proceeding.
- The existing LLM cost-runaway detector (`signal_sources/llm_traces.py`) and its tests must not be broken by any ticket in this sprint.
- `published_at` is never used for freshness decisions. Use `created_at` for Articles, `last_updated` for Signals, `last_summary_generated_at` for Narratives, `generated_at` for Briefings.
- All new `BUGOPS_*` environment variables must be added to `src/crypto_news_aggregator/core/config.py` via the existing settings pattern. Do not modify `bugops/config.py` directly.
- Do not implement Slack UI, buttons, slash commands, or acknowledgement actions.
- Do not implement Railway log ingestion or RuntimeExceptionSignalSource.
- Do not implement dedicated flapping detection.

---

## Implementation Notes

### Expected Branch Naming

```text
task/bugops-[ticket-number]-[short-description]
```

### Expected Commit Format

```text
task(bugops): TASK-1XX description
```

### Test Expectations

- Unit tests required for all logic changes, especially DependencyGraph traversal, detector idle vs. broken logic, cascade suppression processing order, startup detection, and Recovery Window timing.
- Integration/manual verification steps must be documented in the ticket completion summary.
- If a test cannot be automated, document the reason and provide a manual verification path.

### Field Name Map (Architecture → Actual)

The architecture documents use `inserted_at` as the generic term for "time artifact was persisted." Actual field names per collection:

| Subsystem  | Collection        | Authoritative Timestamp Field |
|------------|-------------------|-------------------------------|
| Articles   | `articles`        | `created_at`                  |
| Signals    | `signal_scores`   | `last_updated`                |
| Narratives | `narratives`      | `last_summary_generated_at`   |
| Briefings  | `daily_briefings` | `generated_at`                |

---

## Horizon: Sprint 021 and Sprint 022

Sprint 020 is the detection layer. The next two sprints build on it directly.

**Sprint 021 — Evidence & Investigation**
Goal: BugCase → Evidence Pack → Investigation

Once a BugCase exists, Sprint 021 adds automatic evidence collection (Railway logs, deploy context, system state, related BugCases) via a deterministic EvidenceCollector, then feeds that Evidence Pack to an InvestigationProvider (LLM-backed) that produces a structured analysis with likely causes, evidence references, and verification steps. Railway log access must be validated before Sprint 021 begins. Interface contracts are defined in `20-sprint-021-evidence-investigation-interface.md`.

**Sprint 022 — Ticket Factory & Validation**
Goal: Investigation → Ticket → Human Approval → Coding Agent → Validation

Sprint 022 adds the TicketWriter (generates structured implementation tickets from Investigations), human approval workflow, coding-agent handoff format, and a ValidationRunner that determines whether a fix resolved the BugCase or should reopen it. Interface contracts are defined in `30-sprint-022-ticket-validation-interface.md`.

Neither sprint begins until Sprint 020 success criteria are fully met.

---

## Key Decisions

| Date       | Decision | Rationale | Impact |
|------------|----------|-----------|--------|
| Pre-sprint | `inserted_at` in architecture maps to `created_at` on Articles | Actual field name discovered via codebase inspection | All Article freshness queries use `created_at` |
| Pre-sprint | NarrativeFreshness uses `last_summary_generated_at` as primary freshness field | No formal Pydantic model; this field most accurately reflects narrative output | TASK-106 queries `db.narratives` directly |
| Pre-sprint | BriefingFreshness uses two schedule windows (8AM + 8PM EST) with 30-minute grace period | Briefings run twice daily; single-window approach would produce false positives | TASK-107 config uses morning/evening hour + grace period instead of single freshness window |
| Pre-sprint | ArticleFreshness "expected input" check uses `fetched_at` on Article records | No RSS fetch job collection exists; `fetched_at` is the only audit trail | TASK-104 cannot check for a completed fetch job; uses article `fetched_at` instead |
| Pre-sprint | All new `BUGOPS_*` env vars go into `core/config.py` | `bugops/config.py` delegates to `core/config.py`; adding vars there maintains the existing pattern | All config-touching tickets point to `core/config.py` |
| Pre-sprint | Dedicated flapping detection deferred | Recovery Window handles practical oscillation; no evidence Backdrop needs dedicated flapping detection yet | TASK-110 removed; Recovery Window repeated-failure handling merged into TASK-109 |
| Pre-sprint | Railway log ingestion deferred to Sprint 021 | Log access requires validation of programmatic Railway API access before implementation; does not affect outcome freshness detection | Sprint 020 produces BugCases without log context; Sprint 021 EvidenceCollector adds logs |
| Pre-sprint | Startup detection creates BugCases for active failures | Operator needs to know if production is broken when BugOps starts, regardless of when the failure began | TASK-108A added; detection_type field added to BugCase model |

---

## Discovered Work

| Ticket | Title | Reason Created | Status |
|--------|-------|----------------|--------|
| BUG-104 | Cost Runaway Alert Rounds Small Dollar Amounts To $0.00 | Found during TASK-100C Slack webhook verification | Backlog (low priority) |

---

## Session Log

### Session 1 (2026-06-11)

**Completed:**
- TASK-100: Extended BugCase model with 14 Sprint 020 fields
  - Added subsystem tracking, observation tracking, recovery tracking, detection metadata
  - All fields optional/have defaults for backward compatibility
  - Verified BugCase inheritance, test coverage: 25 tests pass (15 model + 10 cost-runaway)
  - Branch: `task/bugops-100-bugcase-model-sprint020`, commits: 4b1880a, 6abdcc9, b115f70

- TASK-100A: Added canonical BugOps subsystem enum
  - Created `BugOpsSubsystem` string enum with 8 canonical values: scheduler, ingestion, articles, signals, narratives, briefings, worker, database
  - Added Pydantic field validators to enforce enum values on root_subsystem, affected_subsystems, and blast_radius
  - Field annotations remain Optional[str] / list[str] for DB and backward compatibility
  - Validators accept raw strings ("articles") and enum instances (BugOpsSubsystem.ARTICLES), reject invalid strings ("article", "ArticleFreshness"), preserve None/empty list compatibility
  - Exported BugOpsSubsystem from bugops/__init__.py for easy import
  - Test coverage: 12 new tests validating enum and field validation; all 27 model tests pass
  - Broader bugops suite has pre-existing failures in test_alert_to_case_flow.py unrelated to this task
  - Branch: `task/bugops-100-bugcase-model-sprint020`, commit: e1efb93

**Next:**
- TASK-100B: Deterministic severity mapping
- TASK-101: MongoDB indexes

### Session 2 (2026-06-12)

**Completed:**
- TASK-100B: Added deterministic severity mapping for Sprint 020 detectors
  - Created `DETECTOR_SEVERITY` dict in signal_sources/severity.py with 4 freshness detectors → High severity
  - Keys: article_freshness, signal_freshness, narrative_freshness, briefing_freshness (raw detector strings)
  - Severity assigned deterministically at detection time, not computed dynamically
  - Test coverage: 6 tests verifying all detectors present and all assigned High severity
  - All 33 tests pass (6 new + 27 existing model tests)
  - Branch: `task/bugops-100b-severity-mapping`, commits: 7f607e2, e7d8e14
  - PR: https://github.com/mikechavez/Backdrop/pull/358

- TASK-101: Added MongoDB indexes for BugOps collections
  - Added 8 indexes across 3 collections: bug_cases (4), bug_alert_events (2), notification_attempts (2)
  - All index names match spec exactly; collection constants follow existing pattern
  - Wired into initialize_indexes() with idempotent _has_index() checks
  - notification_attempts lazy creation verified safe (created when first index is applied)
  - Branch: `task/bugops-101-mongodb-indexes`, commits: de4108c, d993724
  - Test coverage: All 33 existing bugops tests pass; 8 index names verified by import/assertion
  - Manual verification: Index creation requires write-capable credential (not available in test env); to be verified on deploy

- TASK-102: Added create_case_direct() and attach_observation_to_case() to BugOpsStore
  - Freshness detectors create BugCases directly without going through process_alert_event()
  - create_case_direct(case: BugCaseCreate) → BugCase: inserts directly, returns created case
  - attach_observation_to_case(case_id, last_seen_at, affected_subsystems) → BugCase: uses $inc/$set/$addToSet
  - Used ReturnDocument.AFTER (not boolean) for Motor/PyMongo compatibility
  - Test coverage: 9 new tests in test_store_direct.py covering all patterns
  - All 30 tests pass (21 existing + 9 new)
  - Branch: `task/bugops-102-store-direct-methods`, commits: 4e9159a, 6ed0ee1, a46a97e

- TASK-100C: Configured Slack webhook in Railway for BugOps
  - Slack app: existing app reused
  - Webhook: existing webhook reused, verified operational
  - Channel: `#backdrop-bugops` (renamed from `#all-backdrop`)
  - Environment variables: BUGOPS_ENABLED, BUGOPS_SLACK_ENABLED, BUGOPS_SLACK_WEBHOOK_URL configured in Railway
  - Verification: end-to-end test successful — temporary threshold reduction triggered real BugCase and Slack delivery
  - Status: operational, ready for production
  - Completed: 2026-06-12

- TASK-103: Implement DependencyGraph v1
  - Created DependencyGraph class with upstream/downstream traversal
  - Graph: `["scheduler", "ingestion", "articles", "signals", "narratives", "briefings"]`
  - Accepts both `str` and `BugOpsSubsystem` enum inputs (compatibility enhancement)
  - Both methods return `[]` for unknown/reserved subsystems per spec
  - Test coverage: 35 tests pass (24 original + 11 enum-focused)
  - Branch: `task/bugops-103-dependency-graph`, commit: 3f23999
  - Status: ✅ DONE

**Next:**
- TASK-104–107: Four freshness detectors (can run in parallel)
