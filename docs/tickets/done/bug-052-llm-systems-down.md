---
id: BUG-052
type: bug
status: backlog
priority: critical
severity: critical
created: 2026-03-11
updated: 2026-03-11
---

# All LLM Systems Non-Functional

## Problem
None of the LLM-dependent systems in Backdrop are working. This affects briefing generation, entity extraction, sentiment analysis, and any other component that calls the Anthropic API. The system previously had an "insufficient Anthropic API credits" issue that was resolved (credits added 2026-02-27), so this is a different root cause.

## Expected Behavior
All LLM-dependent services should successfully call the Anthropic API and return results:
- Briefing generation produces morning/afternoon/evening briefings via Claude
- Entity extraction identifies companies, people, and projects from article content
- Sentiment analysis classifies articles as bullish/bearish/neutral

## Actual Behavior
All LLM calls are failing. No briefings are being generated, and enrichment pipeline (entity extraction + sentiment) is not completing.

## Steps to Reproduce
1. Trigger a manual briefing: `curl -X POST "http://localhost:8000/admin/trigger-briefing?briefing_type=morning&force=true"`
2. Check worker logs for LLM-related errors
3. Observe failure across all LLM-dependent tasks

## Environment
- Environment: production
- User impact: high — no new briefings, no article enrichment

## Investigation Guide

This is a shared-dependency failure (all LLM systems down simultaneously). Work through these layers in order, starting from the most likely root cause.

### Layer 1: API Key & Credentials
Check that the Anthropic API key is valid and loaded into the environment.

**Files:**
- `.env` — `ANTHROPIC_API_KEY` value
- `src/crypto_news_aggregator/core/config.py:40-47` — model + key config
- `src/crypto_news_aggregator/llm/factory.py:15-50` — provider initialization, reads API key from settings

**Checks:**
- Verify `ANTHROPIC_API_KEY` env var is set and non-empty in the running worker process
- Test the key directly:
  ```bash
  curl -X POST https://api.anthropic.com/v1/messages \
    -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H "anthropic-version: 2023-06-01" \
    -H "content-type: application/json" \
    -d '{"model":"claude-3-5-haiku-20241022","max_tokens":50,"messages":[{"role":"user","content":"Say ok"}]}'
  ```
- If 401/403: key is invalid or expired — regenerate in Anthropic console
- If 200: key is fine, move to Layer 2

### Layer 2: Model Availability
Check whether the configured model strings are still valid. Anthropic periodically deprecates model versions.

**Files:**
- `src/crypto_news_aggregator/services/briefing_agent.py:46-50` — model fallback list:
  - Primary: `claude-sonnet-4-5-20250929`
  - Fallback 1: `claude-3-5-haiku-20241022`
  - Fallback 2: `claude-3-haiku-20240307`
- `src/crypto_news_aggregator/core/config.py:40-47` — default model config:
  - `ANTHROPIC_DEFAULT_MODEL`: `claude-3-haiku-20240307`
  - `ANTHROPIC_ENTITY_MODEL`: `claude-3-5-haiku-20241022`
  - `ANTHROPIC_ENTITY_FALLBACK_MODEL`: `claude-3-5-sonnet-20241022`

**Checks:**
- Test each model string with a minimal API call (see curl above, swap model name)
- If any return `model_not_found` or similar, that model has been deprecated — update to current equivalent
- Pay attention to `claude-3-haiku-20240307` (oldest, most likely to be deprecated)
- Check Anthropic docs/changelog for any recent model deprecations

### Layer 3: LLM Client & Request Path
Two different call patterns exist in the codebase. Both need to work.

**Pattern A — Direct httpx (briefing generation):**
- `src/crypto_news_aggregator/services/briefing_agent.py:766-834` — `_call_llm()` method
- Uses `httpx.AsyncClient` to POST to `https://api.anthropic.com/v1/messages`
- Headers: `x-api-key`, `anthropic-version: 2023-06-01`, `content-type: application/json`
- Timeout: 120s
- Check: Is httpx installed and working? Is the anthropic-version header still valid?

**Pattern B — LLM Provider abstraction (entity extraction, sentiment):**
- `src/crypto_news_aggregator/llm/factory.py:15-50` — `get_llm_provider()` factory
- `src/crypto_news_aggregator/services/entity_service.py:50-150` — entity extraction calls `self.llm_client.call(prompt)`
- `src/crypto_news_aggregator/core/sentiment_analyzer.py:30-80` — sentiment analysis
- Check: Is the provider initializing correctly? Is `llm_client.call()` raising exceptions silently?

### Layer 4: Network & Infrastructure
- Verify workers can reach `api.anthropic.com` (DNS, firewall, proxy)
- Check Redis broker is running (tasks might not be dispatching at all)
- Check Celery worker logs for connection errors or task failures
- Verify MongoDB is accessible (failed DB reads before LLM call could look like LLM failure)

### Layer 5: Error Handling & Silent Failures
Check whether errors are being swallowed:
- `src/crypto_news_aggregator/services/briefing_agent.py:824-829` — fallback logic after model failure
- `src/crypto_news_aggregator/services/briefing_agent.py:834` — "All LLM models failed" error path
- `src/crypto_news_aggregator/tasks/briefing_tasks.py:123-126` — task-level exception handler (retries up to 2x with 5min delay)
- `src/crypto_news_aggregator/tasks/process_article.py:25-35` — enrichment task error handling

**Check worker logs for:**
- `"All LLM models failed"` — confirms all fallbacks exhausted
- `"Failed to parse LLM response"` — API returned but response was malformed
- `"Starting morning briefing generation task"` — confirms task was dispatched
- Any `403`, `401`, `429`, `500` status codes from the API

## Resolution Checklist
Once root cause is identified:
- [ ] Fix the root cause (update key, model strings, client code, etc.)
- [ ] Verify with manual briefing trigger: `POST /admin/trigger-briefing?briefing_type=morning&force=true`
- [ ] Confirm briefing appears in MongoDB: `db.daily_briefings.findOne({}, {generated_at:1}).sort({generated_at:-1})`
- [ ] Verify entity extraction is running: check recent articles have `entities` populated
- [ ] Verify sentiment analysis is running: check recent articles have `sentiment` populated
- [ ] Monitor next scheduled briefing (check Celery Beat logs) to confirm automated pipeline is restored

---

## Resolution

**Status:** Root Cause Identified - Awaiting Credit Purchase
**Fixed:** Pending
**Branch:** Not needed - operational issue, not a code bug
**Commit:** N/A

### Root Cause
**Anthropic Account Credit Balance Exhausted**

Investigation confirmed:
- API Key: ✅ Valid (108 chars, properly configured in settings)
- Model strings: ✅ Valid (`claude-haiku-4-5-20251001`, `claude-sonnet-4-5-20250929` both active)
- API headers: ✅ Correct (`anthropic-version: 2023-06-01`)
- **ACTUAL ERROR:** 400 Bad Request with message: "Your credit balance is too low to access the Anthropic API"

Timeline:
- 2026-02-27: Previous credit exhaustion fixed (credits added)
- 2026-03-11: Account credits exhausted again

### Changes Made
None required - this is an operational/billing issue, not a code issue.

### Testing & Verification
Direct API test performed:
```bash
curl -X POST https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model":"claude-haiku-4-5-20251001",
    "max_tokens":50,
    "messages":[{"role":"user","content":"Say ok"}]
  }'
```
**Result:** 400 - "Your credit balance is too low to access the Anthropic API"

### Files Changed
None

### Next Steps (For Operations)
1. Visit Anthropic console → Plans & Billing
2. Add sufficient credits to account
3. Redeploy to Railway or restart worker process
4. Verify briefing generation: `POST /admin/trigger-briefing?briefing_type=morning&force=true`
5. Confirm briefing appears in MongoDB and enrichment pipeline runs