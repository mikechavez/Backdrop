---
ticket_id: TASK-093
title: Railway Log Data Shape Spike
priority: high
severity: medium
status: COMPLETE
date_created: 2026-05-08
date_completed: 2026-05-08
branch: chore/093-railway-log-data-shape-spike
commit: 0581175
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

- [x] `tests/bugops/fixtures/railway_logs_sample.txt` contains sanitized sample output.
- [x] `docs/bugops/railway-log-data-shape.md` answers the analysis questions.
- [x] `RailwayLogSignalSource` placeholder has TODOs informed by real log sample shape.
- [x] No production Railway log ingestion is implemented in Sprint 018.

---

## Acceptance Criteria

- [x] Real Railway log output has been inspected.
- [x] Sample log data is captured and sanitized.
- [x] SignalSource interface is confirmed compatible or required changes are documented.
- [x] A future Railway log ingestion ticket can be written without guessing log shape.

---

## Implementation Summary (2026-05-08)

**Commands run:**
- `railway logs --lines 200` — real production output captured
- `railway logs --lines 200 --service crypto-news-aggregator` — confirmed single service, no web/worker/beat split
- `railway logs --lines 200 --filter "@level:error"` — captured startup lines + Railway rate-limit platform warnings
- `railway logs --lines 200 --json` — confirmed JSON schema: `{message, timestamp (ISO8601-nanosecond), level}`
- `railway logs --help` — documented actual CLI flags

**Key findings:**
- Project has one Railway service (`crypto-news-aggregator`); `--service web/worker/beat` all return "Service not found"
- Two plain-text formats: Python logging (`YYYY-MM-DD HH:MM:SS,mmm - logger - LEVEL - msg`) and gunicorn (`[timestamp] [pid] [LEVEL] msg`); JSON mode is preferred for ingestion
- Multiline stack traces arrive line-by-line with no Railway-side grouping
- Only `--lines` fetch supported; no time-window queries via CLI
- Railway API token (not CLI) required for non-interactive/in-container use
- Railway platform log-rate-limit warnings carry no timestamp and are bare text
- Three priority patterns identified: `mongo_autoreconnect`, `budget_soft_limit`, `platform_log_rate_limit`
- `SignalSource` interface is compatible as-is; no changes needed

**Files created/modified:**
- `tests/bugops/fixtures/railway_logs_sample.txt` — sanitized real log output (MongoDB hostname redacted to `<MONGO_HOST>`)
- `docs/bugops/railway-log-data-shape.md` — full analysis answering all 8 questions + normalized mapping proposal
- `src/crypto_news_aggregator/bugops/signal_sources/railway_logs.py` — updated placeholder with compiled regex patterns, `BugAlertEventCreate` field mapping, 4 TODOs grounded in real log shape

---

## Impact

Prevents the BugOps intake layer from accidentally hard-coding `llm_traces` assumptions.

---

## Related Tickets

- FEATURE-056
- FEATURE-057
