# LLM Integration & Briefing Generation

## Overview

The briefing agent uses Anthropic's Claude API to generate crypto market briefings. This document describes LLM initialization, the generation prompt structure, model selection, quality refinement, and cost tracking. Understanding this layer enables debugging generation failures and optimizing LLM usage.

**Anchor:** `#llm-integration-generation`

## Architecture

### Key Components

- **LLM Provider Factory**: Initializes and returns Claude client based on configuration
- **BriefingAgent**: Orchestrates briefing generation using LLM calls
- **Prompt Templates**: System prompts, generation prompts, critique/refinement prompts
- **Self-Refine Loop**: Quality assurance through iterative refinement
- **Cost Tracker**: Logs token usage for billing and optimization
- **Model Fallback**: Automatic fallback to cheaper models on API errors

### Data Flow

1. **Gather Inputs** → Collect signals, narratives, patterns, and memory context
2. **Build Prompts** → Generate system prompt and generation prompt with context
3. **Call LLM** → Make API request to Claude (try primary model, fallback to cheaper models)
4. **Parse Response** → Extract narrative, insights, recommendations from LLM output
5. **Self-Refine** → Critique output and refine if quality issues detected
6. **Track Cost** → Log token usage for cost monitoring
7. **Save Briefing** → Persist final briefing to MongoDB

## Implementation Details

### LLM Client Initialization

**File:** `src/crypto_news_aggregator/llm/factory.py:15-50`

The factory function returns the configured LLM provider:

```python
def get_llm_provider() -> LLMProvider:
    """Get the singleton LLMProvider instance."""
    settings = get_settings()
    provider_name = getattr(settings, "LLM_PROVIDER", "anthropic").lower()

    if provider_name == "anthropic":
        return AnthropicProvider(
            api_key=settings.ANTHROPIC_API_KEY,
            model_name=settings.ANTHROPIC_DEFAULT_MODEL
        )
```

**Key configuration:**
- `LLM_PROVIDER`: Set to "anthropic" (supports other providers via strategy pattern)
- `ANTHROPIC_API_KEY`: Loaded from environment (required)
- `ANTHROPIC_DEFAULT_MODEL`: Defaults to fallback if not specified

**File:** `src/crypto_news_aggregator/core/config.py:40-47`

Model configuration:
- `ANTHROPIC_DEFAULT_MODEL`: "claude-3-haiku-20240307" (fallback)
- `ANTHROPIC_ENTITY_MODEL`: "claude-3-5-haiku-20241022" (entity extraction)
- `ANTHROPIC_ENTITY_FALLBACK_MODEL`: "claude-3-5-sonnet-20241022" (expensive fallback)

### Briefing Generation Workflow

**File:** `src/crypto_news_aggregator/services/briefing_agent.py:111-165`

High-level generation flow:

```python
async def generate_briefing(
    self,
    briefing_type: str,  # "morning", "afternoon", "evening"
    force: bool = False,
    is_smoke: bool = False,
    task_id: str | None = None,
) -> Optional[Dict[str, Any]]:
    # 1. Check if briefing already exists (unless force=true)
    exists = await check_briefing_exists_for_slot(briefing_type)
    if exists and not force:
        return None  # Skip, already generated

    # 2. Gather inputs (signals, narratives, patterns, memory)
    briefing_input = await self._gather_inputs(briefing_type)

    # 3. Generate initial briefing with LLM
    generated = await self._generate_with_llm(briefing_input)

    # 4. Self-refine for quality (up to 2 iterations)
    generated = await self._self_refine(generated, briefing_input)

    # 5. Save to database
    briefing_doc = await self._save_briefing(
        briefing_type, briefing_input, generated, is_smoke, task_id
    )

    return briefing_doc
```

### LLM API Request

**File:** `src/crypto_news_aggregator/services/briefing_agent.py:854-900`

`_call_llm()` is a briefing-specific orchestrator that delegates to the LLM gateway. It does not make direct HTTP calls:

```python
async def _call_llm(
    self,
    prompt: str,
    system_prompt: str,
    max_tokens: int = 2048,
) -> str:
    """Call the LLM via gateway with briefing-specific fallback logic."""
    # Delegates to gateway — all spend cap enforcement and tracing happen there
    response = await self.gateway.call(          # Line 880
        prompt=prompt,
        system_prompt=system_prompt,
        model=BRIEFING_PRIMARY_MODEL,
        max_tokens=max_tokens,
        operation="briefing_generate",
    )
    return response
```

**Key behaviors:**
- Delegates to `gateway.py` (single LLM entry point) — spend caps, tracing, and model routing all enforced there
- Primary model: **Haiku 4.5** (`claude-haiku-4-5-20251001`) — cost-optimized default
- Fallback model: **Sonnet 4.5** (`claude-sonnet-4-5-20250929`) — used when Haiku returns 403 or exhausts retries
- Model constants defined at lines 54-55 of `briefing_agent.py`

### System Prompt

**File:** `src/crypto_news_aggregator/services/briefing_agent.py:402-425`

The system prompt establishes role and constraints:

```
You are a senior crypto market analyst writing a {time_context} briefing memo.

Your role is to synthesize ONLY the narratives listed below into an insightful briefing.

IMPORTANT RULES:
1. Use ONLY the narratives provided—do NOT add external knowledge
2. Focus on explaining narrative themes and their market implications
3. Keep key_insights concise (max 3-5 per briefing)
4. Recommendations must reference narratives provided, not external
5. Be accurate—if data conflicts with your training, trust the data provided
6-8. [internal formatting rules]
9. Consolidate duplicate events — if the same event appears under different narrative angles, present it once with full context, not as separate stories
10. No unnamed entities — every referenced platform, exchange, or project must be explicitly named using only names present in the provided narratives
11. Verify figure plausibility against ~$2-3T crypto market cap baseline — flag or omit figures that are historically unprecedented (e.g., $50B+ liquidations, $10B+ single hacks)
```

The prompt is dynamically set to "morning" or "evening" context (line 404). Rules 9-11 were added in BUG-081 to address duplicate event framing and unnamed entity references.

### Generation Prompt Structure

**File:** `src/crypto_news_aggregator/services/briefing_agent.py:433-650` (estimated)

The generation prompt includes:

1. **Briefing Type & Context**: "Generate a morning briefing" with current time — date is converted from UTC to `America/Chicago` (CST/CDT) before formatting, so the LLM prompt date matches the frontend display timezone (BUG-080, commit 13d0ecc)
2. **Recent Signals** (20 signals max): Market events, price movements, sentiment
3. **Active Narratives** (15 max): Story threads with entities and recent articles
4. **Detected Patterns** (8 max): Market anomalies, correlations, divergences
5. **Memory Context** (feedback history): Past analyst feedback and preferences
6. **Instructions**: Output format (JSON with narrative, key_insights, recommendations)

Example instructions in prompt:
```
Generate a structured briefing with:
- narrative (2-3 paragraphs synthesizing the narratives)
- key_insights (3-5 most important takeaways)
- entities_mentioned (people, companies, projects discussed)
- detected_patterns (market patterns observed)
- recommendations (2-3 narratives to read for context)

Output as JSON only, no markdown.
```

### Self-Refine Quality Loop

**File:** `src/crypto_news_aggregator/services/briefing_agent.py:329-400`

Two-iteration quality assurance:

**Iteration 1:**
1. Generate briefing (line 319-327)
2. Build critique prompt evaluating: completeness, accuracy, grammar, actionability, plus:
   - Check 8: Detect duplicate events presented as separate stories (critical flag)
   - Check 9: Detect unnamed entity references — every platform/exchange must be explicitly named
   - Check 10: Detect implausible figures ($50B+ liquidations, $10B+ hacks flagged as historically unprecedented)
3. Call LLM to get critique response (line 359-363)
4. Parse critique: Does it say "PASS" or list issues? (line 366)
5. If PASS → Return with "Quality passed on iteration 1" (line 371)
6. If issues → Build refinement prompt with critique (line 378-379)

**Iteration 2:**
1. Call LLM with refinement prompt (line 382-386)
2. Parse refined response (line 388)
3. Check quality again
4. If PASS → Return with "Quality passed on iteration 2"
5. If fail → Log warning, reduce confidence to 0.6, add "Max refinement reached" (line 391-398)

**Cost of refinement:**
- Primary generation: 4,000 max tokens (Sonnet, ~$0.02)
- Critique 1: 1,024 max tokens (Sonnet, ~$0.005)
- Refinement 1: 4,000 max tokens (Sonnet, ~$0.02)
- Critique 2: 1,024 max tokens (Sonnet, ~$0.005)
- **Total: ~$0.05 per briefing** (before fallbacks)

### Cost Tracking & Budget Enforcement

**File:** `src/crypto_news_aggregator/llm/gateway.py` (primary), `src/crypto_news_aggregator/services/cost_tracker.py` (aggregation queries)

#### Single Source of Truth: llm_traces Collection

All LLM calls are traced in the `llm_traces` MongoDB collection by the gateway. This is the **authoritative source** for cost enforcement and spend visibility. Budget enforcement reads **exclusively** from `llm_traces`; `api_costs` and `llm_usage` are legacy and not authoritative as of Sprint 15 (BUG-079).

**Trace document structure:**
```python
# Written by gateway.py after every LLM call
{
    "operation": "briefing_generate",      # Caller-supplied operation name (required)
    "model": "claude-haiku-4-5-20251001",
    "input_tokens": 1200,
    "output_tokens": 800,
    "cost": 0.00031,                       # field name is "cost", not "cost_usd"
    "timestamp": ISODate("..."),           # Query field — NOT "created_at"
    "cached": false
}
```

**Critical field names:**
- Always query using `timestamp`, not `created_at` (caught in Sprint 14)
- Cost field is `cost`, not `cost_usd`; aggregations must use `"$cost"`
- `operation` is required; zero `provider_fallback` entries post-BUG-078

**TTL and Indexing:**
- TTL index: 30 days (legacy traces auto-deleted)
- Indexes: `{operation: 1}`, `{operation: 1, timestamp: -1}`

#### Budget Enforcement Mechanism (FEATURE-013, Sprint 15)

**File:** `src/crypto_news_aggregator/llm/gateway.py:143-178` (spend cap enforcement), `src/crypto_news_aggregator/services/cost_tracker.py:45-120` (cost queries)

Two-tier budget system implemented at the gateway, before any call reaches the Anthropic API:

**Daily Hard Limit:** $1.00/day
- Checked by `check_llm_budget(operation_name)` before every LLM call
- If daily spend already ≥ $1.00, call is blocked and raises `BudgetExceededError`
- Reset at 00:00 UTC each day

**Monthly Hard Limit:** $30/month  
- Checked by `check_llm_budget()` as part of daily check
- Monthly window: First of month 00:00 UTC to last day 23:59 UTC
- If monthly spend ≥ $30.00, all LLM calls blocked regardless of daily status
- Monthly limit takes precedence over daily limit

**Soft Limit:** $22.50/month (⚠️ **Alert configured but NOT currently working**)
- Designed to trigger Slack notification when crossed
- Alert was implemented but is non-functional (known issue as of Sprint 15)
- Soft limit does not block calls; it's informational only
- Do not rely on Slack alert for spend awareness; monitor cost dashboard instead

**Implementation:**
```python
# gateway.py: called before every LLM API request
async def check_llm_budget(operation_name: str) -> bool:
    """Check if LLM call would exceed daily or monthly limits."""
    daily_cost = await get_daily_cost()      # Sum of "cost" from llm_traces today
    monthly_cost = await get_monthly_cost()  # Sum of "cost" from llm_traces this month
    
    daily_remaining = DAILY_HARD_LIMIT - daily_cost  # $1.00 - current
    monthly_remaining = MONTHLY_HARD_LIMIT - monthly_cost  # $30.00 - current
    
    if daily_remaining <= 0 or monthly_remaining <= 0:
        raise BudgetExceededError(f"Daily: ${daily_cost:.2f}/${DAILY_HARD_LIMIT}, Monthly: ${monthly_cost:.2f}/${MONTHLY_HARD_LIMIT}")
    
    # Soft limit alert (non-functional; logged but doesn't trigger Slack)
    if monthly_cost >= SOFT_LIMIT and not alerted_today:
        logger.warning(f"Monthly spend at ${monthly_cost:.2f}/${SOFT_LIMIT} — Slack alert not working")
    
    return True
```

**Cost Query Implementation:**
```python
# cost_tracker.py: queries for spend visibility
async def get_daily_cost() -> float:
    """Sum all LLM traces from last 24 hours."""
    now = datetime.utcnow()
    yesterday = now - timedelta(hours=24)
    result = await db.llm_traces.aggregate([
        {"$match": {"timestamp": {"$gte": yesterday}}},
        {"$group": {"_id": None, "total": {"$sum": "$cost"}}}
    ]).to_list(1)
    return result[0]["total"] if result else 0.0

async def get_monthly_cost() -> float:
    """Sum all LLM traces from first of month to now."""
    now = datetime.utcnow()
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.llm_traces.aggregate([
        {"$match": {"timestamp": {"$gte": first_of_month}}},
        {"$group": {"_id": None, "total": {"$sum": "$cost"}}}
    ]).to_list(1)
    return result[0]["total"] if result else 0.0
```

#### Validated Cost Baseline (Post-Sprint 15)

True daily baseline: **~$0.54/day** (monthly: ~$16/month)

The $1.134/day figure from Sprint 14 was incorrect due to:
- BUG-066: Rolling 24h window calculating wrong cost aggregation
- BUG-079: entity_extraction costs ($0.177/day) invisible to enforcement layer

Post-Sprint 15 cost breakdown by operation (typical day):

| Operation | Calls/day | Cost/day | Notes |
|-----------|-----------|----------|-------|
| entity_extraction | ~174 | $0.152 | Highest volume; Tier 1 articles only |
| narrative_generate | ~51 | $0.125 | Narrative summary generation |
| article_enrichment_batch | ~variable | ~$0.150 | RSS enrichment |
| briefing_refine | ~4 | $0.032 | Critique + refinement (2 briefings) |
| briefing_critique | ~4 | $0.023 | Quality assurance loop |
| briefing_generate | ~2 | $0.020 | Primary generation (3 briefings/day × 2) |
| cluster_narrative_gen | ~6 | $0.006 | Embedding-based clustering |
| narrative_polish | ~6 | $0.003 | Final polish |
| **TOTAL** | | **~$0.54** | Well under $1.00 daily hard limit |

Model cost reduction: **89% reduction** from Sprint 12–13 high of $2.50–5.00/day, achieved through:
- Tier classification before enrichment (only ~70 of 300 articles enriched/day)
- Haiku as primary model (100% production routing as of BUG-077)
- Prompt compression (BUG-071: 1,700 → 900 token system prompt)
- Request/response caching (BUG-072)

#### Model Routing Enforcement (BUG-077, Sprint 15)

**File:** `src/crypto_news_aggregator/llm/gateway.py:88-110`

The gateway enforces model selection **before** the Anthropic API is contacted. `_validate_model_routing()` silently corrects misrouted models:

```python
# gateway.py: called inside every API request
def _validate_model_routing(model: str, operation: str) -> str:
    """Enforce correct model for operation; silently correct misroutes."""
    expected_model = self._get_expected_model(operation)  # Maps operation → correct model
    
    if model != expected_model:
        logger.warning(f"Model mismatch: {operation} requested {model}, correcting to {expected_model}")
        # Silently use correct model instead; prevents expensive models reaching API
        return expected_model
    
    return model
```

**Current production routing (post-BUG-077):**
- **All operations → Haiku 4.5** (`claude-haiku-4-5-20251001`)
- 100% Haiku in production (zero Opus/Sonnet except test sessions)
- Fallback model (Sonnet) used only on 403 errors from Anthropic
- Prevents accidental Opus ($0.039/call) and Sonnet ($0.002/call) charges

**Validation result:** 682/683 calls on Haiku; 1 Opus trace from Claude Code test session (not production)

### Response Parsing

**File:** `src/crypto_news_aggregator/services/briefing_agent.py:730-764` (estimated)

LLM response is parsed from JSON:

```python
def _parse_briefing_response(self, response_text: str) -> GeneratedBriefing:
    """Parse JSON response from LLM into GeneratedBriefing dataclass."""
    try:
        data = json.loads(response_text)
        return GeneratedBriefing(
            narrative=data.get("narrative", ""),
            key_insights=data.get("key_insights", []),
            entities_mentioned=data.get("entities_mentioned", []),
            detected_patterns=data.get("detected_patterns", []),
            recommendations=data.get("recommendations", []),
            confidence_score=data.get("confidence_score", 0.85),
        )
    except json.JSONDecodeError:
        logger.error(f"Failed to parse LLM response: {response_text[:200]}")
        # Return low-confidence placeholder
        return GeneratedBriefing(...)
```

## Operational Checks

### Health Verification

**Check 1: LLM provider is accessible**
```bash
# Test API key and connectivity
curl -X POST https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-3-5-haiku-20241022","max_tokens":100,"messages":[{"role":"user","content":"Say ok"}]}'
# Should return 200 with content in response
```
*File reference:* `src/crypto_news_aggregator/services/briefing_agent.py:779-792` (API request structure)

**Check 2: System prompt is well-formed**
```bash
# Verify system prompt doesn't have syntax errors
python -c "
from crypto_news_aggregator.services.briefing_agent import BriefingAgent
agent = BriefingAgent()
prompt = agent._get_system_prompt('morning')
assert 'crypto market analyst' in prompt
assert 'morning' in prompt
print('✓ System prompt OK')
"
```
*File reference:* `src/crypto_news_aggregator/services/briefing_agent.py:402-425`

**Check 3: Cost tracking is working**
```bash
# Query cost tracking database
db.llm_usage.findOne({operation: "briefing_generation"})
# Should return recent documents with model, input_tokens, output_tokens
```
*File reference:* `src/crypto_news_aggregator/services/briefing_agent.py:809-817` (cost tracking)

**Check 4: Briefing generation completes within timeout**
```bash
# Trigger a briefing and measure time
time curl -X POST "http://localhost:8000/admin/trigger-briefing?force=true"
# Should complete in < 120 seconds (timeout is 120s per LLM call)
```
*File reference:* `src/crypto_news_aggregator/services/briefing_agent.py:791` (timeout)

### Model Selection & Fallback

**Current model hierarchy:**
1. **Primary:** `claude-haiku-4-5-20251001` — cost-optimized default for all briefing generation (~10x cheaper than Sonnet)
2. **Fallback:** `claude-sonnet-4-5-20250929` — used when Haiku returns 403 Forbidden or exhausts retries

**When to fallback:**
- 403 Forbidden: Model rate-limited or API key issue → retry with Sonnet
- Spend limit breach: Gateway blocks call before it reaches Anthropic; no fallback attempted
- Timeout: Retry with same model

**Model constants:** Defined at lines 54-55 of `briefing_agent.py` as `BRIEFING_PRIMARY_MODEL` and `BRIEFING_FALLBACK_MODEL`. All calls route through `gateway.py` which enforces model routing and spend caps before the Anthropic API is contacted.

*File reference:* `src/crypto_news_aggregator/services/briefing_agent.py:54-55` (model constants), `854-900` (`_call_llm()` gateway delegation)

## Debugging

**Issue:** LLM API returns "Invalid API key" (403 Forbidden)
- **Root cause:** ANTHROPIC_API_KEY env var not set or expired
- **Verification:** Check `echo $ANTHROPIC_API_KEY` and verify in Anthropic console
- **Fix:** Set/update ANTHROPIC_API_KEY in environment and restart workers
  *Reference:* `src/crypto_news_aggregator/services/briefing_agent.py:94-97` (initialization)

**Issue:** Briefing fails with "All LLM models failed" error
- **Root cause:** All three models returned errors (rate limit, auth, service outage)
- **Verification:** Check worker logs for per-model errors
- **Fix:** Check Anthropic status page; may need to wait for rate limit recovery
  *Reference:* `src/crypto_news_aggregator/services/briefing_agent.py:834`

**Issue:** Generated briefing is empty or has no narrative
- **Root cause:** JSON parsing failed or LLM returned invalid format
- **Verification:** Check worker logs for "Failed to parse LLM response"
- **Fix:** Review generation prompt (may be incomplete); could be malformed JSON
  *Reference:* `src/crypto_news_aggregator/services/briefing_agent.py:730-764` (parsing)

**Issue:** Self-refine loop runs multiple iterations instead of stopping at 1
- **Root cause:** Critique prompt says "needs refinement" even though content is good
- **Verification:** Check logs for "Briefing needs refinement"; review critique response
- **Fix:** Adjust critique prompt to be less strict, or check for LLM consistency issues
  *Reference:* `src/crypto_news_aggregator/services/briefing_agent.py:366-372` (refinement check)

**Issue:** Cost tracking shows high token counts but briefing seems short
- **Root cause:** System prompt and generation prompt are much longer than output
- **Verification:** Log prompt lengths: `len(system_prompt) + len(generation_prompt)`
- **Fix:** This is normal; input tokens include full context. Monitor for outliers
  *Reference:* `src/crypto_news_aggregator/services/briefing_agent.py:805-806` (token counting)

## Relevant Files

### Core Logic
- `src/crypto_news_aggregator/services/briefing_agent.py` - Main generation orchestration
  - Lines 111-165: `generate_briefing()` entry point
  - Lines 315-327: `_generate_with_llm()` - Initial generation
  - Lines 329-400: `_self_refine()` - Quality refinement loop
  - Lines 766-834: `_call_llm()` - API request with fallback
  - Lines 402-425: `_get_system_prompt()` - System prompt template

### Configuration
- `src/crypto_news_aggregator/llm/factory.py:15-50` - Provider initialization
- `src/crypto_news_aggregator/core/config.py:40-47` - Model configuration
- `.env` - ANTHROPIC_API_KEY

### Cost Tracking
- `src/crypto_news_aggregator/services/cost_tracker.py` - Token cost calculation
- `src/crypto_news_aggregator/services/briefing_agent.py:809-817` - Cost logging

### Integration Points
- `src/crypto_news_aggregator/tasks/briefing_tasks.py` - Celery task wrapper calls agent
- `src/crypto_news_aggregator/api/admin.py:415` - HTTP endpoint to trigger generation

### Related Systems
- **Scheduling (20-scheduling.md)** - How briefings are triggered for generation
- **Data Model (50-data-model.md)** - Where generated briefings are stored

---
*Last updated: 2026-04-25* | *Generated from: 04-llm-client.txt, 04-llm-prompts.txt, 05-briefing-generation.txt* | *Anchor: llm-integration-generation*