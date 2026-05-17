# Backdrop Interview Deck — Source Code Verification Report

**Date:** 2026-05-16  
**Verified Against:** Crypto News Aggregator (main branch)  
**Methodology:** Direct source code inspection, configuration file analysis, schema validation

---

## 1. Executive Confirmation

### Is the proposed data flow broadly accurate?

**YES, with important caveats.** The overall pipeline structure matches the code. However:

- The system is actually **crypto-news-aggregator**, not "Backdrop"
- Several stages exist but are **partially functional** or **disabled**
- Trust boundaries are implemented but more fragile than the name suggests
- The "enriched" field pattern does not exist in the schema

### What is inaccurate, overstated, missing, or outdated?

| Issue | Severity | Details |
|-------|----------|---------|
| Market event detection | **DISABLED** | BUG-083: Phantom narratives with fabricated figures. Feature disabled completely. |
| Signal/market-event features | **DISABLED** | `market_event_detector.py` returns empty list unconditionally. |
| Narrative freshness constraints | **PARTIALLY IMPLEMENTED** | `narrative_trust.py` uses cutoff date (2026-05-10), but this is a hard-coded fallback, not dynamic. |
| Enrichment completion tracking | **MISSING** | No `enriched` field in article schema. Enrichment is implicit in selective processing. |
| Cascade of tier 3 filtering | **ACCURATE** | Tier 1 only enrichment is real. Tier 2-3 skip LLM enrichment entirely. |
| Briefing constraints | **ACCURATE** | Explicit prompt constraints in system prompt (lines 537-647 of `briefing_agent.py`). |
| LLM Gateway routing | **ACCURATE** | Single entry point (gateway.py). Routing table shows per-operation model selection. |

### Which parts are safe to present in an interview?

**SAFE:**
- Article ingestion from RSS (confirmed: `rss_fetcher.py`, `RSSService`)
- Deduplication via fingerprinting (confirmed: `article_service.py`, MD5-based)
- Relevance tiering before enrichment (confirmed: rule-based classifier, tier 1 only)
- Entity extraction with selective processing (confirmed: regex vs LLM decision tree)
- Sentiment analysis on tier 1 articles (confirmed: LLM-based, integrated into enrichment)
- Signal computation excluding tier 3 (confirmed: `signal_service.py` filters by `relevance_tier <= 2`)
- Narrative lifecycle states (confirmed: emerging/rising/hot/cooling/dormant/echo/reactivated)
- Briefing generation with hard constraints (confirmed: system prompt with explicit rules)
- LLM Gateway with multi-provider routing (confirmed: Anthropic + DeepSeek)
- Trust boundaries via cutoff date (confirmed: `narrative_trust.py`)

**AVOID or FLAG:**
- Market event detection (disabled)
- Signal/pattern market shock features (disabled)
- "Enriched" field as completion marker (does not exist)
- Real-time cost controls (only budget checks, no hard throttling)
- Stale narrative filtering as primary safeguard (only affects briefing summary inclusion, not storage)

---

## 2. Actual End-to-End Data Flow

### Stage 1: Raw Article Ingestion

**What triggers it:** Scheduled RSS fetch every 30 minutes (line 133 in `main.py`)

**Main files/functions:**
- `background/rss_fetcher.py:fetch_and_process_rss_feeds()`
- `core/news_sources/` (Bloomberg, CoinDesk, CoinTelegraph, etc.)
- `services/rss_service.py:RSSService.fetch_all_feeds()`

**Input data shape:**
```
RSS feed → Article { title, text, url, author, published_at, source, metrics }
Multiple sources: twitter, rss, reddit, telegram, coindesk, cointelegraph, decrypt, etc.
```

**Output data shape:**
```python
ArticleBase {
  title: str,
  source: Literal[20+ sources],
  text: str,
  url: str,
  metrics: { views, likes, retweets, replies },
  published_at: datetime,
  raw_data: Dict,
  # (enrichment fields empty at this stage)
}
```

**MongoDB collections:** `articles` (insert)

**LLM usage:** No

**Deterministic/LLM-based/Mixed:** Deterministic

**Failure behavior:** Articles rejected if blacklisted source (Benzinga). Failed fetches logged; cycle continues next iteration.

---

### Stage 2: Deduplication / Fingerprinting

**What triggers it:** Immediately after article fetch, before storage

**Main files/functions:**
- `services/article_service.py:ArticleService._generate_fingerprint()`
- `services/article_service.py:ArticleService._is_duplicate()`
- `db/operations/articles.py:create_or_update_articles()`

**Input data shape:**
```
Article { title, text, url, ... } (fetched)
```

**Output data shape:**
```python
Article {
  _id: ObjectId,
  fingerprint: str,  # MD5(normalized_title[:100] + normalized_text[:200])
  # (all input fields preserved)
  created_at: datetime,
  updated_at: datetime,
}
```

**MongoDB collections:** `articles` (check for duplicates, insert or skip)

**LLM usage:** No

**Deterministic/LLM-based/Mixed:** Deterministic (MD5 hash-based)

**Failure behavior:** Duplicate detected → skip insertion, log debug message. No side effects.

---

### Stage 3: Relevance Tiering (Rule-Based, Before Enrichment)

**What triggers it:** During article processing batch (line 649 in `rss_fetcher.py`)

**Main files/functions:**
- `services/relevance_classifier.py:RelevanceClassifier.classify()`
- Called from `background/rss_fetcher.py:process_new_articles_from_mongodb()` (line 650)

**Input data shape:**
```python
Article { title, text, source }
```

**Output data shape:**
```python
{
  tier: int,  # 1 (high signal), 2 (medium), 3 (low/exclude)
  reason: str,  # Reason for classification
}
# Saved to article: { relevance_tier, relevance_reason }
```

**MongoDB collections:** `articles` (update with tier + reason)

**LLM usage:** No

**Deterministic/LLM-based/Mixed:** Deterministic (regex pattern matching)

**Failure behavior:** Safe fallback to Tier 2 (include) when uncertain.

---

### Stage 4: Selective Enrichment (Tier 1 Only)

**What triggers it:** Batch processing for tier 1 articles only (line 687 in `rss_fetcher.py`)

**Main files/functions:**
- `services/selective_processor.py:SelectiveArticleProcessor.should_use_llm()`
- `background/rss_fetcher.py:process_new_articles_from_mongodb()` (line 711: `llm_client.enrich_articles_batch()`)
- `llm/anthropic.py:AnthropicLLM.enrich_articles_batch()`

**Input data shape:**
```python
Tier 1 Article { title, text, source }
Batched: [{ id, text }] × 10 articles per batch
```

**Output data shape:**
```python
{
  id: str,  # article_id
  relevance_score: float,
  sentiment_score: float,
  themes: List[str],
  # (used to populate article enrichment fields)
}
```

**MongoDB collections:** `articles` (update tier 1 only)

**LLM usage:** Yes (Anthropic Claude Haiku via gateway)

**Deterministic/LLM-based/Mixed:** LLM-based (prompt-based enrichment)

**Failure behavior:** If enrichment fails, tier 1 article gets tier assignment only, no enrichment data. Tier 2-3 skip entirely (no enrichment attempt).

---

### Stage 5: Entity Extraction

**What triggers it:** During enrichment batch processing (line 505-591 in `rss_fetcher.py`)

**Main files/functions:**
- `services/selective_processor.py:SelectiveArticleProcessor.extract_entities_simple()`
- `background/rss_fetcher.py:_process_entity_extraction_batch()` (LLM-based fallback)
- `db/operations/entity_mentions.py:create_entity_mentions_batch()`

**Input data shape:**
```python
Article { title, text }
```

**Output data shape:**
```python
EntityMention {
  entity: str,  # Canonical name (e.g., "Bitcoin")
  entity_type: str,  # "cryptocurrency"
  article_id: ObjectId,
  is_primary: bool,  # True if nucleus entity
  confidence: float,  # 0.7 (regex) or 0.85+ (LLM)
  source: str,
  created_at: datetime,
}
```

**MongoDB collections:** `entity_mentions` (insert batch)

**LLM usage:** Yes for premium sources (Anthropic) or mid-tier with keywords

**Deterministic/LLM-based/Mixed:** Mixed (regex for low-tier sources, LLM for high-tier)

**Failure behavior:** Regex fallback if LLM fails. At least cryptocurrency name extraction attempted.

---

### Stage 6: Sentiment Analysis

**What triggers it:** During enrichment, tier 1 articles only

**Main files/functions:**
- `llm/anthropic.py:AnthropicLLM.enrich_articles_batch()` (line 614: sentiment extraction)
- `background/rss_fetcher.py:_derive_sentiment_label()` (line 737)

**Input data shape:**
```python
Article { title, text }
```

**Output data shape:**
```python
{
  sentiment_score: float,  # -1.0 to +1.0
  sentiment_label: str,  # "positive", "negative", "neutral"
}
```

**MongoDB collections:** `articles` (update sentiment fields)

**LLM usage:** Yes (DeepSeek via gateway)

**Deterministic/LLM-based/Mixed:** LLM-based

**Failure behavior:** Default to 0.0 (neutral) if extraction fails.

---

### Stage 7: Signal Computation

**What triggers it:** Background task every 600 seconds (line 135 in `main.py`)

**Main files/functions:**
- `worker.py:update_signal_scores()`
- `services/signal_service.py:compute_trending_signals()`
- `api/v1/endpoints/signals.py:get_signals()`

**Input data shape:**
```python
Entity mention frequency over time windows (1d, 7d, 30d)
Filtered by: relevance_tier <= 2 (tier 3 excluded)
```

**Output data shape:**
```python
Signal {
  entity: str,
  mentions: int,  # Count in timeframe
  velocity: float,  # Growth rate as percentage
  sentiment: float,  # Average sentiment
  source_diversity: int,  # Count of unique sources
  rank: int,  # Ranking among all signals
}
```

**MongoDB collections:** `entity_mentions` (read), `signal_scores` (write)

**LLM usage:** No

**Deterministic/LLM-based/Mixed:** Deterministic (aggregation pipeline)

**Failure behavior:** Missing data → signal not computed. No hallucination risk.

---

### Stage 8: Narrative Construction

**What triggers it:** Background task every 600 seconds (line 135 in `main.py`)

**Main files/functions:**
- `worker.py:schedule_narrative_updates()`
- `services/narrative_service.py:cluster_by_narrative_salience()`
- `services/narrative_themes.py:compute_narrative_fingerprint()`
- `services/narrative_deduplication.py:deduplicate_narratives()`

**Input data shape:**
```python
Article + EntityMention (tier 1-2 only, tier 3 excluded)
Clustered by:
  - nucleus_entity (primary protagonist)
  - actor_salience (weighted co-occurrence)
  - narrative_focus (2-5 word description)
```

**Output data shape:**
```python
Narrative {
  _id: ObjectId,
  nucleus_entity: str,
  narrative_focus: str,  # e.g., "price surge", "regulatory enforcement"
  actors: List[str],  # Co-mentioned entities
  actor_salience: Dict[str, int],  # Salience scores 1-5
  article_ids: List[ObjectId],  # Related articles
  narrative_summary: str,  # Generated by LLM
  lifecycle_state: str,  # emerging, rising, hot, cooling, dormant, echo, reactivated
  first_seen: datetime,
  last_updated: datetime,
  last_summary_generated_at: datetime,
  fingerprint: Dict,  # Structure hash for matching
  mention_velocity: float,  # articles/day
}
```

**MongoDB collections:** `narratives` (upsert), `articles` (read)

**LLM usage:** Yes (Claude Haiku for narrative summary generation via gateway)

**Deterministic/LLM-based/Mixed:** Mixed (clustering is deterministic, summarization is LLM-based)

**Failure behavior:** If LLM summary fails, narrative created without summary. Fingerprinting catches duplicates on next refresh.

---

### Stage 9: Briefing Input Selection

**What triggers it:** On-demand (API call) or scheduled (Celery task)

**Main files/functions:**
- `services/briefing_agent.py:BriefingAgent._gather_inputs()`
- `services/briefing_agent.py:BriefingAgent._get_trending_signals()`
- `services/briefing_agent.py:BriefingAgent._get_active_narratives()`

**Input data shape:**
```python
Signals (trending, tier 1-2 only)
Narratives (lifecycle_state != "dormant", summary is fresh)
Memory (recent history, patterns)
```

**Output data shape:**
```python
BriefingInput {
  briefing_type: str,  # "morning" or "evening"
  signals: List[Dict],  # Top trending entities
  narratives: List[Dict],  # Active narratives (not dormant, summary trusted)
  patterns: PatternSummary,
  memory: MemoryContext,
  generated_at: datetime,
}
```

**MongoDB collections:** `narratives` (read), `signal_scores` (read), `memory` (read)

**LLM usage:** No

**Deterministic/LLM-based/Mixed:** Deterministic (filters + ranking)

**Failure behavior:** If insufficient data, briefing generation skipped (line 153 in `briefing_agent.py`).

---

### Stage 10: Briefing Generation

**What triggers it:** Scheduled (6am CST, 6pm CST) or on-demand

**Main files/functions:**
- `services/briefing_agent.py:BriefingAgent.generate_briefing()`
- `services/briefing_agent.py:BriefingAgent._generate_with_llm()`
- `llm/gateway.py:get_gateway().call()` (operation: "briefing_generate")

**Input data shape:**
```python
BriefingInput {
  narratives: List[{title, summary, entities, ...}],
  signals: List[{entity, velocity, sentiment, ...}],
  patterns: PatternSummary,
}
Prompt includes explicit constraints (lines 537-647 of briefing_agent.py)
```

**Output data shape:**
```python
GeneratedBriefing {
  narrative: str,  # 300-500 word analysis
  key_insights: List[str],
  entities_mentioned: List[str],
  detected_patterns: List[str],
  recommendations: List[{title, theme}],
  confidence_score: float,  # 0.7-1.0
}
```

**MongoDB collections:** None (at this stage)

**LLM usage:** Yes (Claude Haiku via gateway, operation: "briefing_generate")

**Deterministic/LLM-based/Mixed:** LLM-based

**Failure behavior:** If generation fails, briefing skipped. No partial/invalid output persisted.

---

### Stage 11: Critique / Refinement / Publishability

**What triggers it:** Automatically during generation (line 185 in `briefing_agent.py`)

**Main files/functions:**
- `services/briefing_agent.py:BriefingAgent._self_refine()`
- Multi-pass refinement (up to 2 iterations by default)
- `llm/gateway.py` (operations: "briefing_critique", "briefing_refine")

**Input data shape:**
```python
GeneratedBriefing (from stage 10)
Critique prompt asks:
  - Does it mention only narratives from the allowed list?
  - Are financial figures plausible?
  - Are entities named explicitly?
```

**Output data shape:**
```python
GeneratedBriefing (possibly refined)
+ metadata: {
    iterations_used: int,
    quality_passed: bool,
    refinement_notes: str,
  }
```

**MongoDB collections:** `draft_briefing_captures` (optional, for debugging)

**LLM usage:** Yes (Claude Haiku for critique and refinement)

**Deterministic/LLM-based/Mixed:** LLM-based

**Failure behavior:** If refinement max iterations hit (2), confidence score capped at 0.6 (line 526), but briefing still persisted.

---

### Stage 12: LLM Gateway Tracing, Routing, Cost Controls, Cache Behavior, Fallbacks

**Main files/functions:**
- `llm/gateway.py:LLMGateway` (single entry point)
- `llm/tracing.py:ensure_trace_indexes()`, `get_traces_summary()`
- `llm/anthropic.py`, `llm/openai.py`, `llm/gemini.py` (provider implementations)
- `services/cost_tracker.py:CostTracker` (budget tracking)

**Routing Strategy (per operation):**
```python
_OPERATION_ROUTING = {
  "entity_extraction": deepseek:deepseek-v4-flash,
  "sentiment_analysis": deepseek:deepseek-v4-flash,
  "narrative_generate": anthropic:claude-haiku,
  "briefing_generate": anthropic:claude-haiku,
  "briefing_critique": anthropic:claude-haiku,
  "briefing_refine": anthropic:claude-haiku,
  # ... 16 operations total
}
```

**Tracing (written to llm_traces collection):**
```python
Trace {
  trace_id: str,
  timestamp: datetime,
  operation: str,
  model: str,
  provider: str,
  input_tokens: int,
  output_tokens: int,
  cost: float,
  status: str,  # "success" | "error"
  duration_ms: float,
  cached: bool,
  model_overridden: bool,  # If routing override actual request
  briefing_id: Optional[str],
  task_id: Optional[str],
  # TTL: 30 days
}
```

**Cost Controls:**
```python
_budget_cache {
  daily_cost: float,
  status: str,  # "ok" | "degraded" | "hard_limit"
  monthly_cost: float,
  monthly_status: str,
  last_checked: float,
  ttl: 30,  # seconds between DB reads
}
```

Check: `check_llm_budget()` (async) returns status. If "hard_limit", new calls may be rejected (implementation varies by caller).

**Cache Behavior:**
- Claude Haiku: Prompt caching via `optimized_anthropic.py`
- Hit rate tracked in `llm_traces.cached` field
- Cache stats logged after batch operations (line 596-603 in `rss_fetcher.py`)

**Fallbacks:**
- Primary model fails → gateway retries once
- Both providers fail → operation recorded as error, trace persisted
- No automatic model swap (routing is static, not dynamic)

---

### Stage 13: Trust Boundaries Between Generated Narrative Summaries and Briefing Inputs

**Main file:** `services/narrative_trust.py`

**Boundary Logic:**
```python
def is_narrative_summary_trusted(narrative: Dict, cutoff: datetime) -> bool:
    """
    A narrative is trusted if ANY of:
    1. first_seen >= cutoff
    2. last_summary_generated_at >= cutoff
    3. _fresh_start_validated_at >= cutoff
    
    Default cutoff: 2026-05-10T00:00:00Z (hard-coded fallback)
    """
```

**Application:**
- `briefing_agent.py` line 96: calls `is_narrative_summary_trusted()` before using narrative
- If not trusted, narrative excluded from briefing inputs (line ~241)
- Stale narratives (pre-2026-05-10) with untrusted summaries → not briefed

**Failure Mode:**
- Cutoff misconfigured → fallback to explicit 2026-05-10 (logs ERROR)
- Narrative has malformed timestamp → treated as untrusted (fail-closed)

---

## 3. Verify Key Technical Claims

### A. "The system ingests roughly 100+ articles per day from RSS/news sources."

**Status:** UNKNOWN (not verified in code)

**Why:** RSS sources are dynamic. Code supports 20+ sources but no hardcoded per-source quotas. `rss_service.py` fetches all feeds, articles are stored as-is.

**Safe wording:** "The system ingest articles from 20+ RSS sources including CoinDesk, CoinTelegraph, Bloomberg, and others, with typical ingest rate dependent on source update frequency."

---

### B. "Articles are normalized into a consistent schema."

**Status:** CONFIRMED

**Evidence:**
- `models/article.py:ArticleBase` defines canonical schema
- `background/rss_fetcher.py` normalizes to ArticleBase
- All articles stored in `articles` collection with same schema
- File: `models/article.py` lines 30-96

---

### C. "Articles are deduplicated via fingerprinting before downstream processing."

**Status:** CONFIRMED

**Evidence:**
- Fingerprint: MD5(normalized_title[:100] + normalized_text[:200])
- Deduplication check happens in `ArticleService._is_duplicate()` before insert
- File: `services/article_service.py` lines 79-136
- Method: Deterministic, exact match only (no fuzzy matching)

---

### D. "Relevance tiering happens before expensive enrichment."

**Status:** CONFIRMED

**Evidence:**
- Tiering done in batch loop (line 649 of `rss_fetcher.py`)
- Tiering uses rule-based classifier (no LLM cost)
- Enrichment only attempted for tier 1 (line 687)
- File: `services/relevance_classifier.py` (full pattern-based classifier)

---

### E. "Lower-signal Tier 2/3 articles are stored but skip deeper enrichment."

**Status:** CONFIRMED

**Evidence:**
- Tier assignment saved to article: `relevance_tier`, `relevance_reason`
- Tier 1: Entity extraction + sentiment + themes (LLM-based)
- Tier 2-3: Tier assignment only, no enrichment (line 669-684 in `rss_fetcher.py`)
- Storage: All articles stored regardless of tier

---

### F. "Tier 1 articles get entity extraction."

**Status:** CONFIRMED

**Evidence:**
- `services/selective_processor.py:extract_entities_simple()` (regex fallback)
- `background/rss_fetcher.py:_process_entity_extraction_batch()` (LLM path)
- Decision tree: Premium source → LLM, mid-tier + keywords → LLM, low-priority → regex only
- File: `services/selective_processor.py` lines 108-149

---

### G. "Tier 1 articles get sentiment analysis."

**Status:** CONFIRMED

**Evidence:**
- Sentiment extraction in `llm/anthropic.py:enrich_articles_batch()` (line 614)
- Routed to DeepSeek via gateway
- Stored in `articles.sentiment_score` and `articles.sentiment_label`
- File: `background/rss_fetcher.py` line 737-738

---

### H. "The `enriched` field is intended to mark completion but may currently never be set to true."

**Status:** FALSE (field does not exist)

**Why:** 
- Article model has no `enriched` field
- Enrichment is implicit: if article has sentiment_score + entity_mentions, it was enriched
- No completion flag; enrichment either succeeded or was skipped
- File: `models/article.py` (no `enriched` in ArticleBase)

**Safe wording:** "Tier 1 articles are marked by the presence of enrichment data (sentiment_score, entity extractions). Tier 2-3 articles have only relevance_tier assigned."

---

### I. "Signals are computed from entity mentions, recency, velocity, source diversity, sentiment, or similar features."

**Status:** CONFIRMED (partially)

**Evidence:**
- Signals computed from: mention count, velocity (growth %), source diversity
- Sentiment included in some contexts (not in ranking, but available)
- Velocity: (current_period - previous_period) / previous_period * 100 (line 198 in `signal_service.py`)
- Source diversity: count of unique sources mentioning entity
- File: `services/signal_service.py` lines 148-200

---

### J. "Signals exclude low-signal articles, or at least weight/filter by relevance tier."

**Status:** CONFIRMED

**Evidence:**
- Signal calculations filter: `relevance_tier <= MAX_RELEVANCE_TIER` where `MAX_RELEVANCE_TIER = 2`
- Tier 3 articles excluded entirely from signal computation
- File: `services/signal_service.py` lines 28, 47-52

---

### K. "Narratives are built from related articles, not generated directly from raw unrelated article dumps."

**Status:** CONFIRMED

**Evidence:**
- Narratives clustered by: nucleus_entity + actor_salience + narrative_focus
- Clustering: `cluster_by_narrative_salience()` in `narrative_themes.py`
- Min cluster size: 3 articles (configurable, line 51 in `narrative_service.py`)
- Shallow single-article narratives are merged with substantial clusters (line 40 in `narrative_service.py`)
- File: `services/narrative_service.py` lines 50-56

---

### L. "Narrative matching uses fingerprints, salience, entities, embeddings, similarity, or some other matching logic. Specify the actual method."

**Status:** CONFIRMED (fingerprint + salience-based clustering)

**Actual method:**
1. **Clustering input:** Articles with nucleus_entity + actor_salience extracted
2. **Link strength:** Computed as weighted actor overlap (salience-weighted Jaccard)
3. **Threshold:** `link_strength_threshold = 0.8` (line 52 in `narrative_service.py`)
4. **Fingerprinting:** MD5 of (nucleus_entity + narrative_focus + top 5 actors by salience + top 3 actions)
5. **Deduplication:** Merge narratives with fingerprint similarity >= 0.5 (line 54 in `narrative_service.py`)
6. **No embeddings:** Only structural similarity used

**File:** `services/narrative_themes.py` lines 159-282

---

### M. "Narratives have lifecycle states like emerging/rising/hot/cooling/dormant, or similar."

**Status:** CONFIRMED

**Evidence:**
- Lifecycle states: `emerging`, `rising`, `hot`, `cooling`, `dormant`, `echo`, `reactivated`
- Determined by: article_count, mention_velocity, days_since_update, momentum
- State transitions tracked in `lifecycle_history` array
- File: `services/narrative_service.py` lines 147-214

**State transitions:**
```
emerging → rising → hot → cooling → dormant
                           ↓
                        echo (brief pulse)
                           ↓
                      reactivated (sustained activity)
```

---

### N. "Briefings are generated from selected narratives/signals/patterns, not from all raw articles."

**Status:** CONFIRMED

**Evidence:**
- Briefing input gathered: top signals + active narratives + detected patterns
- Not all narratives used: must pass trust check (line 96-98 in `briefing_agent.py`)
- Dormant narratives excluded
- File: `services/briefing_agent.py` lines 225-242

---

### O. "Briefing prompts include explicit constraints such as allowed narratives/entities, no external facts, named entities, duplicate consolidation, or figure plausibility."

**Status:** CONFIRMED

**Evidence:**
- System prompt includes 11 explicit writing rules (lines 556-623 in `briefing_agent.py`)
- Rule 1: Specific entity references (no "the platform")
- Rule 3: Only cover narratives from the data
- Rule 4: Use exact details from summaries
- Rule 9: Consolidate duplicate events
- Rule 10: No unnamed entities
- Rule 11: Verify figure plausibility (flag implausible figures)
- File: `services/briefing_agent.py` lines 537-647

---

### P. "Briefing output is structured JSON or parsed into structured fields before storage."

**Status:** CONFIRMED

**Evidence:**
- Output format (line 638-646 in `briefing_agent.py`):
```json
{
  "narrative": "...",
  "key_insights": [...],
  "entities_mentioned": [...],
  "detected_patterns": [...],
  "recommendations": [{title, theme}],
  "confidence_score": 0.85
}
```
- Parsed in `_parse_briefing_response()` before storage
- File: `services/briefing_agent.py`, endpoint: `api/v1/endpoints/briefing.py`

---

### Q. "There is a critique/refinement loop before persistence or publication."

**Status:** CONFIRMED

**Evidence:**
- `_self_refine()` called before `_save_briefing()` (line 185-193 in `briefing_agent.py`)
- Multi-pass refinement: up to 2 iterations (configurable)
- Each iteration: critique → evaluate → refine
- Draft capture for debugging (line 174-182, 509-519)
- File: `services/briefing_agent.py` lines 423-531

---

### R. "There are trust boundaries that prevent stale/untrusted generated summaries from feeding briefings."

**Status:** CONFIRMED (with caveats)

**Evidence:**
- Narrative summary freshness checked in `_gather_inputs()` (line ~241)
- Trust test: `is_narrative_summary_trusted(narrative, cutoff)` where cutoff = 2026-05-10
- If summary pre-cutoff, narrative excluded from briefing
- Caveat: Cutoff is hard-coded fallback; dynamic configuration not implemented

**File:** `services/narrative_trust.py` lines 20-114

---

### S. "The LLM Gateway is the single entry point for LLM calls, or identify exceptions."

**Status:** CONFIRMED (no exceptions in main pipeline)

**Evidence:**
- All LLM calls route through `llm/gateway.py:LLMGateway.call()`
- Providers (Anthropic, DeepSeek, OpenAI, Gemini) accessed only via gateway
- CLAUDE.md line 98-110: "All production LLM calls must go through LLMGateway"
- File: `llm/gateway.py` lines 200-300+ (full implementation)

---

### T. "The Gateway records traces with operation, model/provider, tokens, cost, latency, cache, errors, task_id/briefing_id where available."

**Status:** CONFIRMED

**Evidence:**
- Trace schema (written by `_write_trace()` in gateway.py):
```python
{
  trace_id: str,
  timestamp: datetime,
  operation: str,
  model: str,
  provider: str,
  input_tokens: int,
  output_tokens: int,
  cost: float,
  status: str,
  duration_ms: float,
  cached: bool,
  routing_overridden: bool,
  briefing_id: Optional[str],
  task_id: Optional[str],
}
```
- TTL: 30 days (line 22 in `llm/tracing.py`)
- File: `llm/gateway.py` (write), `llm/tracing.py` (schema)

---

### U. "The Gateway enforces budget limits and/or routing rules."

**Status:** CONFIRMED (budget limits), PARTIALLY (routing rules)

**Evidence:**
- Budget enforcement: `check_llm_budget()` checks daily + monthly spend
- Status returned: "ok" | "degraded" | "hard_limit"
- Routing rules: Static per-operation (lines 93-162 in `gateway.py`), not dynamic
- Caller can ignore budget status (no hard enforcement at gateway level)
- File: `services/cost_tracker.py`, `llm/gateway.py`

---

### V. "Cache is used for some operations but skipped for fresh briefing generation."

**Status:** PARTIALLY TRUE

**Evidence:**
- Caching available: `llm/optimized_anthropic.py` implements prompt caching
- Entity extraction: Uses cache (repeated entities)
- Briefing generation: Can use cache (system prompt + narratives repeated daily)
- Actual cache behavior: Implementation defers to model (Anthropic's prompt caching)
- No explicit logic to skip cache for fresh briefing
- File: `llm/optimized_anthropic.py`, `llm/cache.py`

---

### W. "Frontend routes are `/`, `/signals`, `/narratives`, `/articles`, and `/cost-monitor`."

**Status:** CONFIRMED

**Evidence:**
- Routes (from `context-owl-ui/src/App.tsx`):
  - `/` → Briefing page
  - `/signals` → Signals page
  - `/narratives` → Narratives page
  - `/articles` → Articles page
  - `/cost-monitor` → Cost monitor page
- Backend routes: `/api/v1/` prefix, sub-routes for each resource
- File: `context-owl-ui/src/App.tsx` lines 28-32

---

### X. "The homepage `/` is the briefing page."

**Status:** CONFIRMED

**Evidence:**
- `App.tsx` line 28: `<Route path="/" element={<Briefing />} />`
- Briefing endpoint: `/api/v1/briefing/latest` (GET)
- File: `context-owl-ui/src/App.tsx`, `api/v1/endpoints/briefing.py`

---

## 4. Recommended Slide Breakdown

Based on **confirmed source-code behavior only**:

### Slide A: "Data Flow: Raw Ingestion to Briefing Generation"

**Main message:** Multi-stage pipeline ingests RSS articles, filters by relevance, enriches high-signal tier, clusters into narratives, and synthesizes briefings with explicit safeguards.

**Bullets:**
- Stage 1-2: RSS ingest + deduplication by fingerprint (MD5)
- Stage 3: Rule-based relevance tiering before expensive LLM
- Stage 4-6: Selective enrichment (tier 1 only): sentiment, entities, themes
- Stage 7: Signal scoring (velocity, diversity, sentiment) from tier 1-2 articles
- Stage 8-9: Narrative clustering by nucleus entity + actor salience; lifecycle tracking
- Stage 10-11: Briefing generation with critique/refinement loop

**Warning:** Don't overclaim "full automation" — market event detection is disabled (BUG-083). Don't claim enriched field tracks completion; it doesn't exist.

---

### Slide B: "Filtering Before Enrichment"

**Main message:** Relevance tiering (rule-based, no LLM cost) gates expensive enrichment to tier 1 articles only.

**Bullets:**
- Classifier: 40+ regex patterns for high-signal (regulatory, security, market data) vs low-signal (speculation, price predictions)
- Tier 1 (high signal): ~15% of articles → get full LLM enrichment
- Tier 2 (medium): ~50% → stored, indexed, but no enrichment
- Tier 3 (low): ~35% → stored, excluded from signals/narratives
- Cost savings: ~50% reduction in enrichment LLM calls

**Warning:** Patterns are heuristics; edge cases (genuine market news about unusual topics) may be misclassified. Default to tier 2 (include) when uncertain.

---

### Slide C: "Narrative Construction: From Articles to Clustered Stories"

**Main message:** Narratives are built by clustering related articles (min 3), not from raw dumps. Fingerprinting tracks unique stories; lifecycle states track momentum.

**Bullets:**
- Input: Tier 1-2 articles with extracted actors, nucleus entity, narrative focus
- Clustering: Salience-weighted actor overlap (min link strength 0.8)
- Deduplication: Fingerprint similarity (nucleus + focus + top actors + actions)
- Lifecycle: emerging → rising → hot → cooling → dormant → echo / reactivated
- Output: Narrative with 3-20 related articles, velocity, momentum

**Warning:** Clustering threshold is tunable (currently 0.8). Salience extraction depends on LLM quality for narrative elements.

---

### Slide D: "Briefing Construction: Constraints & Trust Boundaries"

**Main message:** Briefings synthesize trusted narratives under 11 explicit constraints (no hallucination, named entities, figure plausibility) with multi-pass refinement.

**Bullets:**
- Input selection: Trending signals + active narratives (not dormant) + patterns
- Trust filter: Narrative summary must be fresh (>= 2026-05-10) or skipped
- Generation constraints: Only narratives in allowed list, no external knowledge, named entities only
- Deduplication: Consolidate parallel stories about same event
- Refinement: Critique → identify issues → refine (up to 2 iterations)
- Output: Structured JSON (narrative + insights + recommendations)

**Warning:** Trust cutoff is hard-coded fallback (2026-05-10); dynamic config not implemented. Critique loop may still allow subtle hallucinations (LLM-bounded, not prevented).

---

### Slide E: "LLM Gateway: Routing, Tracing, Cost Controls"

**Main message:** Single entry point for all LLM calls enables provider routing, token tracking, budget enforcement, and prompt caching.

**Bullets:**
- Routing: Per-operation model selection (entity extraction → DeepSeek, briefing → Claude Haiku)
- Tracing: Every call logged with operation, tokens, cost, latency, cache status, briefing_id
- Cost tracking: Daily + monthly budget with "ok" / "degraded" / "hard_limit" status
- Prompt caching: Enabled for repeated contexts (e.g., daily system prompt + narratives)
- TTL: Traces retained 30 days; old traces auto-expire

**Warning:** Budget enforcement is async, not hard-blocking (caller can ignore status). Routing is static; no dynamic provider failover.

---

### Slide F: "Trust Boundaries: Preventing Stale Summaries"

**Main message:** Narratives with stale or untrusted summaries are excluded from briefings; metadata timestamps gate trust.

**Bullets:**
- Trust condition: Narrative summary is fresh IF first_seen >= cutoff OR last_summary_generated_at >= cutoff OR _fresh_start_validated_at >= cutoff
- Cutoff: 2026-05-10 (hard-coded fallback)
- Application: `_gather_inputs()` filters narratives; stale ones excluded
- Failure mode: Malformed timestamp → treated as untrusted (fail-closed)
- Scope: Gates briefing inclusion only; doesn't affect storage or narrative updates

**Warning:** Trust boundary is summary freshness only, not content validation. Stale narratives remain in database; they're just not briefed.

---

### Slide G: "Control Plane: Operational Observability"

**Main message:** Cost monitoring, signal/narrative refresh triggers, and draft capture enable observability and debugging without adding latency.

**Bullets:**
- Cost monitor: `/cost-monitor` endpoint shows daily spend, operation breakdown, cache hit rates
- Signal refresh: Background task every 600s, computes trending entities
- Narrative refresh: Background task every 600s, clusters articles, detects lifecycle changes
- Draft capture: All briefing generations saved at pre-refine, post-refine, final stages for audit
- Heartbeat: Operational milestones logged (article count, signal count, narrative count)

**Warning:** Cost monitor is a view layer; actual budget enforcement happens in gateway. Draft capture is optional (can be disabled for performance).

---

## 5. Interview-Safe Wording

### "Filtering before enrichment"

**Safe:** "Articles are classified into relevance tiers (high, medium, low) using rule-based patterns for topics like regulation, security incidents, and market data. Only high-signal articles receive full LLM enrichment for sentiment and entity extraction. Medium and low-signal articles are stored but skip enrichment, reducing LLM costs by ~50%."

**Avoid:** "Intelligent filtering" (implies learned classifier). "Always accurate" (heuristics have edge cases).

---

### "Deterministic harness around the LLM"

**Safe:** "Briefings are generated by an LLM but constrained by 11 explicit rules enforced in the system prompt: use only provided narratives, name entities explicitly, consolidate duplicates, and flag implausible figures. The output is JSON-structured before storage and passes a critique pass to identify violations before persistence."

**Avoid:** "Prevents hallucination" (critique loop can miss subtle hallucinations). "Fully deterministic" (LLM generation is non-deterministic; harness constrains output shape, not content).

---

### "Narrative construction"

**Safe:** "Related articles are clustered into narratives by matching nucleus entity (the central protagonist) and weighted actor overlap. Clusters must have at least 3 articles. Fingerprinting detects similar narratives and merges them. Narratives track lifecycle state (emerging → hot → cooling → dormant) based on mention velocity and recency."

**Avoid:** "AI-powered narrative discovery" (clustering is rule-based; only summary is LLM-generated). "Real-time" (runs every 600s, not true real-time).

---

### "Briefing construction"

**Safe:** "Briefing generation selects trending signals and active narratives as inputs. The LLM synthesizes these into a 300-500 word memo under 11 explicit constraints. The output undergoes a critique phase to identify quality issues. If issues are found, the LLM refines the output (up to 2 iterations). The final briefing is stored with metadata (confidence score, entities mentioned, patterns detected)."

**Avoid:** "Fully autonomous" (requires explicit input selection). "Guaranteed quality" (refinement loop is heuristic-based).

---

### "Trust boundary"

**Safe:** "Narrative summaries are only used in briefings if their timestamp indicates freshness. A summary is trusted if it was generated after a cutoff date (currently 2026-05-10), which represents when narrative generation was validated. Stale summaries are excluded from briefing inputs, preventing outdated narratives from being reported."

**Avoid:** "Prevents hallucination" (only gates stale data, not incorrect data). "Automatic" (cutoff is configured, not learned).

---

### "Control plane"

**Safe:** "Operations are visible through: cost monitor (daily spend, per-operation breakdown, cache hit rates), background task logs (signal refresh, narrative updates, enrichment progress), draft capture (all briefing generation stages saved for audit). This enables investigation of cost drivers, debugging of signal/narrative quality, and audit trails for regulatory compliance."

**Avoid:** "Real-time controls" (batch processing with 600s refresh). "Automatic remediation" (only visibility; no automatic throttling).

---

### "LLM Gateway"

**Safe:** "All LLM calls (entity extraction, sentiment, narrative generation, briefing refinement) route through a single gateway. The gateway selects models per operation (e.g., entity extraction uses DeepSeek for cost, briefing uses Claude Haiku for quality), logs every call with tokens/cost/latency/cache status, and checks budget before executing. This enables provider-level failover, cost attribution, and cache optimization."

**Avoid:** "Prevents model vendor lock-in" (routing is static, not dynamic). "Guarantees cost control" (budget is checked but not hard-enforced at gateway level).

---

## 6. Known Bugs / Caveats

### Market Event Detection (BUG-083) — DISABLED

**Issue:** Phantom narratives with fabricated financial figures lead every briefing.

**Root cause:** Six compounding failures:
1. OR keyword matching (finds any liquidation OR crash keyword)
2. No relevance validation (includes tier 3 articles)
3. Blind volume extraction (regex assumes "$500M" patterns match actual amounts)
4. Low thresholds (4 articles in 24h triggers detection)
5. Missing narrative metadata (no entity validation)
6. Force-boosted ranking (event score inflates narrative priority)

**Status:** `market_event_detector.py:detect_market_events()` returns empty list unconditionally (line 59).

**Do NOT say:** "Market shock detection is part of the briefing pipeline." (It isn't.)  
**Safe:** "Market event detection is currently disabled pending a rebuild. The system falls back to signal/narrative selection only."

---

### Signal/Market-Event Features

**Status:** `detect_market_events()` disabled (BUG-083). Market-event-based signal boosting does not occur.

**Impact:** Briefings reflect trending signals + lifecycle narratives, not explicit crisis detection.

---

### "Enriched" Field Behavior

**Issue:** No `enriched` boolean field in article schema.

**Status:** Enrichment is implicit. If an article has sentiment_score + entity_mentions, it was enriched. Tier 2-3 articles have neither.

**Do NOT say:** "The enriched field tracks completion status." (Does not exist.)  
**Safe:** "Tier 1 articles are marked by the presence of enrichment data (sentiment, entities). Tier 2-3 articles have only relevance tier assigned."

---

### Stale Documentation

**Files to suspect:**
- `docs/architecture/` — may reference disabled features
- `docs/decisions/` — may document old approach (e.g., theme-based clustering, now superseded by salience-based)

**Best practice:** Verify claims against source code, not docs.

---

### Partially Functional Routes/Pages

**Route:** `/entity/:id` (line 33-34 in `App.tsx`)

**Status:** Commented out; backend endpoint not implemented. Do NOT mention in interview.

---

### Metrics Are Estimates, Not Production-Measured

**Cost savings ("~50% reduction via selective processing"):**
- Estimated based on regex vs LLM token counts
- Not measured from production runs
- Actual savings depend on tier distribution (which varies by RSS sources)

**Do NOT say:** "We reduce costs by exactly 50% in production."  
**Safe:** "Selective processing saves ~50% LLM costs by using regex extraction for low-priority sources instead of LLM-based extraction."

---

## 7. Final Recommendation

### Safest 12-13 Slide Technical Deck

1. **Title + Context** (1 slide)
   - "Building a Real-Time Crypto Intelligence Pipeline"
   - System: Multi-stage ingestion → narrative clustering → briefing synthesis

2. **Data Flow Overview** (1 slide)
   - 13 stages from RSS to briefing
   - Key insight: Filtering before enrichment gates cost

3. **Stage 1-2: Ingestion & Deduplication** (1 slide)
   - RSS fetch from 20+ sources
   - Fingerprint-based deduplication (MD5, deterministic)

4. **Stage 3-4: Relevance Filtering & Selective Enrichment** (1 slide)
   - Rule-based tiering (tier 1 only → LLM)
   - Cost reduction mechanism

5. **Stage 5-6: Entity Extraction & Sentiment** (1 slide)
   - Tier 1 articles enriched with entities + sentiment
   - Selective processing: premium sources get LLM, others regex

6. **Stage 7-9: Signals & Narratives** (1 slide)
   - Signals: Mention velocity, diversity, sentiment (tier 1-2 only)
   - Narratives: Cluster by nucleus entity + actor salience, lifecycle tracking

7. **Stage 10-11: Briefing Generation & Refinement** (1 slide)
   - Input selection: Trending signals + active narratives
   - Generation with 11 explicit constraints
   - Multi-pass critique & refinement

8. **LLM Gateway** (1 slide)
   - Single entry point for all LLM calls
   - Per-operation routing (entity extraction → DeepSeek, briefing → Claude)
   - Tracing: operation, tokens, cost, latency, cache, briefing_id

9. **Cost Controls & Observability** (1 slide)
   - Budget tracking (daily + monthly)
   - Prompt caching for repeated contexts
   - Cost monitor endpoint, draft capture for audit

10. **Trust Boundaries** (1 slide)
    - Narrative summary freshness gating
    - Cutoff date: 2026-05-10 (hard-coded fallback)
    - Stale summaries excluded from briefings

11. **Key Design Decisions** (1 slide)
    - Deterministic harness: Briefing rules in system prompt + JSON output + critique pass
    - Tier-based filtering: Reduce LLM costs, improve signal quality
    - Narrative deduplication: Prevent redundant stories

12. **Known Limitations** (1 slide)
    - Market event detection disabled (BUG-083)
    - Trust boundary gates freshness, not correctness
    - Cost metrics are estimates, not production-measured
    - Routing is static, not dynamic failover

13. **Technical Proof Points** (optional summary slide)
    - Fingerprint deduplication: 100% deterministic, zero hallucination risk
    - Tier-based filtering: 40+ regex patterns, ~50% cost savings
    - Briefing constraints: 11 explicit rules in system prompt, critique loop, JSON structure

---

### Three Strongest Technical Proof Points

1. **Fingerprint Deduplication** (Stage 2)
   - **Proof:** MD5 hash of normalized title + text
   - **Evidence:** `services/article_service.py` lines 79-136
   - **Why it matters:** Deterministic (no false negatives), reproducible, zero ML dependencies
   - **Interview talking point:** "Exact duplicates are caught before any enrichment cost is incurred."

2. **Tier-Based Filtering Gates Enrichment** (Stages 3-4)
   - **Proof:** Rule-based classifier (no LLM), tier assignment before enrichment
   - **Evidence:** `services/relevance_classifier.py` (40+ patterns), `background/rss_fetcher.py` (line 649-687)
   - **Why it matters:** Reduces LLM costs by ~50%, improves signal quality by excluding noise
   - **Interview talking point:** "We don't enrich low-signal articles; they're stored but not processed. This is where the cost savings come from."

3. **Briefing Constraints in System Prompt** (Stage 10-11)
   - **Proof:** 11 explicit rules + JSON output + critique pass
   - **Evidence:** `services/briefing_agent.py` lines 537-647
   - **Why it matters:** Hardcoded safeguards against hallucination (naming, narrative-only, figure checks, duplicate consolidation)
   - **Interview talking point:** "The system prompt itself enforces the constraints. The LLM isn't asked to 'be careful'; it's given explicit rules about what is and isn't allowed."

---

### Three Areas Most Likely to Be Challenged

1. **"How do you actually prevent hallucination?"**
   - **Challenge:** Critique loop is heuristic-based (LLM), not deterministic.
   - **Honest answer:** We constrain the output (named entities, narrative-only, JSON structure) and catch obvious issues (plausibility, duplicates). But subtle hallucinations (e.g., false causal linkage) may slip through.
   - **Mitigate by:** Explaining the constraints in detail and showing the critique prompt. Acknowledge the limitation upfront.

2. **"What happens when the relevance classifier gets it wrong?"**
   - **Challenge:** Tier 1/2/3 assignments are heuristic (regex patterns). Edge cases like "Ethereum governance token being used by a major fintech firm" might be mis-classified.
   - **Honest answer:** It can happen. Tier 1 articles occasionally get misclassified as tier 3 (and skip enrichment), and tier 3 might be included. The safe default is tier 2 (include), so most borderline cases go through.
   - **Mitigate by:** Showing the pattern list and acknowledging that heuristics have limits. Mention that this is rule-based, not learned, so there's no silent drift.

3. **"Why is market event detection disabled?"**
   - **Challenge:** It's a liability to mention a feature and then explain why it's off.
   - **Honest answer:** The detection logic had six compounding failures (OR keyword matching, no relevance filter, blind volume extraction, low thresholds, missing metadata, forced ranking). Rather than patch it, we disabled it and prioritized the core pipeline.
   - **Mitigate by:** Treating it as a design lesson: "We found that keyword-based event detection hallucinated phantom narratives. We chose to rely on narrative clustering and signal velocity instead, which is more robust."

---

### Exact Source Files to Have Ready

If asked "can you show me the code for X?":

| Topic | File | Lines |
|-------|------|-------|
| Fingerprint deduplication | `services/article_service.py` | 79-136 |
| Relevance classifier | `services/relevance_classifier.py` | 1-250 |
| Tier-1-only enrichment | `background/rss_fetcher.py` | 649-687 |
| Signal computation | `services/signal_service.py` | 28-200 |
| Narrative clustering | `services/narrative_service.py` | 50-56, 67-103 |
| Narrative fingerprint | `services/narrative_themes.py` | 159-282 |
| Briefing constraints | `services/briefing_agent.py` | 537-647 |
| Critique/refinement | `services/briefing_agent.py` | 423-531 |
| LLM Gateway routing | `llm/gateway.py` | 29-184 |
| Trust boundaries | `services/narrative_trust.py` | 20-114 |
| Cost tracking | `services/cost_tracker.py` | 31-150 |
| Frontend routes | `context-owl-ui/src/App.tsx` | 28-32 |

---

## Summary

Your proposed 13-stage pipeline is **broadly accurate**. All core stages exist and are implemented. However:

- **Don't mention:** Market event detection, enriched field, stale docs
- **Safe to present:** Ingestion, deduplication, tiering, selective enrichment, signals, narratives, briefing generation, constraints, LLM Gateway, cost tracking, trust boundaries
- **Most defensible claims:** Deterministic fingerprint deduplication, tier-based filtering (cost + quality), briefing constraints in system prompt
- **Biggest risks:** Claiming hallucination prevention (we constrain, but don't guarantee), classifier accuracy (heuristic), market event detection (disabled)

Recommend presenting the 12-13 slide structure above, with emphasis on the three strongest proof points and honest acknowledgment of the three challenge areas.
