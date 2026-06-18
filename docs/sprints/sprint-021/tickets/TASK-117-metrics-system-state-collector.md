---
ticket_id: TASK-117
title: Collect subsystem metrics and system state
priority: high
status: OPEN
phase: A
date_created: 2026-06-16
branch: task/bugops-117-metrics-system-state
effort_estimate: medium
---

# TASK-117: Collect subsystem metrics and system state

## Problem Statement

The Evidence Pack has no collector for subsystem freshness metrics or system health state. These are the most compact, high-signal evidence sections and are never truncated regardless of pack size.

---

## Context

For the BUG-064 Golden Investigation, the most diagnostic evidence was NOT logs — it was the combination of cost metrics, the exact incident timestamp, and healthy signals eliminating other subsystems. Subsystem metrics and system state are the highest-value evidence sections.

**Subsystem metrics** — query MongoDB for freshness indicators per affected subsystem. Use `inserted_at` / `created_at` as authoritative timestamp (never `published_at`). Deterministic, no LLM.

**System state** — call `GET /api/v1/health` on FastAPI (no auth required). Returns MongoDB, Redis, LLM gateway, pipeline heartbeat, and data freshness status in one request.

**Healthy signals** — derived from system state. Explicitly enumerate what was confirmed healthy and what each signal eliminates as a primary cause. This section is required, not optional. The Investigation's "What Is Not Broken" section depends entirely on this.

**Celery worker/scheduler liveness** — NOT collected in this ticket. Railway API client does not exist until TASK-119. Explicitly record as `sections_missing` with reason `"Railway client not yet available; worker/scheduler status collected in TASK-120 era"`. Do not block or stub with fake data.

System state is current-at-collection-time. The Evidence Pack records `system_state_collected_at`. The Investigation must not imply system state reflects incident time if collection occurred later.

Use `EvidenceReferenceAllocator` (from TASK-114) for all evidence reference IDs — call `ref_allocator.next_ref()` per reference added. Do not hardcode E-001, E-002, etc.

---

## Task

1. Create `MetricsCollector` at `bugops/evidence/collectors/metrics.py`
2. Create `SystemStateCollector` at `bugops/evidence/collectors/system_state.py`
3. Create `bugops/evidence/collectors/__init__.py`
4. Register both collectors in `EvidenceCollector.__init__` (in `collector.py`)
5. Write unit tests for both collectors

---

## Files to Create

```
src/crypto_news_aggregator/bugops/evidence/collectors/__init__.py
src/crypto_news_aggregator/bugops/evidence/collectors/metrics.py
src/crypto_news_aggregator/bugops/evidence/collectors/system_state.py
tests/bugops/test_metrics_collector.py
tests/bugops/test_system_state_collector.py
```

---

## Files to Modify

```
src/crypto_news_aggregator/bugops/evidence/collector.py  (register both collectors)
src/crypto_news_aggregator/core/config.py                (add BUGOPS_HEALTH_ENDPOINT_URL)
```

---

## Do Not Modify

```
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/api/v1/health.py
src/crypto_news_aggregator/bugops/evidence/base.py
src/crypto_news_aggregator/bugops/models.py
```

---

## Implementation Requirements

### New config key

```python
# In core/config.py BugOps section:
BUGOPS_HEALTH_ENDPOINT_URL: str = "http://localhost:8000"
```

### MetricsCollector

Implements `EvidenceCollectorBase`. `collector_name = "metrics"`.

```python
async def collect(
    self,
    bugcase: BugCase,
    pack_id: str,
    store: BugOpsStore,
    ref_allocator: EvidenceReferenceAllocator,
) -> None:
```

**Subsystem → MongoDB query mapping:**

| Subsystem | Collection | Timestamp field |
|-----------|-----------|-----------------|
| articles | articles | created_at |
| signals | signals | last_updated |
| narratives | narratives | last_summary_generated_at |
| briefings | briefings | generated_at |
| scheduler | — | n/a (no direct collection) |
| ingestion | — | n/a (proxied via articles) |
| worker | — | n/a (no direct collection) |
| database | — | n/a (from system state) |

For each subsystem in `bugcase.blast_radius + [bugcase.root_subsystem]` that has a MongoDB collection:
- `find_one` sorted by timestamp descending → most recent artifact
- `count_documents` with timestamp within `BUGOPS_ARTICLE_FRESHNESS_WINDOW_MINUTES` (use existing config) → recent count
- Build `SectionMetrics` with `last_artifact_at`, `artifact_count`, human-readable `freshness_indicator`

`freshness_indicator` format: `"47 minutes ago"` if outside window, `"within window"` if inside.

For each subsystem metric, add one evidence reference:
```python
ref_id = ref_allocator.next_ref()
evidence_references[ref_id] = {
    "description": f"Last {subsystem} artifact timestamp and count",
    "section": "subsystem_metrics",
    "subsystem": subsystem,
}
```

Write to Evidence Pack:
```python
await store.update_evidence_pack_section(pack_id, {
    "subsystem_metrics": [m.model_dump() for m in metrics_list],
    "subsystem_metrics_collected_at": datetime.utcnow(),
    "evidence_references": evidence_references,
})
```

### SystemStateCollector

Implements `EvidenceCollectorBase`. `collector_name = "system_state"`.

```python
async def collect(
    self,
    bugcase: BugCase,
    pack_id: str,
    store: BugOpsStore,
    ref_allocator: EvidenceReferenceAllocator,
) -> None:
```

**Health endpoint call:**
```python
import httpx

async with httpx.AsyncClient() as client:
    response = await client.get(
        f"{self.settings.BUGOPS_HEALTH_ENDPOINT_URL}/api/v1/health",
        timeout=10.0,
    )
    health_data = response.json()
```

On timeout or HTTP error: record in `sections_missing` with reason, do not raise.

**system_state dict shape** (mirrors `/health` response):
```python
{
    "mongodb": {"status": "ok", "latency_ms": 12},
    "redis": {"status": "ok", "latency_ms": 4},
    "fastapi": {"status": "healthy"},
    "llm": {"status": "ok", "model": "..."},
    "pipeline": {
        "fetch_news": {"status": "ok", "last_success": "..."},
        "generate_briefing": {"status": "unhealthy", "message": "..."},
    },
}
```

**Healthy signals derivation** — add to `healthy_signals` list for each passing check:
- `database.status == "ok"` → `f"MongoDB reachable ({latency_ms}ms)"`
- `redis.status == "ok"` → `f"Redis reachable ({latency_ms}ms)"`
- `llm.status == "ok"` → `"LLM gateway healthy"`
- `pipeline.fetch_news.status == "ok"` → `"RSS fetch pipeline healthy"`
- `pipeline.generate_briefing.status == "ok"` → `"Briefing pipeline healthy"`
- Overall `status == "healthy"` → `"FastAPI healthy"`

Do NOT add a healthy signal for any check with status `"error"`, `"degraded"`, `"warning"`, or `"critical"`.

**Celery worker/scheduler** — NOT collected here. Record explicitly:
```python
sections_missing_entries = [
    {
        "section": "system_state.celery_worker",
        "reason": "Railway client not available until TASK-119; worker status deferred",
        "attempted_at": datetime.utcnow().isoformat(),
    },
    {
        "section": "system_state.celery_scheduler",
        "reason": "Railway client not available until TASK-119; scheduler status deferred",
        "attempted_at": datetime.utcnow().isoformat(),
    },
]
```

Add one evidence reference for the system state section:
```python
ref_id = ref_allocator.next_ref()
evidence_references[ref_id] = {
    "description": "System state at collection time — MongoDB, Redis, FastAPI, pipeline heartbeats",
    "section": "system_state",
    "field": "checks",
}
```

---

## Verification

### Automated Verification

```bash
pytest tests/bugops/test_metrics_collector.py -v
pytest tests/bugops/test_system_state_collector.py -v
pytest tests/bugops/ -v
```

### Required Test Coverage

**MetricsCollector:**
- [ ] Queries correct MongoDB collection for each subsystem (articles, signals, narratives, briefings)
- [ ] Builds `SectionMetrics` with `last_artifact_at`, `artifact_count`, `freshness_indicator`
- [ ] `freshness_indicator` shows `"within window"` for recent artifacts
- [ ] `freshness_indicator` shows elapsed time for stale artifacts
- [ ] Handles subsystem with no artifacts — `last_artifact_at=None`, `artifact_count=0`
- [ ] Skips subsystems without MongoDB collections (scheduler, worker, database)
- [ ] Uses `ref_allocator.next_ref()` for each reference — does not hardcode E-001
- [ ] Writes `subsystem_metrics_collected_at` timestamp

**SystemStateCollector:**
- [ ] Calls `/api/v1/health` on configured URL
- [ ] Parses `database`, `redis`, `llm`, `pipeline` check sections
- [ ] Adds healthy signal only for `status == "ok"` or `status == "healthy"` checks
- [ ] Does NOT add healthy signal for degraded or error checks
- [ ] Records Celery worker and scheduler as `sections_missing` with explicit reason
- [ ] Handles `/health` timeout — records in `sections_missing`, does not raise
- [ ] Uses `ref_allocator.next_ref()` for system state reference

---

## Acceptance Criteria

- [ ] `MetricsCollector` queries MongoDB freshness per affected subsystem
- [ ] `SystemStateCollector` calls `/health` and parses all check sections
- [ ] Healthy signals section is populated — never empty when health data is available
- [ ] Celery worker/scheduler explicitly recorded as `sections_missing` (not silently absent)
- [ ] Both collectors use `ref_allocator` — no hardcoded reference IDs
- [ ] Both collectors registered with `EvidenceCollector`
- [ ] Both collectors handle errors internally — do not raise
- [ ] All new tests pass
- [ ] All existing BugOps tests continue to pass

---

## Related Tickets

- TASK-116: Framework (must be complete first)
- TASK-119: Railway client (Celery liveness deferred until then)

---

## Completion Summary

- Branch:
- Commit:
- Changes made:
- Tests run:
- Deviations from plan:
