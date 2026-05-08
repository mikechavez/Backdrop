---
ticket_id: TASK-093
title: Railway Log Data Shape Spike
priority: high
severity: medium
status: OPEN
date_created: 2026-05-08
branch: feature/bugops-signal-intake
effort_estimate: small
---

# TASK-093: Railway Log Data Shape Spike

## Problem Statement

BugOps ultimately needs Railway logs because many production errors surface there before they appear in structured traces. The SignalSource interface must be validated against real Railway log output, not only `llm_traces`.

Sprint 018 should not implement Railway log ingestion, but it should inspect real log shape and document how a future `RailwayLogSignalSource` maps into `bug_alert_events`.

---

## Task

Run local Railway log commands, capture representative output, and document the normalized mapping.

### Files to Create/Modify

```text
docs/bugops/railway-log-data-shape.md
src/crypto_news_aggregator/bugops/signal_sources/railway_logs.py
tests/bugops/fixtures/railway_logs_sample.txt
```

If `docs/bugops/` does not exist yet, create it or use the actual docs location.

### Commands to Run Locally

Run from the repo/project context where Railway CLI is authenticated:

```bash
railway logs --lines 200
railway logs --lines 200 --service web
railway logs --lines 200 --service worker
railway logs --lines 200 --service beat
```

If service flags differ in the installed Railway CLI, document the actual working commands.

### Capture Examples

Capture at least one example if available:

```text
ERROR line
WARNING line
Celery task failure
missing env var / API key error
stack trace excerpt
Railway platform warning, memory warning, or log-rate-limit warning if present
normal startup line
```

### Analysis Questions

Answer in `docs/bugops/railway-log-data-shape.md`:

- Does output include service/process metadata?
- Does output include timestamps?
- Are multiline stack traces preserved or split line-by-line?
- Can logs be fetched by time window or only by line count?
- Can the command run non-interactively in a Railway service, or is local/manual use only for now?
- What fields can map directly into `bug_alert_events`?
- What fields are missing and would need inference?
- What are the first 3 log patterns worth monitoring later?

### Normalized Mapping

Propose a future mapping into:

```python
source_type = "railway_logs"
source_id = "railway_logs.<pattern_name>"
alert_type = "log_error" | "platform_warning" | "missing_env" | "task_failure"
severity = "warning" | "high" | "critical"
domain = [...]
service = "web" | "worker" | "beat" | None
operation = None or inferred operation
raw_sample_ref = "..."
dedupe_key = "railway_logs:<pattern_name>:<service>:<YYYY-MM-DD>:<HH>"
```

---

## Verification

- [ ] `tests/bugops/fixtures/railway_logs_sample.txt` contains sanitized sample output.
- [ ] `docs/bugops/railway-log-data-shape.md` answers the analysis questions.
- [ ] `RailwayLogSignalSource` placeholder has TODOs informed by real log sample shape.
- [ ] No production Railway log ingestion is implemented in Sprint 018.

---

## Acceptance Criteria

- [ ] Real Railway log output has been inspected.
- [ ] Sample log data is captured and sanitized.
- [ ] SignalSource interface is confirmed compatible or required changes are documented.
- [ ] A future Railway log ingestion ticket can be written without guessing log shape.

---

## Impact

Prevents the BugOps intake layer from accidentally hard-coding `llm_traces` assumptions.

---

## Related Tickets

- FEATURE-056
- FEATURE-057
