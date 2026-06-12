---
ticket_id: TASK-103
title: Implement DependencyGraph v1
priority: high
severity: medium
status: OPEN
date_created: 2025-01-01
branch: task/bugops-103-dependency-graph
effort_estimate: small
---

# TASK-103: Implement DependencyGraph v1

## Problem Statement

Cascade suppression requires a traversable map of operational outcome
dependencies. Without it, a scheduler failure produces four separate BugCases
(articles, signals, narratives, briefings) instead of one — each triggering its
own Slack notification. The DependencyGraph is the primitive that makes
upstream-wins suppression possible.

---

## Context

The DependencyGraph is a permanent architecture primitive. It is hand-maintained
and version-controlled. It is not inferred dynamically and is not a full
architecture map — it represents only the operational outcome dependencies
relevant to freshness detection.

Version 1 graph:
```
scheduler → ingestion → articles → signals → narratives → briefings
```

`worker` and `database` exist in `BugOpsSubsystem` (TASK-100A) but are NOT nodes
in this graph in Sprint 020. Both methods must return `[]` for these values.

The graph supports two traversal directions:
- **Upstream traversal** (cascade suppression): walk from a node toward the root,
  return all nodes upstream of it
- **Downstream traversal** (blast radius): walk from a node toward the leaves,
  return all nodes downstream of it

This ticket has no dependencies on Phase 1 tickets and can be implemented in
parallel with TASK-100 through TASK-102.

Use `BugOpsSubsystem` string values (e.g. `"articles"`) in the internal graph
representation. Import `BugOpsSubsystem` from `..models`. Both methods accept
and return plain strings — callers use `BugOpsSubsystem.value` or string literals.

---

## Task

1. Create `dependency_graph.py` in the bugops directory
2. Implement `DependencyGraph` class with `get_upstream_nodes()` and
   `get_downstream_nodes()`
3. Write comprehensive unit tests for graph traversal

---

## Files to Create

```text
src/crypto_news_aggregator/bugops/dependency_graph.py
src/tests/bugops/test_dependency_graph.py
```

---

## Files to Modify

```text
(none)
```

---

## Do Not Modify

```text
src/crypto_news_aggregator/bugops/models.py
src/crypto_news_aggregator/bugops/store.py
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/bugops/signal_sources/llm_traces.py
```

---

## Implementation Requirements

### `DependencyGraph` class

- [ ] Class attribute `VERSION = "1.0"`
- [ ] Hardcoded v1 graph as an ordered list representing the linear chain:
  `["scheduler", "ingestion", "articles", "signals", "narratives", "briefings"]`
- [ ] `get_upstream_nodes(subsystem: str) -> list[str]` — returns all nodes
  upstream of the given subsystem, ordered from nearest to root.
  Example: `get_upstream_nodes("signals")` → `["articles", "ingestion", "scheduler"]`
- [ ] `get_downstream_nodes(subsystem: str) -> list[str]` — returns all nodes
  downstream of the given subsystem, ordered from nearest to leaves.
  Example: `get_downstream_nodes("articles")` → `["signals", "narratives", "briefings"]`
- [ ] Both methods return `[]` if the given subsystem is not in the graph
  (do not raise) — this handles `"worker"`, `"database"`, and unknown strings
- [ ] Root node (`"scheduler"`) has no upstream: `get_upstream_nodes("scheduler")`
  returns `[]`
- [ ] Leaf node (`"briefings"`) has no downstream: `get_downstream_nodes("briefings")`
  returns `[]`
- [ ] Instantiatable with no arguments: `graph = DependencyGraph()`

### Test cases in `test_dependency_graph.py`

- [ ] `get_upstream_nodes("signals")` → `["articles", "ingestion", "scheduler"]`
- [ ] `get_upstream_nodes("briefings")` → `["narratives", "signals", "articles", "ingestion", "scheduler"]`
- [ ] `get_upstream_nodes("scheduler")` → `[]`
- [ ] `get_upstream_nodes("articles")` → `["ingestion", "scheduler"]`
- [ ] `get_downstream_nodes("articles")` → `["signals", "narratives", "briefings"]`
- [ ] `get_downstream_nodes("scheduler")` → `["ingestion", "articles", "signals", "narratives", "briefings"]`
- [ ] `get_downstream_nodes("briefings")` → `[]`
- [ ] `get_upstream_nodes("unknown_subsystem")` → `[]` (no raise)
- [ ] `get_downstream_nodes("unknown_subsystem")` → `[]` (no raise)
- [ ] `get_upstream_nodes("worker")` → `[]` (reserved, not in graph)
- [ ] `get_downstream_nodes("database")` → `[]` (reserved, not in graph)
- [ ] `VERSION == "1.0"`

### Configuration

No new environment variables required for this ticket.

### Commands to Run

```bash
pytest src/tests/bugops/test_dependency_graph.py -v
```

---

## Verification

### Automated Verification

- [ ] All 12 test cases listed above pass

### Manual Verification

- [ ] Instantiate `DependencyGraph()` in a Python REPL and manually verify
  upstream and downstream traversal for each node in the graph

---

## Acceptance Criteria

- [ ] `DependencyGraph` is instantiatable with no arguments
- [ ] `VERSION = "1.0"` class attribute is present
- [ ] `get_upstream_nodes()` returns correct ordered list for every node
- [ ] `get_downstream_nodes()` returns correct ordered list for every node
- [ ] Both methods return `[]` for `"worker"`, `"database"`, and unknown strings
- [ ] All 12 test cases pass

---

## Impact

Unblocks TASK-108 (cascade suppression wiring). No behavior change to any
existing system.

---

## Related Tickets

- Can run in parallel with TASK-100 through TASK-102
- Depends on: TASK-100A (for `BugOpsSubsystem` import — can stub with strings
  if TASK-100A not yet merged)
- Blocks: TASK-108

---

## Completion Summary

- Branch:
- Commit:
- Changes made:
- Tests run:
- Manual verification:
- Deviations from plan:
