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
1. Tier 1/2 Articles (with entities, sentiment, narrative elements)
                │
                ▼
    ┌─────────────────────────────────┐
    │  Stage 1: Extract Narrative     │  LLM: identify actors,
    │  Elements (Per-Article)         │  tensions, nucleus entity,
    │  discover_narrative_from_article│  focus (2-3 sec/article)
    └────────────┬────────────────────┘
                 │
                 ▼
    ┌─────────────────────────────────┐
    │  Stage 2: Cluster by Salience   │  Weighted link strength:
    │  cluster_by_narrative_salience  │  - Same nucleus: +1.0
    │  (No LLM, pure algorithm)       │  - 2+ core actors: +0.7
    │  Output: 3+ article clusters    │  - Threshold: >= 0.8 (<1 sec)
    └────────────┬────────────────────┘
                 │
                 ▼
    ┌─────────────────────────────────┐
    │  Stage 3: Generate Narrative    │  LLM call 1: Title + summary
    │  generate_narrative_from_cluster│  LLM call 2: Polish summary
    │  Aggregate + LLM summary        │  (4-6 sec/cluster)
    └────────────┬────────────────────┘
                 │
                 ▼
    ┌─────────────────────────────────┐
    │  Stage 4: Determine Lifecycle   │  Emerging / Rising / Hot /
    │  & Detect Signals               │  Cooling / Dormant / Reactivated
    │  determine_lifecycle_state      │  Signal detection: regulatory,
    │  detect_signals_from_narrative  │  price movement, momentum, etc.
    └────────────┬────────────────────┘
                 │
                 ▼
    ┌─────────────────────────────────┐
    │  Store Narrative + Signals      │
    │  in MongoDB                     │
    │  (narratives, signals, patterns)│
    └─────────────────────────────────┘
```

**Processing summary:**
- **Input:** Tier 1/2 articles enriched with entities, sentiment, narrative elements
- **Stage 1:** 2-3 sec per article (LLM extraction)
- **Stage 2:** <1 sec total (clustering algorithm, no LLM)
- **Stage 3:** 4-6 sec per cluster (2 LLM calls: generate + polish)
- **Stage 4:** <1 sec per cluster (lifecycle determination + signal detection)
- **Tier 3 exclusion:** Low-signal articles skip all stages, not included in narratives

## Implementation Details

### Narrative Construction Pipeline

**Tier filtering:** Only Tier 1 and Tier 2 articles are included in narrative clustering. Tier 3 (low-signal) articles are excluded to prevent noise from polluting narratives. This is enforced at line 15-17 and 1207-1230 via `MAX_RELEVANCE_TIER = 2`.

The pipeline consists of four stages:

#### Stage 1: Narrative Element Extraction (Per-Article)

**File:** `src/crypto_news_aggregator/services/narrative_themes.py:discover_narrative_from_article()`

Extract narrative elements from each Tier 1/2 article:

```python
async def discover_narrative_from_article(article: Dict) -> Dict:
    """
    Extract narrative elements: actors, tensions, nucleus_entity, narrative_focus.
    
    Returns:
        {
            'actors': ['SEC', 'Binance', 'Coinbase'],  # Key players
            'actor_salience': {'SEC': 8.5, 'Binance': 7.2, 'Coinbase': 6.1},  # Importance (0-10)
            'tensions': ['Regulatory crackdown', 'Market impact'],  # Core conflicts
            'nucleus_entity': 'SEC',  # Primary focus
            'narrative_focus': 'regulation',  # Story category
            'narrative_summary': '...'  # Article-level summary
        }
    """
    # Use LLM to analyze article structure and identify:
    # - Who are the key actors? (weight by mention frequency & emphasis)
    # - What are the underlying tensions? (conflicts, regulations, innovations)
    # - What entity is this story fundamentally about?
    # - What narrative category does this fit? (regulation, security, adoption, etc.)
```

**Processing:** LLM call per article (Tier 1/2 only)
**Latency:** 2-3 seconds per article

#### Stage 2: Article Clustering by Narrative Salience

**File:** `src/crypto_news_aggregator/services/narrative_themes.py:1054-1172` (`cluster_by_narrative_salience`)

Group articles into cohesive narrative clusters using weighted link strength:

```python
async def cluster_by_narrative_salience(articles: List[Dict], min_cluster_size: int = 3):
    """
    Cluster articles by nucleus entity and weighted actor/tension overlap.
    
    Weighted link strength calculation:
    - Same nucleus entity: +1.0 (strongest — both about same core subject)
    - 2+ shared high-salience actors (≥4.5): +0.7 (key players appear together)
    - 1 shared high-salience actor: +0.4 (some player overlap)
    - 1+ shared tensions: +0.3 (thematic overlap)
    
    Clustering threshold: link_strength >= 0.8
    
    Example:
        Article A: nucleus='SEC', core_actors=['SEC', 'Binance'], tensions=['Regulation']
        Article B: nucleus='SEC', core_actors=['SEC', 'Coinbase'], tensions=['Regulation']
        
        Link strength = 1.0 (same nucleus) + 0.4 (1 core actor: SEC) + 0.3 (shared tension)
                      = 1.7 >= 0.8 ✓ Cluster together
    
    Returns:
        List of article clusters (each cluster is a list of 3+ articles)
    """
    for article in articles:
        best_match = None
        best_strength = 0.0
        
        # Compare to each existing cluster
        for cluster in clusters:
            strength = calculate_link_strength(article, cluster)
            if strength >= 0.8:  # Strong match
                best_match = cluster
                break
        
        # Add to best cluster or create new
        if best_match and best_strength >= 0.8:
            best_match.append(article)  # Join existing cluster
        else:
            clusters.append([article])  # Start new cluster
    
    # Filter out small clusters (< 3 articles)
    return [c for c in clusters if len(c) >= min_cluster_size]
```

**Output:** Clusters of 3+ articles grouped by narrative similarity
**Latency:** <1 second (no LLM calls, pure algorithm)

#### Stage 3: Narrative Title & Summary Generation

**File:** `src/crypto_news_aggregator/services/narrative_themes.py:1317-1500` (`generate_narrative_from_cluster`)

Generate cohesive narrative for each cluster:

```python
async def generate_narrative_from_cluster(cluster: List[Dict]) -> Dict:
    """
    Generate narrative title and summary from article cluster.
    
    Process:
    1. Aggregate actors, tensions, and entity relationships from cluster
    2. Determine primary nucleus entity (most common across articles)
    3. Call LLM to generate title (max 60 chars) and summary (2-3 sentences)
    4. Polish summary for readability (active voice, punchy phrasing)
    
    Critical rules enforced in LLM prompt:
    - ONLY use information from the articles (no external knowledge)
    - Do NOT add titles or roles not explicitly mentioned
    - Do NOT assume current positions (people change roles)
    - Focus on WHAT happened, not WHO holds positions
    
    Returns:
        {
            'title': 'SEC Regulatory Crackdown on Crypto Exchanges',
            'summary': 'The SEC intensified enforcement against major exchanges...',
            'actors': ['SEC', 'Binance', 'Coinbase', ...],
            'nucleus_entity': 'SEC',
            'article_ids': [ObjectId(...), ...],
            'article_count': 5,
            'entity_relationships': [
                {'a': 'SEC', 'b': 'Binance', 'weight': 3},
                {'a': 'SEC', 'b': 'Coinbase', 'weight': 2}
            ]
        }
    """
    # 1. Aggregate data: actors, tensions, entity links (co-occurrence)
    # 2. LLM call 1: Generate narrative title + summary from article snippets
    # 3. LLM call 2: Polish summary for readability (active voice, punchy)
    # 4. Store complete narrative document
```

**Processing:** 2 LLM calls per cluster (one for generation, one for polish)
**Latency:** 4-6 seconds per cluster

#### Stage 4: Narrative Lifecycle & Storage

**File:** `src/crypto_news_aggregator/services/narrative_service.py:147-214`

Track narrative lifecycle and persistence:

```python
def determine_lifecycle_state(article_count: int, mention_velocity: float) -> str:
    """
    Determine narrative state based on activity metrics.
    
    States:
    - 'emerging': 1-3 articles, low velocity (<1.5 articles/day)
    - 'rising': 4-6 articles, moderate velocity (1.5-3.0 articles/day)
    - 'hot': 7+ articles OR velocity >= 3.0 articles/day
    - 'cooling': Transitioning from hot (detected via momentum)
    - 'dormant': No new articles for >14 days
    - 'echo': Resurfaces after dormancy without new articles
    - 'reactivated': Dormant narrative receives new articles
    
    Example lifecycle: emerging → rising → hot → cooling → dormant → reactivated
    """
    if article_count >= 7 or mention_velocity >= 3.0:
        return 'hot'
    elif mention_velocity >= 1.5 and article_count < 7:
        return 'rising'
    else:
        return 'emerging'
```

**Lifecycle tracking:**
- `first_seen`: When narrative was created
- `last_updated`: When last article was added
- `lifecycle_state`: Current state (emerging, rising, hot, cooling, dormant, etc.)
- `lifecycle_history`: Array of state transitions with timestamps and metrics
- `needs_summary_update`: Flag set when narrative merges or reaches milestones (3+ new articles, >24h age)

**Configuration:**
- **Clustering threshold:** link_strength >= 0.8 (weighted actor/tension overlap)
- **Minimum cluster size:** 3 articles (small clusters not promoted to narratives)
- **Narrative grace period:** 7-30 days adaptive (fast-burning: 7d, slow-burn: 30d)
- **Salience threshold:** actor_salience >= 4.5 (out of 10) for "core actor" status

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

### Narrative Matching & Merging

**File:** `src/crypto_news_aggregator/services/narrative_service.py:428-550` (`find_matching_narrative`)

After generating narratives from clusters, the system attempts to match new narratives against existing ones to prevent duplication:

```python
async def find_matching_narrative(
    fingerprint: Dict,  # {nucleus_entity, top_actors, key_actions}
    within_days: int = 14,
    cluster_velocity: Optional[float] = None
) -> Optional[Dict]:
    """
    Find existing narrative that matches fingerprint.
    
    Fingerprint: SHA1 hash of nucleus_entity + top_actors + key_actions
    Similarity: Compares fingerprints across actors and actions
    
    Adaptive thresholds (based on narrative recency):
    - Recent narratives (updated <48h): 0.5 similarity threshold
      Allows near-term continuations to merge more easily
    - Older narratives (>48h): 0.6 similarity threshold
      Strict matching to prevent unrelated stories from merging
    
    Adaptive grace period (based on velocity):
    - High velocity (>2 articles/day): 7 day window
    - Medium velocity (~1 article/day): 14 day window
    - Low velocity (<0.5 articles/day): 30 day window
    
    Returns:
        Best matching narrative dict if similarity >= threshold, else None
    """
    # Query narratives within time window (adaptive based on velocity)
    candidates = await narratives_collection.find({
        'last_updated': {'$gte': cutoff_time},
        'lifecycle_state': {'$in': ['emerging', 'rising', 'hot', 'cooling']}
    }).to_list(length=None)
    
    # Calculate fingerprint similarity for each candidate
    best_match = None
    best_similarity = 0.0
    
    for candidate in candidates:
        similarity = calculate_fingerprint_similarity(
            fingerprint,
            candidate['fingerprint']
        )
        
        # Check against adaptive threshold based on recency
        if candidate['last_updated'] > (now - 48h):
            threshold = 0.5  # Recent: easier merge
        else:
            threshold = 0.6  # Older: strict matching
        
        if similarity >= threshold and similarity > best_similarity:
            best_match = candidate
            best_similarity = similarity
    
    return best_match
```

**Merging logic (when match found):**
1. Append new cluster articles to existing narrative
2. Combine actors and tensions (deduplicated)
3. Recalculate nucleus entity and actor salience
4. Set `needs_summary_update: true` if >3 new articles
5. Update `last_updated` timestamp
6. Preserve lifecycle_history with state transitions

**Reference:** `src/crypto_news_aggregator/services/narrative_service.py:40-50` (merge_shallow_narratives)

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

### Briefing Quality Guardrails (BUG-081, Sprint 15)

**File:** `src/crypto_news_aggregator/services/briefing_agent.py:435-455` (guardrail rules in generation prompt)

The briefing generation prompt enforces data quality via rules 9-11:

**Rule 9 — Duplicate Consolidation:**
- Consolidate duplicate events — if the same event appears under different narrative angles, present it once with full context, not as separate stories
- Prevents briefings from reporting identical events multiple times under different narrative framings
- Example: An SEC filing mentioned in both "SEC Crackdown" narrative and "Regulatory Pressure" narrative should appear as one event

**Rule 10 — Named Entity Requirement:**
- No unnamed entities — every referenced platform, exchange, or project must be explicitly named using only names present in the provided narratives
- Prevents fabricated or implied entities that aren't sourced from articles
- Example: Cannot refer to "a major exchange" without naming it; must say "Coinbase" if Coinbase is mentioned in source articles

**Rule 11 — Figure Plausibility Validation:**
- Verify figure plausibility against ~$2-3T crypto market cap baseline — flag or omit figures that are historically unprecedented (e.g., $50B+ liquidations, $10B+ single hacks)
- Post-generation plausibility check with $50B threshold (BUG-082, Sprint 15)
- Regex pattern + manual review flag problematic figures for editor attention

**Implementation impact:** Reduces fabricated financial figures and unverifiable claims by requiring grounding in source articles only.

### Narrative Summary Grounding Constraints (BUG-084, Sprint 15)

**File:** `src/crypto_news_aggregator/services/narrative_service.py:180-220` (narrative summary generation)

Narrative summary generation (used in briefings and exports) is constrained to source articles:

**LLM Instruction:**
- "Verify all claims against the source articles provided. Do not add external knowledge or hypothetical scenarios."
- "If a claim is not verifiable from the source articles, omit it or flag it as inferred."
- Prevents narrative summaries from inventing events or fabricating quotes

**Validation check (post-generation):**
1. Parse summary for numbered claims or assertions
2. Attempt to match each claim to a source article
3. If unmatched, flag for manual review or demote confidence score

**Impact:** Reduces risk of unreliable or fabricated narratives appearing in briefings or user-facing exports.

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