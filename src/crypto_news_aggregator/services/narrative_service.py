"""
Narrative clustering service with salience-aware detection.

This service identifies narratives by:
- Extracting narrative elements (actors, tensions, nucleus entity) from articles
- Clustering articles by nucleus entity and weighted actor/tension overlap
- Merging shallow single-article narratives into substantial clusters
- Generating AI-powered narrative summaries
- Tracking narrative lifecycle (emerging, hot, mature, declining)

Supports both:
- NEW: Salience-based clustering (default) - uses nucleus entity and actor salience
- OLD: Theme-based clustering (fallback) - uses predefined theme categories

IMPORTANT: Narrative detection only includes articles with relevance_tier <= 2
(high and medium signal). Low-signal articles (tier 3) are excluded to
prevent noise from polluting narratives.
"""

import json
import logging
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from math import exp
from itertools import combinations
from collections import defaultdict, Counter

from ..db.mongodb import mongo_manager
from ..llm.factory import get_llm_provider
from ..db.operations.narratives import upsert_narrative
from .narrative_themes import (
    backfill_themes_for_recent_articles,
    get_articles_by_theme,
    generate_narrative_from_theme,
    backfill_narratives_for_recent_articles,
    cluster_by_narrative_salience,
    generate_narrative_from_cluster,
    merge_shallow_narratives,
    calculate_fingerprint_similarity,
    compute_narrative_fingerprint,
    THEME_CATEGORIES
)

logger = logging.getLogger(__name__)


# Narrative clustering configuration
SALIENCE_CLUSTERING_CONFIG = {
    'min_cluster_size': 3,           # Minimum articles per narrative
    'link_strength_threshold': 0.8,  # Threshold for clustering (0.0-2.0+)
    'core_actor_salience': 4.5,      # Minimum salience for "core" actor
    'merge_similarity_threshold': 0.5, # Minimum similarity to merge shallow narratives
    'ubiquitous_entities': {'Bitcoin', 'Ethereum', 'crypto', 'blockchain'},
}

# Blacklist of entities that should not become narrative nucleus entities
# These are typically advertising/promotional content or irrelevant entities
BLACKLIST_ENTITIES = {'Benzinga', 'Sarah Edwards'}

# Maximum relevance tier to include in narrative detection
# Tier 1 = high signal, Tier 2 = medium, Tier 3 = low (excluded)
MAX_RELEVANCE_TIER = 2


def calculate_recent_velocity(article_dates: List[datetime], lookback_days: int = 7) -> float:
    """
    Calculate article velocity based on recent activity (last N days).
    
    This provides a more accurate measure of current narrative momentum
    compared to dividing total articles by total time span.
    
    Args:
        article_dates: List of article publication dates
        lookback_days: Number of days to look back for velocity calculation (default: 7)
    
    Returns:
        Articles per day over the lookback period
    """
    if not article_dates:
        return 0.0
    
    # Get current time
    now = datetime.now(timezone.utc)
    
    # Filter articles from the last N days
    cutoff_date = now - timedelta(days=lookback_days)
    recent_articles = [d for d in article_dates if d >= cutoff_date]
    
    # Debug logging
    logger.info(f"[VELOCITY DEBUG] ========== VELOCITY CALCULATION START ==========")
    logger.info(f"[VELOCITY DEBUG] Total articles: {len(article_dates)}")
    logger.info(f"[VELOCITY DEBUG] Current time (now): {now} (UTC)")
    logger.info(f"[VELOCITY DEBUG] Cutoff date ({lookback_days} days ago): {cutoff_date} (UTC)")
    logger.info(f"[VELOCITY DEBUG] Time delta calculation: ({now} - {cutoff_date}).total_seconds() / 86400")
    logger.info(f"[VELOCITY DEBUG] Time delta result: {(now - cutoff_date).total_seconds() / 86400:.2f} days")
    logger.info(f"[VELOCITY DEBUG] Time delta in seconds: {(now - cutoff_date).total_seconds():.0f} seconds")
    
    # Log all article dates for debugging
    if article_dates:
        logger.info(f"[VELOCITY DEBUG] All article dates (sorted):")
        for i, date in enumerate(sorted(article_dates, reverse=True)):
            in_window = "✓ IN WINDOW" if date >= cutoff_date else "✗ EXCLUDED"
            logger.info(f"[VELOCITY DEBUG]   [{i+1}] {date} {in_window}")
    
    logger.info(f"[VELOCITY DEBUG] Articles within window: {len(recent_articles)}")
    if recent_articles:
        oldest = min(recent_articles)
        newest = max(recent_articles)
        logger.info(f"[VELOCITY DEBUG] Oldest article in window: {oldest}")
        logger.info(f"[VELOCITY DEBUG] Newest article in window: {newest}")
        logger.info(f"[VELOCITY DEBUG] Article span: {(newest - oldest).total_seconds() / 86400:.2f} days")
    
    logger.info(f"[VELOCITY DEBUG] Final calculation: {len(recent_articles)} articles / {lookback_days} days")
    logger.info(f"[VELOCITY DEBUG] Result: {len(recent_articles) / lookback_days:.2f} articles/day")
    logger.info(f"[VELOCITY DEBUG] ========== VELOCITY CALCULATION END ==========")
    
    # If no recent articles, return 0
    if not recent_articles:
        return 0.0
    
    # Calculate velocity: articles / lookback period
    # Always use the full lookback_days window for consistent velocity measurement
    return len(recent_articles) / lookback_days


def calculate_momentum(article_dates: List[datetime]) -> str:
    """
    Calculate momentum based on velocity change over time.
    
    Args:
        article_dates: Sorted list of article publication dates
    
    Returns:
        Momentum: "growing", "declining", "stable", or "unknown"
    """
    if len(article_dates) < 3:
        return "unknown"
    
    # Split articles into older and recent halves
    midpoint = len(article_dates) // 2
    recent_articles = article_dates[midpoint:]
    older_articles = article_dates[:midpoint]
    
    # Calculate time spans (in hours), minimum 1 hour to avoid division issues
    recent_span = (recent_articles[-1] - recent_articles[0]).total_seconds() / 3600
    older_span = (older_articles[-1] - older_articles[0]).total_seconds() / 3600
    
    # Use minimum of 1 hour to avoid division by zero or extreme values
    recent_span = max(1.0, recent_span)
    older_span = max(1.0, older_span)
    
    # Calculate velocities (articles per hour)
    recent_velocity = len(recent_articles) / recent_span
    older_velocity = len(older_articles) / older_span
    
    # Calculate velocity change ratio
    velocity_change = recent_velocity / older_velocity if older_velocity > 0 else 1
    
    # Determine momentum based on velocity change
    if velocity_change >= 1.3:
        return "growing"
    elif velocity_change <= 0.7:
        return "declining"
    else:
        return "stable"


def determine_lifecycle_state(
    article_count: int,
    mention_velocity: float,
    first_seen: datetime,
    last_updated: datetime,
    previous_state: Optional[str] = None
) -> tuple[str, Optional[datetime]]:
    """
    Determine the lifecycle state of a narrative based on activity patterns.

    Args:
        article_count: Current number of articles in narrative
        mention_velocity: Articles per day rate
        first_seen: When the narrative was first detected
        last_updated: When the narrative was last updated with new articles
        previous_state: Previous lifecycle state from lifecycle_history (optional)

    Returns:
        Tuple of (lifecycle_state, dormant_since):
        - lifecycle_state: emerging, rising, hot, cooling, dormant, echo, or reactivated
        - dormant_since: Timestamp when narrative entered dormant state (or None if not dormant)
    """
    # Calculate days since last update
    now = datetime.now(timezone.utc)
    days_since_update = (now - last_updated).total_seconds() / 86400  # 86400 seconds in a day

    # Calculate recent activity (last 24h and 48h)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_48h = now - timedelta(hours=48)

    # Estimate articles in last 24h and 48h based on velocity
    # This is an approximation; in practice, you'd query actual article timestamps
    articles_last_24h = mention_velocity * 1.0  # velocity is articles/day
    articles_last_48h = mention_velocity * 2.0

    # Check for reactivated state first: echo or dormant narrative with sustained activity (4+ articles in 48h)
    # This takes priority over echo to handle the transition properly
    if previous_state in ['echo', 'dormant'] and articles_last_48h >= 4:
        return ('reactivated', None)  # Clear dormant_since on reactivation

    # Check for echo state: dormant narrative with light activity (1-3 articles in 24h) but NOT sustained (< 4 in 48h)
    # Echo represents a brief "pulse" of activity, not sustained reactivation
    if previous_state == 'dormant' and 1 <= articles_last_24h <= 3 and articles_last_48h < 4:
        return ('echo', None)

    # Check for dormant or cooling states first (based on recency)
    if days_since_update >= 7:
        # Set dormant_since when transitioning to dormant
        dormant_since = now if previous_state != 'dormant' else None  # Only set on transition
        return ('dormant', dormant_since)
    elif days_since_update >= 3:
        return ('cooling', None)

    # Check for hot state (high activity)
    if article_count >= 7 or mention_velocity >= 3.0:
        return ('hot', None)

    # Check for rising state (moderate velocity, not yet hot)
    if mention_velocity >= 1.5 and article_count < 7:
        return ('rising', None)

    # Default to emerging for new/small narratives
    if article_count < 4:
        return ('emerging', None)

    # Fallback for edge cases (4-6 articles, low velocity, recent)
    return ('emerging', None)


def update_lifecycle_history(
    narrative: Dict[str, Any],
    lifecycle_state: str,
    article_count: int,
    mention_velocity: float
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Update lifecycle history by tracking state transitions and resurrection metrics.
    
    Checks if the current lifecycle_state differs from the last entry in
    lifecycle_history. If different or if lifecycle_history doesn't exist,
    appends a new entry with state, timestamp, article_count, and mention_velocity.
    
    When transitioning to 'reactivated' state, also tracks resurrection metrics:
    - reawakening_count: Number of times narrative has been reactivated
    - reawakened_from: Timestamp when narrative went dormant
    - resurrection_velocity: Articles per day in last 48 hours
    
    Args:
        narrative: Narrative dict (may or may not have lifecycle_history)
        lifecycle_state: Current lifecycle state to track
        article_count: Current number of articles in narrative
        mention_velocity: Current articles per day rate
    
    Returns:
        Tuple of (updated lifecycle_history array, resurrection_fields dict)
    
    Example:
        >>> narrative = {'lifecycle_history': [{'state': 'emerging', 'timestamp': ...}]}
        >>> history, resurrection = update_lifecycle_history(narrative, 'rising', 5, 2.3)
        >>> len(history)
        2
    """
    # Get existing lifecycle_history or initialize as empty array
    lifecycle_history = narrative.get('lifecycle_history', [])
    
    # Initialize resurrection fields dict
    resurrection_fields = {}
    
    # Check if we need to add a new entry
    should_add_entry = False
    
    if not lifecycle_history:
        # No history exists, add first entry
        should_add_entry = True
    else:
        # Check if state differs from last entry
        last_entry = lifecycle_history[-1]
        last_state = last_entry.get('state')
        
        if last_state != lifecycle_state:
            should_add_entry = True
            
            # Track resurrection if transitioning to 'reactivated' state
            if lifecycle_state == 'reactivated':
                # Find when narrative went dormant by looking backwards in history
                dormant_timestamp = None
                for entry in reversed(lifecycle_history):
                    if entry.get('state') in ['dormant', 'echo']:
                        dormant_timestamp = entry.get('timestamp')
                        break
                
                # Increment reawakening_count
                current_count = narrative.get('reawakening_count', 0)
                resurrection_fields['reawakening_count'] = current_count + 1
                
                # Set reawakened_from timestamp
                if dormant_timestamp:
                    resurrection_fields['reawakened_from'] = dormant_timestamp
                
                # Calculate resurrection_velocity (articles in last 48 hours / 2)
                # Use mention_velocity as proxy: velocity is articles/day, so multiply by 2 for 48h
                resurrection_velocity = mention_velocity * 2.0
                resurrection_fields['resurrection_velocity'] = round(resurrection_velocity, 2)
                
                logger.info(
                    f"Resurrection detected: count={resurrection_fields['reawakening_count']}, "
                    f"velocity={resurrection_fields['resurrection_velocity']:.2f}"
                )
    
    # Add new entry if needed
    if should_add_entry:
        new_entry = {
            'state': lifecycle_state,
            'timestamp': datetime.now(timezone.utc),
            'article_count': article_count,
            'mention_velocity': round(mention_velocity, 2)
        }
        lifecycle_history.append(new_entry)
        
        logger.debug(
            f"Added lifecycle history entry: {lifecycle_state} "
            f"(articles: {article_count}, velocity: {mention_velocity:.2f})"
        )
    
    return lifecycle_history, resurrection_fields


def calculate_grace_period(mention_velocity: float) -> int:
    """
    Calculate adaptive grace period based on narrative velocity.
    
    Fast-burning narratives get shorter matching windows, slow-burn narratives
    get longer windows. This prevents stale matches for hot topics while allowing
    longer-term tracking of slower narratives.
    
    Args:
        mention_velocity: Articles per day rate
    
    Returns:
        Grace period in days (7-30 days)
    
    Examples:
        >>> calculate_grace_period(3.0)  # High velocity
        7
        >>> calculate_grace_period(1.0)  # Medium velocity
        14
        >>> calculate_grace_period(0.3)  # Low velocity
        30
    """
    # Formula: min(30, max(7, int(14 / max(mention_velocity, 0.5))))
    # - High velocity (>2 articles/day): 7 days
    # - Medium velocity (~1 article/day): 14 days
    # - Low velocity (<0.5 articles/day): 30 days
    return min(30, max(7, int(14 / max(mention_velocity, 0.5))))


def validate_article_mentions_entity(
    article: Dict[str, Any],
    nucleus_entity: str,
    require_exact_match: bool = True
) -> bool:
    """
    Validate that article actually mentions the narrative's nucleus entity.

    This is a final safety check to prevent articles from being assigned to
    narratives they're not actually about.

    Args:
        article: Article document with title and text fields
        nucleus_entity: Narrative's nucleus entity (e.g., "Coinbase", "Bitcoin")
        require_exact_match: If True, require exact entity name match (default True)

    Returns:
        True if article mentions nucleus_entity, False otherwise

    Example:
        >>> article = {"title": "Coinbase Stock Surges", "text": "Coinbase reported..."}
        >>> validate_article_mentions_entity(article, "Coinbase")
        True

        >>> article = {"title": "Sharps Technology", "text": "Sharps announced..."}
        >>> validate_article_mentions_entity(article, "Coinbase")
        False
    """
    if not nucleus_entity:
        return False

    # Get article text
    title = (article.get("title") or "").lower()
    text = (article.get("text") or "").lower()
    entity_lower = nucleus_entity.lower()

    # Check for exact word boundary match
    # This prevents "Bit" matching "Bitcoin" or "Coin" matching "Coinbase"
    pattern = r'\b' + re.escape(entity_lower) + r'\b'

    found_in_title = bool(re.search(pattern, title))
    found_in_text = bool(re.search(pattern, text))

    return found_in_title or found_in_text


def determine_lifecycle_stage(
    article_count: int,
    mention_velocity: float,
    momentum: str = "unknown"
) -> str:
    """
    Determine the lifecycle stage of a narrative with momentum awareness.
    
    DEPRECATED: Use determine_lifecycle_state instead for new code.
    
    Args:
        article_count: Current number of articles in narrative
        mention_velocity: Articles per day rate
        momentum: Momentum indicator (growing, declining, stable, unknown)
    
    Returns:
        Lifecycle stage: emerging, rising, hot, heating, mature, cooling, or declining
    """
    # Calculate base lifecycle with adjusted thresholds
    if mention_velocity >= 5:
        lifecycle = "mature"
    elif mention_velocity >= 1.5:
        lifecycle = "hot"
    elif article_count >= 5:
        lifecycle = "hot"
    else:
        lifecycle = "emerging"
    
    # Integrate momentum to refine lifecycle
    if lifecycle == "mature" and momentum == "declining":
        return "cooling"
    elif lifecycle == "hot" and momentum == "growing":
        return "heating"
    elif lifecycle == "emerging" and momentum == "growing":
        return "rising"
    
    return lifecycle


async def find_matching_narrative(
    fingerprint: Dict[str, Any],
    within_days: int = 14,
    cluster_velocity: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    """
    Find an existing narrative that matches the given fingerprint.
    
    Searches for narratives within a time window and calculates similarity
    using fingerprint comparison. Uses adaptive thresholds based on narrative
    recency to allow easier continuation of recent stories while maintaining
    strict matching for older narratives.
    
    Adaptive Threshold Strategy:
    - Recent narratives (updated within 48h): 0.5 threshold
      Allows near-term continuations to merge more easily, accounting for
      natural variance in actor mentions and phrasing.
    - Older narratives (>48h): 0.6 threshold
      Maintains strict matching to prevent unrelated stories from merging.
    
    Args:
        fingerprint: Narrative fingerprint dict with nucleus_entity, top_actors, key_actions
        within_days: Time window in days to search for matching narratives (default 14)
        cluster_velocity: Optional cluster mention velocity for adaptive grace period
    
    Returns:
        Best matching narrative dict if similarity exceeds adaptive threshold, otherwise None
    
    Example:
        >>> fingerprint = {
        ...     'nucleus_entity': 'SEC',
        ...     'top_actors': ['SEC', 'Binance', 'Coinbase'],
        ...     'key_actions': ['filed lawsuit', 'regulatory enforcement']
        ... }
        >>> narrative = await find_matching_narrative(fingerprint, within_days=14)
        >>> if narrative:
        ...     print(f"Found matching narrative: {narrative['title']}")
    """
    try:
        # Calculate adaptive grace period if cluster velocity provided
        if cluster_velocity is not None:
            within_days = calculate_grace_period(cluster_velocity)
            logger.debug(
                f"Using adaptive grace period: {within_days} days "
                f"(velocity: {cluster_velocity:.2f} articles/day)"
            )
        
        db = await mongo_manager.get_async_database()
        narratives_collection = db.narratives
        
        # Calculate time window
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=within_days)
        
        # Query for active narratives within time window
        active_statuses = ['emerging', 'rising', 'hot', 'cooling', 'dormant', 'echo', 'reactivated']
        query = {
            'last_updated': {'$gte': cutoff_time},
            '$or': [
                {'status': {'$in': active_statuses}},
                {'lifecycle_state': {'$in': active_statuses}}
            ]
        }
        
        cursor = narratives_collection.find(query)
        candidates = await cursor.to_list(length=None)
        
        if not candidates:
            logger.debug(f"No candidate narratives found within {within_days} days")
            return None
        
        logger.info(f"Evaluating {len(candidates)} candidate narratives for similarity")
        
        # Calculate similarity for each candidate
        best_match = None
        best_similarity = 0.0
        best_threshold = 0.6  # Track which threshold applies to best match
        
        # Calculate 48-hour cutoff for adaptive threshold
        now = datetime.now(timezone.utc)
        recent_cutoff = now - timedelta(hours=48)
        
        for candidate in candidates:
            # Extract fingerprint from candidate narrative
            candidate_fingerprint = candidate.get('fingerprint')
            if not candidate_fingerprint:
                # Try to construct fingerprint from legacy fields
                candidate_fingerprint = {
                    'nucleus_entity': candidate.get('theme', ''),
                    'top_actors': candidate.get('entities', []),
                    'key_actions': []  # Legacy narratives may not have actions
                }
            
            # Calculate similarity
            similarity = calculate_fingerprint_similarity(fingerprint, candidate_fingerprint)
            
            # Determine adaptive threshold based on last_updated
            candidate_last_updated = candidate.get('last_updated')
            # Ensure timezone-aware for comparison
            if candidate_last_updated and candidate_last_updated.tzinfo is None:
                candidate_last_updated = candidate_last_updated.replace(tzinfo=timezone.utc)
            if candidate_last_updated and candidate_last_updated >= recent_cutoff:
                # Recent narrative (within 48h): use lower threshold (0.5)
                threshold = 0.5
                recency_label = "recent (48h)"
            else:
                # Older narrative: use stricter threshold (0.6)
                threshold = 0.6
                recency_label = "older (>48h)"
            
            logger.debug(
                f"Narrative '{candidate.get('title', 'unknown')}' similarity: {similarity:.3f} "
                f"(threshold: {threshold}, {recency_label})"
            )
            
            # Track best match that meets its threshold
            if similarity >= threshold and similarity > best_similarity:
                best_similarity = similarity
                best_match = candidate
                best_threshold = threshold
        
        # Return best match if found
        if best_match:
            logger.info(
                f"Found matching narrative: '{best_match.get('title')}' "
                f"(similarity: {best_similarity:.3f}, threshold: {best_threshold})"
            )
            return best_match
        else:
            logger.info(
                f"No matching narrative found - best similarity: {best_similarity:.3f} "
                f"(adaptive thresholds: 0.5 for recent, 0.6 for older)"
            )
            return None
    
    except Exception as e:
        logger.exception(f"Error finding matching narrative: {e}")
        return None


async def should_reactivate_or_create_new(
    fingerprint: Dict[str, Any],
    nucleus_entity: Optional[str] = None
) -> tuple[str, Optional[Dict[str, Any]]]:
    """
    Decide whether to reactivate a dormant narrative or create a new one.

    Checks for dormant narratives with the same nucleus_entity within the 30-day
    reactivation window and calculates similarity. Returns reactivation decision.

    Args:
        fingerprint: Current cluster fingerprint with nucleus_entity, narrative_focus, etc.
        nucleus_entity: Primary nucleus entity (optional, extracted from fingerprint if not provided)

    Returns:
        Tuple of (decision, matched_narrative):
        - decision: "reactivate" or "create_new"
        - matched_narrative: The dormant narrative to reactivate (or None if creating new)
    """
    try:
        # Get nucleus_entity from fingerprint if not provided
        entity = nucleus_entity or fingerprint.get('nucleus_entity', '')
        if not entity:
            logger.warning("Cannot check reactivation - no nucleus_entity in fingerprint")
            return ("create_new", None)

        # Log reactivation decision process
        logger.info(f"Checking for narrative reactivation: entity='{entity}'")
        logger.debug(f"Input fingerprint: {fingerprint}")

        db = await mongo_manager.get_async_database()
        narratives_collection = db.narratives

        # Query for dormant narratives with same nucleus_entity
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)

        dormant_query = {
            "nucleus_entity": entity,
            "lifecycle_state": "dormant",
            "dormant_since": {"$gte": thirty_days_ago}  # Within 30-day reactivation window
        }

        cursor = narratives_collection.find(dormant_query)
        dormant_candidates = await cursor.to_list(length=None)

        logger.debug(f"Found {len(dormant_candidates)} dormant narrative(s) within 30-day window")

        if not dormant_candidates:
            logger.debug(f"No dormant narratives found for entity '{entity}'")
            return ("create_new", None)

        # Log details of each candidate
        for i, candidate in enumerate(dormant_candidates):
            logger.debug(
                f"  Candidate {i+1}: "
                f"ID={candidate.get('_id')}, "
                f"Title={candidate.get('title')}, "
                f"DormantSince={candidate.get('dormant_since')}"
            )

        # Calculate similarity for each candidate
        best_match = None
        best_similarity = 0.0

        for i, candidate in enumerate(dormant_candidates):
            candidate_fingerprint = candidate.get('fingerprint', {})
            if not candidate_fingerprint:
                logger.warning(f"Candidate {candidate['_id']} missing fingerprint - skipping")
                continue

            # Calculate similarity
            similarity = calculate_fingerprint_similarity(fingerprint, candidate_fingerprint)

            logger.debug(
                f"Candidate {i+1} similarity: {similarity:.3f} "
                f"(title='{candidate.get('title')}', focus='{candidate_fingerprint.get('narrative_focus')}')"
            )

            # Track best match
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = candidate

        # Decision threshold (calibrated for weighted scoring)
        # Reactivation is safer than initial matching, so 0.8 threshold is appropriate
        # - 0.5 weight focus + 0.3 weight nucleus = 0.8 (matches when both aligned)
        # - Additional actor/action overlap pushes above 0.8
        REACTIVATION_THRESHOLD = 0.80
        logger.debug(f"Best similarity: {best_similarity:.3f}, threshold: {REACTIVATION_THRESHOLD}")

        if best_match and best_similarity >= REACTIVATION_THRESHOLD:
            dormant_since = best_match.get('dormant_since', now)
            # Handle timezone-aware vs naive datetime comparison
            if dormant_since.tzinfo is None:
                dormant_since = dormant_since.replace(tzinfo=timezone.utc)
            dormant_days = (now - dormant_since).total_seconds() / 86400
            logger.info(
                f"REACTIVATING narrative: {best_match['_id']} | "
                f"similarity={best_similarity:.3f} | dormant_days={dormant_days:.1f}"
            )
            return ("reactivate", best_match)
        else:
            logger.debug(
                f"No reactivation match: best_similarity={best_similarity:.3f}, "
                f"threshold={REACTIVATION_THRESHOLD}, has_match={bool(best_match)}"
            )
            return ("create_new", None)

    except Exception as e:
        logger.exception(f"Error in reactivation check: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return ("create_new", None)


async def _reactivate_narrative(
    dormant_narrative: Dict[str, Any],
    new_article_ids: List[str],
    cluster: List[Dict[str, Any]],
    fingerprint: Dict[str, Any]
) -> str:
    """
    Reactivate a dormant narrative by merging new articles and updating state.

    Args:
        dormant_narrative: The dormant narrative document to reactivate
        new_article_ids: Article IDs from the new cluster
        cluster: The cluster articles for extracting metrics
        fingerprint: Current cluster fingerprint

    Returns:
        The ID of the reactivated narrative
    """
    from bson import ObjectId

    db = await mongo_manager.get_async_database()
    narratives_collection = db.narratives
    articles_collection = db.articles

    narrative_id = dormant_narrative["_id"]
    now = datetime.now(timezone.utc)

    # 1. Deduplicate article IDs
    existing_articles = set(str(aid) for aid in dormant_narrative.get("article_ids", []))
    new_articles_set = set(str(aid) for aid in new_article_ids)

    # Validate that existing articles still exist in the database
    if existing_articles:
        valid_existing = await articles_collection.distinct(
            "_id",
            {"_id": {"$in": [ObjectId(aid) if aid.isalnum() and len(aid) == 24 else aid for aid in existing_articles]}}
        )
        existing_articles = set(str(aid) for aid in valid_existing)
        logger.info(f"[REACTIVATE VALIDATION] Existing articles: {len(valid_existing)} valid out of {len(dormant_narrative.get('article_ids', []))}")

    combined_article_ids = list(existing_articles | new_articles_set)

    # 2. Recalculate sentiment (weighted average)
    existing_sentiment = dormant_narrative.get("avg_sentiment", 0.0)
    existing_count = len(existing_articles)

    # Extract sentiment from new articles if available
    new_sentiment = 0.0
    for article in cluster:
        if str(article.get("_id")) in new_articles_set:
            article_sentiment = article.get("sentiment_score", 0.0)
            new_sentiment += article_sentiment

    new_count = len(new_articles_set)
    if new_count > 0:
        new_sentiment = new_sentiment / new_count

    # Weighted average
    total_weight = existing_count + new_count
    if total_weight > 0:
        combined_sentiment = (existing_sentiment * existing_count + new_sentiment * new_count) / total_weight
    else:
        combined_sentiment = 0.0

    # 3. Update lifecycle state to reactivated
    lifecycle_state = "reactivated"

    # 4. Increment reactivation counter
    reactivated_count = dormant_narrative.get("reactivated_count", 0) + 1

    # 5. Clear dormant_since timestamp
    dormant_since_value = None

    # 6. Update lifecycle history
    lifecycle_history = dormant_narrative.get("lifecycle_history", [])

    # Calculate new velocity for lifecycle history
    article_dates = []
    for article in cluster:
        if str(article.get("_id")) in new_articles_set:
            pub_date = article.get("published_at")
            if pub_date:
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=timezone.utc)
                article_dates.append(pub_date)

    new_velocity = calculate_recent_velocity(article_dates, lookback_days=7)

    # Add reactivation entry to lifecycle history
    lifecycle_history.append({
        "state": lifecycle_state,
        "timestamp": now,
        "article_count": len(combined_article_ids),
        "mention_velocity": round(new_velocity, 2)
    })

    # 7. Update narrative in database
    await narratives_collection.update_one(
        {"_id": narrative_id},
        {
            "$set": {
                "article_ids": combined_article_ids,
                "article_count": len(combined_article_ids),
                "avg_sentiment": combined_sentiment,
                "lifecycle_state": lifecycle_state,
                "lifecycle_history": lifecycle_history,
                "reactivated_count": reactivated_count,
                "dormant_since": dormant_since_value,
                "last_updated": now,
                "mention_velocity": round(new_velocity, 2)
            }
        }
    )

    logger.info(
        f"REACTIVATED narrative {narrative_id}: "
        f"merged {len(new_articles_set)} articles, "
        f"total {len(combined_article_ids)} articles, "
        f"reactivation #{reactivated_count}"
    )

    return str(narrative_id)


async def extract_entities_from_articles(articles: List[Dict[str, Any]]) -> List[str]:
    """
    Extract all unique entities mentioned across a list of articles.
    
    Args:
        articles: List of article documents
    
    Returns:
        List of unique entity names
    """
    from bson import ObjectId
    
    db = await mongo_manager.get_async_database()
    entity_mentions_collection = db.entity_mentions
    
    entities = set()
    
    for article in articles:
        article_id = article.get("_id")
        
        # entity_mentions.article_id has mixed formats (ObjectId and string)
        # Query for both to handle legacy data
        cursor = entity_mentions_collection.find({
            "$or": [
                {"article_id": article_id},        # ObjectId format
                {"article_id": str(article_id)}    # String format
            ]
        })
        async for mention in cursor:
            entity = mention.get("entity")
            if entity:
                entities.add(entity)
    
    return list(entities)


async def detect_narratives(
    hours: int = 48,
    min_articles: int = 3,
    use_salience_clustering: bool = True
) -> List[Dict[str, Any]]:
    """
    Detect narratives using salience-aware clustering.
    
    Args:
        hours: Lookback window for articles
        min_articles: Minimum articles per narrative cluster
        use_salience_clustering: Use new salience-based system (vs old theme-based)
    
    Returns:
        List of narrative dicts with full structure including lifecycle tracking
    """
    try:
        if use_salience_clustering:
            # NEW: Use salience-aware clustering
            logger.info(f"Using salience-based narrative detection for last {hours} hours")
            
            # Backfill narrative data for recent articles if needed
            backfilled_count = await backfill_narratives_for_recent_articles(hours=hours)
            logger.info(f"Backfilled narrative data for {backfilled_count} articles")
            
            # Get recent articles with narrative data
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            db = await mongo_manager.get_async_database()
            articles_collection = db.articles
            
            # Filter for high-signal articles only (tier 1 & 2)
            # Include articles with no tier yet (unclassified) for backward compatibility
            # EXCLUDE degraded narratives (status="degraded") to prevent quality degradation
            cursor = articles_collection.find({
                "published_at": {"$gte": cutoff_time},
                "narrative_summary": {"$exists": True},  # Has narrative data
                "status": {"$ne": "degraded"},  # Exclude degraded narratives
                "$or": [
                    {"relevance_tier": {"$lte": MAX_RELEVANCE_TIER}},
                    {"relevance_tier": {"$exists": False}},
                    {"relevance_tier": None},
                ]
            })
            
            articles = await cursor.to_list(length=None)
            logger.info(f"Found {len(articles)} articles with narrative data in last {hours}h")
            
            if not articles:
                logger.warning("No articles with narrative data found")
                return []
            
            # Cluster articles by nucleus entity and weighted overlap
            clusters = await cluster_by_narrative_salience(
                articles,
                min_cluster_size=min_articles
            )
            
            logger.info(f"Created {len(clusters)} narrative clusters")

            # Process each cluster: compute fingerprint, check for matches, merge or create
            saved_narratives = []
            matched_count = 0
            created_count = 0
            
            for cluster in clusters:
                # Build cluster data dict for fingerprint computation
                # Aggregate nucleus entities, narrative focuses, actors, and actions from cluster articles
                nucleus_entities = []
                narrative_focuses = []
                all_actors = {}
                all_actions = []

                for article in cluster:
                    # Skip if article is not a dict (defensive programming)
                    if not isinstance(article, dict):
                        logger.warning(f"Skipping non-dict article in cluster: {type(article)}")
                        continue

                    nucleus = article.get('nucleus_entity')
                    if nucleus:
                        nucleus_entities.append(nucleus)

                    # Aggregate narrative focus
                    focus = article.get('narrative_focus')
                    if focus:
                        narrative_focuses.append(focus.lower().strip())

                    # Aggregate actors with salience
                    actors = article.get('actors', [])
                    actor_salience = article.get('actor_salience', {})

                    # Handle actors as list or dict
                    if isinstance(actors, list):
                        for actor in actors:
                            salience = actor_salience.get(actor, 3) if isinstance(actor_salience, dict) else 3
                            all_actors[actor] = max(all_actors.get(actor, 0), salience)

                    # Aggregate actions
                    narrative_summary = article.get('narrative_summary', {})
                    if isinstance(narrative_summary, dict):
                        actions = narrative_summary.get('actions', [])
                        if isinstance(actions, list):
                            all_actions.extend(actions)

                # Determine primary nucleus (most common)
                nucleus_counts = Counter(nucleus_entities)
                primary_nucleus = nucleus_counts.most_common(1)[0][0] if nucleus_counts else ''

                # Determine primary focus (most common)
                focus_counts = Counter(narrative_focuses)
                primary_focus = focus_counts.most_common(1)[0][0] if focus_counts else ''

                # Build cluster dict for fingerprint
                cluster_data = {
                    'nucleus_entity': primary_nucleus,
                    'narrative_focus': primary_focus,
                    'actors': all_actors,
                    'actions': list(set(all_actions))[:5]  # Unique actions, top 5
                }
                
                # Compute fingerprint from cluster data
                fingerprint = compute_narrative_fingerprint(cluster_data)
                logger.debug(f"Computed fingerprint for cluster with nucleus_entity: {fingerprint.get('nucleus_entity')}")
                
                # Check if nucleus_entity is blacklisted (advertising/promotional content)
                nucleus_entity = fingerprint.get('nucleus_entity', '')
                if nucleus_entity in BLACKLIST_ENTITIES:
                    logger.info(f"Skipping blacklisted nucleus_entity: {nucleus_entity}")
                    continue
                
                # Calculate cluster velocity for adaptive grace period
                cluster_article_count = len(cluster)
                # Use the detection window (hours) to estimate velocity
                cluster_time_span_days = hours / 24.0
                cluster_velocity = cluster_article_count / cluster_time_span_days if cluster_time_span_days > 0 else 0
                
                # Check for matching existing narrative with adaptive grace period
                matching_narrative = await find_matching_narrative(
                    fingerprint,
                    cluster_velocity=cluster_velocity
                )
                
                if matching_narrative:
                    # Update existing narrative by appending new articles
                    matched_count += 1
                    narrative_id = str(matching_narrative['_id'])
                    logger.debug(
                        f"Match found for cluster with nucleus '{primary_nucleus}': "
                        f"merging into narrative '{matching_narrative.get('title')}' (ID: {narrative_id})"
                    )
                    
                    # Get existing article_ids and append new ones from cluster
                    existing_article_ids = set(matching_narrative.get('article_ids', []))
                    # Extract article_ids from cluster articles
                    new_article_ids = set(str(article.get('_id')) for article in cluster if isinstance(article, dict))
                    combined_article_ids = list(existing_article_ids | new_article_ids)
                    
                    # Calculate updated metrics for lifecycle_state
                    updated_article_count = len(combined_article_ids)
                    first_seen = matching_narrative.get('first_seen', datetime.now(timezone.utc))
                    # Ensure first_seen is timezone-aware
                    if first_seen.tzinfo is None:
                        first_seen = first_seen.replace(tzinfo=timezone.utc)
                    last_updated = datetime.now(timezone.utc)
                    
                    # Calculate mention velocity based on recent activity (last 7 days)
                    # Fetch article dates for velocity calculation
                    article_dates = []
                    for article in articles:
                        if str(article.get('_id')) in combined_article_ids:
                            pub_date = article.get('published_at')
                            if pub_date:
                                # Ensure timezone-aware
                                if pub_date.tzinfo is None:
                                    pub_date = pub_date.replace(tzinfo=timezone.utc)
                                article_dates.append(pub_date)
                    
                    # Use recent velocity calculation (last 7 days) for more accurate current activity
                    mention_velocity = calculate_recent_velocity(article_dates, lookback_days=7)
                    
                    # Get previous state from lifecycle_history
                    lifecycle_history_existing = matching_narrative.get('lifecycle_history', [])
                    previous_state = lifecycle_history_existing[-1].get('state') if lifecycle_history_existing else None
                    
                    # Calculate lifecycle_state for updated narrative
                    lifecycle_state, dormant_since = determine_lifecycle_state(
                        updated_article_count, mention_velocity, first_seen, last_updated, previous_state
                    )

                    # Update lifecycle history and get resurrection fields
                    lifecycle_history, resurrection_fields = update_lifecycle_history(
                        matching_narrative,
                        lifecycle_state,
                        updated_article_count,
                        mention_velocity
                    )
                    
                    # Use upsert_narrative to ensure timestamp validation
                    # Get theme from existing narrative or fingerprint
                    theme = matching_narrative.get('theme') or fingerprint.get('nucleus_entity', 'unknown')
                    title = matching_narrative.get('title', 'Unknown')
                    summary = matching_narrative.get('summary', '')
                    
                    # DEBUG: Log all article dates and timestamp calculation
                    logger.info(f"[MERGE NARRATIVE DEBUG] ========== MERGE UPSERT START ==========")
                    logger.info(f"[MERGE NARRATIVE DEBUG] Theme: {theme}")
                    logger.info(f"[MERGE NARRATIVE DEBUG] Title: {title}")
                    logger.info(f"[MERGE NARRATIVE DEBUG] Combined article IDs: {combined_article_ids}")
                    logger.info(f"[MERGE NARRATIVE DEBUG] Article dates collected: {len(article_dates)}")
                    if article_dates:
                        logger.info(f"[MERGE NARRATIVE DEBUG] Article dates (sorted):")
                        for i, date in enumerate(sorted(article_dates)):
                            logger.info(f"[MERGE NARRATIVE DEBUG]   [{i+1}] {date}")
                        logger.info(f"[MERGE NARRATIVE DEBUG] Earliest article: {min(article_dates)}")
                        logger.info(f"[MERGE NARRATIVE DEBUG] Latest article: {max(article_dates)}")
                    logger.info(f"[MERGE NARRATIVE DEBUG] Existing narrative first_seen: {matching_narrative.get('first_seen')}")
                    logger.info(f"[MERGE NARRATIVE DEBUG] Calculated first_seen (from existing or now): {first_seen}")
                    logger.info(f"[MERGE NARRATIVE DEBUG] Calculated last_updated (now): {last_updated}")
                    logger.info(f"[MERGE NARRATIVE DEBUG] Is first_seen > last_updated? {first_seen > last_updated}")
                    logger.info(f"[MERGE NARRATIVE DEBUG] Timestamp sources: first_seen from existing narrative, last_updated from now()")
                    logger.info(f"[MERGE NARRATIVE DEBUG] ========== MERGE UPSERT END ==========")

                    # Post-clustering validation: Ensure articles mention nucleus_entity
                    nucleus_entity = fingerprint.get('nucleus_entity', '')
                    if nucleus_entity and combined_article_ids:
                        # Filter article_ids to only include articles mentioning nucleus_entity
                        validated_article_ids = []
                        rejected_articles = []

                        for article_id in combined_article_ids:
                            # Find the article in the original articles list
                            article = next((a for a in articles if str(a.get("_id")) == str(article_id)), None)

                            if article and validate_article_mentions_entity(article, nucleus_entity):
                                validated_article_ids.append(article_id)
                            else:
                                rejected_articles.append({
                                    "article_id": article_id,
                                    "title": article.get("title", "") if article else "unknown"
                                })

                        # Log rejected articles
                        if rejected_articles:
                            logger.info(
                                f"Post-cluster validation: {len(rejected_articles)} articles rejected from "
                                f"'{nucleus_entity}' narrative",
                                extra={
                                    "narrative_nucleus": nucleus_entity,
                                    "total_clustered": len(combined_article_ids),
                                    "validated": len(validated_article_ids),
                                    "rejected": len(rejected_articles)
                                }
                            )
                            for rejected in rejected_articles:
                                logger.warning(
                                    f"Post-cluster validation rejected article from narrative",
                                    extra={
                                        "narrative_nucleus": nucleus_entity,
                                        "article_title": rejected["title"][:100],
                                        "article_id": str(rejected["article_id"]),
                                        "reason": "nucleus_entity_not_in_text"
                                    }
                                )

                        # Update with validated articles
                        combined_article_ids = validated_article_ids
                        updated_article_count = len(validated_article_ids)

                    try:
                        narrative_id = await upsert_narrative(
                            theme=theme,
                            title=title,
                            summary=summary,
                            entities=matching_narrative.get('entities', []),
                            article_ids=combined_article_ids,
                            article_count=updated_article_count,
                            mention_velocity=round(mention_velocity, 2),
                            lifecycle=matching_narrative.get('lifecycle', 'unknown'),
                            momentum=matching_narrative.get('momentum', 'unknown'),
                            recency_score=matching_narrative.get('recency_score', 0.0),
                            entity_relationships=matching_narrative.get('entity_relationships', []),
                            first_seen=first_seen,
                            lifecycle_state=lifecycle_state,
                            lifecycle_history=lifecycle_history,
                            reawakening_count=resurrection_fields.get('reawakening_count') if resurrection_fields else None,
                            reawakened_from=resurrection_fields.get('reawakened_from') if resurrection_fields else None,
                            resurrection_velocity=resurrection_fields.get('resurrection_velocity') if resurrection_fields else None,
                            dormant_since=dormant_since
                        )
                        
                        logger.info(
                            f"Merged {len(new_article_ids)} new articles into existing narrative: "
                            f"'{title}' (ID: {narrative_id})"
                        )
                        
                        # Fetch updated narrative for return value
                        db = await mongo_manager.get_async_database()
                        updated_narrative = await db.narratives.find_one({'_id': matching_narrative['_id']})
                        if updated_narrative:
                            saved_narratives.append(updated_narrative)
                    except Exception as e:
                        logger.exception(f"Failed to update narrative '{theme}': {e}")
                        # Still add to saved narratives with local data
                        matching_narrative['article_ids'] = combined_article_ids
                        matching_narrative['article_count'] = updated_article_count
                        matching_narrative['last_updated'] = last_updated
                        matching_narrative['mention_velocity'] = round(mention_velocity, 2)
                        matching_narrative['lifecycle_state'] = lifecycle_state
                        matching_narrative['lifecycle_history'] = lifecycle_history
                        saved_narratives.append(matching_narrative)
                    
                else:
                    # No match found - check for reactivation before creating new
                    reactivation_decision, reactivated_candidate = await should_reactivate_or_create_new(
                        fingerprint, nucleus_entity=primary_nucleus
                    )

                    if reactivation_decision == "reactivate" and reactivated_candidate:
                        # Reactivate dormant narrative instead of creating new
                        logger.info(
                            f"Reactivating dormant narrative '{reactivated_candidate.get('title')}' "
                            f"for nucleus entity '{primary_nucleus}'"
                        )
                        narrative_id = await _reactivate_narrative(
                            reactivated_candidate,
                            [str(article.get("_id")) for article in cluster if isinstance(article, dict)],
                            cluster,
                            fingerprint
                        )

                        # Fetch and return the updated narrative
                        db = await mongo_manager.get_async_database()
                        updated_narrative = await db.narratives.find_one({"_id": reactivated_candidate["_id"]})
                        if updated_narrative:
                            saved_narratives.append(updated_narrative)
                    else:
                        # Create new narrative
                        created_count += 1
                        narrative = await generate_narrative_from_cluster(cluster)

                        if not narrative:
                            logger.warning(f"Failed to generate narrative for cluster with nucleus: {cluster.get('nucleus_entity')}")
                            continue

                        # Add fingerprint to narrative data
                        narrative['fingerprint'] = fingerprint
                        narrative['needs_summary_update'] = False  # Fresh summary, no update needed

                        narrative_data = narrative
                        # Calculate mention velocity (articles per day) based on recent activity
                        article_count = narrative_data.get("article_count", 0)

                        # Get articles for this narrative to extract dates
                        article_ids = narrative_data.get("article_ids", [])
                        article_dates = []
                        articles_found = 0
                        for article in articles:
                            if str(article.get("_id")) in article_ids:
                                articles_found += 1
                                pub_date = article.get("published_at")
                                if pub_date:
                                    # Ensure timezone-aware
                                    if pub_date.tzinfo is None:
                                        pub_date = pub_date.replace(tzinfo=timezone.utc)
                                    article_dates.append(pub_date)

                        # DEBUG: Log if we're missing articles
                        if articles_found != len(article_ids):
                            logger.warning(f"[CREATE NARRATIVE] Only found {articles_found}/{len(article_ids)} articles in articles list!")

                        # Use recent velocity calculation (last 7 days) for more accurate current activity
                        mention_velocity = calculate_recent_velocity(article_dates, lookback_days=7)

                        # Calculate momentum from article dates

                        # Sort dates and calculate momentum
                        article_dates.sort()
                        momentum = calculate_momentum(article_dates)

                        # Calculate recency score (0-1, higher = more recent)
                        newest_article = article_dates[-1] if article_dates else None
                        if newest_article:
                            # Ensure newest_article is timezone-aware
                            if newest_article.tzinfo is None:
                                newest_article = newest_article.replace(tzinfo=timezone.utc)
                            hours_since_last_update = (datetime.now(timezone.utc) - newest_article).total_seconds() / 3600
                            recency_score = exp(-hours_since_last_update / 24)  # 24h half-life
                        else:
                            recency_score = 0.0

                        # Determine lifecycle stage with momentum awareness (legacy)
                        lifecycle = determine_lifecycle_stage(article_count, mention_velocity, momentum)

                        # Determine lifecycle state (new approach)
                        # Use article dates for first_seen and last_updated, not now()
                        if article_dates:
                            first_seen = min(article_dates)
                            last_updated = max(article_dates)
                            logger.info(f"[CREATE NARRATIVE] Using article dates: first_seen={first_seen}, last_updated={last_updated}, article_count={len(article_dates)}")
                        else:
                            # Fallback to now() if no article dates available
                            first_seen = datetime.now(timezone.utc)
                            last_updated = datetime.now(timezone.utc)
                            logger.warning(f"[CREATE NARRATIVE] NO ARTICLE DATES! Using now(): first_seen={first_seen}, last_updated={last_updated}")
                        # No previous state for new narratives
                        lifecycle_state, dormant_since = determine_lifecycle_state(
                            article_count, mention_velocity, first_seen, last_updated, previous_state=None
                        )

                        # Initialize lifecycle history for new narrative
                        lifecycle_history, resurrection_fields = update_lifecycle_history(
                            {},  # Empty dict for new narrative
                            lifecycle_state,
                            article_count,
                            mention_velocity
                        )

                        # Use nucleus_entity as theme for database compatibility
                        theme = narrative_data.get("nucleus_entity", "unknown")

                        # Enrich narrative_data with computed fields for return value
                        narrative_data["theme"] = theme
                        narrative_data["entities"] = narrative_data.get("actors", [])[:10]
                        narrative_data["mention_velocity"] = round(mention_velocity, 2)
                        narrative_data["lifecycle"] = lifecycle
                        narrative_data["lifecycle_state"] = lifecycle_state
                        narrative_data["lifecycle_history"] = lifecycle_history
                        narrative_data["momentum"] = momentum
                        narrative_data["recency_score"] = round(recency_score, 3)

                        # DEBUG: Log all article dates and timestamp calculation for new narrative
                        logger.info(f"[CREATE NARRATIVE DEBUG] ========== CREATE UPSERT START ==========")
                        logger.info(f"[CREATE NARRATIVE DEBUG] Theme: {theme}")
                        logger.info(f"[CREATE NARRATIVE DEBUG] Title: {narrative_data.get('title')}")
                        logger.info(f"[CREATE NARRATIVE DEBUG] Article IDs: {narrative_data['article_ids']}")
                        logger.info(f"[CREATE NARRATIVE DEBUG] Article dates collected: {len(article_dates)}")
                        if article_dates:
                            logger.info(f"[CREATE NARRATIVE DEBUG] Article dates (sorted):")
                            for i, date in enumerate(sorted(article_dates)):
                                logger.info(f"[CREATE NARRATIVE DEBUG]   [{i+1}] {date}")
                            logger.info(f"[CREATE NARRATIVE DEBUG] Earliest article: {min(article_dates)}")
                            logger.info(f"[CREATE NARRATIVE DEBUG] Latest article: {max(article_dates)}")
                        else:
                            logger.warning(f"[CREATE NARRATIVE DEBUG] NO ARTICLE DATES FOUND!")
                        logger.info(f"[CREATE NARRATIVE DEBUG] Calculated first_seen (now): {first_seen}")
                        logger.info(f"[CREATE NARRATIVE DEBUG] Calculated last_updated (now): {last_updated}")
                        logger.info(f"[CREATE NARRATIVE DEBUG] Is first_seen > last_updated? {first_seen > last_updated}")
                        logger.info(f"[CREATE NARRATIVE DEBUG] Timestamp sources: BOTH from now() - THIS IS THE BUG!")
                        logger.info(f"[CREATE NARRATIVE DEBUG] Should use: first_seen = min(article_dates), last_updated = max(article_dates)")
                        logger.info(f"[CREATE NARRATIVE DEBUG] ========== CREATE UPSERT END ==========")

                        try:
                            # Validate fingerprint before creation
                            if not fingerprint or not fingerprint.get('nucleus_entity'):
                                logger.error(f"Cannot create narrative - invalid fingerprint: {fingerprint}")
                                raise ValueError("Narrative fingerprint must have a valid nucleus_entity")

                            # Post-clustering validation: Ensure articles mention nucleus_entity
                            nucleus_entity = narrative_data.get("nucleus_entity", "")
                            article_ids = narrative_data.get("article_ids", [])

                            if nucleus_entity and article_ids:
                                # Filter article_ids to only include articles mentioning nucleus_entity
                                validated_article_ids = []
                                rejected_articles = []

                                for article_id in article_ids:
                                    # Find the article in the original articles list
                                    article = next((a for a in articles if str(a.get("_id")) == str(article_id)), None)

                                    if article and validate_article_mentions_entity(article, nucleus_entity):
                                        validated_article_ids.append(article_id)
                                    else:
                                        rejected_articles.append({
                                            "article_id": article_id,
                                            "title": article.get("title", "") if article else "unknown"
                                        })

                                # Log rejected articles
                                if rejected_articles:
                                    logger.info(
                                        f"Post-cluster validation: {len(rejected_articles)} articles rejected from "
                                        f"'{nucleus_entity}' narrative",
                                        extra={
                                            "narrative_nucleus": nucleus_entity,
                                            "total_clustered": len(article_ids),
                                            "validated": len(validated_article_ids),
                                            "rejected": len(rejected_articles)
                                        }
                                    )
                                    for rejected in rejected_articles:
                                        logger.warning(
                                            f"Post-cluster validation rejected article from narrative",
                                            extra={
                                                "narrative_nucleus": nucleus_entity,
                                                "article_title": rejected["title"][:100],
                                                "article_id": str(rejected["article_id"]),
                                                "reason": "nucleus_entity_not_in_text"
                                            }
                                        )

                                # Update narrative with validated articles
                                narrative_data["article_ids"] = validated_article_ids
                                narrative_data["article_count"] = len(validated_article_ids)
                                article_count = len(validated_article_ids)

                            # Use upsert_narrative to ensure timestamp validation
                            narrative_id = await upsert_narrative(
                                theme=theme,
                                title=narrative_data["title"],
                                summary=narrative_data["summary"],
                                entities=narrative_data.get("actors", [])[:10],
                                article_ids=narrative_data["article_ids"],
                                article_count=article_count,
                                mention_velocity=round(mention_velocity, 2),
                                lifecycle=lifecycle,
                                momentum=momentum,
                                recency_score=round(recency_score, 3),
                                entity_relationships=narrative_data.get("entity_relationships", []),
                                first_seen=first_seen,
                                lifecycle_state=lifecycle_state,
                                lifecycle_history=lifecycle_history,
                                dormant_since=dormant_since
                            )

                            logger.info(f"Created new narrative {narrative_id}: {narrative_data['title']}")
                            saved_narratives.append(narrative_data)
                        except Exception as e:
                            logger.exception(f"Failed to save narrative '{narrative_data.get('title')}': {e}")
            
            logger.info(
                f"Narrative detection complete: {matched_count} merged into existing, "
                f"{created_count} newly created, {len(saved_narratives)} total"
            )
            return saved_narratives
        
        else:
            # OLD: Use theme-based clustering (fallback)
            logger.info(f"Using theme-based narrative detection for last {hours} hours")
            
            # Step 1: Backfill themes for recent articles that don't have them
            backfilled = await backfill_themes_for_recent_articles(hours=hours, limit=100)
            logger.info(f"Backfilled themes for {backfilled} articles")
            
            # Step 2: Get existing narratives for comparison (lifecycle tracking)
            db = await mongo_manager.get_async_database()
            narratives_collection = db.narratives
            existing_narratives = {}
            async for narrative in narratives_collection.find({}):
                theme = narrative.get("theme")
                if theme:
                    existing_narratives[theme] = narrative
            
            # Step 3: For each theme, find articles and create narratives
            narratives = []
            
            for theme in THEME_CATEGORIES:
                # Get articles for this theme
                articles = await get_articles_by_theme(theme, hours=hours, min_articles=min_articles)
                
                if not articles:
                    continue
                
                logger.info(f"Found {len(articles)} articles for theme '{theme}'")
                
                # Extract entities from these articles
                entities = await extract_entities_from_articles(articles)
                
                # Generate narrative summary
                narrative_content = await generate_narrative_from_theme(theme, articles)
                
                if not narrative_content:
                    logger.warning(f"Failed to generate narrative for theme '{theme}'")
                    continue
                
                # Calculate mention velocity (articles per day)
                article_count = len(articles)
                time_span_days = hours / 24.0
                mention_velocity = article_count / time_span_days if time_span_days > 0 else 0
                
                # Get first_seen for lifecycle tracking
                first_seen = datetime.now(timezone.utc)
                if theme in existing_narratives:
                    first_seen = existing_narratives[theme].get("first_seen", first_seen)
                
                # Calculate momentum from article dates
                article_dates = sorted([a.get("published_at") for a in articles if a.get("published_at")])
                momentum = calculate_momentum(article_dates)
                
                # Calculate recency score (0-1, higher = more recent)
                newest_article = article_dates[-1] if article_dates else None
                if newest_article:
                    # Ensure newest_article is timezone-aware
                    if newest_article.tzinfo is None:
                        newest_article = newest_article.replace(tzinfo=timezone.utc)
                    hours_since_last_update = (datetime.now(timezone.utc) - newest_article).total_seconds() / 3600
                    recency_score = exp(-hours_since_last_update / 24)  # 24h half-life
                else:
                    recency_score = 0.0
                
                # Determine lifecycle stage with momentum awareness (legacy)
                lifecycle = determine_lifecycle_stage(article_count, mention_velocity, momentum)
                
                # Get previous state from existing narrative's lifecycle_history
                existing_narrative = existing_narratives.get(theme, {})
                lifecycle_history_existing = existing_narrative.get('lifecycle_history', [])
                previous_state = lifecycle_history_existing[-1].get('state') if lifecycle_history_existing else None

                # Determine lifecycle state (new approach)
                last_updated = datetime.now(timezone.utc)
                lifecycle_state, dormant_since = determine_lifecycle_state(
                    article_count, mention_velocity, first_seen, last_updated, previous_state
                )
                
                # Update lifecycle history (check existing narrative for history)
                lifecycle_history, resurrection_fields = update_lifecycle_history(
                    existing_narrative,
                    lifecycle_state,
                    article_count,
                    mention_velocity
                )
                
                # Build narrative document
                narrative = {
                    "theme": theme,
                    "title": narrative_content["title"],
                    "summary": narrative_content["summary"],
                    "entities": entities[:10],  # Limit to top 10 entities
                    "article_ids": [str(a["_id"]) for a in articles],
                    "first_seen": first_seen,
                    "last_updated": last_updated,
                    "article_count": article_count,
                    "mention_velocity": round(mention_velocity, 2),
                    "lifecycle": lifecycle,
                    "lifecycle_state": lifecycle_state,
                    "lifecycle_history": lifecycle_history,
                    "momentum": momentum,
                    "recency_score": round(recency_score, 3)
                }
                
                narratives.append(narrative)
                logger.info(f"Created narrative for theme '{theme}': {article_count} articles, lifecycle={lifecycle}, lifecycle_state={lifecycle_state}, momentum={momentum}")
                
                # Save narrative to database
                try:
                    # Prepare upsert arguments with resurrection fields if present
                    upsert_args = {
                        "theme": narrative["theme"],
                        "title": narrative["title"],
                        "summary": narrative["summary"],
                        "entities": narrative["entities"],
                        "article_ids": narrative["article_ids"],
                        "article_count": narrative["article_count"],
                        "mention_velocity": narrative["mention_velocity"],
                        "lifecycle": narrative["lifecycle"],
                        "momentum": narrative["momentum"],
                        "recency_score": narrative["recency_score"],
                        "first_seen": narrative["first_seen"],
                        "lifecycle_state": narrative["lifecycle_state"],
                        "lifecycle_history": narrative["lifecycle_history"],
                        "dormant_since": dormant_since
                    }

                    # Add resurrection fields if present
                    if resurrection_fields:
                        if "reawakening_count" in resurrection_fields:
                            upsert_args["reawakening_count"] = resurrection_fields["reawakening_count"]
                        if "reawakened_from" in resurrection_fields:
                            upsert_args["reawakened_from"] = resurrection_fields["reawakened_from"]
                        if "resurrection_velocity" in resurrection_fields:
                            upsert_args["resurrection_velocity"] = resurrection_fields["resurrection_velocity"]

                    narrative_id = await upsert_narrative(**upsert_args)
                    logger.info(f"Saved narrative {narrative_id} to database")
                except Exception as e:
                    logger.exception(f"Failed to save narrative for theme '{theme}': {e}")
            
            logger.info(f"Generated {len(narratives)} theme-based narratives")
            return narratives

    except Exception as e:
        logger.exception(f"Error in detect_narratives: {e}")
        return []


async def consolidate_duplicate_narratives() -> Dict[str, Any]:
    """
    Find and merge duplicate narratives (similarity ≥0.9).

    Returns:
        Dict with merge_count, merged_pairs, errors
    """
    logger.info("Starting narrative consolidation pass")

    db = await mongo_manager.get_async_database()
    narratives_collection = db.narratives
    articles_collection = db.articles

    # Only consolidate active narratives (not dormant or merged)
    active_states = ["emerging", "rising", "hot", "cooling"]
    narratives = await narratives_collection.find({
        "lifecycle_state": {"$in": active_states}
    }).to_list(length=None)

    logger.info(f"Found {len(narratives)} active narratives to check")

    # Group by nucleus_entity
    narratives_by_entity = {}
    for narrative in narratives:
        entity = narrative.get("nucleus_entity")
        if not entity:
            continue
        if entity not in narratives_by_entity:
            narratives_by_entity[entity] = []
        narratives_by_entity[entity].append(narrative)

    # Find high-similarity pairs within each entity group
    merge_count = 0
    merged_pairs = []
    errors = []

    for entity, entity_narratives in narratives_by_entity.items():
        if len(entity_narratives) < 2:
            continue

        logger.info(f"Checking {len(entity_narratives)} narratives for {entity}")

        # Check all pairs
        for n1, n2 in combinations(entity_narratives, 2):
            try:
                # Compute similarity using existing fingerprint method
                fp1 = n1.get("fingerprint", {})
                fp2 = n2.get("fingerprint", {})

                # IMPORTANT: Requires narrative_focus in fingerprint
                if not fp1.get("narrative_focus") or not fp2.get("narrative_focus"):
                    logger.warning(f"Skipping merge check - missing narrative_focus: {n1['_id']} or {n2['_id']}")
                    continue

                similarity = calculate_fingerprint_similarity(fp1, fp2)

                if similarity >= 0.9:
                    logger.info(f"High similarity ({similarity:.3f}) between {n1['_id']} and {n2['_id']}")

                    # Merge n2 into n1 (keep larger narrative)
                    if n2.get("article_count", 0) > n1.get("article_count", 0):
                        n1, n2 = n2, n1  # Swap so n1 is larger

                    await _merge_narratives(n1, n2, similarity, db)
                    merge_count += 1
                    merged_pairs.append({
                        "survivor": str(n1["_id"]),
                        "merged": str(n2["_id"]),
                        "similarity": similarity
                    })

            except Exception as e:
                logger.error(f"Error merging {n1['_id']} and {n2['_id']}: {e}")
                errors.append({
                    "n1": str(n1["_id"]),
                    "n2": str(n2["_id"]),
                    "error": str(e)
                })

    logger.info(f"Consolidation complete: {merge_count} merges, {len(errors)} errors")

    return {
        "merge_count": merge_count,
        "merged_pairs": merged_pairs,
        "errors": errors
    }


async def _merge_narratives(survivor: Dict, merged: Dict, similarity: float, db) -> None:
    """
    Merge two narratives: combine data into survivor, mark merged as merged.

    Args:
        survivor: Narrative to keep (larger article count)
        merged: Narrative to merge in (will be marked merged)
        similarity: Similarity score for logging
        db: MongoDB database instance
    """
    narratives_collection = db.narratives
    articles_collection = db.articles

    survivor_id = survivor["_id"]
    merged_id = merged["_id"]

    logger.info(f"Merging {merged_id} into {survivor_id} (similarity={similarity:.3f})")

    # 1. Combine article_ids (deduplicate)
    survivor_articles = set(survivor.get("article_ids", []))
    merged_articles = set(merged.get("article_ids", []))

    # Validate that article IDs exist in the database
    from bson import ObjectId
    all_article_ids = survivor_articles | merged_articles

    if all_article_ids:
        # Filter for valid ObjectId format
        valid_ids_to_check = []
        for aid in all_article_ids:
            try:
                # Try to convert to ObjectId if it looks like one
                if isinstance(aid, str) and len(aid) == 24 and aid.isalnum():
                    valid_ids_to_check.append(ObjectId(aid))
                else:
                    valid_ids_to_check.append(aid)
            except:
                valid_ids_to_check.append(aid)

        valid_articles = await articles_collection.distinct(
            "_id",
            {"_id": {"$in": valid_ids_to_check}}
        )
        valid_articles_set = set(str(aid) for aid in valid_articles)

        removed_count = len(all_article_ids) - len(valid_articles_set)
        if removed_count > 0:
            logger.warning(f"[MERGE VALIDATION] Removing {removed_count} invalid article references from {len(all_article_ids)} total")

        combined_articles = list(valid_articles_set)
    else:
        combined_articles = []

    # 2. Recalculate metrics
    combined_article_count = len(combined_articles)

    # Take weighted average of sentiment (by article count)
    survivor_sentiment = survivor.get("avg_sentiment", 0.0)
    merged_sentiment = merged.get("avg_sentiment", 0.0)
    survivor_weight = len(survivor_articles)
    merged_weight = len(merged_articles)
    total_weight = survivor_weight + merged_weight

    if total_weight > 0:
        combined_sentiment = (
            (survivor_sentiment * survivor_weight + merged_sentiment * merged_weight)
            / total_weight
        )
    else:
        combined_sentiment = 0.0

    # 3. Merge timeline_data (combine and sum overlapping dates)
    survivor_timeline = {t["date"]: t for t in survivor.get("timeline_data", [])}
    merged_timeline = merged.get("timeline_data", [])

    for entry in merged_timeline:
        date = entry["date"]
        if date in survivor_timeline:
            # Sum metrics for overlapping dates
            survivor_timeline[date]["article_count"] = survivor_timeline[date].get("article_count", 0) + entry.get("article_count", 0)
            survivor_timeline[date]["velocity"] = survivor_timeline[date].get("velocity", 0.0) + entry.get("velocity", 0.0)

            # Combine entities (deduplicate)
            survivor_entities = set(survivor_timeline[date].get("entities", []))
            merged_entities = set(entry.get("entities", []))
            survivor_timeline[date]["entities"] = list(survivor_entities | merged_entities)
        else:
            # Add new date entry
            survivor_timeline[date] = entry

    combined_timeline = sorted(survivor_timeline.values(), key=lambda x: x["date"])

    # 4. Lifecycle state - take most advanced
    state_precedence = {
        "emerging": 1,
        "rising": 2,
        "hot": 3,
        "cooling": 4,
        "dormant": 5
    }
    survivor_state = survivor.get("lifecycle_state", "emerging")
    merged_state = merged.get("lifecycle_state", "emerging")

    if state_precedence.get(merged_state, 0) > state_precedence.get(survivor_state, 0):
        combined_state = merged_state
    else:
        combined_state = survivor_state

    # 5. Update survivor narrative
    await narratives_collection.update_one(
        {"_id": survivor_id},
        {
            "$set": {
                "article_ids": combined_articles,
                "article_count": combined_article_count,
                "avg_sentiment": combined_sentiment,
                "timeline_data": combined_timeline,
                "lifecycle_state": combined_state,
                "last_updated": datetime.now(timezone.utc)
            }
        }
    )

    # 6. Mark merged narrative
    await narratives_collection.update_one(
        {"_id": merged_id},
        {
            "$set": {
                "merged_into": survivor_id,
                "lifecycle_state": "merged",
                "last_updated": datetime.now(timezone.utc)
            }
        }
    )

    # 7. Update article references
    await articles_collection.update_many(
        {"narrative_id": merged_id},
        {"$set": {"narrative_id": survivor_id}}
    )

    logger.info(f"Merge complete: {merged_id} → {survivor_id} ({combined_article_count} articles)")
