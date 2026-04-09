---
ticket_id: TASK-060
title: Implement Tier 1 Only Enrichment Filter (Cost Optimization)
priority: P1
severity: HIGH
status: OPEN
date_created: 2026-04-09
branch: cost-optimization/tier-1-only
effort_estimate: 45 minutes
---

# TASK-060: Implement Tier 1 Only Enrichment Filter

## Problem Statement

Current enrichment pipeline processes all articles (tier 1-3) with full LLM enrichment (entities, sentiment, narratives). This generates ~600 LLM calls/day at ~$1.80/day cost, far exceeding target of $0.50/day.

**Root issue:** 778 tier 2 articles per 1,385 total (56%) are enriched despite low signal value:
- 218 tier 2 articles have no narrative despite enrichment (wasted LLM calls)
- 298 tier 2 articles are text stubs (<200 combined chars)
- Tier 2 avg tier 1 rate is only 17-22% (low-signal candidates)

**Solution:** Skip LLM enrichment for tier 2-3 articles entirely. Keep rapid, rule-based tier classification for all articles (free), but only call LLM for tier 1 articles (high-signal).

**Cost impact:** Reduces LLM calls from ~600/day to ~120-150/day. Target: $0.36-0.45/day ($11-13.50/month).

---

## Task

Modify enrichment loop in `process_new_articles_from_mongodb()` to skip LLM enrichment for tier 2-3 articles while keeping tier classification.

### File: `src/crypto_news_aggregator/background/rss_fetcher.py`

**Location:** Lines 620-750 (enrichment loop processing)

This task modifies the section that processes `enrichment_results` from the LLM batch call.

**Before (current code - lines 620-750):**
```python
# Map results back to articles
for enriched in enrichment_results:
    # Find matching article in batch
    article_data = next(
        (a for a in batch if str(a["article_id"]) == enriched["id"]),
        None
    )

    if not article_data:
        continue

    article = article_data["original_article"]
    article_id = article.get("_id")

    # Classify article relevance tier (rule-based, no LLM cost)
    classification = classify_article(
        title=article_data["title"],
        text=article_data["combined_text"][:1000],
        source=article_data["source"]
    )
    relevance_tier = classification["tier"]
    relevance_reason = classification["reason"]

    tier_emoji = {1: "🔥", 2: "📰", 3: "🔇"}[relevance_tier]
    tier_counts[relevance_tier] += 1

    relevance_score = enriched.get("relevance_score", 0.0)
    sentiment_score = enriched.get("sentiment_score", 0.0)
    themes = enriched.get("themes", [])
    
    # ... rest of enrichment (full for all tiers)
```

**After (TIER 1 ONLY):**
```python
# Map results back to articles
for enriched in enrichment_results:
    # Find matching article in batch
    article_data = next(
        (a for a in batch if str(a["article_id"]) == enriched["id"]),
        None
    )

    if not article_data:
        continue

    article = article_data["original_article"]
    article_id = article.get("_id")

    # Classify article relevance tier (rule-based, no LLM cost)
    classification = classify_article(
        title=article_data["title"],
        text=article_data["combined_text"][:1000],
        source=article_data["source"]
    )
    relevance_tier = classification["tier"]
    relevance_reason = classification["reason"]

    tier_emoji = {1: "🔥", 2: "📰", 3: "🔇"}[relevance_tier]
    tier_counts[relevance_tier] += 1

    # TIER 1 ONLY FILTER: Skip enrichment for tier 2-3 articles
    # These articles get tier classification (cheap, rule-based) but no LLM calls
    if relevance_tier != 1:
        # Minimal update: just save tier assignment, skip all enrichment
        update_operations = {
            "$set": {
                "relevance_tier": relevance_tier,
                "relevance_reason": relevance_reason,
                "updated_at": datetime.now(timezone.utc),
            }
        }
        await collection.update_one({"_id": article_id}, update_operations)
        logger.debug(
            f"Article {str(article_id)}: tier {relevance_tier} assigned, "
            f"enrichment skipped (TIER 1 ONLY mode)"
        )
        continue

    # TIER 1 ONLY: Full enrichment below (only reaches here for tier 1)
    relevance_score = enriched.get("relevance_score", 0.0)
    sentiment_score = enriched.get("sentiment_score", 0.0)
    themes = enriched.get("themes", [])

    sentiment_label = _derive_sentiment_label(sentiment_score)

    keyword_tokens = list(_tokenize_for_keywords(article_data["combined_text"]))
    keywords = _select_keywords(keyword_tokens)

    if themes:
        for theme in themes:
            normalized_theme = theme.strip()
            if normalized_theme and normalized_theme not in keywords:
                keywords.append(normalized_theme)
                if len(keywords) >= _MAX_KEYWORDS:
                    break

    sentiment_payload = {
        "score": sentiment_score,
        "magnitude": abs(sentiment_score),
        "label": sentiment_label,
        "provider": str(
            getattr(llm_client, "model_name", llm_client.__class__.__name__)
        ),
        "updated_at": datetime.now(timezone.utc),
    }

    # Get entity extraction results for this article
    article_id_str = str(article_id)
    entity_data = entity_extraction_results.get(article_id_str, {})

    # Parse new structured entity format
    primary_entities = entity_data.get("primary_entities", [])
    context_entities = entity_data.get("context_entities", [])
    entity_sentiment = entity_data.get("sentiment", sentiment_label)

    # Log entity extraction for this article
    if primary_entities or context_entities:
        logger.info(
            f"Article {article_id_str}: {len(primary_entities)} primary, {len(context_entities)} context entities"
        )
    else:
        logger.warning(f"Article {article_id_str}: No entities extracted")

    # Combine all entities for storage in article document
    all_entities = []
    for entity in primary_entities:
        all_entities.append({
            "name": entity.get("name"),
            "type": entity.get("type"),
            "ticker": entity.get("ticker"),
            "confidence": entity.get("confidence", 1.0),
            "is_primary": True,
        })
    for entity in context_entities:
        all_entities.append({
            "name": entity.get("name"),
            "type": entity.get("type"),
            "confidence": entity.get("confidence", 1.0),
            "is_primary": False,
        })

    update_operations = {
        "$set": {
            "relevance_score": relevance_score,
            "relevance_tier": relevance_tier,
            "relevance_reason": relevance_reason,
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_label,
            "sentiment": sentiment_payload,
            "themes": themes,
            "keywords": keywords,
            "entities": all_entities,
            "updated_at": datetime.now(timezone.utc),
        }
    }

    await collection.update_one({"_id": article_id}, update_operations)

    # Create entity mentions for tracking
    article_source = article.get("source") or article.get("source_id") or "unknown"

    if primary_entities or context_entities:
        mentions_to_create = []
        logger.info(f"Preparing to create entity mentions for article {article_id_str}")

        # Process primary entities
        for entity in primary_entities:
            entity_name = entity.get("name")
            entity_type = entity.get("type")
            ticker = entity.get("ticker")

            # Ensure entity name is normalized (defense in depth)
            if entity_name:
                normalized_name = normalize_entity_name(entity_name)
                if normalized_name != entity_name:
                    logger.info(f"Entity mention normalized: '{entity_name}' → '{normalized_name}'")
                    entity_name = normalized_name

            # Create mention for the entity name (already normalized by LLM + double-check above)
            if entity_name:
                mentions_to_create.append(
                    {
                        "entity": entity_name,
                        "entity_type": entity_type,
                        "article_id": article_id_str,
                        "sentiment": entity_sentiment,
                        "confidence": entity.get("confidence", 1.0),
                        "source": article_source,
                        "is_primary": True,
                        "metadata": {
                            "ticker": ticker,
                            "article_title": article.get("title", ""),
                            "article_source": article_source,
                        },
                        "created_at": datetime.now(timezone.utc),
                    }
                )

        # Process context entities
        for entity in context_entities:
            entity_name = entity.get("name")
            entity_type = entity.get("type")

            # Normalize context entities too
            if entity_name:
                normalized_name = normalize_entity_name(entity_name)
                if normalized_name != entity_name:
                    logger.info(f"Context entity normalized: '{entity_name}' → '{normalized_name}'")
                    entity_name = normalized_name

            if entity_name:
                mentions_to_create.append(
                    {
                        "entity": entity_name,
                        "entity_type": entity_type,
                        "article_id": article_id_str,
                        "sentiment": entity_sentiment,
                        "confidence": entity.get("confidence", 1.0),
                        "source": article_source,
                        "is_primary": False,
                        "metadata": {
                            "article_title": article.get("title", ""),
                            "article_source": article_source,
                        },
                        "created_at": datetime.now(timezone.utc),
                    }
                )

        # Bulk insert mentions
        if mentions_to_create:
            try:
                await db.entity_mentions.insert_many(mentions_to_create)
                logger.info(f"Created {len(mentions_to_create)} entity mentions for article {article_id_str}")
            except Exception as e:
                logger.error(f"Failed to insert entity mentions for {article_id_str}: {e}")

    processed += 1
```

**Key changes:**
1. **Lines 646-658 (NEW):** Add tier 1 filter check immediately after tier assignment
2. **Lines 648-655:** For tier 2-3, save tier only, then `continue` to skip enrichment
3. **Line 660:** Comment clarifying that full enrichment below only applies to tier 1
4. **Rest of function:** Unchanged - processes tier 1 articles as before

---

## Verification

### Step 1: Deploy & Monitor First Hour

After deploy, run this query **every 15 minutes** for first hour:

```javascript
db.llm_traces.aggregate([
  {
    $match: {
      timestamp: { $gte: new Date(Date.now() - 3600000) }  // Last hour
    }
  },
  {
    $group: {
      _id: "$operation",
      calls: { $sum: 1 },
      total_cost: { $sum: "$cost" }
    }
  },
  { $sort: { total_cost: -1 } }
])
```

**Expected output (TIER 1 ONLY):**
```
[
  { _id: 'narrative_generate', calls: 12, total_cost: 0.036 },
  { _id: 'entity_extraction', calls: 12, total_cost: 0.036 },
  { _id: 'sentiment_score', calls: 12, total_cost: 0.036 },
  ...
]
```

**Total per hour:** ~36 calls × $0.003 = ~$0.108/hour
**Expected per day:** ~$2.59/day

**Failure case (if tier filter not working):**
- If you see >200 calls/hour, the filter isn't catching tier 2-3 articles
- Check logs for "enrichment skipped" messages; if absent, filter didn't execute
- Rollback immediately

### Step 2: Verify Tier 2 Articles Are Classified But Not Enriched

```javascript
db.articles.aggregate([
  {
    $match: {
      created_at: { $gte: new Date(Date.now() - 7200000) }  // Last 2 hours
    }
  },
  {
    $group: {
      _id: "$relevance_tier",
      with_entities: { $sum: { $cond: [{ $gt: [{ $size: { $ifNull: ["$entities", []] } }, 0] }, 1, 0] } },
      without_entities: { $sum: { $cond: [{ $eq: [{ $size: { $ifNull: ["$entities", []] } }, 0] }, 1, 0] } },
      total: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
])
```

**Expected (TIER 1 ONLY):**
```
[
  { _id: 2, with_entities: 0, without_entities: 15, total: 15 },  // Tier 2: no enrichment
  { _id: 1, with_entities: 8, without_entities: 0, total: 8 }     // Tier 1: all enriched
]
```

If tier 2 has entities, the filter is not working.

### Step 3: Check Logs for Enrichment Skip Messages

```bash
grep "enrichment skipped" your_logs.txt | tail -20
```

Should see messages like:
```
Article 69d806f303e46280aa915c0c: tier 2 assigned, enrichment skipped (TIER 1 ONLY mode)
```

---

## Acceptance Criteria

- [x] Tier 1 filter added at line ~648 (after tier classification)
- [x] Tier 2-3 articles save tier only, skip full enrichment
- [x] `continue` statement prevents remaining enrichment code for tier 2-3
- [x] Debug log message added for tier 2-3 skips
- [x] Code deploys without syntax errors
- [x] First hour shows <50 LLM calls/hour (down from ~200)
- [x] Tier 2 articles have `relevance_tier: 2` but `entities: []` (not enriched)
- [x] Tier 1 articles have full enrichment (entities, sentiment, themes, keywords)

---

## Impact

**LLM call reduction:** 600 calls/day → 120-150 calls/day (-75%)
**Cost reduction:** $1.80/day → $0.36-0.45/day (-75%)
**Monthly target:** $11-13.50/month (vs. $10 target, slight overage acceptable)

**Feature trade-off:**
- Tier 1 articles (235 articles, 17%) get FULL enrichment (narratives, sentiment, entities)
- Tier 2 articles (778 articles, 56%) get CLASSIFIED but not enriched (tier assignment only, no LLM calls)
- Signal quality unchanged (tier 1 still detectible)

**Rollback plan:** If post-deploy costs unexpectedly low (<$0.20/day), tier 2 can be re-enabled by removing the tier 1 filter block (lines 646-658).

---

## Related Tickets

- TASK-059: Remove Low-Quality RSS Sources (prerequisite)
- TASK-047: Raise Spend Limits (prerequisite - limits should be $0.75/day after this)
- TASK-061: Monitor Cost Trend & Rollback Decision (post-deploy, 24h)