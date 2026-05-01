---
id: TASK-087
type: task
status: open
priority: P2
complexity: medium
created: 2026-05-01
updated: 2026-05-01
branch: refactor/gateway-owned-reliability-controls
effort_estimate: 4-6 hours
---

# TASK-087: Refactor Gateway-Owned Provider-Scoped Reliability Controls

## Problem Statement

Reliability controls are currently enforced in the wrong layer.

Circuit breaker and rate limiter checks are implemented only in `anthropic.py`, and only in three async tracked methods:

- `score_relevance_tracked()`
- `analyze_sentiment_tracked()`
- `extract_themes_tracked()`

They are **not enforced inside `LLMGateway`**.

This creates four problems:

1. **Provider switching is unsafe.** DeepSeek and Anthropic share operation-level reliability state instead of provider-specific state.
2. **Gateway callers are inconsistent.** Some async tracked methods have reliability checks, but gateway sync calls do not.
3. **Reliability is duplicated and hard to reason about.** Callers own checks that should belong to the centralized gateway.
4. **Provider failures are not isolated.** If DeepSeek fails, the circuit breaker should open only for `deepseek:<operation>`, not for Anthropic or the operation globally.

TASK-085 added DeepSeek support through `LLMGateway`. TASK-086 deployed DeepSeek-backed `article_enrichment_batch` to production. TASK-087 makes the gateway the owner of reliability enforcement so future model/provider switches are safer.

---

## Current State

### Reliability location

Reliability checks currently live in `anthropic.py`, not in `gateway.py`.

Tracked async methods use this pattern:

```python
allowed, message = await circuit_breaker.check_circuit("sentiment_analysis")
allowed, message = await rate_limiter.check_limit("sentiment_analysis")
```

### Current key format

Rate limiter keys are operation-only:

```text
rate_limit:{operation}:{YYYY-MM-DD}
```

Example:

```text
rate_limit:sentiment_analysis:2026-05-01
```

Circuit breaker keys are also operation-only:

```text
circuit_breaker:state:{operation}
circuit_breaker:failures:{operation}
circuit_breaker:last_failure:{operation}
```

Example:

```text
circuit_breaker:state:sentiment_analysis
```

### Missing coverage

- `LLMGateway.call()` does not enforce circuit breaker or rate limiter checks.
- `LLMGateway.call_sync()` does not enforce circuit breaker or rate limiter checks.
- Sync paths currently call the gateway without reliability enforcement.
- Retries happen in Celery task handlers, not in gateway.

---

## Goal

Move circuit breaker and rate limiter ownership into `LLMGateway` and make reliability keys provider-scoped.

Provider-scoped key format:

```text
{provider}:{operation}
```

Examples:

```text
deepseek:article_enrichment_batch
anthropic:article_enrichment_batch
deepseek:sentiment_analysis
anthropic:sentiment_analysis
```

The underlying Redis keys should become:

```text
rate_limit:deepseek:article_enrichment_batch:2026-05-01

circuit_breaker:state:deepseek:article_enrichment_batch
circuit_breaker:failures:deepseek:article_enrichment_batch
circuit_breaker:last_failure:deepseek:article_enrichment_batch
```

This ensures:

- DeepSeek failures do not open Anthropic’s circuit.
- Anthropic failures do not open DeepSeek’s circuit.
- Rate limits are tracked per provider and operation.
- Sync and async gateway calls share the same reliability model.

---

## Non-Goals

Do **not**:

- Add retries to `LLMGateway`.
- Change Celery retry behavior.
- Change model routing decisions.
- Change prompts.
- Change output parsing.
- Change cost tracking behavior.
- Change trace schema.
- Add a dashboard.
- Add a new provider.
- Modify MongoDB data.
- Delete or mutate production data manually.
- Remove caller-level reliability checks until gateway enforcement is tested.

Retries stay where they are today: Celery task handlers.

---

## Safety Principle

This refactor must be phased.

Do **not** remove old caller-level checks in the same step that first adds gateway-level checks unless tests prove the new behavior is equivalent or safer.

Preferred rollout:

1. Add gateway-owned reliability checks.
2. Add tests proving provider-scoped enforcement.
3. Keep or remove old caller checks only after the new gateway behavior is verified.
4. Preserve fast rollback by keeping model routing centralized.

---

## Files Likely to Modify

Expected files:

```text
src/crypto_news_aggregator/llm/gateway.py
src/crypto_news_aggregator/llm/anthropic.py
```

Possible test files to add or modify:

```text
tests/llm/test_gateway_reliability.py
tests/llm/test_gateway.py
tests/llm/test_anthropic.py
```

Use actual existing test locations if different.

Do not modify unrelated files.

---

## Implementation Plan

## Phase A — Add Provider-Scoped Reliability to LLMGateway

### 1. Resolve provider before reliability checks

Inside `LLMGateway.call()` and `LLMGateway.call_sync()`, determine the final model/provider before making external API calls.

Use existing provider-aware parsing logic, likely:

```python
provider, parsed_model = self._parse_model_string(actual_model_or_model_ref)
```

The operation should already be available from the gateway call:

```python
operation = "article_enrichment_batch"
```

Build the provider-scoped reliability key:

```python
reliability_key = f"{provider}:{operation}"
```

Examples:

```python
deepseek:article_enrichment_batch
anthropic:article_enrichment_batch
```

### 2. Add async reliability checks to `LLMGateway.call()`

Before any external LLM API request, enforce:

```python
allowed, message = await circuit_breaker.check_circuit(reliability_key)
if not allowed:
    raise RuntimeError(f"Circuit breaker open for {reliability_key}: {message}")

allowed, message = await rate_limiter.check_limit(reliability_key)
if not allowed:
    raise RuntimeError(f"Rate limit exceeded for {reliability_key}: {message}")
```

Use the project’s existing exception style if there is a custom exception already used for circuit breaker or rate limit failures.

Important:

- Reliability checks must happen after model/provider resolution.
- Reliability checks must happen before external provider request.
- Cache-hit behavior should avoid unnecessary external-provider checks if the current gateway can determine cache hit before provider call. If cache lookup requires provider/model identity, resolve model first but do not consume rate limit on cache hits unless that is already the existing intended behavior.

### 3. Record provider-scoped success/failure

After successful provider response:

```python
await circuit_breaker.record_success(reliability_key)
```

After provider/request failure:

```python
await circuit_breaker.record_failure(reliability_key)
```

Preserve existing behavior if the current circuit breaker API uses different method names.

Do not record circuit breaker failures for:

- cache hits
- local validation errors before provider call
- parse errors after a successful provider response, unless current behavior already treats parse failures as provider/system failures

Use the existing project convention if present.

### 4. Add sync reliability handling to `LLMGateway.call_sync()`

`call_sync()` also needs reliability enforcement.

Preferred implementation:

- If current circuit breaker/rate limiter APIs are async-only, add a small sync wrapper/helper in gateway that runs the async checks safely.
- If the project already has sync wrappers, use them.
- If sync enforcement cannot be implemented safely in this task, document it explicitly and add tests proving async enforcement. Do not pretend sync is covered if it is not.

The desired behavior is:

```python
self._check_reliability_sync(reliability_key)
```

before provider request, and:

```python
self._record_reliability_success_sync(reliability_key)
self._record_reliability_failure_sync(reliability_key)
```

around provider execution.

Do not add retries.

### 5. Add helper methods in `gateway.py`

Add small private helpers to reduce duplication:

```python
def _build_reliability_key(self, provider: str, operation: str) -> str:
    return f"{provider}:{operation}"
```

Async helpers:

```python
async def _check_reliability(self, reliability_key: str) -> None:
    ...

async def _record_reliability_success(self, reliability_key: str) -> None:
    ...

async def _record_reliability_failure(self, reliability_key: str) -> None:
    ...
```

Sync helpers if needed:

```python
def _check_reliability_sync(self, reliability_key: str) -> None:
    ...

def _record_reliability_success_sync(self, reliability_key: str) -> None:
    ...

def _record_reliability_failure_sync(self, reliability_key: str) -> None:
    ...
```

Keep helper behavior narrow and testable.

---

## Phase B — Tests Before Removing Caller-Level Checks

Add or update tests proving:

### Provider-scoped key generation

- `deepseek:article_enrichment_batch` is used for DeepSeek route.
- `anthropic:article_enrichment_batch` is used for Anthropic route.
- Provider-prefixed model refs are parsed correctly.

### Async gateway enforcement

- `LLMGateway.call()` checks circuit breaker before provider request.
- `LLMGateway.call()` checks rate limiter before provider request.
- If circuit breaker denies, provider request is not made.
- If rate limiter denies, provider request is not made.
- On provider success, success is recorded for the provider-scoped key.
- On provider failure, failure is recorded for the provider-scoped key.

### Sync gateway enforcement

- `LLMGateway.call_sync()` enforces the same provider-scoped reliability checks, if technically feasible.
- If sync enforcement is deferred, test coverage and ticket notes must explicitly say sync remains uncovered and why.

### Provider isolation

- DeepSeek failure records against `deepseek:article_enrichment_batch`.
- Anthropic success records against `anthropic:article_enrichment_batch`.
- DeepSeek failure does not open or increment Anthropic circuit state.

### Cache behavior

- Cached responses do not call external provider.
- Cached responses do not incorrectly count as provider failures.
- Cached responses do not consume provider rate limit unless existing system behavior intentionally does this.

---

## Phase C — Remove Duplicate Caller-Level Checks Only After Tests Pass

After gateway enforcement is verified, remove duplicate reliability checks from `anthropic.py` tracked methods where safe.

Likely affected methods:

- `score_relevance_tracked()`
- `analyze_sentiment_tracked()`
- `extract_themes_tracked()`

Remove caller-level circuit breaker and rate limiter checks only if:

- those methods call `LLMGateway`
- gateway enforcement is active for those paths
- tests pass
- no behavior regression is introduced

Do not remove unrelated tracking, logging, cost, or trace behavior.

Do not remove Celery retries.

---

## Phase D — Verification in Production-Like Environment

After implementation, run smoke checks for both providers through gateway paths.

Required smoke coverage:

1. Anthropic route still works.
2. DeepSeek route still works.
3. DeepSeek route uses `deepseek:<operation>` reliability key.
4. Anthropic route uses `anthropic:<operation>` reliability key.
5. Existing traces still write.
6. Cost tracking still works.
7. No unexpected rate limit/circuit breaker blocks.

---

## Acceptance Criteria

- [ ] `LLMGateway.call()` enforces circuit breaker checks before external LLM calls.
- [ ] `LLMGateway.call()` enforces rate limiter checks before external LLM calls.
- [ ] Reliability keys are provider-scoped: `{provider}:{operation}`.
- [ ] DeepSeek and Anthropic reliability state are isolated.
- [ ] Provider-scoped circuit breaker keys work.
- [ ] Provider-scoped rate limiter keys work.
- [ ] Cache hits do not incorrectly count as provider failures.
- [ ] Provider success records circuit breaker success using provider-scoped key.
- [ ] Provider failure records circuit breaker failure using provider-scoped key.
- [ ] `LLMGateway.call_sync()` has equivalent reliability coverage, or the limitation is explicitly documented with follow-up work.
- [ ] Duplicate caller-level checks in `anthropic.py` are removed only after gateway tests pass.
- [ ] No retries are added to gateway.
- [ ] Celery retry behavior remains unchanged.
- [ ] Existing model routing behavior remains unchanged.
- [ ] Existing cost tracking behavior remains unchanged.
- [ ] Existing trace writing behavior remains unchanged.
- [ ] Tests cover provider isolation.
- [ ] Tests cover circuit breaker denial.
- [ ] Tests cover rate limiter denial.
- [ ] Tests cover successful provider call.
- [ ] Tests cover failed provider call.
- [ ] Tests cover cache-hit behavior if cache is part of the gateway path.

---

## Verification Commands

Run static checks:

```bash
python -m compileall src/crypto_news_aggregator/llm/gateway.py
python -m compileall src/crypto_news_aggregator/llm/anthropic.py
```

Run targeted tests:

```bash
pytest tests/llm/test_gateway_reliability.py -q
```

If test file names differ, run the relevant gateway/LLM tests:

```bash
pytest tests/llm -q
```

Run smoke tests if available:

```bash
poetry run python scripts/task_086_phase1_smoke_test.py
```

---

## Manual Redis Verification

If Redis inspection is available, verify provider-scoped keys appear after calls.

Expected examples:

```text
rate_limit:deepseek:article_enrichment_batch:2026-05-01
rate_limit:anthropic:article_enrichment_batch:2026-05-01

circuit_breaker:state:deepseek:article_enrichment_batch
circuit_breaker:state:anthropic:article_enrichment_batch
```

There should not be new gateway-generated keys that collapse both providers into:

```text
rate_limit:article_enrichment_batch:2026-05-01
circuit_breaker:state:article_enrichment_batch
```

Old operation-only keys may still exist temporarily from pre-refactor behavior.

---

## Rollback Plan

If TASK-087 causes unexpected production issues:

1. Revert the TASK-087 commit.
2. Redeploy previous version.
3. Confirm `article_enrichment_batch` still routes through current TASK-086 model route.
4. Run one smoke test.
5. Confirm `llm_traces` still records calls.
6. Document the failure mode.

Do not change the model provider route unless the issue is provider-specific.

---

## Notes for Agent

Be careful with ordering.

The gateway must know the selected provider before it can build the reliability key. Do not use the raw model ref blindly if model refs can be provider-prefixed.

Do not add direct DeepSeek calls.

Do not bypass `LLMGateway`.

Do not change external behavior except reliability enforcement location and provider-scoped isolation.

Do not silently leave sync paths uncovered. Either implement sync reliability or explicitly document why it is deferred.

---

## Completion Summary

- Actual complexity:
- Key decisions made:
- Deviations from plan:
- Follow-up required:
