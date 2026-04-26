# Article Analysis & Pattern Detection

## Overview

Once articles are ingested and enriched, the system analyzes them to detect narratives (story threads), identify market signals, and discover trading patterns. This document describes entity linking, narrative clustering, signal detection, and pattern analysis, enabling debugging of missing narrative connections and pattern detection failures.

**Anchor:** `#processing-pipeline`

## Architecture

### Key Components

- **Narrative Service**: Groups articles into story threads using semantic similarity
- **Entity Linker**: Connects entity mentions across articles and narratives
- **Signal Detector**: Identifies market events (price movements, regulatory news, etc.)
- **Pattern Analyzer**: Discovers correlations and divergences across narratives
- **Relevance Scorer**: Ranks narratives and signals by importance

### Data Flow

```
1. Enriched Article (entities, sentiment)
                │
                ▼
    ┌───────────────────────────┐
    │  Semantic Embedding        │  Convert text to vector
    │  (OpenAI/Anthropic)        │
    └────────────┬────────────────┘
                 │
                 ▼
    ┌───────────────────────────┐
    │  Similarity Matching       │  Compare to existing narratives
    │  (cosine similarity)       │  Find threshold match (>0.75)
    └────────────┬────────────────┘
                 │
          ┌──────┴──────┐
          │             │
          ▼             ▼
   New Narrative   Existing Narrative
   (create)        (append article)
          │             │
          └──────┬──────┘
                 │
                 ▼
    ┌───────────────────────────┐
    │  Update Entity Index       │  Link entities to narrative
    │                           │
    └────────────┬────────────────┘
                 │
                 ▼
    ┌───────────────────────────┐
    │  Detect Signals           │  Market events, price anomalies
    │                           │
    └────────────┬────────────────┘
                 │
                 ▼
    ┌───────────────────────────┐
    │  Store Narrative +        │
    │  Signals in MongoDB       │
    └───────────────────────────┘
```

## Implementation Details

### Narrative Detection & Clustering

**File:** `src/crypto_news_aggregator/services/narrative_service.py:100-250`

Narrative grouping via semantic similarity:

```python
async def detect_or_match_narrative(
    article: Article,
    entities: List[str]
) -> str | None:
    """Find or create narrative for article."""

    # 1. Generate embedding for article content
    embedding = await self._get_embedding(article.content)  # Line 110

    # 2. Query existing narratives (by entity mention)
    candidate_narratives = await self._find_candidates(entities)  # Line 115

    # 3. Calculate similarity to each candidate
    matches = []
    for narrative in candidate_narratives:
        similarity = self._cosine_similarity(          # Line 120
            embedding,
            narrative.embedding
        )
        if similarity > 0.75:  # Threshold
            matches.append((narrative, similarity))

    # 4. Return best match or create new
    if matches:
        best = max(matches, key=lambda x: x[1])
        narrative_id = best[0]._id
        await self._append_article_to_narrative(narrative_id, article)  # Line 130
        return narrative_id
    else:
        narrative_id = await self._create_narrative(article, entities)  # Line 135
        return narrative_id
```

**Configuration:**
- **Similarity threshold:** 0.75 (cosine similarity)
- **Embedding model:** `text-embedding-3-small` (OpenAI) or Claude embeddings
- **Embedding dimension:** 1536 (or 4096 for larger models)
- **Cache:** Narratives cached in memory with embedding (re-fetched hourly)

**Narrative document schema:**
```javascript
{
  "_id": ObjectId("..."),
  "title": "Bitcoin Regulatory Pressure",           // Summary title
  "description": "Story thread about regulatory crackdowns",
  "entities": ["SEC", "Bitcoin", "Coinbase"],      // Key entities
  "embedding": [0.123, -0.456, ...],               // 1536 dimensions
  "article_ids": [ObjectId(...), ...],             // Linked articles
  "sentiment": "bearish",                           // Aggregate sentiment
  "first_seen": ISODate("2026-02-01T..."),         // When narrative started
  "last_updated": ISODate("2026-02-10T..."),       // Last article added
  "lifecycle_state": "emerging" | "rising" | "hot" | "cooling" | "dormant" | "echo" | "reactivated",
  // State machine: emerging → rising → hot → cooling → dormant
  // echo: narrative resurfaces after resolution without new articles
  // reactivated: dormant narrative receives new articles and re-enters active flow

  // Summary staleness tracking (BUG-088)
  "needs_summary_update": false,                   // true when merge path detects stale summary
  "last_summary_generated_at": ISODate("..."),     // Stamped at creation; baseline for staleness check

  // Auto-dormant audit trail (TASK-073)
  "dormant_since": ISODate("..."),                 // Set when zombie cleanup marks dormant
  "_disabled_by": "TASK-073-auto-cleanup"          // Audit label; null on active narratives
}
```

### Entity Linking & Index

**File:** `src/crypto_news_aggregator/services/entity_service.py:100-200`

Entity extraction and mention tracking:

```python
async def extract_entities(article: Article) -> List[Entity]:
    """Extract entities from article using LLM."""

    prompt = f"""Extract key entities from this article:

    {article.content}

    Return JSON: {{"entities": [{{"name": "Coinbase", "type": "company", "relevance": 0.9}}, ...]}}"""

    response = await self.llm_client.call(prompt)  # Line 115
    entities = self._parse_response(response)       # Line 120

    # 2. Link entities to article
    for entity in entities:
        mention = {
            "entity": entity.name,
            "type": entity.type,  # company, person, crypto, concept
            "article_id": article._id,
            "sentiment": article.sentiment
        }
        await self.db.entity_mentions.insert_one(mention)  # Line 130

    return entities
```

**Entity types:**
- `company`: Exchange, wallet service (Coinbase, Kraken, MetaMask)
- `crypto`: Cryptocurrency (Bitcoin, Ethereum, Solana)
- `person`: Key figures (Vitalik Buterin, Elon Musk)
- `concept`: Trading patterns, regulatory terms, tech innovations

**Entity index query:**
```javascript
// Find all articles mentioning "Coinbase"
db.entity_mentions.find({entity: "Coinbase", type: "company"})

// Find narratives mentioning multiple entities
db.narratives.find({entities: {$all: ["SEC", "Binance"]}})
```

### Signal Detection

**File:** `src/crypto_news_aggregator/services/signal_service.py:50-200`

Market signal identification:

```python
async def detect_signals_from_narrative(
    narrative: Narrative
) -> List[Signal]:
    """Detect market signals from narrative articles."""

    signals = []

    # 1. Price-movement signals
    if any(word in narrative.description.lower() for word in ["surge", "crash", "rally", "plunge"]):
        signals.append(Signal(
            type="price_movement",
            strength="high" if "surge" in narrative.description else "medium",
            affected_assets=narrative.entities  # Line 75
        ))

    # 2. Regulatory signals
    if any(word in narrative.description.lower() for word in ["sec", "cftc", "regulation", "ban"]):
        signals.append(Signal(
            type="regulatory",
            strength="high",  # Regulatory changes are high-impact
            context=narrative.description[:200]  # Line 85
        ))

    # 3. Sentiment-based signals
    if narrative.sentiment == "bullish" and narrative.article_count > 5:
        signals.append(Signal(
            type="momentum",
            strength="medium",
            confidence=0.8
        ))

    await self.db.signals.insert_many(signals)  # Line 95
    return signals
```

**Signal types:**
- `price_movement`: Sudden price changes
- `regulatory`: Regulatory announcements or crackdowns
- `momentum`: Sustained positive/negative sentiment
- `technical`: Chart patterns (double bottom, breakdown, etc.)
- `on_chain`: Blockchain metrics (whale movements, network activity)
- `correlation`: Multiple assets moving in sync
- `market_shock`: ⚠️ **Currently disabled** — `detect_market_events()` returns an empty list as of BUG-083 Part 1 (commit 6850efb). The original implementation had six compounding failures (OR keyword matching, no relevance validation, blind volume extraction) that produced fabricated financial figures. Pending rebuild as TASK-072 with proper phrase matching and relevance validation.

**Signal strength:** "high" | "medium" | "low"

### Pattern Detection

**File:** `src/crypto_news_aggregator/services/pattern_detector.py:100-250`

Cross-narrative pattern analysis:

```python
async def detect_patterns_in_narratives(
    narratives: List[Narrative]
) -> List[Pattern]:
    """Identify market patterns across multiple narratives."""

    patterns = []

    # 1. Detect correlation patterns
    for i, narrative1 in enumerate(narratives):
        for narrative2 in narratives[i+1:]:
            correlation = self._calculate_correlation(  # Line 125
                narrative1.sentiment_timeline,
                narrative2.sentiment_timeline
            )
            if correlation > 0.7:  # Strong correlation
                patterns.append(Pattern(
                    type="correlation",
                    narratives=[narrative1._id, narrative2._id],
                    strength=correlation,
                    description=f"{narrative1.title} and {narrative2.title} move together"
                ))

    # 2. Detect divergence patterns
    # When similar narratives have opposite sentiment trends
    for entity in self._get_entities(narratives):
        entity_narratives = self._filter_by_entity(narratives, entity)
        sentiment_scores = [n.sentiment for n in entity_narratives]
        if max(sentiment_scores) - min(sentiment_scores) > 0.5:
            patterns.append(Pattern(
                type="divergence",
                entity=entity,
                description=f"Divergent sentiment for {entity}"
            ))

    await self.db.patterns.insert_many(patterns)  # Line 155
    return patterns
```

**Pattern types:**
- `correlation`: Multiple assets/narratives moving together (BTC-ETH, tech-crypto)
- `divergence`: Expected correlated items moving differently
- `momentum_cascade`: One pattern triggering another
- `seasonal`: Time-based patterns (end-of-month rallies, etc.)

## Operational Checks

### Health Verification

**Check 1: Narrative detection is running**
```bash
# Count narratives created in past 24 hours
db.narratives.find({first_seen: {$gte: ISODate("2026-02-09T00:00:00Z")}}).count()
# Should be > 0; if 0, narrative detection may not be running
```
*File reference:* `src/crypto_news_aggregator/services/narrative_service.py:135` (create narrative)

**Check 2: Entity linking is working**
```bash
# Count entity mentions linked to articles
db.entity_mentions.find({article_id: {$exists: true}}).count()
# Should be >> article count (multiple entities per article)
```
*File reference:* `src/crypto_news_aggregator/services/entity_service.py:130` (insert mention)

**Check 3: Signals are detected**
```bash
# Count signals created in past 24 hours
db.signals.find({created_at: {$gte: ISODate("2026-02-09T00:00:00Z")}}).count()
# Should be > 0; if 0, signal detection may be failing
```
*File reference:* `src/crypto_news_aggregator/services/signal_service.py:95` (insert signals)

**Check 4: Patterns are identified**
```bash
# Count patterns detected
db.patterns.find({created_at: {$gte: ISODate("2026-02-09T00:00:00Z")}}).count()
# Should be > 0; if 0, pattern detection may need optimization
```
*File reference:* `src/crypto_news_aggregator/services/pattern_detector.py:155` (insert patterns)

### Processing Quality Metrics

| Metric | Target | Notes |
|--------|--------|-------|
| Narrative creation rate | 5-20/day | New stories, not duplicates |
| Avg articles per narrative | 3-8 | Shows clustering effectiveness |
| Entity mention accuracy | >95% | Checked via manual sampling |
| Signal detection latency | <10s after article | Should be real-time |
| Pattern detection latency | <60s after article | Cross-narrative analysis is slower |

### Debugging

**Issue:** Narratives not being created for new articles
- **Root cause:** Embedding model timeout or all articles match existing narratives
- **Verification:** Check if embedding calls are timing out in worker logs
- **Fix:** Verify embedding API key; adjust similarity threshold (0.75 → 0.70)
  *Reference:* `src/crypto_news_aggregator/services/narrative_service.py:110`

**Issue:** Entity extraction is incomplete (empty entity lists)
- **Root cause:** LLM API error or entity prompt unclear
- **Verification:** Query for articles with `entities: []` count
- **Fix:** Retry entity extraction task; check ANTHROPIC_API_KEY
  *Reference:* `src/crypto_news_aggregator/services/entity_service.py:115-120`

**Issue:** Narratives are duplicating (same story as separate narratives)
- **Root cause:** Embedding similarity threshold too high or narratives created before similarity match
- **Verification:** Manually compare narratives with similar entity sets
- **Fix:** Lower similarity threshold (0.75 → 0.70) or run deduplication script
  *Reference:* `src/crypto_news_aggregator/services/narrative_service.py:120` (threshold)

**Issue:** Signals or patterns not appearing in briefings
- **Root cause:** Signals detected but not retrieved by briefing agent
- **Verification:** Query signals in MongoDB; check if briefing query includes them
- **Fix:** Ensure briefing agent queries signals with correct filters
  *Reference:* `src/crypto_news_aggregator/services/briefing_agent.py:83` (gather inputs)

## Relevant Files

### Core Logic
- `src/crypto_news_aggregator/services/narrative_service.py:100-250` - Narrative clustering
- `src/crypto_news_aggregator/services/entity_service.py:100-200` - Entity extraction and linking
- `src/crypto_news_aggregator/services/signal_service.py:50-200` - Signal detection
- `src/crypto_news_aggregator/services/pattern_detector.py:100-250` - Pattern analysis

### Database
- `src/crypto_news_aggregator/db/operations/narratives.py` - Narrative CRUD
- `src/crypto_news_aggregator/db/operations/signals.py` - Signal CRUD
- `src/crypto_news_aggregator/db/operations/patterns.py` - Pattern CRUD

### Configuration
- `src/crypto_news_aggregator/core/config.py:40-60` - Embedding model config
- `src/crypto_news_aggregator/services/narrative_service.py:15-30` - Similarity threshold

## Related Documentation
- **[30-ingestion.md](#ingestion-pipeline)** - Article enrichment that feeds into analysis
- **[60-llm.md](#llm-integration-generation)** - How patterns are used in briefing generation
- **[50-data-model.md](#data-model-mongodb)** - Narrative and signal collection schemas

---
*Last updated: 2026-04-25* | *Anchor: processing-pipeline*