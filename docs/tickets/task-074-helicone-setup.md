---
ticket_id: TASK-074
title: Helicone Setup — Proxy + Kill Switch Configuration
priority: medium
severity: low
status: OPEN
date_created: 2026-04-27
updated: 2026-04-27
effort_estimate: 2-3 hours
---

# TASK-074: Helicone Setup — Proxy + Kill Switch Configuration

## Problem Statement

Currently, gateway.py hits api.anthropic.com directly with no trace UI for multi-step LLM interactions. For Flash evaluations (FEATURE-053), we need visibility into Anthropic calls and a way to toggle proxy behavior at runtime without code changes.

**Important Note:** Helicone proxy only traces Anthropic API calls. Gemini calls made directly via GeminiProvider will not appear in Helicone dashboards. This is acceptable for now (separate observability for Gemini is out of scope for Sprint 16).

---

## Task

### 1. Verify Helicone Capacity
- Confirm free tier supports ~210K calls/month (current burn rate)
- Confirm Helicone-Auth header requirements documented

### 2. Add Configuration (config.py)
- Add `USE_HELICONE_PROXY: bool = False` (env var, default off initially)
- Add `HELICONE_API_KEY: Optional[str] = None` (env var, will be set when enabled)

### 3. Implement Dynamic URL Selection (gateway.py)
- Add `_get_anthropic_url()` method to GatewayClient
- Returns `"https://api.helicone.ai/anthropic/v1/messages"` if `USE_HELICONE_PROXY=True`
- Returns `"https://api.anthropic.com/v1/messages"` otherwise
- Replace hardcoded _ANTHROPIC_API_URL (line 26) with call to `_get_anthropic_url()`

### 4. Update Header Construction (gateway.py)
- Modify `_build_headers()` method (~line 460-470)
- Add Helicone-Auth header when `USE_HELICONE_PROXY=True`:
  ```python
  if settings.USE_HELICONE_PROXY and settings.HELICONE_API_KEY:
      headers["Helicone-Auth"] = f"Bearer {settings.HELICONE_API_KEY}"
  ```
- Ensure no auth header leakage if proxy disabled

### 5. Testing
- [ ] Verify gateway.call() works with proxy disabled (baseline)
- [ ] Verify gateway.call() works with proxy enabled (requires valid HELICONE_API_KEY)
- [ ] Confirm Helicone dashboard receives traces when enabled
- [ ] Verify no performance degradation when proxy disabled

---

## Verification

- [ ] Config loads USE_HELICONE_PROXY and HELICONE_API_KEY correctly
- [ ] _get_anthropic_url() returns correct URL based on flag state
- [ ] Helicone-Auth header only added when enabled
- [ ] At least one successful call through proxy produces visible trace in Helicone UI
- [ ] Toggling USE_HELICONE_PROXY=False → direct API calls work without modification

---

## Acceptance Criteria

- [ ] USE_HELICONE_PROXY env var controls proxy behavior at runtime
- [ ] No code changes required to swap between proxy and direct API
- [ ] Helicone-Auth header added only when proxy enabled
- [ ] All existing gateway tests pass (with proxy disabled)
- [ ] Integration test demonstrates proxy toggling without downtime

---

## Important Limitations

**Helicone only traces Anthropic API calls.** In FEATURE-053, when Flash evaluations call Gemini via GeminiProvider, those calls will NOT appear in Helicone dashboards. This is expected and acceptable:
- Anthropic calls (Haiku baseline) → visible in Helicone
- Gemini calls (Flash variant) → requires separate Gemini Cloud Logging (out of scope for Sprint 16)

This means Helicone is useful for debugging Anthropic routing/latency, but is not a complete observability solution for multi-model evaluations.

---

## Impact

- Enables observability for multi-step Anthropic LLM interactions (useful for debugging FEATURE-053 Haiku baseline)
- Zero-friction toggle for evaluation runs
- Foundation for future tracer abstraction
- No blocking impact on FEATURE-053 (optional enhancement)

---

## Related Tickets

- BUG-090 (blocking: model routing must be observable first)
- FEATURE-053 (evals benefit from trace visibility, not required)