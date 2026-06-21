---
ticket_id: TASK-122
title: Collect Railway log excerpts with redaction
priority: high
status: OPEN
phase: A
date_created: 2026-06-16
branch: task/bugops-122-railway-log-collector-redaction
effort_estimate: medium
---

# TASK-122: Collect Railway log excerpts with redaction

## Problem Statement

The Evidence Pack has no log excerpts. Logs provide supporting context for hypotheses formed from metrics and system state. They must be redacted before storage and before any LLM sees them.

---

## Context

Log collection uses `RailwayClient` from TASK-119. Three services: `fastapi`, `celery_worker`, `celery_scheduler`. Redis logs excluded in Sprint 021.

Window: `BUGOPS_LOG_WINDOW_MINUTES` (default 10) on each side of `first_seen_at` and `last_seen_at`. Line cap: `BUGOPS_LOG_LINE_CAP` (default 200) per service.

**Truncation detection** — `RailwayClient.get_logs()` already handles this via the `line_cap + 1` strategy (implemented in TASK-119) and returns `(lines, was_truncated)`. `LogCollector` uses that return value directly.

**Redaction is mandatory.** Log lines must be redacted before writing to Evidence Pack storage. The InvestigationProvider must never receive unredacted log content. Redaction happens in `LogCollector` before calling `store.update_evidence_pack_section()`.

**Evidence note from BUG-064:** For cost-control failures, logs confirmed the retry pattern but were not the primary diagnostic evidence. Metrics and config evidence were more decisive. Log excerpts are supporting context — valuable but not always the highest-signal section.

---

## Task

1. Create `LogRedactor` at `bugops/evidence/redaction.py`
2. Create `LogCollector` at `bugops/evidence/collectors/logs.py`
3. Register `LogCollector` with `EvidenceCollector`
4. Write unit tests for both

---

## Files to Create

```
src/crypto_news_aggregator/bugops/evidence/redaction.py
src/crypto_news_aggregator/bugops/evidence/collectors/logs.py
tests/bugops/test_log_redactor.py
tests/bugops/test_log_collector.py
```

---

## Files to Modify

```
src/crypto_news_aggregator/bugops/evidence/collector.py  (register LogCollector)
```

---

## Do Not Modify

```
src/crypto_news_aggregator/bugops/clients/railway.py
src/crypto_news_aggregator/bugops/models.py
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/bugops/signal_sources/railway_logs.py
```

---

## Implementation Requirements

### LogRedactor

```python
# bugops/evidence/redaction.py
import re

REDACTION_PATTERNS = [
    # MongoDB connection strings
    (r'mongodb(\+srv)?://[^\s\'"<>]+', '[REDACTED:MONGO_URI]'),
    # Bearer tokens
    (r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', 'Bearer [REDACTED]'),
    # Authorization headers
    (r'(Authorization|X-Api-Key)\s*:\s*\S+', r'\1: [REDACTED]'),
    # Generic secret key=value patterns
    (r'(api[_-]?key|token|secret|password|passwd|pwd)\s*[=:]\s*[^\s\'"<>{},]{8,}',
     r'\1=[REDACTED:SECRET]'),
    # Email addresses
    (r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[REDACTED:EMAIL]'),
    # Long hex strings (likely tokens/keys — 32+ hex chars)
    (r'\b[0-9a-fA-F]{32,}\b', '[REDACTED:TOKEN]'),
]

class LogRedactor:
    
    def __init__(self):
        self._patterns = [
            (re.compile(pattern, re.IGNORECASE), replacement)
            for pattern, replacement in REDACTION_PATTERNS
        ]
    
    def redact_line(self, line: str) -> tuple[str, bool]:
        """
        Apply all redaction patterns to a single log line.
        Returns (redacted_line, was_redacted).
        was_redacted is True if any pattern matched.
        """
        redacted = line
        was_redacted = False
        for pattern, replacement in self._patterns:
            new_line = pattern.sub(replacement, redacted)
            if new_line != redacted:
                was_redacted = True
                redacted = new_line
        return redacted, was_redacted
    
    def redact_lines(self, lines: list[str]) -> tuple[list[str], int]:
        """
        Redact all lines in a list.
        Returns (redacted_lines, total_lines_with_redactions).
        """
        redacted_lines = []
        redaction_count = 0
        for line in lines:
            redacted, was_redacted = self.redact_line(line)
            redacted_lines.append(redacted)
            if was_redacted:
                redaction_count += 1
        return redacted_lines, redaction_count
```

### LogCollector

Implements `EvidenceCollectorBase`. `collector_name = "logs"`.

```python
SERVICES = ["fastapi", "celery_worker", "celery_scheduler"]

class LogCollector:
    
    def __init__(self, railway_client: RailwayClient, redactor: LogRedactor, settings):
        self.railway = railway_client
        self.redactor = redactor
        self.settings = settings
    
    async def collect(
        self,
        bugcase: BugCase,
        pack_id: str,
        store: BugOpsStore,
        ref_allocator: EvidenceReferenceAllocator,
    ) -> None:
        window_minutes = self.settings.BUGOPS_LOG_WINDOW_MINUTES
        line_cap = self.settings.BUGOPS_LOG_LINE_CAP
        
        # Expand window around the full incident duration
        window_start = bugcase.first_seen_at - timedelta(minutes=window_minutes)
        window_end = (bugcase.last_seen_at or bugcase.first_seen_at) + timedelta(minutes=window_minutes)
        
        log_sections = []
        total_redactions = 0
        missing_sections = []
        
        for service in SERVICES:
            try:
                lines, was_truncated = await self.railway.get_logs(
                    service_name=service,
                    start_time=window_start,
                    end_time=window_end,
                    line_cap=line_cap,
                )
                
                redacted_lines, redaction_count = self.redactor.redact_lines(lines)
                total_redactions += redaction_count
                
                section = LogExcerptSection(
                    service=service,
                    lines_fetched=len(lines),
                    lines_stored=len(redacted_lines),
                    truncated=was_truncated,
                    window_start=window_start,
                    window_end=window_end,
                    excerpts=redacted_lines,
                )
                log_sections.append(section.model_dump())
                
            except Exception as e:
                missing_sections.append({
                    "section": f"logs.{service}",
                    "reason": f"Railway API error: {type(e).__name__}: {str(e)[:100]}",
                    "attempted_at": datetime.utcnow().isoformat(),
                })
                logger.error(f"LogCollector: failed to fetch logs for {service}: {e}")
        
        section_data = {
            "log_excerpts": log_sections,
            "redactions_applied": total_redactions,
        }
        
        if missing_sections:
            section_data["sections_missing"] = missing_sections
        
        # Add one evidence reference for logs overall
        if log_sections:
            ref_id = ref_allocator.next_ref()
            total_lines = sum(s["lines_stored"] for s in log_sections)
            truncated_services = [s["service"] for s in log_sections if s["truncated"]]
            ref_description = (
                f"Log excerpts: {total_lines} lines across {len(log_sections)} services"
                + (f" (truncated: {', '.join(truncated_services)})" if truncated_services else "")
            )
            section_data["evidence_references"] = {
                ref_id: {
                    "description": ref_description,
                    "section": "log_excerpts",
                }
            }
        
        await store.update_evidence_pack_section(pack_id, section_data)
```

---

## Verification

### Automated Verification

```bash
pytest tests/bugops/test_log_redactor.py -v
pytest tests/bugops/test_log_collector.py -v
pytest tests/bugops/ -v
```

### Required Test Coverage

**LogRedactor:**
- [ ] Redacts MongoDB URIs (mongodb:// and mongodb+srv://)
- [ ] Redacts Bearer tokens in Authorization headers
- [ ] Redacts `api_key=<value>` and `token=<value>` patterns
- [ ] Redacts email addresses
- [ ] Redacts 32+ character hex strings
- [ ] Does NOT redact normal log content (timestamps, log levels, Python exception messages, stack traces)
- [ ] `was_redacted` is True only when a pattern matched
- [ ] `redaction_count` matches lines-with-redactions (not total substitutions)
- [ ] Handles empty string input

**LogCollector:**
- [ ] Fetches logs for all three services (fastapi, celery_worker, celery_scheduler)
- [ ] Window is `first_seen_at - window_minutes` to `last_seen_at + window_minutes`
- [ ] Uses `BUGOPS_LOG_LINE_CAP` from settings
- [ ] `LogExcerptSection.truncated` reflects `was_truncated` from Railway client
- [ ] `LogExcerptSection.lines_fetched` and `lines_stored` are accurate
- [ ] Redacts all lines before calling `store.update_evidence_pack_section()`
- [ ] Railway unavailable for one service → recorded in `sections_missing`, continues to other services
- [ ] Railway unavailable for all services → all recorded in `sections_missing`, empty `log_excerpts`
- [ ] `redactions_applied` count is sum across all services
- [ ] Adds evidence reference describing total lines and truncated services
- [ ] Uses `ref_allocator.next_ref()` — does not hardcode reference IDs

---

## Acceptance Criteria

- [ ] `LogRedactor` applies all patterns, returns accurate redaction count
- [ ] `LogCollector` fetches logs for fastapi, celery_worker, celery_scheduler
- [ ] Log lines are redacted before `store.update_evidence_pack_section()` is called
- [ ] Truncation metadata (`truncated`, `lines_fetched`, `lines_stored`) recorded per service
- [ ] Railway failure recorded in `sections_missing` per service — does not raise
- [ ] `redactions_applied` count written to Evidence Pack stats
- [ ] `LogCollector` registered with `EvidenceCollector`
- [ ] All tests pass, no regressions

---

## Related Tickets

- TASK-119: Railway client (must be complete first)
- TASK-116: Framework (must be complete first)
- TASK-123: Monitor wiring (depends on all collectors)

---

## Completion Summary

- **Branch:** `task/bugops-122-railway-log-collector-redaction`
- **Commits:** 
  - 8b5c1f9 (implementation + tests)
  - bb45faa (defensive checks for edge cases)
- **Changes made:**
  - Created `bugops/evidence/redaction.py` — LogRedactor with 6 patterns
  - Created `bugops/evidence/collectors/logs.py` — LogCollector with Railway integration
  - Created `tests/bugops/test_log_redactor.py` — 24 comprehensive tests
  - Created `tests/bugops/test_log_collector.py` — 16 comprehensive tests (including None-safety)
  - Modified `bugops/evidence/collector.py` — auto-register LogCollector
  - Modified `tests/bugops/test_evidence_collector.py` — update for 6th collector
- **Redaction patterns added beyond baseline:** None; all 6 patterns match ticket specification exactly
- **Deviations from plan:** 
  - Added defensive `first_seen_at=None` check (same pattern as TASK-120)
  - Added test case for None-safety verification
  - Documented `redactions_applied` field ownership for future cumulative redaction support

**Test Results:** 62 total tests passing (24 redactor + 16 collector + 22 framework tests; zero regressions)
