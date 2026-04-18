"""
Database operations for narrative tracking.

Narratives represent theme-based clusters of articles
with AI-generated summaries and lifecycle tracking.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from crypto_news_aggregator.db.mongodb import mongo_manager


def _should_append_timeline_snapshot(existing: Optional[Dict[str, Any]]) -> bool:
    """
    Determine if we should append a new timeline snapshot.
    
    Only append if:
    - No existing timeline data, OR
    - Last snapshot is from a different day (UTC)
    
    Args:
        existing: Existing narrative document or None
    
    Returns:
        True if we should append a new snapshot
    """
    if not existing:
        return True
    
    timeline_data = existing.get("timeline_data", [])
    if not timeline_data:
        return True
    
    # Get the last snapshot date
    last_snapshot = timeline_data[-1]
    last_date_str = last_snapshot.get("date")
    
    if not last_date_str:
        return True
    
    # Check if today is different from last snapshot date
    today = datetime.now(timezone.utc).date().isoformat()
    return today != last_date_str


def _calculate_days_active(first_seen: datetime) -> int:
    """
    Calculate number of days a narrative has been active.
    
    Args:
        first_seen: When narrative was first detected
    
    Returns:
        Number of days (minimum 1)
    """
    now = datetime.now(timezone.utc)
    # Ensure first_seen is timezone-aware
    if first_seen.tzinfo is None:
        first_seen = first_seen.replace(tzinfo=timezone.utc)
    delta = now - first_seen
    return max(1, delta.days + 1)  # +1 to count partial days


async def upsert_narrative(
    theme: str,
    title: str,
    summary: str,
    entities: List[str],
    article_ids: List[str],
    article_count: int,
    mention_velocity: float,
    lifecycle: str,
    momentum: str = "unknown",
    recency_score: float = 0.0,
    entity_relationships: Optional[List[Dict[str, Any]]] = None,
    first_seen: Optional[datetime] = None,
    lifecycle_state: Optional[str] = None,
    lifecycle_history: Optional[List[Dict[str, Any]]] = None,
    reawakening_count: Optional[int] = None,
    reawakened_from: Optional[datetime] = None,
    resurrection_velocity: Optional[float] = None,
    dormant_since: Optional[datetime] = None,
    reactivated_count: Optional[int] = None,
    needs_summary_update: Optional[bool] = None
) -> str:
    """
    Create or update a narrative record with full structure and timeline tracking.

    Upserts based on theme to avoid duplicates. Updates all fields
    if the narrative already exists. Appends daily snapshots to timeline_data.

    Args:
        theme: Theme category (e.g., "regulatory", "defi_adoption")
        title: Generated narrative title
        summary: AI-generated narrative summary
        entities: List of entity names in this narrative
        article_ids: List of article IDs supporting this narrative
        article_count: Number of articles supporting this narrative
        mention_velocity: Articles per day rate
        lifecycle: Lifecycle stage (emerging, rising, hot, heating, mature, cooling, declining)
        momentum: Momentum indicator (growing, declining, stable, unknown)
        recency_score: Freshness score (0-1, higher = more recent)
        entity_relationships: Top 5 entity co-occurrence pairs with weights: [{"a": "SEC", "b": "Binance", "weight": 3}]
        first_seen: When narrative was first detected (optional)
        lifecycle_state: Lifecycle state (emerging, rising, hot, cooling, dormant) - optional
        lifecycle_history: History of lifecycle state transitions - optional
        reawakening_count: Number of times narrative has been reactivated (optional)
        reawakened_from: Timestamp when narrative went dormant before reactivation (optional)
        resurrection_velocity: Articles per day in last 48 hours during reactivation (optional)
        dormant_since: Timestamp when narrative transitioned to dormant state (optional)
        reactivated_count: Number of times narrative has been reactivated from dormancy (optional)
        needs_summary_update: Whether narrative summary should be refreshed; when None, field not modified (optional)

    Returns:
        The ID of the upserted narrative
    """
    db = await mongo_manager.get_async_database()
    collection = db.narratives
    
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    
    # Check if narrative with this theme exists
    existing = await collection.find_one({"theme": theme})
    
    # Validate and normalize first_seen and last_updated timestamps
    first_seen_date = first_seen or now
    if first_seen_date.tzinfo is None:
        first_seen_date = first_seen_date.replace(tzinfo=timezone.utc)
    
    # Ensure last_updated >= first_seen (prevent data corruption)
    if now < first_seen_date:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            f"[NARRATIVE VALIDATION] Detected reversed timestamps for theme '{theme}': "
            f"last_updated ({now}) < first_seen ({first_seen_date}). "
            f"Using first_seen as last_updated to maintain data integrity."
        )
        # Use first_seen as the update time if current time is somehow before first_seen
        # (this shouldn't happen in normal operation but protects against clock skew)
        last_updated_date = first_seen_date
    else:
        last_updated_date = now
    
    # Create today's timeline snapshot
    timeline_snapshot = {
        "date": today,
        "article_count": article_count,
        "entities": entities[:10],  # Limit to top 10
        "velocity": round(mention_velocity, 2)
    }
    
    if existing:
        # Update existing narrative
        existing_first_seen = existing.get("first_seen", now)
        if existing_first_seen.tzinfo is None:
            existing_first_seen = existing_first_seen.replace(tzinfo=timezone.utc)
        
        # Check if existing first_seen is already corrupted (in the future)
        if existing_first_seen > now:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"[NARRATIVE VALIDATION] Detected corrupted first_seen for theme '{theme}': "
                f"first_seen ({existing_first_seen}) is in the future (now: {now}). "
                f"Resetting first_seen to now to fix data corruption."
            )
            # Fix corrupted first_seen by using current time
            existing_first_seen = now
        
        # Validate existing first_seen vs new last_updated
        # If last_updated would be before first_seen, keep the existing first_seen
        if last_updated_date < existing_first_seen:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"[NARRATIVE VALIDATION] Update would create reversed timestamps for theme '{theme}': "
                f"new last_updated ({last_updated_date}) < existing first_seen ({existing_first_seen}). "
                f"Keeping existing first_seen and using it as last_updated."
            )
            # Use existing first_seen as both first_seen and last_updated
            first_seen_date = existing_first_seen
            last_updated_date = existing_first_seen
        else:
            first_seen_date = existing_first_seen
        
        days_active = _calculate_days_active(first_seen_date)
        
        # Get existing timeline data and peak activity
        timeline_data = existing.get("timeline_data", [])
        peak_activity = existing.get("peak_activity", {})
        
        # Check if we should append a new snapshot (once per day)
        if _should_append_timeline_snapshot(existing):
            timeline_data.append(timeline_snapshot)
        else:
            # Update today's snapshot if it already exists
            if timeline_data:
                timeline_data[-1] = timeline_snapshot
        
        # Update peak activity if today exceeds previous peak
        peak_article_count = peak_activity.get("article_count", 0)
        if article_count > peak_article_count:
            peak_activity = {
                "date": today,
                "article_count": article_count,
                "velocity": round(mention_velocity, 2)
            }
        
        update_data = {
            "title": title,
            "summary": summary,
            "entities": entities,
            "article_ids": article_ids,
            "article_count": article_count,
            "mention_velocity": mention_velocity,
            "lifecycle": lifecycle,
            "momentum": momentum,
            "recency_score": recency_score,
            "entity_relationships": entity_relationships or [],
            "first_seen": first_seen_date,
            "last_updated": last_updated_date,
            "timeline_data": timeline_data,
            "peak_activity": peak_activity,
            "days_active": days_active
        }

        # Add lifecycle_state if provided
        if lifecycle_state is not None:
            update_data["lifecycle_state"] = lifecycle_state

        # Add lifecycle_history if provided
        if lifecycle_history is not None:
            update_data["lifecycle_history"] = lifecycle_history

        # Add resurrection tracking fields if provided
        if reawakening_count is not None:
            update_data["reawakening_count"] = reawakening_count
        if reawakened_from is not None:
            update_data["reawakened_from"] = reawakened_from
        if resurrection_velocity is not None:
            update_data["resurrection_velocity"] = resurrection_velocity

        # Add dormancy tracking fields if provided
        if dormant_since is not None:
            update_data["dormant_since"] = dormant_since
        if reactivated_count is not None:
            update_data["reactivated_count"] = reactivated_count

        # Add summary update flag if provided
        if needs_summary_update is not None:
            update_data["needs_summary_update"] = needs_summary_update

        await collection.update_one(
            {"theme": theme},
            {"$set": update_data}
        )
        return str(existing["_id"])
    else:
        # Create new narrative with initial timeline data
        days_active = _calculate_days_active(first_seen_date)
        
        narrative_data = {
            "theme": theme,
            "title": title,
            "summary": summary,
            "entities": entities,
            "article_ids": article_ids,
            "first_seen": first_seen_date,
            "last_updated": last_updated_date,
            "article_count": article_count,
            "mention_velocity": mention_velocity,
            "lifecycle": lifecycle,
            "momentum": momentum,
            "recency_score": recency_score,
            "entity_relationships": entity_relationships or [],
            "timeline_data": [timeline_snapshot],
            "peak_activity": {
                "date": today,
                "article_count": article_count,
                "velocity": round(mention_velocity, 2)
            },
            "days_active": days_active
        }

        # Add lifecycle_state if provided
        if lifecycle_state is not None:
            narrative_data["lifecycle_state"] = lifecycle_state

        # Add lifecycle_history if provided
        if lifecycle_history is not None:
            narrative_data["lifecycle_history"] = lifecycle_history

        # Add resurrection tracking fields if provided
        if reawakening_count is not None:
            narrative_data["reawakening_count"] = reawakening_count
        if reawakened_from is not None:
            narrative_data["reawakened_from"] = reawakened_from
        if resurrection_velocity is not None:
            narrative_data["resurrection_velocity"] = resurrection_velocity

        # Add dormancy tracking fields if provided
        if dormant_since is not None:
            narrative_data["dormant_since"] = dormant_since
        if reactivated_count is not None:
            narrative_data["reactivated_count"] = reactivated_count

        # Add summary update flag if provided
        if needs_summary_update is not None:
            narrative_data["needs_summary_update"] = needs_summary_update

        result = await collection.insert_one(narrative_data)
        return str(result.inserted_id)


async def get_active_narratives(
    limit: int = 10,
    lifecycle_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get active narratives sorted by most recently updated.
    
    Filters narratives to only include active states (emerging, rising, hot, 
    cooling, reactivated). Excludes dormant and echo states which should appear
    in the archive view.
    
    Args:
        limit: Maximum number of narratives to return (default 10)
        lifecycle_filter: Optional filter by lifecycle stage
    
    Returns:
        List of narrative documents
    """
    db = await mongo_manager.get_async_database()
    collection = db.narratives
    
    # Build query filter - exclude dormant and echo states
    # Active states: emerging, rising, hot, cooling, reactivated
    active_states = ['emerging', 'rising', 'hot', 'cooling', 'reactivated']
    
    query = {
        '$or': [
            {'lifecycle_state': {'$in': active_states}},
            {'lifecycle_state': {'$exists': False}}  # Include narratives without lifecycle_state for backward compatibility
        ]
    }
    
    if lifecycle_filter:
        query["lifecycle"] = lifecycle_filter
    
    # Get narratives sorted by last_updated (most recent first)
    cursor = collection.find(query).sort("last_updated", -1).limit(limit)
    
    narratives = []
    async for narrative in cursor:
        narrative["_id"] = str(narrative["_id"])
        narratives.append(narrative)
    
    return narratives


async def delete_old_narratives(days: int = 7) -> int:
    """
    Delete narratives older than specified days.
    
    Args:
        days: Number of days to keep (default 7)
    
    Returns:
        Number of deleted narratives
    """
    db = await mongo_manager.get_async_database()
    collection = db.narratives
    
    from datetime import timedelta
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    result = await collection.delete_many({
        "last_updated": {"$lt": cutoff_date}
    })
    
    return result.deleted_count


async def get_narrative_timeline(narrative_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Get timeline data for a specific narrative.
    
    Args:
        narrative_id: MongoDB ObjectId as string
    
    Returns:
        List of timeline snapshots or None if narrative not found
    """
    from bson import ObjectId
    
    db = await mongo_manager.get_async_database()
    collection = db.narratives
    
    try:
        narrative = await collection.find_one({"_id": ObjectId(narrative_id)})
        if not narrative:
            return None
        
        return narrative.get("timeline_data", [])
    except Exception:
        return None


async def get_archived_narratives(
    limit: int = 50,
    days: int = 30
) -> List[Dict[str, Any]]:
    """
    Get archived (dormant) narratives sorted by most recently updated.
    
    Returns narratives with lifecycle_state = 'dormant' that have been updated
    within the lookback window. These are narratives that have gone quiet but
    may still be relevant.
    
    Args:
        limit: Maximum number of narratives to return (default 50)
        days: Look back X days from now (default 30)
    
    Returns:
        List of dormant narrative documents
    """
    import logging
    logger = logging.getLogger(__name__)
    
    db = await mongo_manager.get_async_database()
    collection = db.narratives
    
    # Calculate cutoff date
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    # First, let's check what narratives exist in the database
    total_count = await collection.count_documents({})
    logger.info(f"[DEBUG] Total narratives in database: {total_count}")
    
    # Check how many have lifecycle_state field
    with_lifecycle_state = await collection.count_documents({"lifecycle_state": {"$exists": True}})
    logger.info(f"[DEBUG] Narratives with lifecycle_state field: {with_lifecycle_state}")
    
    # Check lifecycle_state distribution
    pipeline = [{"$group": {"_id": "$lifecycle_state", "count": {"$sum": 1}}}]
    lifecycle_distribution = []
    async for doc in collection.aggregate(pipeline):
        lifecycle_distribution.append(doc)
    logger.info(f"[DEBUG] Lifecycle state distribution: {lifecycle_distribution}")
    
    # Query for narratives with lifecycle_state = 'dormant' within lookback window
    query = {
        "lifecycle_state": "dormant",
        "last_updated": {"$gte": cutoff_date}
    }
    
    logger.info(f"[DEBUG] Query for archived narratives: {query}")
    logger.info(f"[DEBUG] Cutoff date: {cutoff_date}")
    
    # Sort by last_updated descending (most recently dormant first)
    cursor = collection.find(query).sort("last_updated", -1).limit(limit)
    
    narratives = []
    async for narrative in cursor:
        narrative["_id"] = str(narrative["_id"])
        narratives.append(narrative)
    
    logger.info(f"[DEBUG] Found {len(narratives)} archived narratives")
    
    return narratives


async def get_resurrected_narratives(
    limit: int = 20,
    days: int = 7
) -> List[Dict[str, Any]]:
    """
    Get narratives that have been reactivated (resurrected from dormant state).
    
    Returns narratives with reawakening_count > 0 that have been updated within
    the lookback window, sorted by most recently updated.
    
    Args:
        limit: Maximum number of narratives to return (default 20, max 100)
        days: Look back X days from now (default 7)
    
    Returns:
        List of resurrected narrative documents with resurrection metrics
    """
    db = await mongo_manager.get_async_database()
    collection = db.narratives
    
    # Calculate cutoff date
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    # Query for narratives with reawakening_count > 0 and last_updated within lookback window
    # This captures narratives that were resurrected recently, regardless of when they went dormant
    query = {
        "reawakening_count": {"$gt": 0},
        "last_updated": {"$gte": cutoff_date}
    }
    
    # Sort by last_updated descending (most recently active first)
    cursor = collection.find(query).sort("last_updated", -1).limit(limit)
    
    narratives = []
    async for narrative in cursor:
        narrative["_id"] = str(narrative["_id"])
        narratives.append(narrative)
    
    return narratives


async def ensure_indexes():
    """
    Ensure required indexes exist on the narratives collection.
    
    Creates indexes for:
    - last_updated (for sorting and cleanup)
    - theme (for upsert operations, non-unique due to null values)
    - lifecycle (for filtering - legacy)
    - lifecycle_state (for filtering - new field)
    - reawakened_from (for resurrection queries)
    - compound index on lifecycle_state + last_updated (for efficient active narrative queries)
    """
    db = await mongo_manager.get_async_database()
    collection = db.narratives
    
    # Helper to create index if it doesn't exist
    async def create_index_if_not_exists(keys, name, **kwargs):
        try:
            await collection.create_index(keys, name=name, **kwargs)
        except Exception as e:
            # Index might already exist, that's okay
            if "already exists" not in str(e) and "IndexOptionsConflict" not in str(e):
                # Only raise if it's not an "already exists" error
                pass
    
    # Index on last_updated for sorting and cleanup
    await create_index_if_not_exists("last_updated", name="idx_last_updated")
    
    # Index on theme for upsert operations (non-unique due to potential null values)
    await create_index_if_not_exists("theme", name="idx_theme")
    
    # Index on lifecycle for filtering (legacy)
    await create_index_if_not_exists("lifecycle", name="idx_lifecycle")
    
    # Index on lifecycle_state for filtering (new field) - THIS IS THE CRITICAL ONE
    await create_index_if_not_exists("lifecycle_state", name="idx_lifecycle_state")
    
    # Compound index for efficient active narrative queries (lifecycle_state + last_updated)
    await create_index_if_not_exists(
        [("lifecycle_state", 1), ("last_updated", -1)],
        name="idx_lifecycle_state_last_updated"
    )
    
    # Index on reawakened_from for resurrection queries
    await create_index_if_not_exists("reawakened_from", name="idx_reawakened_from")
