---
ticket_id: TASK-121
title: Collect Configuration Evidence
priority: high
status: OPEN
phase: A
date_created: 2026-06-16
branch: task/bugops-121-config-evidence-collector
effort_estimate: small
---

# TASK-121: Collect Configuration Evidence

## Problem Statement

The BUG-064 Golden Incident exercise revealed that the operation name mismatch (`briefing_generate` vs `briefing_generation` in `CRITICAL_OPERATIONS`) was unconfirmable from the Evidence Pack without reading the config. Configuration Evidence is a first-class collector added specifically to close this gap.

---

## Context

Configuration Evidence collects incident-relevant configuration values only — not a full config dump. This is the smallest and most deterministic collector. No Railway API, no MongoDB queries, no LLM.

Sprint 021 scope:
- LLM gateway budget settings: `LLM_DAILY_SOFT_LIMIT`, `LLM_DAILY_HARD_LIMIT`
- `CRITICAL_OPERATIONS` list from `cost_tracker.py`
- BugOps freshness window thresholds from `core/config.py`

Can run in parallel with TASK-117, TASK-118, and TASK-119 — no dependencies on those tickets.

Use `EvidenceReferenceAllocator` for reference IDs.

---

## Task

1. Create `ConfigEvidenceCollector` at `bugops/evidence/collectors/config_evidence.py`
2. Register with `EvidenceCollector`
3. Write unit tests

---

## Files to Create

```
src/crypto_news_aggregator/bugops/evidence/collectors/config_evidence.py
tests/bugops/test_config_evidence_collector.py
```

---

## Files to Modify

```
src/crypto_news_aggregator/bugops/evidence/collector.py  (register collector)
```

---

## Do Not Modify

```
src/crypto_news_aggregator/services/cost_tracker.py
src/crypto_news_aggregator/core/config.py
src/crypto_news_aggregator/bugops/models.py
src/crypto_news_aggregator/bugops/monitor.py
```

---

## Implementation Requirements

### ConfigEvidenceCollector

Implements `EvidenceCollectorBase`. `collector_name = "config_evidence"`.

```python
class ConfigEvidenceCollector:
    
    def __init__(self, settings, cost_tracker_module):
        """
        settings: the get_settings() instance
        cost_tracker_module: imported cost_tracker module
          (allows reading CRITICAL_OPERATIONS without modifying cost_tracker.py)
        """
        self.settings = settings
        self.cost_tracker = cost_tracker_module
    
    async def collect(
        self,
        bugcase: BugCase,
        pack_id: str,
        store: BugOpsStore,
        ref_allocator: EvidenceReferenceAllocator,
    ) -> None:
        config = {
            "llm_daily_soft_limit": getattr(self.settings, "LLM_DAILY_SOFT_LIMIT", None),
            "llm_daily_hard_limit": getattr(self.settings, "LLM_DAILY_HARD_LIMIT", None),
            "critical_operations": sorted(list(
                getattr(self.cost_tracker, "CRITICAL_OPERATIONS", set())
            )),
            "bugops_thresholds": {
                "article_freshness_window_minutes": getattr(
                    self.settings, "BUGOPS_ARTICLE_FRESHNESS_WINDOW_MINUTES", None
                ),
                "signal_freshness_window_minutes": getattr(
                    self.settings, "BUGOPS_SIGNAL_FRESHNESS_WINDOW_MINUTES", None
                ),
                "narrative_freshness_window_minutes": getattr(
                    self.settings, "BUGOPS_NARRATIVE_FRESHNESS_WINDOW_MINUTES", None
                ),
                "recovery_window_minutes": getattr(
                    self.settings, "BUGOPS_RECOVERY_WINDOW_MINUTES", None
                ),
                "evidence_settling_window_minutes": getattr(
                    self.settings, "BUGOPS_EVIDENCE_SETTLING_WINDOW_MINUTES", None
                ),
            },
            "investigation_config": {
                # Investigation model and budget settings — not needed for Phase A
                # but recorded now so future incidents are diagnosable if investigation
                # generation fails due to model routing or budget issues
                "investigation_model": getattr(
                    self.settings, "BUGOPS_INVESTIGATION_MODEL", None
                ),
                "investigation_max_input_tokens": getattr(
                    self.settings, "BUGOPS_INVESTIGATION_MAX_INPUT_TOKENS", None
                ),
                "evidence_max_total_chars": getattr(
                    self.settings, "BUGOPS_EVIDENCE_MAX_TOTAL_CHARS", None
                ),
            }
        }
        
        # Add two evidence references:
        # One for budget threshold (directly relevant to cost-control failures like BUG-064)
        # One for critical_operations list (directly relevant to operation classification failures)
        ref_budget = ref_allocator.next_ref()
        ref_ops = ref_allocator.next_ref()
        
        evidence_references = {
            ref_budget: {
                "description": f"LLM daily soft limit: {config['llm_daily_soft_limit']}",
                "section": "config_evidence",
                "field": "llm_daily_soft_limit",
            },
            ref_ops: {
                "description": f"Critical operations list: {config['critical_operations']}",
                "section": "config_evidence",
                "field": "critical_operations",
            },
        }
        
        await store.update_evidence_pack_section(pack_id, {
            "config_evidence": config,
            "config_evidence_collected_at": datetime.utcnow(),
            "evidence_references": evidence_references,
        })
```

**Missing settings handling:** Use `getattr(self.settings, "KEY", None)` throughout. If a setting doesn't exist on the settings object, store `None` — do not raise. This makes the collector forward-compatible if config keys are renamed.

---

## Verification

### Automated Verification

```bash
pytest tests/bugops/test_config_evidence_collector.py -v
pytest tests/bugops/ -v
```

### Required Test Coverage

- [ ] Reads `LLM_DAILY_SOFT_LIMIT` from settings
- [ ] Reads `LLM_DAILY_HARD_LIMIT` from settings
- [ ] Reads `CRITICAL_OPERATIONS` from cost_tracker module as a sorted list
- [ ] Reads all four BugOps freshness window thresholds
- [ ] Handles missing settings keys gracefully — stores `None`, does not raise
- [ ] Handles `CRITICAL_OPERATIONS` missing from cost_tracker — stores empty list
- [ ] Adds two evidence references: one for budget threshold, one for critical_operations
- [ ] Reference descriptions include the actual values (not just field names)
- [ ] Writes `config_evidence_collected_at` timestamp
- [ ] Uses `ref_allocator.next_ref()` — does not hardcode reference IDs

---

## Acceptance Criteria

- [ ] `ConfigEvidenceCollector` reads LLM budget settings and `CRITICAL_OPERATIONS`
- [ ] Two evidence references added — budget threshold and critical operations list with actual values in description
- [ ] Missing settings handled gracefully with `None` values
- [ ] Collector registered with `EvidenceCollector`
- [ ] All tests pass, no regressions

---

## Related Tickets

- TASK-116: Framework (must be complete first)
- TASK-119: Not required — no Railway dependency
- TASK-123: Monitor wiring (depends on all collectors)

---

## Completion Summary

- Branch: task/bugops-121-config-evidence-collector
- Commit: 68a97e4
- Changes made:
  - Created `ConfigEvidenceCollector` at `bugops/evidence/collectors/config_evidence.py`
  - Collects LLM daily soft/hard limits, CRITICAL_OPERATIONS, BugOps thresholds, investigation config
  - Handles missing settings gracefully (stores None, forward-compatible)
  - Adds two evidence references: one for budget threshold, one for operations list
  - Evidence descriptions include actual values for diagnostic value
  - Auto-registered with EvidenceCollector during initialization
  - Created 13 comprehensive unit tests covering all acceptance criteria
  - Updated framework tests to expect 5 collectors (added config_evidence)
- Deviations from plan: None; implementation matches ticket requirements exactly
