---
id: TASK-085
type: task
status: backlog
priority: P1
complexity: medium
created: 2026-04-30
updated: 2026-04-30
---

# TASK-085: Build DeepSeek Provider Integration

## Problem

FEATURE-054 Phase 4 discovered that direct DeepSeek API is 10-12x cheaper than OpenRouter. Current Backdrop uses only Anthropic provider. To realize $54k+/year savings, need to add DeepSeek V4 Flash as an LLM provider option for all three Tier 1 operations (entity extraction, sentiment analysis, theme extraction).

## Proposed Solution

Create `DeepSeekProvider` class following the existing `AnthropicProvider` pattern. Integrate with LLM Gateway to support model routing, cost tracking, error handling, and rate limiting.

## User Story

As an infrastructure engineer optimizing Backdrop costs, I want to add DeepSeek as a supported LLM provider so that I can route Tier 1 operations to DeepSeek V4 Flash and reduce annual LLM spend by ~$55k.

## Acceptance Criteria

- [ ] `DeepSeekProvider` class implemented at `src/crypto_news_aggregator/llm/deepseek_provider.py`
  - Follows same interface as `AnthropicProvider`
  - Implements: `__init__`, `call()`, `get_model()`, error handling, retries
  - Supports both non-thinking and thinking modes (via parameter)
  - Implements cost tracking (input tokens, output tokens)
  
- [ ] LLM Gateway integration
  - Gateway can instantiate `DeepSeekProvider` via factory pattern
  - Model routing enforces DeepSeek for specified operations
  - Cost tracking logs DeepSeek calls to `llm_traces` collection
  - Rate limiting applied (DeepSeek API limits)
  
- [ ] Configuration & environment
  - New env var: `DEEPSEEK_API_KEY` loaded in config
  - New env var: `DEEPSEEK_DEFAULT_MODEL` (default: "deepseek-v4-flash")
  - Provider can be selected via `LLM_PROVIDER` config or per-operation routing
  
- [ ] Error handling & retries
  - Handles rate limit (429) with exponential backoff
  - Handles auth errors (401/403) gracefully
  - Fallback behavior: retry logic, optional fallback to Haiku
  - Logs errors with context for debugging
  
- [ ] Testing & validation
  - Unit tests: provider instantiation, API request formatting
  - Integration test: end-to-end call on 5 golden set articles (entity, sentiment, theme)
  - Validation report: cost per operation, agreement rates with Haiku baseline
  - [ ] entity_extraction: 5 articles, verify F1 >= 0.30 (accept baseline risk)
  - [ ] sentiment_analysis: 5 articles, verify agreement >= 80% with Haiku
  - [ ] theme_extraction: 5 articles, verify output format correct
  
- [ ] Documentation
  - Update `60-llm.md` with DeepSeek provider details
  - Add cost comparison table: Haiku vs DeepSeek direct API
  - Document: when to use DeepSeek, known limitations, monitoring
  
- [ ] Cost tracking validation
  - Verify token counts are accurate (compared to DeepSeek dashboard)
  - Verify costs calculated correctly: (input_tokens * $0.14 + output_tokens * $0.28) / 1M
  - Spot-check: 3 operations × 5 articles = 15 calls total

## Dependencies

- FEATURE-054: Tier 1 Cost Optimization Evals (completed)
- TASK-081: Fix Tier 1 Prompts (completed)
- DeepSeek API account with API key (prerequisite)

## Implementation Notes

### File Structure
```
src/crypto_news_aggregator/llm/
  ├── deepseek_provider.py         (NEW — 200-300 lines)
  ├── anthropic_provider.py        (existing — reference for interface)
  ├── factory.py                   (update to support DeepSeek)
  └── gateway.py                   (update cost tracking format)

src/crypto_news_aggregator/core/
  ├── config.py                    (add DEEPSEEK_API_KEY, DEEPSEEK_DEFAULT_MODEL)

tests/
  ├── test_deepseek_provider.py    (NEW — unit tests)
  ├── test_deepseek_integration.py (NEW — end-to-end validation)

docs/
  ├── 60-llm.md                    (update with DeepSeek section)
```

### DeepSeekProvider Interface

```python
class DeepSeekProvider(LLMProvider):
    def __init__(self, api_key: str, model_name: str = "deepseek-v4-flash"):
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = "https://api.deepseek.com"
    
    async def call(
        self,
        prompt: str,
        system_prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        thinking_mode: bool = False,
    ) -> str:
        """Call DeepSeek API with retry logic."""
        # Implementation
    
    def get_model(self) -> str:
        return self.model_name
    
    # Cost tracking
    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * 0.14 + output_tokens * 0.28) / 1_000_000
```

### Testing Plan

**Unit Tests:**
1. Provider instantiation (check API key, model name)
2. Request formatting (system prompt, user prompt, max_tokens)
3. Response parsing (JSON structure, token counting)
4. Error handling (rate limit, auth failure, timeout)

**Integration Tests:**
1. End-to-end calls on 5 articles per operation
2. Compare outputs with Haiku baseline (agreement %)
3. Cost calculation accuracy
4. Cost logging to `llm_traces`

**Validation Report:**
- Template: `docs/sprints/sprint-018/validation/TASK-085-deepseek-validation-report.md`
- Include: token counts, latencies, costs, agreement rates, spot-checked failures

### Known Constraints

- **Cache hit pricing:** DeepSeek offers 90% discount on cache hits ($0.0028/M input tokens). Not implemented in Phase 1; defer to Phase 2 optimization.
- **Thinking mode:** DeepSeek V4 Pro supports extended reasoning. V4 Flash supports standard thinking (default). Confirm thinking_mode parameter works as expected.
- **Rate limits:** DeepSeek API rate limits (TBD from docs). Implement exponential backoff; alert if hitting limits in production.
- **Fallback model:** If DeepSeek unavailable, fallback to Haiku (via gateway logic).

## Open Questions

- [ ] Should we implement cache support (cache_control header) for DeepSeek? Would require Redis or similar. Defer to Sprint 18+?
- [ ] Thinking mode: Should it be opt-in per operation, or always off for speed?
- [ ] Rate limit strategy: Hard cap on daily DeepSeek spend? Or just log and alert?
- [ ] Gradual rollout: Deploy sentiment first (low risk), entity/theme second (higher risk)? Or all at once?

## Timeline & Effort

- **Effort:** 3-4 hours (implementation + testing)
- **Sprint:** Sprint 18, Day 1-2
- **Blocker for:** TASK-086 (production deployment & validation)

## Success Criteria

- [ ] Provider implemented and integrated with gateway
- [ ] 15 validation calls (5 per operation) pass with documented results
- [ ] Cost tracking working (costs logged to `llm_traces`)
- [ ] Documentation updated
- [ ] Ready to hand off to TASK-086 (production rollout)

## Completion Summary

*Fill in after completion*

---

*Related: FEATURE-054, TASK-086 (production deployment)*