# Data Flow: From Articles to Signals to Narratives to Briefings

A complete walk-through of how data moves through your system, from article ingestion through briefing generation. Each section maps to code, explains transformations, and shows data structures.

---

## 1. ARTICLE INGESTION PIPELINE

### 1.1 RSS Fetch → Normalize → Deduplicate

```
External RSS Feeds (CoinTelegraph, CoinDesk, Decrypt, The Block)
         ↓
    RSSService.fetch_all()
         ↓
    [Raw feed entries]
         ↓
    normalize_article() — Map to Article schema
         ↓
    [Normalized Article objects]
         ↓
    create_fingerprint() — MD5 hash of title + first 500 chars
         ↓
    check_duplicate() — Query MongoDB for existing fingerprint
         ↓
    ├─→ [DUPLICATE] — Skip
    └─→ [NEW] — Insert to articles collection
         ↓
    [articles collection]
```

**File References:**
- **Fetching:** `background/rss_fetcher.py`
- **Normalization:** `core/news_collector.py:30-120` (Article schema, field mapping)
- **Fingerprinting:** `services/article_service.py:200-280` (MD5 hash, duplicate detection)

**Key Data Structures:**

```python
# Input: feedparser entry dict
{
    "title": "Bitcoin Hits New High",
    "summary": "BTC surged 15% in 24 hours...",
    "link": "https://...",
    "published": "2026-05-15T10:30:00Z",
    "source": {"title": "CoinTelegraph"},
    "author": "Jane Smith"
}

# Output: Article document (MongoDB)
{
    "_id": ObjectId("..."),
    "title": "Bitcoin Hits New High",
    "content": "BTC surged 15% in 24 hours...",
    "source": "CoinTelegraph",
    "source_url": "https://...",
    "url": "https://...",
    "published_at": ISODate("2026-05-15T10:30:00Z"),
    "fetched_at": ISODate("2026-05-15T11:45:00Z"),
    "author": "Jane Smith",
    "fingerprint": "a3f2c1d9e8b4f7a2c5e6d9b1a4c7f0e3",  # MD5 hash
    "relevance_tier": None,  # Set in next step
    "enriched": False,       # Set to true after entity + sentiment complete
    "entities": [],          # Filled by entity extraction
    "sentiment": None        # Filled by sentiment analysis
}
```

**Validation rules (articles rejected if):**
- Title length < 10 or > 500 chars
- Content length < 100 chars
- published_at > now (future-dated)
- published_at < 30 days ago (on first fetch only)

---

### 1.2 Tier Classification (BEFORE Enrichment)

**Critical optimization:** Articles are classified by relevance **before** any LLM enrichment. Only Tier 1 articles are enriched (entity extraction + sentiment), reducing LLM costs by ~98%.

**File:** `tasks/process_article.py` (Tier 1-only task queuing), `services/relevance_classifier.py`

```
[Normalized Article]
         ↓
    classify_relevance_tier()  — LLM call to assess importance
         ↓
    {
        "relevance_tier": 1, 2, or 3,
        "relevance_reason": "High signal: mentions SEC regulations",
        "relevance_score": 0.92
    }
         ↓
    Update articles collection with tier info
         ↓
    IF tier == 1:
        Queue entity_extraction_task
        Queue sentiment_analysis_task
    ELSE:
        Mark enriched: false (skip enrichment)
```

**Tier definitions:**
- **Tier 1** (High Signal): Direct market impact, regulatory announcements, major entity news
  - Example: "SEC Approves Bitcoin ETF" → 70 articles/day enriched
- **Tier 2** (Medium Signal): Commentary, analysis, secondary news
  - Example: "Markets React to Fed Decision" → Included in signal calculations, skipped in enrichment
- **Tier 3** (Low Signal): Promotional, tangential, low relevance
  - Example: "Crypto Influencer's New Podcast" → Excluded from signals and narratives

**Cost baseline per tier:**
- Tier 1 enrichment: ~2-3 LLM calls per article (entity + sentiment)
- Tier 2-3: 0 LLM calls per article

---

### 1.3 Entity Extraction (Tier 1 Only)

**File:** `tasks/process_article.py:extract_entities_task()`, `services/entity_service.py`

```
[Tier 1 Article]
         ↓
    Extract entities using LLM
         ↓
    LLM Prompt:
    "Extract key entities from this article:
     {article.content}
     Return JSON: {"entities": [{"name": "Coinbase", "type": "company", "relevance": 0.9}, ...]}"
         ↓
    Parse JSON response
         ↓
    For each entity:
        Create entity_mention document:
        {
            "_id": ObjectId("..."),
            "entity": "Coinbase",
            "type": "company",  # company | crypto | person | concept
            "article_id": ObjectId("article._id"),
            "created_at": ISODate("..."),
            "sentiment": article.sentiment,  # bullish | bearish | neutral
            "is_primary": True  # True if extracted as primary entity
        }
         ↓
    Insert to entity_mentions collection
         ↓
    Update articles collection:
        articles.update_one(
            {"_id": article_id},
            {"$set": {"entities": ["Coinbase", "Bitcoin", ...], "enriched": true}}
        )
```

**Entity types:**
- `company`: Exchanges (Coinbase, Kraken), custodians (BlackRock), platforms
- `crypto`: Cryptocurrencies (Bitcoin, Ethereum, Solana)
- `person`: Key figures (Vitalik Buterin, Elon Musk)
- `concept`: Trends, protocols, regulatory terms

**LLM routing:** DeepSeek (cost-optimized for structured extraction)

**Latency per article:** 2-5 seconds

---

### 1.4 Sentiment Analysis (Tier 1 Only)

**File:** `core/sentiment_analyzer.py:30-80`, `tasks/process_article.py:analyze_sentiment_task()`

```
[Tier 1 Article]
         ↓
    Analyze sentiment using LLM
         ↓
    LLM Prompt:
    "Classify the sentiment of this crypto article:
     {article.title} {article.content[:500]}
     
     Return JSON: {"sentiment": "bullish|bearish|neutral", "confidence": 0.85}"
         ↓
    Parse JSON response
         ↓
    Update articles collection:
        articles.update_one(
            {"_id": article_id},
            {"$set": {"sentiment": "bullish"}}  # bullish | bearish | neutral
        )
         ↓
    Update entity_mentions with article's sentiment:
        entity_mentions.update_many(
            {"article_id": article_id},
            {"$set": {"sentiment": "bullish"}}
        )
```

**Sentiment values:**
- `bullish`: Positive news, price surge, institutional adoption
- `bearish`: Regulatory crackdown, security breach, market crash
- `neutral`: Analysis, commentary, no clear sentiment

**LLM routing:** Claude Haiku 4.5 (cost-optimized)

**Latency per article:** 1-2 seconds

---

## 2. SIGNAL DETECTION & SCORING

### 2.1 Trending Signal Computation

**File:** `services/signal_service.py:compute_trending_signals()`

```
Input: timeframe="24h", limit=20, min_score=0.0

Step 1: Get all entities from entity_mentions (last 24h)
         ↓
    SELECT DISTINCT entity FROM entity_mentions
    WHERE created_at >= now() - 24h
    AND article_id IN (
        SELECT _id FROM articles
        WHERE relevance_tier <= 2  -- Tier 1/2 only; Tier 3 excluded
    )

Step 2: For each entity, calculate metrics
         ↓
    For entity = "Bitcoin":
        • Count mentions in current 24h window
        • Count mentions in previous 24h window
        • Calculate velocity: (current - previous) / previous * 100
        ↓
        Example:
        - Previous 24h: 50 mentions
        - Current 24h: 75 mentions
        - Velocity: (75 - 50) / 50 * 100 = 50% growth
         ↓
    • Count unique sources (articles with different source names)
    • Calculate average sentiment (sum of bullish/bearish/neutral, weighted)
    • Calculate sentiment divergence (disagreement between sources)
         ↓
    Result per entity:
    {
        "entity": "Bitcoin",
        "metrics": {
            "mentions_24h": 75,
            "mentions_prev_24h": 50,
            "velocity_24h": 50.0,        # Growth rate percentage
            "unique_sources": 3,         # Count of distinct sources
            "sentiment_avg": 0.65,       # Weighted average (-1 to 1)
            "sentiment_divergence": 0.2, # How split is sentiment
            "score_24h": 8.3             # Composite score (0-10)
        }
    }

Step 3: Sort by score, return top 20
         ↓
    [20 signals sorted by score]

Step 4: Cache in Redis (15min TTL)
         ↓
    Redis key: signals:trending:24h
    Value: [20 signals]
```

**Signal Score Formula:**
```
score = (velocity_weight * velocity) + 
        (source_weight * unique_sources) + 
        (sentiment_weight * abs(sentiment_avg)) + 
        (divergence_penalty * sentiment_divergence)
```

**Key constraint:** Only `relevance_tier <= 2` articles included. Tier 3 (low signal) is excluded to reduce noise.

**Latency:** ~500ms for top 20 entities (pre-computed, cached)

---

### 2.2 Signal Data Structure

```python
# Result document (in-memory, not persisted)
{
    "entity": "Bitcoin",
    "type": "crypto",  # inferred from entity type
    "metrics": {
        "mentions_24h": 75,
        "mentions_prev_24h": 50,
        "velocity_24h": 50.0,      # Percentage change
        "unique_sources": 3,
        "sentiment_avg": 0.65,      # -1.0 to 1.0
        "sentiment_divergence": 0.2,
        "score_24h": 8.3
    },
    "trend": "rising",  # rising | falling | stable
    "articles_sample": [
        {
            "title": "Bitcoin Surges Past $100K",
            "source": "CoinTelegraph",
            "published_at": "2026-05-15T10:30:00Z",
            "sentiment": "bullish"
        }
    ]
}
```

---

## 3. NARRATIVE CLUSTERING & CREATION

### 3.1 Narrative Detection Pipeline

**File:** `services/narrative_service.py`, `services/narrative_themes.py`

The system uses **salience-based clustering** to group related articles into narratives:

```
[Enriched Articles (Tier 1-2 only)]
         ↓
Step 1: Extract narrative elements from each article
         ↓
    For each article, call LLM to extract:
    {
        "nucleus_entity": "Binance",     # Main entity (top 1 from entities)
        "actors": [                      # Other important entities
            {"name": "SEC", "salience": 5.2},
            {"name": "Coinbase", "salience": 3.8}
        ],
        "tensions": [                    # Conflict/resolution themes
            {"name": "regulatory_pressure", "intensity": 0.8},
            {"name": "market_expansion", "intensity": 0.6}
        ]
    }
         ↓
    Store in MongoDB collection: narrative_elements
         ↓
Step 2: Cluster articles by nucleus entity + actor overlap
         ↓
    For nucleus_entity = "Binance":
        Find all articles with nucleus = "Binance"
         ↓
        Calculate pairwise similarity:
        - Shared actors (weighted by salience)
        - Shared tensions
        - Link strength (0.0 to 2.0+)
         ↓
        Group articles where link_strength >= 0.8
         ↓
    Result: clusters of 3+ related articles
         ↓
Step 3: Generate AI-powered narrative summaries
         ↓
    For each cluster:
        Call LLM with:
        {
            "cluster_nucleus": "Binance",
            "articles": [article1, article2, article3, ...],
            "prompt": "Synthesize these articles into a narrative summary.
                       Facts only, no external knowledge.
                       Verify all claims against source articles."
        }
         ↓
        LLM returns:
        {
            "title": "Binance Expands in South Korea",
            "summary": "Binance announced new partnerships with local banks...",
            "key_themes": ["market_expansion", "regulatory_compliance"],
            "entities": ["Binance", "South Korea", "Banking Partners"]
        }
         ↓
Step 4: Determine lifecycle state
         ↓
    For narrative with:
        - article_count = 8
        - mention_velocity = 2.1 articles/day
        - last_updated = 2 days ago
        - first_seen = 10 days ago
         ↓
    Calculate lifecycle_state:
        IF days_since_update >= 7 → dormant
        ELIF days_since_update >= 3 → cooling
        ELIF article_count >= 7 OR velocity >= 3.0 → hot
        ELIF velocity >= 1.5 → rising
        ELSE → emerging
         ↓
    Result: lifecycle_state = "rising"
         ↓
Step 5: Upsert narrative to MongoDB
         ↓
    narratives.update_one(
        {"_id": narrative_id},
        {
            "$set": {
                "title": "Binance Expands in South Korea",
                "summary": "...",
                "entities": ["Binance", "South Korea"],
                "article_ids": [ObjectId(...), ...],
                "lifecycle_state": "rising",
                "first_seen": ISODate("2026-05-05T..."),
                "last_updated": ISODate("2026-05-15T..."),
                "needs_summary_update": False,
                "last_summary_generated_at": ISODate("...")
            }
        },
        upsert=True
    )
```

**Constraint:** Only `relevance_tier <= 2` articles are included in narrative clustering. Tier 3 articles are excluded.

---

### 3.2 Narrative Document Schema

```python
{
    "_id": ObjectId("..."),
    
    # Content
    "title": "Binance Expands in South Korea",
    "summary": "Binance announced partnerships with local banks to expand services...",
    "description": "Market expansion, regulatory compliance",
    
    # Entity & Article Linking
    "entities": ["Binance", "South Korea", "Banking Partners"],
    "article_ids": [ObjectId(...), ObjectId(...), ...],
    "article_count": 8,
    
    # Lifecycle & Recency
    "lifecycle_state": "rising",  # emerging | rising | hot | cooling | dormant | echo | reactivated
    "lifecycle_history": [
        {
            "state": "emerging",
            "timestamp": ISODate("2026-05-05T..."),
            "article_count": 1,
            "mention_velocity": 0.2
        },
        {
            "state": "rising",
            "timestamp": ISODate("2026-05-10T..."),
            "article_count": 5,
            "mention_velocity": 1.2
        }
    ],
    "first_seen": ISODate("2026-05-05T..."),
    "last_updated": ISODate("2026-05-15T..."),
    
    # Momentum & Velocity
    "momentum": "growing",  # growing | declining | stable | unknown
    "mention_velocity": 2.1,  # articles per day (7-day window)
    
    # Resurrection Tracking
    "reawakening_count": 0,      # Times narrative has been reactivated
    "reawakened_from": None,     # Timestamp when narrative went dormant
    "resurrection_velocity": 0,  # Articles per day at resurrection
    
    # Summary Quality
    "needs_summary_update": False,  # Set to true if articles merged into narrative
    "last_summary_generated_at": ISODate("2026-05-15T..."),
    
    # Sentiment & Themes
    "sentiment": "bullish",  # Aggregate sentiment from articles
    "themes": ["regulatory_compliance", "market_expansion"],
    
    # Audit Trail
    "dormant_since": None,  # When narrative entered dormant state
    "_disabled_by": None    # Audit label if disabled (e.g., "TASK-073-auto-cleanup")
}
```

**Lifecycle state machine:**
```
emerging → rising → hot → cooling → dormant
                                       ↓
                                     echo (brief activity pulse)
                                       ↓
                                  reactivated (sustained activity)
                                       ↓
                                  (back to rising/hot)
```

---

### 3.3 Trust Boundary: Fresh-Start Filter

**File:** `services/narrative_trust.py`, `briefing_agent.py:374-385`

Before narratives reach the briefing agent, they pass through a **trust boundary**:

```
[All active narratives (50-100)]
         ↓
    get_fresh_start_cutoff()
         ↓
    Returns: timestamp T = "Last known-good narrative generation"
    (Initially set during system validation; updated after successful briefing)
         ↓
    Filter narratives:
        IF narrative.last_summary_generated_at >= T
        AND narrative.needs_summary_update == False
            → INCLUDE in briefing
        ELSE
            → EXCLUDE from briefing
         ↓
    Result: 8-15 trusted narratives (30-40% of available filtered out)
```

**Why this works:**
- If a narrative's summary was generated **before** a known-good time, it may contain old or hallucinated data
- The `needs_summary_update` flag is set when articles are merged into a narrative (BUG-102)
- Only narratives with recent, validated summaries are safe to use

---

## 4. BRIEFING GENERATION FLOW

### 4.1 High-Level Briefing Workflow

**File:** `services/briefing_agent.py:111-223`

```
Scheduled trigger (3x daily: 8 AM, 2 PM, 8 PM EST)
         ↓
    generate_briefing(briefing_type="morning|afternoon|evening")
         ↓
Step 1: Gather inputs
         ↓
    A. Load memory context (7-day history, manual inputs, patterns)
    B. Compute trending signals (top 20 from cache)
    C. Fetch active narratives (top 15, apply trust boundary filter)
    D. Detect patterns (entity surges, sentiment shifts, expected events)
         ↓
    Result: BriefingInput object with:
    {
        "briefing_type": "morning",
        "signals": [20 signals],
        "narratives": [8-15 narratives],
        "patterns": {
            "entity_surges": [...],
            "sentiment_shifts": [...],
            "expected_events": [...]
        },
        "memory": {
            "history": [7-day feedback],
            "patterns": [...],
            "manual_inputs": [...]
        },
        "generated_at": datetime.now()
    }
         ↓
Step 2: Generate initial briefing (LLM call)
         ↓
    Build generation prompt:
    - Time context ("morning briefing for May 15, 2026")
    - Memory context ("User feedback: focus on regulatory news")
    - Signals section (20 signals with scores/velocities)
    - Narratives section (8-15 narrative summaries + entity lists)
    - Patterns section (market anomalies detected)
    - ALLOWED NARRATIVES list (explicit allowlist)
    - ALLOWED ENTITIES list (extracted from narratives)
    - 11 explicit constraints (no hallucination, named entities, etc.)
         ↓
    Call LLM:
    gateway.call(
        messages=[{"role": "user", "content": generation_prompt}],
        system_prompt="You are a senior crypto analyst...",
        operation="briefing_generate",
        max_tokens=4096
    )
         ↓
    Routed to: Claude Haiku 4.5 (model routing enforced by gateway)
    Cached: NO (briefings always fresh)
    Cost: ~$0.005-0.010 per call
         ↓
    LLM returns: JSON briefing
    {
        "narrative": "Bitcoin's resurgence above $65K reflects...",
        "key_insights": ["Institutional adoption accelerating", "..."],
        "entities_mentioned": ["Bitcoin", "BlackRock", "..."],
        "detected_patterns": ["momentum_shift", "..."],
        "recommendations": [
            {"title": "Bitcoin Regulatory Pressure", "theme": "Regulation"}
        ],
        "confidence_score": 0.85
    }
         ↓
    Parse JSON response
         ↓
Step 3: Self-refine (quality assurance loop, max 2 iterations)
         ↓
    Iteration 1:
    A. Build critique prompt with:
       - Generated briefing
       - Available narratives (ground truth)
       - Available entities (allowlist)
       - 10 explicit checks (hallucination, vague references, etc.)
         ↓
    B. Call LLM to critique:
       gateway.call(
           messages=[{"role": "user", "content": critique_prompt}],
           system_prompt="You are a crypto briefing reviewer...",
           operation="briefing_critique",
           max_tokens=1024
       )
         ↓
    C. LLM returns:
       {
           "needs_refinement": false,
           "issues": [],
           "suggestions": []
       }
         ↓
    D. Check: needs_refinement == false?
       → YES: Exit refinement loop, return briefing
       → NO: Proceed to refinement
         ↓
    Iteration 2 (if needed):
    A. Build refinement prompt with:
       - Original briefing
       - Critique feedback
       - Full narrative details (source context)
       - Trending signals
       - Detected patterns
       - Explicit instruction: "Use ONLY provided sources"
         ↓
    B. Call LLM to refine:
       gateway.call(
           messages=[{"role": "user", "content": refinement_prompt}],
           system_prompt="You are a crypto analyst refining a briefing...",
           operation="briefing_refine",
           max_tokens=4096
       )
         ↓
    C. LLM returns: Refined JSON briefing
         ↓
    D. Parse and critique refined version (same checks)
         ↓
    E. If still needs refinement:
       - Log warning "Max refinement reached"
       - Set confidence_score = 0.6
       - Return anyway (don't waste more tokens)
         ↓
    Final result: GeneratedBriefing with 0.85 or 0.6 confidence
         ↓
Step 4: Validate recommendations
         ↓
    For each recommendation {title, theme}:
        Try to match title to narrative in provided list:
        title_to_id_map = {
            "bitcoin regulatory pressure": ObjectId("..."),
            "ethereum shanghai upgrade": ObjectId("..."),
            ...
        }
         ↓
        IF recommendation.title.lower() in title_to_id_map:
            → Add narrative_id to recommendation
        ELSE:
            → Log debug message (hallucinated recommendation)
            → Keep recommendation with no narrative_id
         ↓
    Matched recommendations ready for database
         ↓
Step 5: Save briefing to MongoDB
         ↓
    daily_briefings.insert_one({
        "_id": ObjectId("..."),
        "briefing_id": "abc123",  # Shared across all traces for this briefing
        "briefing_type": "morning",
        "date": datetime(2026, 5, 15),
        "generated_at": datetime.now(),
        
        "narrative": "Bitcoin's resurgence above $65K...",
        "key_insights": ["Institutional adoption accelerating", ...],
        "entities_mentioned": ["Bitcoin", "BlackRock", ...],
        "detected_patterns": ["momentum_shift", ...],
        "recommendations": [
            {
                "title": "Bitcoin Regulatory Pressure",
                "theme": "Regulation",
                "narrative_id": ObjectId("...")  # Added by validation
            }
        ],
        "confidence_score": 0.85,
        
        "context": {
            "signals_count": 20,
            "narratives_count": 12,
            "patterns_count": 6
        },
        
        "is_smoke": False,
        "task_id": "task-xyz"  # Celery task ID
    })
         ↓
Step 6: Save patterns
         ↓
    For each pattern in detected_patterns:
        patterns.insert_one({
            "_id": ObjectId("..."),
            "briefing_id": ObjectId(briefing._id),
            "pattern_name": "momentum_shift",
            "description": "Bitcoin momentum increased 2.5x in 48h",
            "entities": ["Bitcoin", "Ethereum"],
            "confidence": 0.8,
            "detected_at": datetime.now()
        })
         ↓
Step 7: Record heartbeat
         ↓
    heartbeats.insert_one({
        "stage": "generate_briefing",
        "duration_seconds": 45,
        "summary": "morning briefing generated, 20 signals, 12 narratives",
        "timestamp": datetime.now()
    })
         ↓
[Briefing saved to MongoDB, ready for API consumption]
```

---

### 4.2 Briefing Data Structure

```python
# Document in daily_briefings collection
{
    "_id": ObjectId("..."),
    "briefing_id": "a1b2c3d4",  # Correlates all LLM traces
    
    # Metadata
    "briefing_type": "morning",  # morning | afternoon | evening
    "date": ISODate("2026-05-15"),
    "generated_at": ISODate("2026-05-15T08:30:00Z"),
    
    # Generated Content
    "narrative": "Bitcoin's resurgence above $65K reflects growing institutional adoption...",
    "key_insights": [
        "Institutional adoption accelerating despite regulatory scrutiny",
        "Ethereum sentiment divergence suggests caution on smart contracts",
        "Solana network recovery attracting venture capital"
    ],
    "entities_mentioned": ["Bitcoin", "Ethereum", "Solana", "SEC", "BlackRock"],
    "detected_patterns": [
        "momentum_shift: Bitcoin velocity +150% vs 24h baseline",
        "sentiment_divergence: 0.6 gap between BTC and ETH sentiment",
        "entity_surge: Solana mentions up 3.2x"
    ],
    
    # Recommendations with narrative linking
    "recommendations": [
        {
            "title": "Bitcoin Regulatory Pressure",
            "theme": "Regulation",
            "narrative_id": ObjectId("...")
        },
        {
            "title": "Ethereum Shanghai Upgrade Impact",
            "theme": "Technical",
            "narrative_id": ObjectId("...")
        }
    ],
    
    # Quality Score
    "confidence_score": 0.85,  # 0.6 if max refinement reached, else 0.85
    
    # Context for debugging
    "context": {
        "signals_count": 20,
        "narratives_count": 12,
        "patterns_count": 6
    },
    
    # Operational flags
    "is_smoke": False,          # true if smoke test, false for production
    "task_id": "celery-task-xyz",  # Celery task ID for correlation
    
    # Audit trail
    "created_by": "system",
    "last_modified": ISODate("...")
}
```

---

## 5. TRACING & COST TRACKING

### 5.1 LLM Traces

Every LLM call writes a trace to `llm_traces` collection. This enables full auditability of briefing generation.

**File:** `gateway.py:653-714`

```python
# Document in llm_traces collection
{
    "_id": ObjectId("..."),
    "trace_id": "f1a2b3c4-d5e6-7f8a-9b0c-1d2e3f4a5b6c",
    
    # Operation & Routing
    "operation": "briefing_generate",  # operation name from caller
    "status": "success",               # success | error
    
    # Model Information
    "requested_model": None,           # What caller asked for
    "model": "claude-haiku-4-5-20251001",  # Actual model used
    "provider": "anthropic",           # anthropic | deepseek
    "routing_overridden": False,       # true if gateway changed model
    
    # Tokens & Cost
    "input_tokens": 2847,
    "output_tokens": 412,
    "cost": 0.00089,                   # USD cost
    "duration_ms": 3240,               # Latency
    
    # Caching
    "cached": False,                   # true if result from cache
    "cache_key": None,                 # SHA1 hash if cached
    
    # Error Info
    "error": None,                     # Error message if failed
    "error_type": None,                # auth_error | rate_limit | etc.
    
    # Correlation for Briefing
    "task_id": "celery-task-xyz",      # Celery task ID
    "briefing_id": "a1b2c3d4",         # Briefing ID (shared across phases)
    "is_smoke": False,                 # Smoke test flag
    "phase": "generate",               # generate | critique | refine
    "iteration": 0,                    # Refinement iteration (0, 1, 2)
    
    # Timestamps
    "timestamp": ISODate("2026-05-15T08:30:15Z"),  # Creation time
}
```

**Trace correlation example for one briefing:**

```
[Morning Briefing Generation] briefing_id = "a1b2c3d4"
    ├─ trace_id: "...", phase: "generate", iteration: 0
    │   operation: briefing_generate
    │   input_tokens: 2847, output_tokens: 412, cost: $0.00089
    │
    ├─ trace_id: "...", phase: "critique", iteration: 1
    │   operation: briefing_critique
    │   input_tokens: 1523, output_tokens: 89, cost: $0.00034
    │
    └─ trace_id: "...", phase: "refine", iteration: 1
        operation: briefing_refine
        input_tokens: 2450, output_tokens: 398, cost: $0.00082

[Total Cost] $0.00089 + $0.00034 + $0.00082 = $0.00205 per briefing
[Total Tokens] 2847 + 1523 + 2450 = 6,820 input tokens
```

---

### 5.2 Cost Tracking & Budget Enforcement

**File:** `services/cost_tracker.py:45-120`, `gateway.py:378-386`

**Budget system:**
- **Daily hard limit:** $1.00/day
- **Monthly hard limit:** $30.00/month
- **Soft limit:** $22.50/month (alert configured but not working)

**Cost queries:**

```python
async def get_daily_cost() -> float:
    """Sum all LLM traces from last 24 hours."""
    db = await mongo_manager.get_async_database()
    now = datetime.utcnow()
    yesterday = now - timedelta(hours=24)
    
    result = await db.llm_traces.aggregate([
        {"$match": {"timestamp": {"$gte": yesterday}}},
        {"$group": {"_id": None, "total": {"$sum": "$cost"}}}
    ]).to_list(1)
    
    return result[0]["total"] if result else 0.0

async def check_llm_budget(operation: str) -> tuple[bool, Optional[str]]:
    """Check if LLM call would exceed daily or monthly limits."""
    daily_cost = await get_daily_cost()
    monthly_cost = await get_monthly_cost()
    
    if daily_cost >= 1.00:
        return False, f"Daily: ${daily_cost:.2f}/$1.00"
    if monthly_cost >= 30.00:
        return False, f"Monthly: ${monthly_cost:.2f}/$30.00"
    
    return True, None
```

**Baseline cost breakdown (typical day):**

| Operation | Calls/day | Cost/day | Notes |
|-----------|-----------|----------|-------|
| entity_extraction | ~174 | $0.152 | Tier 1 articles only |
| narrative_generate | ~51 | $0.125 | Narrative summaries |
| sentiment_analysis | ~70 | ~$0.050 | Tier 1 articles |
| briefing_generate | 2 | $0.010 | 2 primary briefings |
| briefing_critique | 2 | $0.005 | Quality checks |
| briefing_refine | 0-2 | $0.008 | Refinement passes |
| **TOTAL** | | **~$0.54** | Under $1.00 daily limit |

---

## 6. QUERY PATTERNS & INDEXING

### 6.1 Key Collections & Indexes

**Articles collection:**
```javascript
// Indexes
db.articles.createIndex({"fingerprint": 1})        // Fast duplicate check
db.articles.createIndex({"relevance_tier": 1})     // Filter by tier
db.articles.createIndex({"created_at": -1})        // Recency ordering
db.articles.createIndex({"sentiment": 1})          // Group by sentiment
```

**Entity mentions collection:**
```javascript
// Indexes
db.entity_mentions.createIndex({"entity": 1})                    // Find entity
db.entity_mentions.createIndex({"entity": 1, "created_at": -1})  // Entity + time
db.entity_mentions.createIndex({"article_id": 1})                // Reverse lookup
db.entity_mentions.createIndex({"is_primary": 1})                // Filter primary only
db.entity_mentions.createIndex({"relevance_tier": 1})            // Filter by tier
```

**Narratives collection:**
```javascript
// Indexes
db.narratives.createIndex({"lifecycle_state": 1})        // Filter active narratives
db.narratives.createIndex({"last_updated": -1})          // Recency
db.narratives.createIndex({"needs_summary_update": 1})   // Find stale summaries
```

**LLM traces collection:**
```javascript
// Indexes
db.llm_traces.createIndex({"operation": 1})                      // Find by operation
db.llm_traces.createIndex({"operation": 1, "timestamp": -1})     // Time-based cost queries
db.llm_traces.createIndex({"briefing_id": 1})                    // Trace a briefing's calls
db.llm_traces.createIndex({"timestamp": 1}, {expireAfterSeconds: 2592000})  // TTL: 30 days
```

**Daily briefings collection:**
```javascript
// Indexes
db.daily_briefings.createIndex({"briefing_type": 1, "date": -1})  // Find briefings by type/date
db.daily_briefings.createIndex({"briefing_id": 1})                 // Look up by ID
```

---

### 6.2 Common Query Patterns

**Get trending signals (pre-computed, cached):**
```javascript
// Not directly queried; computed by compute_trending_signals()
// Result cached in Redis: signals:trending:24h (900s TTL)
```

**Get active narratives for briefing:**
```javascript
db.narratives.find({
    lifecycle_state: {$in: ["emerging", "rising", "hot", "cooling", "echo", "reactivated"]},
    last_updated: {$gte: ISODate("2026-05-08")}  // Last 7 days
})
.sort({last_updated: -1})
.limit(15)
```

**Get high-signal articles:**
```javascript
db.articles.find({
    relevance_tier: {$lte: 2},
    created_at: {$gte: ISODate("2026-05-14")}  // Last 24h
})
```

**Get entity mentions for trending analysis:**
```javascript
db.entity_mentions.find({
    entity: "Bitcoin",
    is_primary: true,
    created_at: {$gte: ISODate("2026-05-14")},  // Last 24h
    article_id: {$in: [high_signal_article_ids]}
})
```

**Get cost for today:**
```javascript
db.llm_traces.aggregate([
    {$match: {timestamp: {$gte: new Date(Date.now() - 24*60*60*1000)}}},
    {$group: {_id: null, total: {$sum: "$cost"}}}
])
```

**Trace a briefing's all LLM calls:**
```javascript
db.llm_traces.find({briefing_id: "a1b2c3d4"})
    .sort({timestamp: 1})
```

---

## 7. DATA DEPENDENCIES & CRITICAL PATHS

### 7.1 Dependency Graph

```
RSS Feeds
    ↓
[Articles]
    ├─→ [Fingerprint Check] ← Ensures no duplicates
    ├─→ [Tier Classification] ← Required before enrichment
    │       ├─→ [Entity Extraction] (Tier 1 only)
    │       └─→ [Sentiment Analysis] (Tier 1 only)
    │           ↓
    │       [Entity Mentions]
    │           ↓
    └─→ [Signal Computation] ← Only uses Tier 1-2, high-signal articles
            ├─→ [Mention Velocity]
            ├─→ [Sentiment Aggregation]
            └─→ [Signal Scores]
                ↓
            [Redis Cache: signals:trending:24h]
                ↓
        ┌───────────────────┐
        ↓                   ↓
    [Narrative Clustering] [Memory Context]
        ├─→ (Extract elements)
        ├─→ (Cluster by nucleus entity)
        ├─→ (Generate summaries)
        ├─→ (Determine lifecycle)
        └─→ [Narratives]
            ├─→ [Trust Boundary Filter]
            │   ├─→ Check summary_age >= known-good
            │   └─→ Check needs_summary_update == false
            │
            └─→ [Active Narratives (8-15)]
                    ↓
        ┌───────────────────────────────┐
        ↓                               ↓
    [Briefing Generation] ← [Pattern Detection]
        ├─→ Build prompts (signals, narratives, patterns)
        ├─→ Call LLM (gateway routing, budget check)
        ├─→ Parse response
        ├─→ [Self-Critique Loop]
        │   ├─→ Check for hallucinations
        │   ├─→ Validate against allowlist
        │   └─→ Refine if needed (max 2 iterations)
        ├─→ Match recommendations to narratives
        └─→ [Daily Briefing Document]
            ├─→ Save briefing
            ├─→ Save patterns
            └─→ Record heartbeat
```

### 7.2 Critical Path (Latency Bottlenecks)

**Article Ingestion (per article):**
- Fetch: 30-60s (all feeds)
- Normalize: <1ms per article
- Fingerprint check: 1ms (indexed)
- Tier classification: 2-3s (LLM call)
- Entity extraction (Tier 1): 2-5s (LLM call)
- Sentiment analysis (Tier 1): 1-2s (LLM call)
- **Total Tier 1:** ~5-10s per article
- **Total Tier 2-3:** ~2-3s per article

**Signal Computation:**
- Entity aggregation: ~500ms (cached after first run)
- Velocity/score calculation: ~200ms
- Redis cache: <10ms on hit

**Narrative Detection:**
- Element extraction: 1-2s per article (LLM)
- Clustering: <100ms (in-memory)
- Summary generation: 3-5s per narrative (LLM)
- Lifecycle determination: <10ms
- **Total:** 5-10s per narrative

**Briefing Generation:**
- Gather inputs: ~2s
- Generate + parse: 3-5s (LLM)
- Critique: 1-2s (LLM)
- Refine (if needed): 3-5s (LLM)
- Save to DB: <100ms
- **Total:** 8-15s per briefing (without refinement); up to 25s with full refinement

**Daily throughput (3 briefings/day):**
- ~3 briefings × 15s avg = 45s LLM time
- Plus ~0.54/day in cost (~$0.18 per briefing)

---

## 8. OPERATIONAL RUNBOOKS

### 8.1 Trace a Single Briefing

```bash
# Find briefing ID
briefing_id=$(mongosh crypto_news --eval 'db.daily_briefings.findOne({date: ISODate("2026-05-15"), briefing_type: "morning"})._id.toString()')

# Get all LLM traces for this briefing
mongosh crypto_news --eval "db.llm_traces.find({briefing_id: '$briefing_id'}).sort({timestamp: 1})"

# Calculate total cost
mongosh crypto_news --eval "db.llm_traces.aggregate([{\\$match: {briefing_id: '$briefing_id'}}, {\\$group: {_id: null, total_cost: {\\$sum: '\\$cost'}, total_tokens: {\\$sum: {\\$add: ['\\$input_tokens', '\\$output_tokens']}}}}])"

# Check for errors/timeouts
mongosh crypto_news --eval "db.llm_traces.find({briefing_id: '$briefing_id', error: {\\$ne: null}})"
```

### 8.2 Monitor Daily Costs

```bash
# Cost so far today
mongosh crypto_news --eval "db.llm_traces.aggregate([{\\$match: {timestamp: {\\$gte: new Date(new Date().toDateString())}}}, {\\$group: {_id: '\\$operation', count: {\\$sum: 1}, cost: {\\$sum: '\\$cost'}}}, {\\$sort: {cost: -1}}])"

# Cost this month
mongosh crypto_news --eval "db.llm_traces.aggregate([{\\$match: {timestamp: {\\$gte: new Date('2026-05-01')}}}, {\\$group: {_id: null, total_cost: {\\$sum: '\\$cost'}, total_calls: {\\$sum: 1}}}])"
```

### 8.3 Audit Narrative Trust Boundary

```bash
# Check narratives with stale summaries
mongosh crypto_news --eval "db.narratives.find({needs_summary_update: true})"

# Count narratives excluded by trust boundary
cutoff=$(mongosh crypto_news --eval "db.system.config.findOne({key: 'fresh_start_cutoff'}).value")
mongosh crypto_news --eval "db.narratives.find({last_summary_generated_at: {\\$lt: ISODate('$cutoff')}})" --count
```

---

**Last Updated:** 2026-05-15
