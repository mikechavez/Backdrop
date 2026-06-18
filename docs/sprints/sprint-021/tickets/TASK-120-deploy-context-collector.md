---
ticket_id: TASK-120
title: Collect deploy context via Railway
priority: high
status: OPEN
phase: A
date_created: 2026-06-16
branch: task/bugops-120-deploy-context-collector
effort_estimate: medium
---

# TASK-120: Collect deploy context via Railway

## Problem Statement

The Evidence Pack has no deploy context. Recent deployments are critical evidence — in the BUG-064 Golden Investigation, the absence of recent deployments was itself diagnostic, eliminating deployment regression as a cause.

---

## Context

Deploy context comes from `RailwayClient` built in TASK-119. Backdrop does not store deployment events internally.

Collect for three services: `fastapi`, `celery_worker`, `celery_scheduler`. Lookback window: 24 hours before `bugcase.first_seen_at` through collection time.

If Railway is unavailable, record as `sections_missing` with explicit reason — do not block Evidence Pack creation.

The absence of deployments must be recorded explicitly in the Evidence Pack (empty list + evidence reference noting no deployments found). Silence about no deployments is ambiguous.

Use `EvidenceReferenceAllocator` for reference IDs.

---

## Task

1. Create `DeployContextCollector` at `bugops/evidence/collectors/deploy_context.py`
2. Register with `EvidenceCollector`
3. Write unit tests

---

## Files to Create

```
src/crypto_news_aggregator/bugops/evidence/collectors/deploy_context.py
tests/bugops/test_deploy_context_collector.py
```

---

## Files to Modify

```
src/crypto_news_aggregator/bugops/evidence/collector.py  (register collector)
```

---

## Do Not Modify

```
src/crypto_news_aggregator/bugops/clients/railway.py
src/crypto_news_aggregator/bugops/models.py
src/crypto_news_aggregator/bugops/monitor.py
```

---

## Implementation Requirements

### DeployContextCollector

Implements `EvidenceCollectorBase`. `collector_name = "deploy_context"`.

```python
SERVICES = ["fastapi", "celery_worker", "celery_scheduler"]
LOOKBACK_HOURS = 24

class DeployContextCollector:
    
    def __init__(self, railway_client: RailwayClient):
        self.railway = railway_client
    
    async def collect(
        self,
        bugcase: BugCase,
        pack_id: str,
        store: BugOpsStore,
        ref_allocator: EvidenceReferenceAllocator,
    ) -> None:
        window_start = bugcase.first_seen_at - timedelta(hours=LOOKBACK_HOURS)
        
        all_deployments = []
        railway_errors = []
        
        for service in SERVICES:
            try:
                deployments = await self.railway.get_recent_deployments(
                    service_name=service,
                    since=window_start,
                )
                for d in deployments:
                    d["service"] = service
                all_deployments.extend(deployments)
            except Exception as e:
                railway_errors.append({
                    "section": f"deploy_context.{service}",
                    "reason": f"Railway API error: {type(e).__name__}: {str(e)[:100]}",
                    "attempted_at": datetime.utcnow().isoformat(),
                })
        
        # Sort by created_at descending
        all_deployments.sort(
            key=lambda d: d.get("created_at", ""),
            reverse=True,
        )
        
        # Evidence reference — absence of deployments is itself evidence
        ref_id = ref_allocator.next_ref()
        ref_description = (
            f"No deployments in 24h preceding incident across {', '.join(SERVICES)}"
            if not all_deployments
            else f"{len(all_deployments)} deployments in 24h window preceding incident"
        )
        
        section_data = {
            "deploy_context": all_deployments,
            "deploy_context_collected_at": datetime.utcnow(),
            "evidence_references": {
                ref_id: {
                    "description": ref_description,
                    "section": "deploy_context",
                }
            },
        }
        
        if railway_errors:
            section_data["sections_missing"] = railway_errors
        
        await store.update_evidence_pack_section(pack_id, section_data)
```

---

## Verification

### Automated Verification

```bash
pytest tests/bugops/test_deploy_context_collector.py -v
pytest tests/bugops/ -v
```

### Required Test Coverage

- [ ] Fetches deployments for all three services (fastapi, celery_worker, celery_scheduler)
- [ ] Passes `window_start = first_seen_at - 24h` to Railway client
- [ ] Handles empty deployments — writes empty list and `deploy_context_collected_at`
- [ ] Adds evidence reference regardless of whether deployments found
- [ ] Reference description states "No deployments" when list is empty
- [ ] Reference description states count when deployments present
- [ ] Sorts deployments by `created_at` descending
- [ ] Handles Railway error for one service — records in `sections_missing`, continues to other services
- [ ] Handles Railway unavailable for all services — records all as `sections_missing`, writes empty deploy_context
- [ ] Uses `ref_allocator.next_ref()` — does not hardcode reference IDs

---

## Acceptance Criteria

- [ ] Deploy context collected for all three services
- [ ] 24-hour lookback window from `first_seen_at`
- [ ] Evidence reference always added — absence of deployments explicitly recorded
- [ ] Railway failure recorded in `sections_missing` per service — does not raise
- [ ] Uses `ref_allocator` for reference IDs
- [ ] All tests pass, no regressions

---

## Related Tickets

- TASK-119: Railway client (must be complete first)
- TASK-123: Monitor wiring (depends on all collectors)

---

## Completion Summary

- Branch:
- Commit:
- Changes made:
- Deviations from plan:
