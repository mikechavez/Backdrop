import asyncio
import logging
import re
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Iterable, List, Sequence, Dict, Any, Optional

from ..services.rss_service import RSSService
from ..db.operations.articles import create_or_update_articles
from ..db.operations.entity_mentions import create_entity_mentions_batch_idempotent
from ..db.operations.enrichment_state import (
    claim_batch,
    mark_completed,
    mark_failed,
    mark_skipped,
    renew_batch_leases,
    renew_lease,
    write_enriched_fields,
)
from ..llm.factory import get_llm_provider, get_optimized_llm
from ..db.mongodb import mongo_manager
from ..core.config import settings
from ..services.entity_normalization import normalize_entity_name
from ..services.selective_processor import create_processor
from ..services.relevance_classifier import classify_article

logger = logging.getLogger(__name__)

# Blacklist of sources to exclude from processing
# These sources contain advertising or low-quality content
BLACKLIST_SOURCES = ['benzinga']

_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "from",
    "have",
    "will",
    "into",
    "been",
    "after",
    "their",
    "about",
    "there",
    "would",
    "could",
    "should",
    "while",
    "where",
    "which",
    "among",
    "using",
    "against",
    "across",
    "still",
    "other",
    "between",
    "taking",
    "because",
    "until",
    "during",
    "under",
    "whose",
    "however",
    "today",
    "yesterday",
    "tomorrow",
    "news",
    "crypto",
    "cryptocurrency",
    "market",
    "markets",
    "price",
}

_MAX_KEYWORDS = 10

ENRICHMENT_ROTATION_STATE_COLLECTION = "enrichment_rotation_state"
ENRICHMENT_ROTATION_STATE_ID = "rss_fetcher_rotation_tick"


async def _next_rotation_tick(db) -> int:
    """Atomically increment and return the persisted fairness rotation counter.

    Persisted in MongoDB (not in-process memory) so the oldest-first fairness
    cadence survives worker restarts instead of resetting to 0 each time.
    """
    from pymongo import ReturnDocument

    collection = db[ENRICHMENT_ROTATION_STATE_COLLECTION]
    doc = await collection.find_one_and_update(
        {"_id": ENRICHMENT_ROTATION_STATE_ID},
        {"$inc": {"tick": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc["tick"]


async def fetch_and_process_rss_feeds():
    """Fetches RSS feeds, processes articles, and stores them."""
    rss_service = RSSService()
    articles = await rss_service.fetch_all_feeds()
    
    # Filter out blacklisted sources with detailed logging
    original_count = len(articles)
    logger.info(f"Fetched {original_count} articles from RSS feeds")
    
    # Log sources before filtering
    source_counts = {}
    for article in articles:
        source = article.source.lower()
        source_counts[source] = source_counts.get(source, 0) + 1
    logger.info(f"Articles by source before filtering: {source_counts}")
    
    # Apply blacklist filter
    articles = [a for a in articles if a.source.lower() not in BLACKLIST_SOURCES]
    filtered_count = original_count - len(articles)
    
    if filtered_count > 0:
        logger.warning(f"🚫 Filtered out {filtered_count} articles from blacklisted sources: {BLACKLIST_SOURCES}")
    else:
        logger.info(f"✅ No blacklisted articles found (blacklist: {BLACKLIST_SOURCES})")
    
    logger.info(f"Processing {len(articles)} articles after blacklist filter")
    await create_or_update_articles(articles)

    # Run LLM analysis on the newly fetched articles
    await process_new_articles_from_mongodb()


def _tokenize_for_keywords(text: str) -> Iterable[str]:
    for token in re.findall(r"\b[A-Za-z][A-Za-z0-9\-\$]{2,}\b", text):
        lowered = token.lower()
        if lowered in _STOPWORDS:
            continue
        if lowered.isdigit():
            continue
        yield token.strip("$#")


def _select_keywords(
    tokens: Sequence[str], max_keywords: int = _MAX_KEYWORDS
) -> List[str]:
    if not tokens:
        return []
    counter = Counter(tokens)
    sorted_tokens = sorted(
        counter.items(), key=lambda item: (-item[1], item[0].lower())
    )
    keywords: List[str] = []
    for word, _ in sorted_tokens:
        normalized = word.upper() if word.isupper() else word.title()
        if normalized not in keywords:
            keywords.append(normalized)
        if len(keywords) >= max_keywords:
            break
    return keywords


def _derive_sentiment_label(score: float) -> str:
    """Derive sentiment label from sentiment score."""
    if score is None:
        return "neutral"
    if score >= 0.4:
        return "positive"
    if score <= -0.4:
        return "negative"
    return "neutral"


def _normalize_entity(entity_value: str, entity_type: str) -> str:
    """Normalize entity values for consistency.

    Args:
        entity_value: Raw entity value from extraction
        entity_type: Type of entity (ticker, project, event)

    Returns:
        Normalized entity value
    """
    if not entity_value:
        return entity_value

    # Normalize tickers to uppercase
    if entity_type == "ticker":
        # Ensure $ prefix and uppercase
        if not entity_value.startswith("$"):
            entity_value = f"${entity_value}"
        return entity_value.upper()

    # Normalize project names to title case
    if entity_type == "project":
        # Common crypto project names that should be capitalized
        canonical_names = {
            "bitcoin": "Bitcoin",
            "ethereum": "Ethereum",
            "solana": "Solana",
            "cardano": "Cardano",
            "polkadot": "Polkadot",
            "avalanche": "Avalanche",
            "polygon": "Polygon",
            "chainlink": "Chainlink",
            "uniswap": "Uniswap",
            "aave": "Aave",
        }
        lower_value = entity_value.lower()
        if lower_value in canonical_names:
            return canonical_names[lower_value]
        # Default to title case
        return entity_value.title()

    # Normalize event types to lowercase
    if entity_type == "event":
        return entity_value.lower()

    return entity_value


def _deduplicate_entities(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate entities, keeping highest confidence for duplicates.

    Args:
        entities: List of entity dicts with type, value, confidence

    Returns:
        Deduplicated list of entities
    """
    # Group by (type, normalized_value)
    entity_map = {}

    for entity in entities:
        entity_type = entity.get("type")
        entity_value = entity.get("value")
        confidence = entity.get("confidence", 1.0)

        # Normalize the value
        normalized_value = _normalize_entity(entity_value, entity_type)
        key = (entity_type, normalized_value)

        # Keep entity with highest confidence
        if key not in entity_map or confidence > entity_map[key]["confidence"]:
            entity_map[key] = {
                "type": entity_type,
                "value": normalized_value,
                "confidence": confidence,
            }

    return list(entity_map.values())


async def _process_entity_extraction_batch(
    articles_batch: List[Dict[str, Any]], llm_client, retry_individual: bool = True
) -> Dict[str, Any]:
    """
    Processes a batch of articles for entity extraction with partial failure handling.

    Args:
        articles_batch: List of article dicts with _id, title, and text
        llm_client: LLM provider instance
        retry_individual: If True, retry failed articles individually

    Returns:
        Dict with extraction results, usage stats, and metrics
    """
    if not articles_batch:
        return {
            "results": [],
            "usage": {},
            "metrics": {"articles_processed": 0, "entities_extracted": 0},
        }

    start_time = time.time()

    # Prepare articles for batch processing
    batch_input = []
    article_id_map = {}

    for article in articles_batch:
        article_id = str(article.get("_id"))
        title = article.get("title") or ""
        body_parts = [
            article.get("text") or "",
            article.get("content") or "",
            article.get("description") or "",
        ]
        combined_text = " ".join(part.strip() for part in body_parts if part).strip()

        # Truncate text if too long (keep first 2000 chars)
        if len(combined_text) > 2000:
            combined_text = combined_text[:2000] + "..."

        batch_input.append(
            {
                "id": article_id,
                "title": title,
                "text": combined_text,
            }
        )
        article_id_map[article_id] = article

    # Call batch entity extraction
    try:
        result = llm_client.extract_entities_batch(batch_input)

        # Normalize and deduplicate entities in results
        for article_result in result.get("results", []):
            if "entities" in article_result:
                article_result["entities"] = _deduplicate_entities(
                    article_result["entities"]
                )

        processing_time = time.time() - start_time

        # Calculate metrics
        total_entities = sum(
            len(r.get("entities", [])) for r in result.get("results", [])
        )
        result["metrics"] = {
            "articles_processed": len(result.get("results", [])),
            "entities_extracted": total_entities,
            "processing_time": processing_time,
        }

        return result

    except Exception as exc:
        logger.exception("Batch entity extraction failed: %s", exc)

        # If retry_individual is enabled, try processing articles one by one
        if retry_individual and len(articles_batch) > 1:
            logger.info(
                "Retrying %d articles individually after batch failure",
                len(articles_batch),
            )
            return await _retry_individual_extractions(
                articles_batch, llm_client, start_time
            )

        return {
            "results": [],
            "usage": {},
            "metrics": {"articles_processed": 0, "entities_extracted": 0},
        }


async def _retry_individual_extractions(
    articles_batch: List[Dict[str, Any]], llm_client, start_time: float
) -> Dict[str, Any]:
    """
    Retry failed articles individually.

    Args:
        articles_batch: List of article dicts
        llm_client: LLM provider instance
        start_time: Start time of the original batch

    Returns:
        Combined results from individual extractions
    """
    all_results = []
    total_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "input_cost": 0.0,
        "output_cost": 0.0,
        "total_cost": 0.0,
    }
    failed_articles = []
    first_error = None
    first_error_type = None

    for article in articles_batch:
        article_id = str(article.get("_id"))
        try:
            # Process single article
            result = await _process_entity_extraction_batch(
                [article], llm_client, retry_individual=False
            )

            if result.get("results"):
                all_results.extend(result["results"])

                # Aggregate usage
                usage = result.get("usage", {})
                for key in total_usage:
                    total_usage[key] += usage.get(key, 0)
            else:
                failed_articles.append(article_id)

        except Exception as exc:
            failed_articles.append(article_id)
            if not first_error:
                first_error = str(exc)
                first_error_type = type(exc).__name__

    processing_time = time.time() - start_time
    total_entities = sum(len(r.get("entities", [])) for r in all_results)

    if failed_articles:
        log_msg = (
            "Individual extraction retry: %d articles failed (out of %d), "
            "sample_ids=%s"
        )
        log_args = [len(failed_articles), len(articles_batch), ", ".join(failed_articles[:5])]
        if first_error_type:
            log_msg += ", error_type=%s, error_sample=%s"
            log_args.extend([first_error_type, first_error[:100]])
        logger.warning(log_msg, *log_args)

    return {
        "results": all_results,
        "usage": total_usage,
        "metrics": {
            "articles_processed": len(all_results),
            "entities_extracted": total_entities,
            "processing_time": processing_time,
            "failed_articles": failed_articles,
        },
    }


async def _verify_mention_uniqueness_index(db) -> tuple[bool, str]:
    """Verify the article_entity_type_primary_unique index exists and is valid.

    The index is created only via the explicit, operator-gated rollout in
    entity_mentions_index_rollout.py (BUG-108 review: never automatically
    at application startup, to avoid crashing startup on pre-existing
    duplicate keys). Without a valid index, create_entity_mentions_batch_idempotent()'s
    upsert-plus-DuplicateKeyError-retry is NOT guaranteed safe under
    concurrent workers writing the same mention key at the same time.

    When the index is absent, invalid, or unverifiable, enrichment must be
    blocked (no claims, LLM calls, or writes) to preserve the concurrency
    guarantee. RSS ingestion and API availability are preserved (only
    enrichment is paused).

    Returns: (is_valid, diagnostic_message)
    """
    from ..db.operations.entity_mentions_index_rollout import verify_unique_index_exists_and_valid

    return await verify_unique_index_exists_and_valid(db.entity_mentions)


async def process_new_articles_from_mongodb():
    """
    Analyzes and enriches new articles from MongoDB that haven't been processed yet.

    Uses cost-optimized processing:
    - OptimizedAnthropicLLM with caching and Haiku model (12x cheaper)
    - SelectiveArticleProcessor to decide LLM vs regex extraction (~50% reduction)
    - Combined savings: ~85% cost reduction
    """
    db = await mongo_manager.get_async_database()
    collection = db.articles

    # Verify the mention-uniqueness guarantee once per run (cheap:
    # index_information() is a single fast call). When the index is absent,
    # invalid, or unverifiable, BLOCK enrichment (no claims, LLM, writes)
    # to preserve the concurrency guarantee. RSS ingestion and API remain
    # available (only enrichment pauses until the index is rolled out).
    index_is_valid, index_diagnostic = await _verify_mention_uniqueness_index(db)
    if not index_is_valid:
        logger.error(
            "⚠️ BLOCKING enrichment: entity_mentions unique index "
            "(article_entity_type_primary_unique) is INVALID or MISSING. "
            "Diagnostic: %s. Concurrent mention writes are not guaranteed safe. "
            "Operator must run the explicit index rollout "
            "(db/operations/entity_mentions_index_rollout.py: check_for_duplicate_mentions() "
            "then create_unique_index()). RSS ingestion and API remain available.",
            index_diagnostic,
        )
        return 0

    # Initialize optimized LLM with caching and cost tracking
    try:
        optimized_llm = await get_optimized_llm(db)
        logger.info("✅ Optimized LLM initialized with caching and cost tracking")
    except Exception as e:
        logger.error(f"Failed to initialize optimized LLM, falling back to standard: {e}")
        optimized_llm = None

    # Initialize selective processor
    selective_processor = create_processor(db)
    logger.info(f"✅ Selective processor initialized - {selective_processor.get_processing_stats()}")

    # Keep standard LLM for sentiment/relevance (not entity extraction)
    llm_client = get_llm_provider()

    # Claim a bounded batch of eligible articles via the durable enrichment
    # state machine (BUG-108). This atomically transitions each article to
    # IN_PROGRESS with a lease, so concurrent workers cannot double-process
    # the same article and interrupted runs can be safely recovered once
    # their lease expires.
    age_cutoff_days = settings.ENRICHMENT_AGE_CUTOFF_DAYS
    max_batch_articles = settings.ENRICHMENT_MAX_ARTICLES_PER_RUN

    cutoff_date = datetime.now(timezone.utc) - __import__('datetime').timedelta(days=age_cutoff_days)

    rotation_tick = await _next_rotation_tick(db)
    claim = await claim_batch(
        collection,
        cutoff_date=cutoff_date,
        limit=max_batch_articles,
        rotation_tick=rotation_tick,
    )
    owner_token = claim.owner_token

    if not claim.article_ids:
        logger.debug("No articles to enrich")
        return 0

    articles_list = []
    async for article in collection.find({"_id": {"$in": claim.article_ids}}):
        articles_list.append(article)

    logger.info(
        f"🚀 Processing {len(articles_list)} claimed article(s) with cost-optimized extraction "
        f"(owner_token={owner_token[:8]}..., rotation_tick={rotation_tick})"
    )

    # Tracks which claimed article ids this worker still holds a live lease
    # on. Renewed periodically below so a batch that legitimately takes
    # longer than the lease duration isn't silently reclaimed mid-processing;
    # any id that drops out of this set must not be written to again.
    live_lease_ids = set(claim.article_ids)

    # Process entity extraction using selective processing
    batch_size = settings.ENTITY_EXTRACTION_BATCH_SIZE
    entity_extraction_results = {}
    total_llm_processed = 0
    total_regex_processed = 0
    total_failed_extraction = 0
    first_extraction_error = None
    first_extraction_error_type = None
    failed_extraction_ids = []

    for i in range(0, len(articles_list), batch_size):
        raw_batch = articles_list[i : i + batch_size]

        # Renew leases before working this sub-batch; drop any article whose
        # lease has already been reclaimed by another worker so we never
        # extract/write for an article we no longer own.
        still_owned = await renew_batch_leases(
            collection, [a["_id"] for a in raw_batch], owner_token
        )
        still_owned_set = set(still_owned)
        lost_ids = {a["_id"] for a in raw_batch} - still_owned_set
        if lost_ids:
            logger.warning(
                "Lease lost for %d article(s) mid-batch (reclaimed by another worker); skipping",
                len(lost_ids),
            )
            live_lease_ids -= lost_ids
        batch = [a for a in raw_batch if a["_id"] in still_owned_set]

        if not batch:
            continue

        logger.info(
            "Processing entity extraction batch %d-%d of %d articles",
            i,
            min(i + batch_size, len(articles_list)),
            len(articles_list),
        )

        # Use selective processing if optimized LLM is available
        if optimized_llm:
            # Process each article with selective method
            for article in batch:
                article_id_str = str(article.get("_id"))

                # Decide processing method
                use_llm = selective_processor.should_use_llm(article)

                if use_llm:
                    # Use optimized LLM (with caching)
                    try:
                        entity_results = await optimized_llm.extract_entities_batch([{
                            "title": article.get("title", ""),
                            "text": article.get("text") or article.get("content") or article.get("description") or ""
                        }])
                        entities = entity_results[0].get("entities", []) if entity_results else []

                        # Convert to expected format
                        entity_extraction_results[article_id_str] = {
                            "article_id": article_id_str,
                            "primary_entities": [
                                {
                                    "name": e.get("name"),
                                    "type": e.get("type"),
                                    "confidence": e.get("confidence", 0.9),
                                    "ticker": None
                                }
                                for e in entities if e.get("is_primary", False)
                            ],
                            "context_entities": [
                                {
                                    "name": e.get("name"),
                                    "type": e.get("type"),
                                    "confidence": e.get("confidence", 0.9)
                                }
                                for e in entities if not e.get("is_primary", False)
                            ],
                            "sentiment": "neutral",
                            "method": "llm"
                        }
                        total_llm_processed += 1
                    except Exception as e:
                        # Fall back to regex after LLM failure
                        if not first_extraction_error:
                            first_extraction_error = str(e)
                            first_extraction_error_type = type(e).__name__
                        use_llm = False

                if not use_llm:
                    # Use regex extraction (free, fast)
                    try:
                        regex_entities = await selective_processor.extract_entities_simple(
                            article.get("_id"),
                            article
                        )

                        entity_extraction_results[article_id_str] = {
                            "article_id": article_id_str,
                            "primary_entities": [
                                {
                                    "name": e.get("entity"),
                                    "type": e.get("entity_type"),
                                    "confidence": e.get("confidence", 0.7),
                                    "ticker": None
                                }
                                for e in regex_entities if e.get("is_primary", False)
                            ],
                            "context_entities": [
                                {
                                    "name": e.get("entity"),
                                    "type": e.get("entity_type"),
                                    "confidence": e.get("confidence", 0.7)
                                }
                                for e in regex_entities if not e.get("is_primary", False)
                            ],
                            "sentiment": "neutral",
                            "method": "regex"
                        }
                        total_regex_processed += 1
                    except Exception as e:
                        # Both LLM and regex failed
                        if not first_extraction_error:
                            first_extraction_error = str(e)
                            first_extraction_error_type = type(e).__name__
                        total_failed_extraction += 1
                        if len(failed_extraction_ids) < 5:
                            failed_extraction_ids.append(article_id_str)
        else:
            # Fallback to original batch processing
            extraction_result = await _process_entity_extraction_batch(batch, llm_client)

            for result in extraction_result.get("results", []):
                article_id = result.get("article_id")
                if article_id:
                    entity_extraction_results[article_id] = result

            total_llm_processed += len(batch)

    # Log processing summary
    total_extraction_attempts = total_llm_processed + total_regex_processed + total_failed_extraction
    extraction_log = (
        "Entity extraction complete: articles=%d, llm=%d, regex=%d, failed=%d, "
        "cost_savings_percent=%.1f"
    )
    extraction_log_args = [
        total_extraction_attempts,
        total_llm_processed,
        total_regex_processed,
        total_failed_extraction,
        total_regex_processed / max(1, total_llm_processed + total_regex_processed) * 100,
    ]

    if total_failed_extraction > 0 and first_extraction_error_type:
        extraction_log += ", error_type=%s, sample_ids=%s, error_sample=%s"
        extraction_log_args.extend([
            first_extraction_error_type,
            ", ".join(failed_extraction_ids[:5]),
            first_extraction_error[:100],
        ])

    logger.info(extraction_log, *extraction_log_args)
    
    # Log cache stats if using optimized LLM
    if optimized_llm:
        try:
            cache_stats = await optimized_llm.get_cache_stats()

            logger.info(
                f"📈 Cache stats: {cache_stats.get('active_entries', 0)} entries, "
                f"{cache_stats.get('hit_rate_percent', 0):.1f}% hit rate"
            )
        except Exception as e:
            logger.warning(f"Failed to get cache/cost stats: {e}")

    # Now process articles in batches for enrichment (TASK-025: 50% cost reduction via batching)
    processed = 0
    tier_counts = {1: 0, 2: 0, 3: 0}  # Track tier distribution

    # Reuse the already-claimed articles_list (no second query) so we operate
    # on exactly the set of articles this worker holds a valid lease on.
    # Articles whose lease was lost during entity extraction (live_lease_ids
    # no longer contains them) are excluded here as well.
    articles_for_enrichment = []
    claimed_ids_without_text = []
    for article in articles_list:
        article_id = article.get("_id")
        if article_id not in live_lease_ids:
            continue
        title = article.get("title") or ""
        body_parts = [
            article.get("text") or "",
            article.get("content") or "",
            article.get("description") or "",
        ]
        combined_text = " ".join(
            part.strip() for part in [title, *body_parts] if part
        ).strip()

        if combined_text:
            articles_for_enrichment.append({
                "article_id": article_id,
                "combined_text": combined_text,
                "title": title,
                "source": article.get("source"),
                "original_article": article
            })
        else:
            # Claimed but no usable text: terminal skip so the lease doesn't
            # dangle and the article isn't reclaimed forever.
            claimed_ids_without_text.append(article_id)

    for article_id in claimed_ids_without_text:
        await mark_skipped(
            collection, article_id, owner_token, reason="no_usable_text"
        )

    # Process articles in batches of 10 (TASK-025 Priority 3: batch enrichment)
    BATCH_SIZE = 10
    total_enriched = 0

    for batch_start in range(0, len(articles_for_enrichment), BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, len(articles_for_enrichment))
        batch = articles_for_enrichment[batch_start:batch_end]

        logger.info(f"Processing batch {batch_start}-{batch_end}/{len(articles_for_enrichment)}")

        # Renew leases before working this enrichment batch; drop any article
        # whose lease was reclaimed by another worker.
        batch_ids = [a["article_id"] for a in batch]
        still_owned = await renew_batch_leases(collection, batch_ids, owner_token)
        still_owned_set = set(still_owned)
        lost_ids = set(batch_ids) - still_owned_set
        if lost_ids:
            logger.warning(
                "Lease lost for %d article(s) before enrichment batch; skipping",
                len(lost_ids),
            )
            live_lease_ids -= lost_ids
        batch = [a for a in batch if a["article_id"] in still_owned_set]

        if not batch:
            continue

        # TIER 1 ONLY: Classify all articles into tiers FIRST (rule-based, no LLM cost)
        tier_1_articles = []
        tier_classifications = {}  # Map article_id → {tier, reason}

        for article_data in batch:
            article_id = str(article_data["original_article"].get("_id"))

            # Classify article relevance tier (rule-based, no LLM cost)
            classification = classify_article(
                title=article_data["title"],
                text=article_data["combined_text"][:1000],
                source=article_data["source"]
            )

            tier_emoji = {1: "🔥", 2: "📰", 3: "🔇"}[classification["tier"]]
            tier_counts[classification["tier"]] += 1

            # Store classification for all articles
            tier_classifications[article_id] = {
                "tier": classification["tier"],
                "reason": classification["reason"],
            }

            # Only add tier 1 articles to enrichment queue
            if classification["tier"] == 1:
                tier_1_articles.append(article_data)
            else:
                # Tier 2-3: Save tier assignment only, skip enrichment entirely.
                # Fenced on ownership: a worker that lost its lease between the
                # renewal above and here must not write article content.
                await write_enriched_fields(
                    collection,
                    article_data["original_article"].get("_id"),
                    owner_token,
                    {
                        "relevance_tier": classification["tier"],
                        "relevance_reason": classification["reason"],
                        "updated_at": datetime.now(timezone.utc),
                    },
                )
                await mark_skipped(
                    collection,
                    article_data["original_article"].get("_id"),
                    owner_token,
                    reason=f"tier_{classification['tier']}_skip",
                )
                logger.debug(
                    f"Article {article_id}: tier {classification['tier']} assigned, "
                    f"enrichment skipped (TIER 1 ONLY mode)"
                )
                processed += 1

        # If no tier 1 articles, skip enrichment batch entirely
        if not tier_1_articles:
            logger.info(
                f"Batch {batch_start}-{batch_end}: No tier 1 articles, skipping enrichment"
            )
            continue

        logger.info(
            f"Enriching {len(tier_1_articles)} tier 1 articles "
            f"(batch {batch_start}-{batch_end} had {len(batch)} total)"
        )

        # Build prompt input ONLY for tier 1 articles
        batch_input = [
            {"id": str(a["article_id"]), "text": a["combined_text"]}
            for a in tier_1_articles
        ]

        # Track mention creation stats for batch-level summary
        batch_mentions_created = 0
        batch_articles_with_mentions = 0
        batch_mention_insert_failures = 0

        try:
            enrichment_results = await llm_client.enrich_articles_batch(batch_input)

            # Map results back to tier 1 articles only
            for enriched in enrichment_results:
                # Find matching article in tier 1 subset
                article_data = next(
                    (a for a in tier_1_articles if str(a["article_id"]) == enriched["id"]),
                    None
                )

                if not article_data:
                    continue

                article = article_data["original_article"]
                article_id = article.get("_id")

                # Use pre-computed tier classification (no re-classification needed)
                tier_info = tier_classifications[str(article_id)]
                relevance_tier = tier_info["tier"]
                relevance_reason = tier_info["reason"]

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

                # Batch-level tracking (no per-article logs)

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

                # Fenced write: enrich_articles_batch() above is a long-running
                # LLM call, so the lease may have expired and been reclaimed
                # by another worker while we were waiting on it. If so, this
                # write must not land -- the new owner may already be
                # processing (or have completed) this article.
                wrote_fields = await write_enriched_fields(
                    collection,
                    article_id,
                    owner_token,
                    {
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
                    },
                )
                if not wrote_fields:
                    logger.warning(
                        "Article %s: lease lost before enrichment write landed; "
                        "skipping mention persistence and completion for this article",
                        article_id_str,
                    )
                    live_lease_ids.discard(article_id)
                    continue

                # Create entity mentions for tracking
                article_source = article.get("source") or article.get("source_id") or "unknown"

                if primary_entities or context_entities:
                    mentions_to_create = []
                    batch_articles_with_mentions += 1

                    # Process primary entities
                    for entity in primary_entities:
                        entity_name = entity.get("name")
                        entity_type = entity.get("type")
                        ticker = entity.get("ticker")

                        # Ensure entity name is normalized (defense in depth)
                        if entity_name:
                            normalized_name = normalize_entity_name(entity_name)
                            if normalized_name != entity_name:
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

                    # Idempotent upsert of mentions: safe to retry after a
                    # partial write without creating duplicate mentions.
                    if mentions_to_create:
                        # entity_mentions is a separate collection with no
                        # owner_token of its own, so mark_completed()'s
                        # fencing on the article document alone is not
                        # enough. create_entity_mentions_batch_idempotent()
                        # enforces ownership atomically with the mention
                        # writes via a MongoDB transaction: a fenced
                        # conditional write to the article's ownership
                        # record and all mention upserts commit or abort as
                        # one unit, so a lease reclaimed at any point before
                        # commit results in zero mentions written rather
                        # than a stale insert.
                        try:
                            upserted = await create_entity_mentions_batch_idempotent(
                                mentions_to_create,
                                article_id=article_id,
                                owner_token=owner_token,
                            )
                            batch_mentions_created += upserted
                        except Exception as e:
                            batch_mention_insert_failures += 1
                            logger.error(f"Failed to insert entity mentions for {article_id_str}: {e}")
                            # Mention persistence is required before completion;
                            # mark this article failed/retryable rather than
                            # completed with missing mentions.
                            await mark_failed(
                                collection,
                                article_id,
                                owner_token,
                                error_reason="mention_persistence_failed",
                            )
                            processed += 1
                            continue

                # Only mark completed after all required writes (article
                # fields + mentions) have succeeded.
                completed = await mark_completed(collection, article_id, owner_token)
                if not completed:
                    logger.warning(
                        "Article %s completion write skipped: lease no longer owned "
                        "(likely reclaimed after expiry)",
                        article_id_str,
                    )

                processed += 1

            # Log batch-level entity mention summary
            if batch_mentions_created > 0:
                logger.info(
                    "Entity mentions batch: created=%d, articles_with_mentions=%d, insert_failures=%d",
                    batch_mentions_created,
                    batch_articles_with_mentions,
                    batch_mention_insert_failures,
                )

        except Exception as e:
            logger.error(f"Error enriching batch {batch_start}-{batch_end}: {e}")
            for article_data in tier_1_articles:
                await mark_failed(
                    collection,
                    article_data["article_id"],
                    owner_token,
                    error_reason="batch_enrichment_exception",
                )
            continue

    total_enriched = processed

    if total_enriched:
        logger.info(
            "✅ Batch enriched %s article(s) with sentiment, themes, keywords, and entities (TASK-025)",
            total_enriched,
        )
        # Log tier distribution
        logger.info(
            f"📊 Relevance tiers: 🔥 High={tier_counts[1]}, 📰 Medium={tier_counts[2]}, 🔇 Low={tier_counts[3]}"
        )
    return total_enriched

async def schedule_rss_fetch(interval_seconds: int, run_immediately: bool = False) -> None:
    """Continuously run the RSS fetcher on a fixed interval.
    
    Args:
        interval_seconds: Time to wait between RSS fetch cycles
        run_immediately: If True, run first fetch immediately on startup
    """
    logger.info(
        "Starting RSS fetcher schedule with interval %s seconds", interval_seconds
    )
    
    if run_immediately:
        logger.info("Running initial RSS fetch on startup...")
        try:
            await fetch_and_process_rss_feeds()
            logger.info("Initial RSS ingestion cycle completed")
        except Exception as exc:
            logger.exception("Initial RSS ingestion cycle failed: %s", exc)
    
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await fetch_and_process_rss_feeds()
            logger.info("RSS ingestion cycle completed")
        except asyncio.CancelledError:
            logger.info("RSS fetcher schedule cancelled")
            raise
        except Exception as exc:
            logger.exception("RSS ingestion cycle failed: %s", exc)
