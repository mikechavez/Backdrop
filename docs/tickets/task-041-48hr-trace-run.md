---
id: TASK-041
type: feature
status: backlog
priority: critical
complexity: low
created: 2026-04-08
updated: 2026-04-08
---

# Attribution Burn-in — 48hr Traced Run + Findings Doc

## Problem/Opportunity

We suspect briefing_agent is the cost driver but have been guessing based on code review. With the gateway, tracing, and all call sites wired, we can now measure exactly what costs what. This ticket is the payoff: run the system for 48 hours with full tracing, then write a findings doc that drives optimization decisions.

## Proposed Solution

Add $5 Anthropic credits, let the system run for 48 hours with all tracing active, then query `llm_traces` and `api_costs` to produce a cost attribution report. The report drives Sprint 14 decisions (kill refine loop? downgrade model? throttle frequency?).

## Acceptance Criteria

- [ ] $5 Anthropic credits added to the account before starting
- [ ] System runs for 48 hours with no manual intervention
- [ ] Sentry and UptimeRobot confirm no errors during burn-in
- [ ] Findings document written with data from `llm_traces` collection
- [ ] Findings doc includes: cost per operation, cost per pipeline run, call volume by operation, model breakdown, token counts, avg latency
- [ ] Findings doc includes a decision section: what to fix and why, based on the data
- [ ] If daily spend exceeds $0.33 target, document explains why and what would fix it
- [ ] If daily spend is within target, document confirms the gateway + spend cap is sufficient

## Dependencies

- TASK-036 (gateway)
- TASK-037 (tracing schema + query helper)
- TASK-038 (briefing_agent wired)
- TASK-039 (health.py wired)
- TASK-040 (draft capture active, so we can see refine loop behavior)

## Implementation Notes

### Pre-burn-in checklist

1. Deploy all Sprint 13 changes to Railway
2. Add $5 to Anthropic credits
3. Verify `llm_traces` collection is receiving records (check one trace exists after first pipeline run)
4. Verify `briefing_drafts` collection is receiving records
5. Verify UptimeRobot health endpoint returns "healthy" or "degraded" (not "unhealthy")
6. Verify Sentry has no new unresolved errors
7. Note start time

### Analysis queries (run after 48hr)

Use `get_traces_summary(days=2)` from TASK-037's `tracing.py`, or run directly:

```python
# Cost by operation
db.llm_traces.aggregate([
    {"$match": {"timestamp": {"$gte": ISODate("...")}}},
    {"$group": {
        "_id": "$operation",
        "total_cost": {"$sum": "$cost"},
        "calls": {"$sum": 1},
        "avg_input_tokens": {"$avg": "$input_tokens"},
        "avg_output_tokens": {"$avg": "$output_tokens"},
        "avg_duration_ms": {"$avg": "$duration_ms"},
    }},
    {"$sort": {"total_cost": -1}}
])

# Cost by model
db.llm_traces.aggregate([
    {"$match": {"timestamp": {"$gte": ISODate("...")}}},
    {"$group": {
        "_id": "$model",
        "total_cost": {"$sum": "$cost"},
        "calls": {"$sum": 1},
    }},
    {"$sort": {"total_cost": -1}}
])

# Refine loop: how many iterations per briefing?
db.briefing_drafts.aggregate([
    {"$group": {
        "_id": "$briefing_id",
        "stages": {"$push": "$stage"},
        "count": {"$sum": 1},
    }},
])

# Error rate
db.llm_traces.aggregate([
    {"$match": {"timestamp": {"$gte": ISODate("...")}}},
    {"$group": {
        "_id": "$operation",
        "total": {"$sum": 1},
        "errors": {"$sum": {"$cond": [{"$ne": ["$error", None]}, 1, 0]}},
    }},
])
```

### Findings doc template

File: `docs/sprint-13-burn-in-findings.md`

```markdown
# Sprint 13 Burn-in Findings

**Period:** [start] to [end] (48 hours)
**Credits consumed:** $X.XX
**Daily average:** $X.XX/day (target: $0.33/day)

## Cost by Operation

| Operation | Calls | Cost | Avg Input Tokens | Avg Output Tokens | Avg Latency |
|-----------|-------|------|------------------|-------------------|-------------|
| briefing_generate | | | | | |
| briefing_critique | | | | | |
| briefing_refine | | | | | |
| entity_extraction | | | | | |
| narrative_extraction | | | | | |
| narrative_summary | | | | | |
| health_check | | | | | |
| sentiment_analysis | | | | | |
| theme_extraction | | | | | |
| relevance_scoring | | | | | |

## Cost by Model

| Model | Calls | Cost |
|-------|-------|------|
| claude-sonnet-4-5-20250929 | | |
| claude-haiku-4-5-20251001 | | |

## Refine Loop Behavior

- Briefings generated: X
- Average refinement iterations: X
- Briefings needing 0 iterations: X
- Briefings needing 1 iteration: X
- Briefings needing 2 iterations (max): X

## Error Rate

| Operation | Total | Errors | Rate |
|-----------|-------|--------|------|
| | | | |

## Decision

[Based on the data above, what should Sprint 14 optimize?]

Possible actions (decide by data, not guesses):
- [ ] Downgrade briefing model from Sonnet to Haiku
- [ ] Reduce/eliminate refine loop
- [ ] Throttle briefing frequency
- [ ] Adjust spend cap limits
- [ ] Other: ___
```

## Open Questions

- None

## Completion Summary
- Actual complexity:
- Key decisions made:
- Deviations from plan: