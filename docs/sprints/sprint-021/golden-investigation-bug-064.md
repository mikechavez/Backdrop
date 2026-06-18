# Golden Investigation: BUG-064
## Memory Leak + Retry Storm — Briefing Generation Failure

**Status:** Reference artifact. Written by hand. Used as the target output for Sprint 021 InvestigationProvider.

**Rule:** Sprint 021 is successful when the InvestigationProvider can produce an Investigation of comparable quality from the Evidence Pack alone — without access to this document or the BUG-064 ticket.

---

## 1. Incident Summary

Briefing generation stopped producing output beginning at approximately 00:00 UTC on 2026-04-13. The failure persisted for at least 70 minutes with no successful briefing generated. The condition was not self-resolving.

The failure manifested as a continuous retry loop: briefing tasks attempted execution every 5 minutes, failed consistently, and re-queued without limit. By the time evidence was collected, four retry cycles had been observed within the evidence window.

Failure type: `config_error`

---

## 2. Impact

**Directly broken:**
- Briefing generation — no evening briefing produced
- `generate_briefing` pipeline heartbeat — reporting unhealthy

**Downstream affected:**
- Briefing freshness — BriefingFreshness detector firing

**Not affected:**
- Article ingestion — healthy
- Signal generation — healthy
- Narrative refresh — healthy
- All upstream pipeline stages functioning normally

The failure is isolated to the briefing generation stage. The rest of the pipeline is intact.

---

## 3. What Is Broken

| Observation | Evidence Reference |
|---|---|
| No briefing produced since 23:59:42 UTC (prior evening) | E-001 |
| 4 failed briefing attempts in 70-minute window | E-002 |
| Briefing tasks retrying every 300 seconds | E-005 |
| `generate_briefing` pipeline heartbeat unhealthy | E-011 |
| Soft limit reached at 00:00:10 UTC: $0.2954 >= $0.25 | E-003 |
| Briefing generation blocked as non-critical operation | E-004 |
| `Event loop is closed` errors beginning at 00:05:20 UTC | E-006 |
| Motor client recreating on each retry | E-007 |

---

## 4. What Is Not Broken

| Healthy Signal | What It Eliminates |
|---|---|
| MongoDB reachable, 12ms latency [E-010] | Database unavailability as primary cause |
| Redis reachable, 4ms latency [E-010] | Cache/queue infrastructure as primary cause |
| FastAPI healthy [E-010] | API layer as primary cause |
| Celery worker deployment active, 0 restarts in 24h [E-008] | Worker crash or deployment failure as primary cause |
| Celery scheduler deployment active, 0 restarts in 24h [E-008] | Scheduler failure as primary cause |
| No deployments in 24 hours preceding incident [E-009] | Deployment regression as primary cause |
| Article ingestion pipeline healthy [E-011] | Upstream pipeline failure as primary cause |
| RSS fetch heartbeat healthy [E-011] | Feed ingestion as primary cause |

Database failure, worker crash, scheduler failure, deployment regression, and upstream pipeline failure are all unlikely primary causes based on healthy signals.

---

## 5. Recent Changes

No deployments detected within 24 hours preceding the incident across FastAPI, Celery worker, or Celery scheduler services. [E-009]

No configuration changes detected in deploy context.

The incident began at exactly 00:00:10 UTC — the start of a new UTC day. This timing is significant. Daily budget reset logic or budget threshold enforcement may have a daily boundary trigger.

---

## 6. Evidence Timeline

```
23:59:42 UTC  Last successful briefing (prior evening)

00:00:10 UTC  Soft limit reached: $0.2954 >= $0.25         [E-003]
00:00:10 UTC  briefing_generate blocked as non-critical     [E-004]
00:00:10 UTC  Daily spend limit reached (soft_limit)        [E-003]
00:00:10 UTC  Task retry: Retry in 300s                     [E-005]

00:05:20 UTC  Task generate_evening_briefing retry          [E-005]
00:05:20 UTC  Event loop is closed                          [E-006]
00:05:20 UTC  Motor client recreating for new loop          [E-007]

00:10:30 UTC  Task generate_evening_briefing retry          [E-005]

[Pattern continues every 300 seconds]

00:15:00 UTC  Evidence collected (4 retries observed)
```

Key observation: The failure began at exactly 00:00:10 UTC, immediately after daily budget reset. No gradual degradation. Instant failure at day boundary.

---

## 7. Recommended Investigation Order

**Step 1 — Verify budget configuration** *(~1 minute)*

Check `LLM_DAILY_SOFT_LIMIT` in Railway environment variables. Compare against actual daily LLM spend from the previous day. If `LLM_DAILY_SOFT_LIMIT` is lower than typical daily spend, the budget is structurally too low and will trigger every day at midnight UTC.

Expected finding: `LLM_DAILY_SOFT_LIMIT=0.25` with actual daily spend of $0.29–0.70.

**Step 2 — Verify critical operations classification** *(~2 minutes)*

In `cost_tracker.py`, check `CRITICAL_OPERATIONS` set against the operation name passed by briefing tasks. The log shows the operation blocked is `"briefing_generate"` [E-004]. Confirm whether `"briefing_generate"` appears in `CRITICAL_OPERATIONS`.

Expected finding: `CRITICAL_OPERATIONS` contains `"briefing_generation"` but not `"briefing_generate"` — a name mismatch causing briefing generation to be treated as non-critical.

**Step 3 — Verify retry behavior** *(~2 minutes)*

In `briefing_tasks.py`, check `max_retries` on briefing task definitions and confirm whether a failed budget check triggers indefinite retries. The log shows retries at 300-second intervals continuing beyond 00:15 UTC with no sign of stopping [E-005].

Expected finding: `max_retries` is set but Celery re-queues on budget failure in a way that circumvents the limit, or the limit is too high for a budget-blocked scenario.

**Step 4 — Review event loop lifecycle in briefing tasks** *(~5 minutes)*

The `Event loop is closed` errors [E-006] and Motor client recreation [E-007] on every retry suggest event loops are not being closed between task executions. Review `_run_async()` in `briefing_tasks.py` for loop creation and cleanup in the finally block.

Expected finding: `loop.close()` missing or not executing, causing loops to accumulate across retries.

**Step 5 — Correlate retry count with memory consumption** *(~3 minutes)*

If Railway metrics are available, plot worker memory over the incident window. Each retry that leaves an unclosed event loop adds approximately 25MB. Memory growth rate × 300-second interval should correlate with observed loop accumulation.

Expected finding: Linear memory growth starting at 00:00 UTC, approximately 25MB per retry cycle.

---

## 8. Hypotheses

### Hypothesis 1 — Budget threshold too low + operation name mismatch

**Summary:** The daily soft limit ($0.25) is below actual daily LLM spend. At the UTC day boundary, the budget resets and immediately reaches the soft limit. Because `briefing_generate` is not in `CRITICAL_OPERATIONS` (only `briefing_generation` is), briefing generation is classified as non-critical and blocked rather than allowed through.

**Supporting evidence:**
- Soft limit reached at 00:00:10 UTC — immediately at day boundary [E-003]
- Operation blocked is `briefing_generate` specifically [E-004]
- Log states "blocking non-critical operation" [E-004]
- Daily spend at failure: $0.2954, threshold: $0.25 [E-003]
- No deployments that would have changed config [E-009]

**Contradicting evidence:**
- None identified. All available evidence is consistent with this hypothesis.

**Confidence:** High

**If true, fix area:** `cost_tracker.py` (operation name), Railway environment variables (soft limit value)

---

### Hypothesis 2 — Retry loop without exit condition creates compounding failure

**Summary:** Once the budget check blocks briefing generation, the task retries indefinitely. Each retry creates a new asyncio event loop that is not closed, causing memory accumulation. The retry storm is a consequence of Hypothesis 1, not an independent root cause — but it amplifies the impact significantly.

**Supporting evidence:**
- Retries observed at exact 300-second intervals with no stopping [E-005]
- `Event loop is closed` errors on every retry [E-006]
- Motor client recreation on every retry indicates new loop per attempt [E-007]
- Pattern began immediately after budget block at 00:00:10 UTC [E-003, E-005]

**Contradicting evidence:**
- Max retries may be configured but circumvented by re-queue behavior. Cannot confirm without code inspection.

**Confidence:** High

**If true, fix area:** `briefing_tasks.py` (`_run_async()` loop cleanup, `max_retries` configuration)

---

### Hypothesis 3 — Unrelated worker instability causing briefing failure

**Summary:** Worker instability independent of budget logic causes briefing tasks to fail and retry.

**Supporting evidence:**
- `Event loop is closed` errors present [E-006]

**Contradicting evidence:**
- Worker deployment active with 0 restarts in 24h [E-008]
- Failure begins at exact UTC day boundary, not randomly [E-003]
- Log explicitly states budget block as failure reason [E-004]
- All other pipeline stages healthy [E-011]

**Confidence:** Low — the timing and explicit budget block log eliminate this as primary cause.

---

## 9. Potential Fix Areas

**High confidence — address first:**

```
Likely files to modify:
  - src/crypto_news_aggregator/services/cost_tracker.py
    → CRITICAL_OPERATIONS set: add "briefing_generate" variant

  - Railway environment variables
    → LLM_DAILY_SOFT_LIMIT: increase above actual daily spend

  - src/crypto_news_aggregator/tasks/briefing_tasks.py
    → _run_async(): verify loop.close() in finally block
    → max_retries: add budget-blocked retry limit or exit condition
```

**Likely files to inspect (do not modify without verification):**

```
  - src/crypto_news_aggregator/tasks/briefing_tasks.py
    → Task definitions: max_retries, default_retry_delay
    → _run_async(): full event loop lifecycle

  - src/crypto_news_aggregator/services/cost_tracker.py
    → check_llm_budget(): return behavior when soft limit active
    → is_critical_operation(): full CRITICAL_OPERATIONS definition
```

**Do not modify:**
```
  - Narrative generation pipeline
  - Article ingestion pipeline
  - Signal generation pipeline
  - Briefing schedule configuration
```

**Unknowns requiring code inspection:**
- Exact Celery re-queue behavior when budget check returns False — whether max_retries is respected or circumvented
- Whether `loop.close()` exists but fails silently, or is absent entirely
- Actual daily LLM spend over prior 7 days (not available in Evidence Pack)

---

## 10. Unknowns and Missing Evidence

| Gap | Impact | Source Needed |
|---|---|---|
| Actual daily LLM spend history | Cannot confirm soft limit is structurally too low vs. one-time spike | LLM gateway spend logs or `llm_traces` collection |
| `CRITICAL_OPERATIONS` exact definition | Cannot confirm name mismatch without code inspection | `cost_tracker.py` source |
| `_run_async()` finally block contents | Cannot confirm loop leak without code inspection | `briefing_tasks.py` source |
| Worker memory consumption over incident window | Cannot confirm memory growth rate | Railway metrics |
| Retry count at time of discovery | Log window shows 4 retries; actual total unknown | Full Railway log history |
| Configuration Evidence: `LLM_DAILY_SOFT_LIMIT` value | Not collected in Evidence Pack | Config collector (not yet implemented) |

**Note on Configuration Evidence gap:** The most direct confirmation of Hypothesis 1 would be reading `LLM_DAILY_SOFT_LIMIT` from the Railway environment. This value was not available in the Evidence Pack because a Configuration Evidence collector does not yet exist. Adding this collector would make Hypothesis 1 confirmable without code inspection.

---

## Quality Check

**Automatic failure modes — verified:**

- [ ] Unsupported claim: No hypothesis asserted without evidence reference ✓
- [ ] Missed obvious evidence: Budget block log [E-004] cited in Hypothesis 1 ✓
- [ ] No actionable next step: 5-step investigation order provided with time estimates ✓
- [ ] Wrong subsystem: Worker, scheduler, DB, and upstream pipeline all eliminated via healthy signals ✓

**15-minute benchmark:**

An engineer unfamiliar with Backdrop who reads this Investigation should be able to:
- Open `cost_tracker.py` and locate `CRITICAL_OPERATIONS` within 2 minutes (Step 2)
- Confirm the name mismatch `briefing_generate` vs `briefing_generation` within 1 minute
- Identify the fix within 5 minutes total

The likely fix area is confirmed before opening Railway logs or inspecting memory metrics.

---

## Notes for InvestigationProvider Prompt Design

These observations are for prompt engineering only. They are not part of the Investigation artifact itself.

**What made this Investigation possible from the Evidence Pack:**

The most diagnostic evidence was not logs — it was the combination of:
1. Cost control metrics (soft limit value, blocked operation name)
2. Exact incident timestamp (00:00:10 UTC = day boundary)
3. Healthy signals eliminating all other subsystems

Logs confirmed the retry pattern but were not required to form the primary hypothesis.

**What the Evidence Pack could not provide:**

Configuration Evidence — specifically `LLM_DAILY_SOFT_LIMIT` from Railway environment — would have made Hypothesis 1 confirmable rather than probable. This gap is called out explicitly in Section 10 and validates adding a Configuration Evidence collector to Sprint 021.

**What the InvestigationProvider must not do:**

- Assert the operation name mismatch (`briefing_generate` vs `briefing_generation`) as confirmed — the Evidence Pack contains the blocked operation name but not the `CRITICAL_OPERATIONS` definition. This is correctly flagged as an unknown requiring code inspection.
- State memory consumption figures (2.5GB) — these are not in the Evidence Pack and must not be invented.
- Name specific line numbers or exact code — file guidance is probabilistic, not authoritative.
