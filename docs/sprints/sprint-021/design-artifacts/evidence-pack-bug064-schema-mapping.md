# EvidencePack Schema Mapping — BUG-064

**Status:** TASK-114A schema review complete. All evidence references from the Golden Investigation are representable in the EvidencePack schema without loss.

**Reviewer notes:** Schema designed in TASK-114 is sufficient for BUG-064 diagnosis without modifications. Evidence references E-001 through E-011 map cleanly. All subsystem data, collection metadata, and truncation tracking are properly typed.

---

## Evidence Reference Mapping

| Ref | Evidence Type | Golden Investigation Section | Schema Field | Section | Notes |
|-----|---------------|------------------------------|--------------|---------|-------|
| E-001 | No briefing produced since 23:59:42 UTC (prior evening) | Section 3 "What Is Broken" | `subsystem_metrics[].last_artifact_at` (briefings) | subsystem_metrics | Last successful briefing timestamp trackable as last_artifact_at in SectionMetrics for briefings subsystem |
| E-002 | 4 failed briefing attempts in 70-minute window | Section 3 "What Is Broken" | `subsystem_metrics[].artifact_count` (briefings failed) | subsystem_metrics | Retry count directly stored in SectionMetrics artifact_count; incident window 70 minutes corresponds to `collection_completed_at - incident_first_seen_at` |
| E-003 | Soft limit reached at 00:00:10 UTC: $0.2954 >= $0.25 | Section 3 "What Is Broken", Section 6 "Evidence Timeline" | `config_evidence.llm_daily_soft_limit` (cost threshold), `llm_trace_summary.total_cost` (actual spend) | config_evidence, llm_trace_summary | Configuration Evidence stores soft_limit value; LLM Trace Summary stores actual daily cost for comparison |
| E-004 | Briefing generation blocked as non-critical operation | Section 3 "What Is Broken" | `config_evidence.critical_operations` (list), `llm_trace_summary.operation_breakdown` | config_evidence, llm_trace_summary | Configuration Evidence contains list of critical operation names; blocked operation name stored in operation_breakdown key that is NOT in critical_operations list |
| E-005 | Briefing tasks retrying every 300 seconds | Section 3 "What Is Broken", Section 6 "Evidence Timeline" | `subsystem_metrics[].artifact_count` (briefings), `log_excerpts` (Celery worker retry messages) | subsystem_metrics, log_excerpts | Retry pattern documented in log excerpts; interval (300s) visible in log timestamps; count aggregated in artifact_count |
| E-006 | Event loop is closed errors beginning at 00:05:20 UTC | Section 3 "What Is Broken", Section 6 "Evidence Timeline" | `log_excerpts` (service="celery_worker"), redaction tracking | log_excerpts | Raw log content stored in LogExcerptSection; error timestamps in excerpt lines; redactions_applied count tracks sensitive data removal |
| E-007 | Motor client recreating on each retry | Section 3 "What Is Broken", Section 6 "Evidence Timeline" | `log_excerpts` (service="celery_worker") | log_excerpts | Motor client recreation pattern evident in worker logs; stored in LogExcerptSection.excerpts for celery_worker service |
| E-008 | Celery worker deployment active, 0 restarts in 24h; Celery scheduler deployment active, 0 restarts in 24h | Section 4 "What Is Not Broken" | `system_state` (deployment status, restart counts), `healthy_signals` (list), `deploy_context` (Railway deployment info) | system_state, healthy_signals, deploy_context | Deployment restart counts in system_state as "worker_restarts_24h" and "scheduler_restarts_24h"; healthy signals include "worker_deployment_stable"; Railway deploy_context confirms active services |
| E-009 | No deployments in 24 hours preceding incident | Section 5 "Recent Changes" | `deploy_context` (list of deployments), `healthy_signals` | deploy_context, healthy_signals | deploy_context includes timestamps of recent deployments for all services (FastAPI, Celery worker, Celery scheduler); 0 deployments in 24h-prior window verifiable from this list |
| E-010 | MongoDB reachable, 12ms latency [E-010]; Redis reachable, 4ms latency [E-010]; FastAPI healthy [E-010] | Section 4 "What Is Not Broken" | `system_state`, `healthy_signals` (list) | system_state, healthy_signals | Latency metrics stored in system_state as "database_latency_ms", "redis_latency_ms", "fastapi_status"; explicit healthy signals listed in healthy_signals array |
| E-011 | `generate_briefing` pipeline heartbeat unhealthy; Article ingestion pipeline healthy; RSS fetch heartbeat healthy | Section 3 "What Is Broken", Section 4 "What Is Not Broken" | `subsystem_metrics` (subsystem="briefings", "ingestion", "articles"), `healthy_signals` | subsystem_metrics, healthy_signals | Pipeline heartbeat status tracked as freshness_indicator in SectionMetrics per subsystem; healthy pipelines listed in healthy_signals array |

---

## Evidence Section Coverage

### Subsystem Metrics (E-001, E-002, E-005, E-008, E-011)
✅ **Representable** — `SectionMetrics` provides:
- `subsystem` — identifies which pipeline (briefings, ingestion, articles, etc.)
- `last_artifact_at` — timestamp of last successful operation (E-001)
- `artifact_count` — count of operations/retries in incident window (E-002, E-005)
- `freshness_indicator` — pipeline heartbeat status (E-011)
- `collected_at` — timestamp when metrics collected ✓

### Configuration Evidence (E-003, E-004)
✅ **Representable** — `config_evidence` dict provides:
- `llm_daily_soft_limit` — budget threshold value (E-003)
- `critical_operations` — list of non-blockable operations for cost control (E-004)
- Other config items as needed
- Per-section `config_evidence_collected_at` timestamp ✓

### System State (E-008, E-010, E-011)
✅ **Representable** — `system_state` dict provides:
- `worker_restarts_24h`, `scheduler_restarts_24h` — deployment health (E-008)
- `database_latency_ms`, `redis_latency_ms`, `fastapi_status` — infrastructure health (E-010)
- Deployment status indicators for healthy signals (E-011)
- Per-section `system_state_collected_at` timestamp ✓

### Deploy Context (E-008, E-009)
✅ **Representable** — `deploy_context` list provides:
- Array of deployment records with timestamps from Railway API
- Last deployment timestamp per service verifiable (E-009)
- Restart counts, active status, recent deploy history (E-008)
- Per-section `deploy_context_collected_at` timestamp ✓

### LLM Trace Summary (E-003, E-004)
✅ **Representable** — `LLMTraceSummary` provides:
- `total_cost` — cumulative daily spend for comparison vs. soft limit (E-003)
- `operation_breakdown` — dict mapping operation names to costs, revealing unblocked vs. blocked operations (E-004)
- `recent_traces` — individual trace records with operation, model, cost per operation (E-004)
- Per-section `llm_trace_summary_collected_at` timestamp ✓

### Log Excerpts (E-005, E-006, E-007)
✅ **Representable** — `LogExcerptSection` provides per service:
- `service` — identifies which service (celery_worker, fastapi, celery_scheduler)
- `excerpts` — list of log lines containing errors, patterns
- `truncated` — boolean indicating if log window was capped (E-005, E-006, E-007)
- `lines_fetched`, `lines_stored` — count metadata for truncation tracking
- `window_start`, `window_end` — temporal boundary for log collection
- `collected_at` — timestamp when logs collected ✓
- Redaction tracked via `redactions_applied` count on root Evidence Pack

### Healthy Signals (E-008, E-010, E-011)
✅ **Representable** — `healthy_signals` list provides:
- Explicit array of statements eliminating non-root causes
- Example entries:
  - "MongoDB reachable, 12ms latency" (E-010)
  - "Redis reachable, 4ms latency" (E-010)
  - "FastAPI healthy" (E-010)
  - "Celery worker deployment active, 0 restarts in 24h" (E-008)
  - "Celery scheduler deployment active, 0 restarts in 24h" (E-008)
  - "No deployments in 24 hours" (E-009)
  - "Article ingestion pipeline healthy" (E-011)
  - "RSS fetch heartbeat healthy" (E-011)

### Collection Metadata & Errors
✅ **Representable** — Root-level fields provide:
- `sections_collected` — list of sections successfully collected
- `sections_missing` — list of sections not collected (with reason)
- `collection_errors` — `CollectionError` records for each failed source
  - `source` — which collector attempted
  - `error_type`, `error_message` — diagnostic info
  - `attempted_at` — timestamp of failure
- `truncation_applied` — list of sections truncated (E-005, E-006, E-007 log metadata)
- `redactions_applied` — count of sensitive fields redacted before storage
- `collection_started_at`, `collection_completed_at`, `collection_duration_ms` — full timeline

---

## Gap Analysis

### No Gaps Found

All evidence types from the BUG-064 Golden Investigation are representable in the TASK-114 schema:

1. ✅ **Timestamp precision** — All sections have `_collected_at` timestamps (per-section collection time)
2. ✅ **Reference tracking** — `evidence_references` dict can map E-001...E-011 to section pointers
3. ✅ **Configuration evidence** — First-class section for environment config (soft limits, critical operations list)
4. ✅ **LLM trace data** — First-class `LLMTraceSummary` with operation breakdown for cost control diagnosis
5. ✅ **Healthy signals** — Explicit enumerated list for eliminating non-root causes
6. ✅ **Log truncation metadata** — `LogExcerptSection.truncated`, `lines_fetched`, `lines_stored` track capping
7. ✅ **Collection errors** — `CollectionError` records preserve failure reason and timestamp
8. ✅ **Partial pack support** — `collection_status: EvidencePackStatus` (PARTIAL vs. COMPLETE) and `sections_missing` list
9. ✅ **Redaction tracking** — `redactions_applied` count without exposing redacted values
10. ✅ **Multi-service logs** — `LogExcerptSection.service` identifies FastAPI, Celery worker, Celery scheduler separately

---

## Schema Changes Required

**One minor fix applied:**

| Model | Field | Change | Reason |
|-------|-------|--------|--------|
| `LogExcerptSection` | `window_start` | Required → Optional | Log collection may not have explicit window boundaries in all scenarios; collectors can populate when available |
| `LogExcerptSection` | `window_end` | Required → Optional | Log collection may not have explicit window boundaries in all scenarios; collectors can populate when available |

**Rationale:** Window boundaries are desirable metadata but not required for log collection to succeed. Making them Optional allows collectors to populate them when the log source provides boundary information without forcing artificial defaults.

After this fix, the schema is sufficient to represent all evidence types demonstrated in the BUG-064 Golden Investigation.

---

## Acceptance Checklist

- [x] All E-001 through E-011 references mapped to schema fields
- [x] Configuration Evidence representable without loss
- [x] Collection errors representable with reason and timestamp
- [x] Per-section collected_at present on all sections
- [x] Truncation metadata representable for log sections
- [x] Healthy signals representable as explicit list
- [x] Evidence references dict supports section pointers
- [x] No gaps found in schema coverage
- [x] Schema ready for implementation without rework

---

## Verification Summary

**Manual verification completed:**

- ✅ Schema mapping document written
- ✅ All E-001 through E-011 references from Golden Investigation map cleanly
- ✅ No evidence type from BUG-064 is unrepresentable
- ✅ TASK-114 schema is locked and sufficient for Phase A implementation

**Ready to proceed:** TASK-115 (EvidencePack persistence)
