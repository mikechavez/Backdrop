---
ticket_id: TASK-032
title: Clean Up Stale Anthropic Model Env Vars on Railway
priority: low
severity: low
status: OPEN
date_created: 2026-04-02
branch: n/a (Railway config change only)
effort_estimate: 10 min
---

# TASK-032: Clean Up Stale Anthropic Model Env Vars on Railway

## Problem Statement

The Railway crypto-news-aggregator service has two env vars with outdated model strings:

| Env Var | Current Value (Railway) | Value in config.py |
|---------|------------------------|-------------------|
| `ANTHROPIC_ENTITY_MODEL` | `claude-3-5-haiku-20241022` | `claude-haiku-4-5-20251001` |
| `ANTHROPIC_ENTITY_FALLBACK_MODEL` | `claude-3-5-sonnet-20241022` | Deprecated — removed by BUG-039 |

Additionally, from `config.py`:
```python
# DEPRECATED by BUG-039: Entity extraction no longer falls back to Sonnet.
# This config was removed from extract_entities_batch() to prevent silent 5x cost escalation.
# ANTHROPIC_ENTITY_FALLBACK_MODEL: str = "claude-sonnet-4-5-20250929"
```

The fallback model env var is completely unused (the config field is commented out and `pydantic_settings` has `extra = "ignore"`). The entity model env var overrides the default with an older model string — this may still work if Anthropic keeps old model IDs active, but it's inconsistent with the rest of the codebase.

---

## Task

This is a Railway config change only — no code changes required.

### Step 1: Remove deprecated env var

In Railway → crypto-news-aggregator → Variables:
- **Delete** `ANTHROPIC_ENTITY_FALLBACK_MODEL` — this config field no longer exists in code (deprecated by BUG-039)

### Step 2: Update entity model to current string

In Railway → crypto-news-aggregator → Variables:
- **Update** `ANTHROPIC_ENTITY_MODEL` from `claude-3-5-haiku-20241022` to `claude-haiku-4-5-20251001`

This aligns the env var with the default in `config.py` and the model string used in tests and health checks.

### Step 3: Verify

After the service redeploys:
- Check health endpoint — LLM check should use `claude-haiku-4-5-20251001` (it already does, since `ANTHROPIC_DEFAULT_MODEL` is correct)
- Trigger an entity extraction (once LLM credits are added) and confirm it uses the correct model in logs

---

## Verification

- [ ] `ANTHROPIC_ENTITY_FALLBACK_MODEL` removed from Railway env vars
- [ ] `ANTHROPIC_ENTITY_MODEL` set to `claude-haiku-4-5-20251001`
- [ ] Service redeploys without errors
- [ ] Entity extraction uses correct model (verify in logs after credits added)

---

## Acceptance Criteria

- [ ] No stale or deprecated model env vars on Railway
- [ ] Entity model consistent between Railway, config.py, and test files

---

## Impact

Low — the old model strings may still work, but having inconsistent model references across Railway, config, and tests creates confusion and potential pricing miscalculations in the cost tracker.

---

## Related Tickets

- BUG-039: Entity extraction fallback model deprecated
- TASK-025: Cost controls (cost tracker uses model strings for pricing)
- TASK-031: Switch to Railway Redis (do both Railway config tasks in same session)