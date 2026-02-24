"""
Database operations for signal scores.

Signal scores track trending entities based on mention velocity,
source diversity, and sentiment metrics.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from crypto_news_aggregator.db.mongodb import mongo_manager


async def upsert_signal_score(
    entity: str,
    entity_type: str,
    score: float,
    velocity: float,
    source_count: int,
    sentiment: Dict[str, float],
    narrative_ids: List[str] = None,
    is_emerging: bool = False,
    first_seen: datetime = None,
    # Multi-timeframe fields
    score_24h: Optional[float] = None,
    score_7d: Optional[float] = None,
    score_30d: Optional[float] = None,
    velocity_24h: Optional[float] = None,
    velocity_7d: Optional[float] = None,
    velocity_30d: Optional[float] = None,
    mentions_24h: Optional[int] = None,
    mentions_7d: Optional[int] = None,
    mentions_30d: Optional[int] = None,
    recency_24h: Optional[float] = None,
    recency_7d: Optional[float] = None,
    recency_30d: Optional[float] = None,
) -> str:
    """
    Create or update a signal score record.
    
    Args:
        entity: The entity name/value
        entity_type: Type of entity (ticker, project, event)
        score: Overall signal score (0-10) - legacy field
        velocity: Mention velocity metric - legacy field
        source_count: Number of unique sources
        sentiment: Sentiment metrics dict
        narrative_ids: List of narrative IDs containing this entity
        is_emerging: True if entity is not part of any narrative
        first_seen: When entity was first detected (optional)
        score_24h: Signal score for 24h timeframe
        score_7d: Signal score for 7d timeframe
        score_30d: Signal score for 30d timeframe
        velocity_24h: Velocity for 24h timeframe
        velocity_7d: Velocity for 7d timeframe
        velocity_30d: Velocity for 30d timeframe
        mentions_24h: Mention count for 24h timeframe
        mentions_7d: Mention count for 7d timeframe
        mentions_30d: Mention count for 30d timeframe
        recency_24h: Recency factor for 24h timeframe
        recency_7d: Recency factor for 7d timeframe
        recency_30d: Recency factor for 30d timeframe
    
    Returns:
        The ID of the upserted signal score record
    """
    db = await mongo_manager.get_async_database()
    collection = db.signal_scores
    
    now = datetime.now(timezone.utc)
    
    # Check if record exists
    existing = await collection.find_one({"entity": entity})
    
    if existing:
        # Update existing record
        update_data = {
            "entity_type": entity_type,
            "score": score,
            "velocity": velocity,
            "source_count": source_count,
            "sentiment": sentiment,
            "narrative_ids": narrative_ids or [],
            "is_emerging": is_emerging,
            "last_updated": now,
        }
        
        # Add multi-timeframe fields if provided
        if score_24h is not None:
            update_data["score_24h"] = score_24h
        if score_7d is not None:
            update_data["score_7d"] = score_7d
        if score_30d is not None:
            update_data["score_30d"] = score_30d
        if velocity_24h is not None:
            update_data["velocity_24h"] = velocity_24h
        if velocity_7d is not None:
            update_data["velocity_7d"] = velocity_7d
        if velocity_30d is not None:
            update_data["velocity_30d"] = velocity_30d
        if mentions_24h is not None:
            update_data["mentions_24h"] = mentions_24h
        if mentions_7d is not None:
            update_data["mentions_7d"] = mentions_7d
        if mentions_30d is not None:
            update_data["mentions_30d"] = mentions_30d
        if recency_24h is not None:
            update_data["recency_24h"] = recency_24h
        if recency_7d is not None:
            update_data["recency_7d"] = recency_7d
        if recency_30d is not None:
            update_data["recency_30d"] = recency_30d
        
        await collection.update_one(
            {"entity": entity},
            {"$set": update_data}
        )
        return str(existing["_id"])
    else:
        # Create new record
        signal_data = {
            "entity": entity,
            "entity_type": entity_type,
            "score": score,
            "velocity": velocity,
            "source_count": source_count,
            "sentiment": sentiment,
            "narrative_ids": narrative_ids or [],
            "is_emerging": is_emerging,
            "first_seen": first_seen or now,
            "last_updated": now,
            "created_at": now,
        }
        
        # Add multi-timeframe fields if provided
        if score_24h is not None:
            signal_data["score_24h"] = score_24h
        if score_7d is not None:
            signal_data["score_7d"] = score_7d
        if score_30d is not None:
            signal_data["score_30d"] = score_30d
        if velocity_24h is not None:
            signal_data["velocity_24h"] = velocity_24h
        if velocity_7d is not None:
            signal_data["velocity_7d"] = velocity_7d
        if velocity_30d is not None:
            signal_data["velocity_30d"] = velocity_30d
        if mentions_24h is not None:
            signal_data["mentions_24h"] = mentions_24h
        if mentions_7d is not None:
            signal_data["mentions_7d"] = mentions_7d
        if mentions_30d is not None:
            signal_data["mentions_30d"] = mentions_30d
        if recency_24h is not None:
            signal_data["recency_24h"] = recency_24h
        if recency_7d is not None:
            signal_data["recency_7d"] = recency_7d
        if recency_30d is not None:
            signal_data["recency_30d"] = recency_30d
        
        result = await collection.insert_one(signal_data)
        return str(result.inserted_id)


async def get_trending_entities(
    limit: int = 20,
    min_score: float = 0.0,
    entity_type: Optional[str] = None,
    timeframe: str = "7d",
) -> List[Dict[str, Any]]:
    """
    Get trending entities sorted by signal score for a specific timeframe.

    Filters out stale entities that have no recent entity_mentions within the timeframe.

    Args:
        limit: Maximum number of results (default 20)
        min_score: Minimum signal score threshold (default 0.0)
        entity_type: Filter by entity type (optional)
        timeframe: Time window for scoring (24h, 7d, or 30d, default 7d)

    Returns:
        List of signal score documents with recent mentions in the timeframe
    """
    db = await mongo_manager.get_async_database()
    collection = db.signal_scores
    entity_mentions = db.entity_mentions

    # Map timeframe to score field and days
    score_field_map = {
        "24h": "score_24h",
        "7d": "score_7d",
        "30d": "score_30d",
    }

    timeframe_days_map = {
        "24h": 1,
        "7d": 7,
        "30d": 30,
    }

    score_field = score_field_map.get(timeframe, "score_7d")
    days = timeframe_days_map.get(timeframe, 7)

    # Calculate cutoff date for filtering mentions
    from datetime import timedelta
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Build query - filter by the timeframe-specific score
    query = {score_field: {"$gte": min_score}}
    if entity_type:
        query["entity_type"] = entity_type

    # Get trending entities sorted by timeframe-specific score
    # Fetch more than needed to account for filtering
    cursor = collection.find(query).sort(score_field, -1).limit(limit * 2)

    results = []
    async for signal in cursor:
        entity = signal.get("entity")

        # Verify entity has RECENT mentions within the timeframe (filter out stale signals)
        mention_count = await entity_mentions.count_documents(
            {
                "entity": entity,
                "created_at": {"$gte": cutoff_date}
            },
            limit=1
        )

        if mention_count > 0:
            signal["_id"] = str(signal["_id"])
            results.append(signal)

            # Stop once we have enough valid results
            if len(results) >= limit:
                break

    return results


async def get_entity_signal(entity: str) -> Optional[Dict[str, Any]]:
    """
    Get signal score for a specific entity.
    
    Args:
        entity: The entity to get signal for
    
    Returns:
        Signal score document or None if not found
    """
    db = await mongo_manager.get_async_database()
    collection = db.signal_scores
    
    signal = await collection.find_one({"entity": entity})
    
    if signal:
        signal["_id"] = str(signal["_id"])
        return signal
    
    return None


async def delete_old_signals(days: int = 7) -> int:
    """
    Delete signal scores older than specified days.
    
    Args:
        days: Number of days to keep (default 7)
    
    Returns:
        Number of deleted records
    """
    db = await mongo_manager.get_async_database()
    collection = db.signal_scores
    
    from datetime import timedelta
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    result = await collection.delete_many({
        "last_updated": {"$lt": cutoff_date}
    })
    
    return result.deleted_count
