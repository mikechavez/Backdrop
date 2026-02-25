"""
Narrative API endpoints.

Provides access to detected narrative clusters from co-occurring entities.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
from bson import ObjectId

from ....db.operations.narratives import get_active_narratives, get_narrative_timeline, get_resurrected_narratives, get_archived_narratives
from ....core.redis_rest_client import redis_client
from ....db.mongodb import mongo_manager

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory cache for narratives with 1-minute TTL
_narratives_cache: Dict[str, tuple[Any, datetime]] = {}
_narratives_cache_ttl = timedelta(minutes=1)


async def get_articles_for_narrative(article_ids: List[str], limit: int = 20) -> List[Dict[str, Any]]:
    """
    Fetch article details for a list of article IDs.

    Args:
        article_ids: List of article MongoDB ObjectIds (as strings)
        limit: Maximum number of articles to return (default 20)

    Returns:
        List of article dicts with title, url, source, published_at
    """
    if not article_ids:
        return []

    db = await mongo_manager.get_async_database()
    articles_collection = db.articles

    # Convert string IDs to ObjectIds
    object_ids = []
    for article_id in article_ids[:limit]:
        try:
            if isinstance(article_id, str):
                object_ids.append(ObjectId(article_id))
            else:
                object_ids.append(article_id)
        except Exception:
            continue

    if not object_ids:
        return []

    # Fetch articles by _id
    cursor = articles_collection.find(
        {"_id": {"$in": object_ids}}
    ).sort("published_at", -1).limit(limit)

    articles = []
    async for article in cursor:
        articles.append({
            "title": article.get("title", ""),
            "url": article.get("url", ""),
            "source": article.get("source", ""),
            "published_at": article.get("published_at").isoformat() if article.get("published_at") else None
        })

    return articles


async def get_articles_paginated(
    narrative_id: str,
    offset: int,
    limit: int,
    db: Any
) -> Dict[str, Any]:
    """
    Fetch paginated articles for a narrative with total count and has_more flag.

    Args:
        narrative_id: MongoDB ObjectId of the narrative (as string)
        offset: Number of articles to skip (0-based indexing)
        limit: Maximum number of articles to return (1-50)
        db: Database connection (AsyncIO motor database)

    Returns:
        Dict with:
        - articles: List of article dicts (title, url, source, published_at)
        - total_count: Total number of articles in narrative
        - offset: Requested offset
        - limit: Requested limit
        - has_more: Boolean indicating if more articles exist beyond this page

    Raises:
        HTTPException 400: If offset < 0, limit <= 0, limit > 50, or invalid narrative ID
        HTTPException 404: If narrative not found
    """
    # Validate offset and limit
    if offset < 0:
        raise HTTPException(status_code=400, detail="Offset cannot be negative")

    if limit <= 0:
        raise HTTPException(status_code=400, detail="Limit must be greater than 0")

    if limit > 50:
        raise HTTPException(status_code=400, detail="Limit cannot exceed 50")

    # Validate narrative ID format
    try:
        narrative_obj_id = ObjectId(narrative_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid narrative ID format")

    # Fetch narrative to get article_ids
    narratives_collection = db.narratives
    narrative = await narratives_collection.find_one({"_id": narrative_obj_id})

    if not narrative:
        raise HTTPException(status_code=404, detail="Narrative not found")

    # Get article IDs and total count
    article_ids = narrative.get("article_ids", [])
    total_count = len(article_ids)

    # Slice article IDs based on offset and limit
    sliced_article_ids = article_ids[offset:offset + limit]

    # Fetch article details
    articles = []
    if sliced_article_ids:
        articles_collection = db.articles

        # Convert string IDs to ObjectIds
        object_ids = []
        for article_id in sliced_article_ids:
            try:
                if isinstance(article_id, str):
                    object_ids.append(ObjectId(article_id))
                else:
                    object_ids.append(article_id)
            except Exception:
                continue

        if object_ids:
            # Fetch articles by _id
            cursor = articles_collection.find(
                {"_id": {"$in": object_ids}}
            ).sort("published_at", -1).limit(len(object_ids))

            async for article in cursor:
                articles.append({
                    "title": article.get("title", ""),
                    "url": article.get("url", ""),
                    "source": article.get("source", ""),
                    "published_at": article.get("published_at").isoformat() if article.get("published_at") else None
                })

    # Calculate has_more
    has_more = (offset + limit) < total_count

    return {
        "articles": articles,
        "total_count": total_count,
        "offset": offset,
        "limit": limit,
        "has_more": has_more
    }


class TimelineSnapshot(BaseModel):
    """Timeline snapshot for a single day."""
    date: str = Field(..., description="Date in ISO format (YYYY-MM-DD)")
    article_count: int = Field(..., description="Number of articles on this day")
    entities: List[str] = Field(..., description="Top entities mentioned on this day")
    velocity: float = Field(..., description="Articles per day rate")


class PeakActivity(BaseModel):
    """Peak activity metrics for a narrative."""
    date: str = Field(..., description="Date of peak activity")
    article_count: int = Field(..., description="Number of articles at peak")
    velocity: float = Field(..., description="Velocity at peak")


class LifecycleHistoryEntry(BaseModel):
    """Lifecycle history entry."""
    state: str = Field(..., description="Lifecycle state (emerging, rising, hot, cooling, dormant)")
    timestamp: str = Field(..., description="ISO timestamp when state changed")
    article_count: int = Field(..., description="Article count at time of change")
    velocity: float = Field(..., description="Velocity at time of change")


class NarrativeResponse(BaseModel):
    """Response model for a narrative."""
    id: Optional[str] = Field(default=None, alias="_id", description="MongoDB ObjectId as string")
    theme: str = Field(..., description="Theme category (e.g., regulatory, defi_adoption)")
    title: str = Field(..., description="Generated narrative title")
    summary: str = Field(..., description="AI-generated narrative summary")
    entities: List[str] = Field(..., description="List of entities in this narrative")
    article_count: int = Field(..., description="Number of articles supporting this narrative")
    mention_velocity: float = Field(..., description="Articles per day rate")
    lifecycle: str = Field(..., description="Lifecycle stage: emerging, hot, mature, declining")
    lifecycle_state: Optional[str] = Field(default=None, description="New lifecycle state (emerging, rising, hot, cooling, dormant)")
    lifecycle_history: Optional[List[LifecycleHistoryEntry]] = Field(default=None, description="History of lifecycle state transitions")
    fingerprint: Optional[List[float]] = Field(default=None, description="Narrative fingerprint vector for similarity matching")
    momentum: Optional[str] = Field(default="unknown", description="Momentum trend: growing, declining, stable, or unknown")
    recency_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Freshness score (0-1), higher = more recent, 24h half-life")
    entity_relationships: Optional[List[Dict[str, Any]]] = Field(default=[], description="Top 5 entity co-occurrence pairs with weights: [{'a': 'SEC', 'b': 'Binance', 'weight': 3}]")
    first_seen: str = Field(..., description="ISO timestamp when narrative was first detected")
    last_updated: str = Field(..., description="ISO timestamp of last update")
    last_article_at: Optional[str] = Field(default=None, description="ISO timestamp when the most recent article was published to this narrative")
    days_active: int = Field(default=1, description="Number of days narrative has been active")
    peak_activity: Optional[PeakActivity] = Field(default=None, description="Peak activity metrics")
    articles: List[Dict[str, Any]] = Field(default=[], description="Recent articles in this narrative")
    reawakening_count: Optional[int] = Field(default=None, description="Number of times narrative has been reactivated from dormant state")
    reawakened_from: Optional[str] = Field(default=None, description="ISO timestamp when narrative went dormant before most recent reactivation")
    resurrection_velocity: Optional[float] = Field(default=None, description="Articles per day in last 48 hours during reactivation")

    class Config:
        populate_by_name = True  # Allow both 'id' and '_id' as field names
        json_encoders = {str: lambda v: v}  # Ensure strings are serialized properly
        json_schema_extra = {
            "example": {
                "theme": "regulatory",
                "title": "SEC crypto enforcement actions intensify",
                "summary": "The SEC has ramped up enforcement actions against major crypto exchanges, with new lawsuits and regulatory guidance affecting the industry.",
                "entities": ["SEC", "Coinbase", "Binance", "Gary Gensler"],
                "article_count": 15,
                "mention_velocity": 3.1,
                "lifecycle": "hot",
                "recency_score": 0.607,
                "first_seen": "2025-10-01T19:30:00Z",
                "last_updated": "2025-10-06T14:20:00Z",
                "days_active": 6,
                "peak_activity": {
                    "date": "2025-10-05",
                    "article_count": 18,
                    "velocity": 4.2
                }
            }
        }


class PaginatedNarrativesResponse(BaseModel):
    """Paginated response for narratives list."""
    narratives: List[NarrativeResponse] = Field(..., description="List of narratives on this page")
    total_count: int = Field(..., ge=0, description="Total number of narratives")
    offset: int = Field(..., ge=0, description="Number of narratives skipped")
    limit: int = Field(..., ge=1, le=200, description="Maximum narratives per page")
    has_more: bool = Field(..., description="Whether more narratives exist beyond this page")


@router.get("/active", response_model=PaginatedNarrativesResponse)
async def get_active_narratives_endpoint(
    limit: int = Query(10, ge=1, le=200, description="Maximum number of narratives per page"),
    offset: int = Query(0, ge=0, description="Number of narratives to skip for pagination"),
    lifecycle_state: Optional[str] = Query(None, description="Filter by lifecycle_state (emerging, hot, mature)")
):
    """
    Get active narrative clusters using optimized aggregation pipeline.
    
    Returns the most recently updated narratives, representing groups of
    co-occurring crypto entities with AI-generated thematic summaries.
    
    Results are cached in-memory for 1 minute to reduce database load.
    
    Args:
        limit: Maximum number of narratives (1-200, default 50)
        lifecycle_state: Optional filter by lifecycle_state
    
    Returns:
        List of narrative objects with theme, entities, story, and metadata
    """
    # Check in-memory cache
    cache_key = f"narratives:active:v2:{lifecycle_state or 'all'}"
    
    if cache_key in _narratives_cache:
        cached_data, cached_time = _narratives_cache[cache_key]
        if datetime.now() - cached_time < _narratives_cache_ttl:
            # Paginate from cached full result
            all_narratives = cached_data.get("narratives", [])
            total_count = len(all_narratives)
            page_narratives = all_narratives[offset:offset + limit]
            return PaginatedNarrativesResponse(
                narratives=page_narratives,
                total_count=total_count,
                offset=offset,
                limit=limit,
                has_more=(offset + limit) < total_count
            )
        else:
            # Remove expired entry
            del _narratives_cache[cache_key]
    
    # Cache miss - fetch from database using optimized aggregation pipeline
    try:
        db = await mongo_manager.get_async_database()
        narratives_collection = db.narratives
        
        # Build match filter for active states
        active_states = ['emerging', 'rising', 'hot', 'cooling', 'reactivated']
        match_stage = {
            '$or': [
                {'lifecycle_state': {'$in': active_states}},
                {'lifecycle_state': {'$exists': False}}
            ]
        }
        if lifecycle_state:
            match_stage = {'lifecycle_state': lifecycle_state}
        
        # Single aggregation pipeline (use inclusion-only projection)
        pipeline = [
            {'$match': match_stage},
            {'$sort': {'last_updated': -1}},
            {'$limit': 200},  # Fetch full set for caching
            # Note: Removed $lookup for articles (was O(narratives × articles) on Atlas M0)
            # Articles are fetched on-demand when user requests narrative details
            {'$project': {
                '_id': 1,
                'theme': 1,
                'title': 1,
                'summary': 1,
                'entities': 1,
                'article_count': 1,
                'mention_velocity': 1,
                'lifecycle': 1,
                'lifecycle_state': 1,
                'momentum': 1,
                'recency_score': 1,
                'entity_relationships': 1,
                'first_seen': 1,
                'last_updated': 1,
                'days_active': 1,
                'peak_activity': 1,
                'reawakening_count': 1,
                'reawakened_from': 1,
                'resurrection_velocity': 1
                # Exclude heavy fields by not including them: fingerprint, lifecycle_history, timeline_data
            }}
        ]
        
        cursor = narratives_collection.aggregate(pipeline)
        narratives = await cursor.to_list(length=None)

        if not narratives:
            return PaginatedNarrativesResponse(
                narratives=[],
                total_count=0,
                offset=offset,
                limit=limit,
                has_more=False
            )
        
        # Convert to response models and fetch articles
        response_data = []
        for narrative in narratives:
            # Handle both old (updated_at) and new (last_updated) field names
            last_updated = narrative.get("last_updated") or narrative.get("updated_at")
            if last_updated:
                last_updated_str = last_updated.isoformat() if hasattr(last_updated, 'isoformat') else str(last_updated)
            else:
                # Fallback to current time if no timestamp
                from datetime import timezone as tz
                last_updated_str = datetime.now(tz.utc).isoformat()
            
            first_seen = narrative.get("first_seen") or narrative.get("created_at")
            if first_seen:
                first_seen_str = first_seen.isoformat() if hasattr(first_seen, 'isoformat') else str(first_seen)
            else:
                # Use last_updated as fallback
                first_seen_str = last_updated_str
            
            # DEBUG: Log timestamp ordering
            theme = narrative.get("theme", "unknown")
            if first_seen and last_updated:
                if first_seen > last_updated:
                    logger.warning(f"[API TIMESTAMP BUG] Narrative '{theme}': first_seen={first_seen_str} > last_updated={last_updated_str}")
                else:
                    logger.debug(f"[API TIMESTAMP OK] Narrative '{theme}': first_seen={first_seen_str} <= last_updated={last_updated_str}")
            
            # Handle both old (story) and new (summary) field names
            summary = narrative.get("summary") or narrative.get("story", "")
            
            # Get timeline tracking fields
            days_active = narrative.get("days_active", 1)
            peak_activity = narrative.get("peak_activity")
            
            # Don't fetch articles for list view - only fetch when user requests details
            # This prevents N+1 query problem and speeds up initial page load from 2 minutes to <1 second
            articles = []
            
            # Lifecycle fields (heavy fields excluded in projection)
            lifecycle_state = narrative.get("lifecycle_state")
            
            # Handle reawakened_from timestamp
            reawakened_from = narrative.get("reawakened_from")
            reawakened_from_str = None
            if reawakened_from:
                reawakened_from_str = reawakened_from.isoformat() if hasattr(reawakened_from, 'isoformat') else str(reawakened_from)
            
            # Note: last_article_at computation removed (was O(narratives × articles) via $lookup)
            # Use last_updated as proxy for activity timestamp
            last_article_at_str = last_updated_str
            
            narrative_id = str(narrative.get("_id", ""))
            response_data.append({
                "id": narrative_id,  # Include as 'id' for Pydantic model
                "_id": narrative_id,  # Also include as '_id' for frontend compatibility
                "theme": narrative.get("theme", ""),
                "title": narrative.get("title", narrative.get("theme", "")),  # Fallback to theme if no title
                "summary": summary,
                "entities": narrative.get("entities", []),
                "article_count": narrative.get("article_count", 0),
                "mention_velocity": narrative.get("mention_velocity", 0.0),
                "lifecycle": narrative.get("lifecycle", "emerging"),
                "lifecycle_state": lifecycle_state,
                "lifecycle_history": None,  # Excluded for performance
                "fingerprint": None,  # Excluded for performance
                "momentum": narrative.get("momentum", "unknown"),
                "recency_score": narrative.get("recency_score", 0.0),
                "entity_relationships": narrative.get("entity_relationships", []),
                "first_seen": first_seen_str,
                "last_updated": last_updated_str,
                "last_article_at": last_article_at_str,
                "days_active": days_active,
                "peak_activity": peak_activity,
                "articles": articles,
                "reawakening_count": narrative.get("reawakening_count"),
                "reawakened_from": reawakened_from_str,
                "resurrection_velocity": narrative.get("resurrection_velocity"),
                # Add backward compatibility fields for old UI
                "updated_at": last_updated_str,
                "story": summary
            })
        
        # Convert to response models
        response = [NarrativeResponse(**n) for n in response_data]

        # Store full list in cache (without pagination)
        cache_data = {"narratives": response}
        _narratives_cache[cache_key] = (cache_data, datetime.now())

        # Return paginated slice
        total_count = len(response)
        page_narratives = response[offset:offset + limit]
        return PaginatedNarrativesResponse(
            narratives=page_narratives,
            total_count=total_count,
            offset=offset,
            limit=limit,
            has_more=(offset + limit) < total_count
        )
    
    except Exception as e:
        logger.exception(f"Error fetching active narratives: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch narratives")


@router.get("/archived", response_model=List[NarrativeResponse])
async def get_archived_narratives_endpoint(
    limit: int = Query(50, ge=1, le=200, description="Maximum number of narratives to return"),
    days: int = Query(30, ge=1, le=90, description="Look back X days for archived narratives")
):
    """
    Get archived (dormant) narratives.
    
    Returns narratives with lifecycle_state = 'dormant' that have gone quiet
    but may still be relevant. These narratives have not received new articles
    for 7+ days.
    
    Args:
        limit: Maximum number of narratives (1-200, default 50)
        days: Look back X days from now (1-90, default 30)
    
    Returns:
        List of dormant narrative objects
    """
    try:
        narratives = await get_archived_narratives(limit=limit, days=days)
        
        logger.info(f"[DEBUG] get_archived_narratives returned {len(narratives)} narratives")
        if narratives:
            logger.info(f"[DEBUG] First narrative: {narratives[0].get('theme', 'N/A')}, lifecycle_state: {narratives[0].get('lifecycle_state', 'N/A')}")
        
        if not narratives:
            return []
        
        # Convert to response models and fetch articles
        response_data = []
        for narrative in narratives:
            # Handle both old (updated_at) and new (last_updated) field names
            last_updated = narrative.get("last_updated") or narrative.get("updated_at")
            if last_updated:
                last_updated_str = last_updated.isoformat() if hasattr(last_updated, 'isoformat') else str(last_updated)
            else:
                # Fallback to current time if no timestamp
                from datetime import datetime, timezone as tz
                last_updated_str = datetime.now(tz.utc).isoformat()
            
            first_seen = narrative.get("first_seen") or narrative.get("created_at")
            if first_seen:
                first_seen_str = first_seen.isoformat() if hasattr(first_seen, 'isoformat') else str(first_seen)
            else:
                # Use last_updated as fallback
                first_seen_str = last_updated_str
            
            # Handle both old (story, narrative_summary) and new (summary) field names
            summary = narrative.get("summary") or narrative.get("story") or narrative.get("narrative_summary", "")
            
            # Handle old schema: extract entities from actors dict or use nucleus_entity
            entities = narrative.get("entities", [])
            if not entities:
                # Old schema: try actors dict keys or nucleus_entity
                actors = narrative.get("actors", {})
                if actors:
                    # Get top 10 actors by count
                    entities = sorted(actors.keys(), key=lambda k: actors[k], reverse=True)[:10]
                elif narrative.get("nucleus_entity"):
                    entities = [narrative.get("nucleus_entity")]
            
            # Handle old schema: use nucleus_entity or first action as title
            title = narrative.get("title") or narrative.get("theme")
            if not title:
                # Old schema fallback: use nucleus_entity or first action
                if narrative.get("nucleus_entity"):
                    title = f"{narrative.get('nucleus_entity')} Activity"
                elif narrative.get("actions") and len(narrative.get("actions", [])) > 0:
                    title = narrative.get("actions")[0][:100]  # Use first action, truncated
                else:
                    title = "Untitled Narrative"
            
            # Get timeline tracking fields
            days_active = narrative.get("days_active", 1)
            peak_activity = narrative.get("peak_activity")
            
            # Fetch articles for this narrative
            article_ids = narrative.get("article_ids", [])
            articles = await get_articles_for_narrative(article_ids, limit=20)
            
            # Get lifecycle fields
            lifecycle_state = narrative.get("lifecycle_state")
            
            # Normalize lifecycle_history
            lifecycle_history_raw = narrative.get("lifecycle_history")
            lifecycle_history = None
            if lifecycle_history_raw:
                lifecycle_history = []
                for entry in lifecycle_history_raw:
                    timestamp = entry.get("timestamp")
                    if hasattr(timestamp, 'isoformat'):
                        timestamp_str = timestamp.isoformat()
                    else:
                        timestamp_str = str(timestamp)
                    
                    velocity = entry.get("velocity", entry.get("mention_velocity", 0.0))
                    
                    lifecycle_history.append({
                        "state": entry.get("state", ""),
                        "timestamp": timestamp_str,
                        "article_count": entry.get("article_count", 0),
                        "velocity": velocity
                    })
            
            # Normalize fingerprint
            fingerprint_raw = narrative.get("fingerprint")
            fingerprint = None
            if fingerprint_raw:
                if isinstance(fingerprint_raw, dict):
                    fingerprint = fingerprint_raw.get("vector")
                elif isinstance(fingerprint_raw, list):
                    fingerprint = fingerprint_raw
            
            # Handle reawakened_from timestamp
            reawakened_from = narrative.get("reawakened_from")
            reawakened_from_str = None
            if reawakened_from:
                reawakened_from_str = reawakened_from.isoformat() if hasattr(reawakened_from, 'isoformat') else str(reawakened_from)
            
            response_data.append({
                "_id": str(narrative.get("_id", "")),  # Include MongoDB ObjectId as string
                "theme": narrative.get("theme", narrative.get("nucleus_entity", "")),
                "title": title,
                "summary": summary,
                "entities": entities,
                "article_count": narrative.get("article_count", 0),
                "mention_velocity": narrative.get("mention_velocity", 0.0),
                "lifecycle": narrative.get("lifecycle", "emerging"),
                "lifecycle_state": lifecycle_state,
                "lifecycle_history": lifecycle_history,
                "fingerprint": fingerprint,
                "momentum": narrative.get("momentum", "unknown"),
                "recency_score": narrative.get("recency_score", 0.0),
                "entity_relationships": narrative.get("entity_relationships", []),
                "first_seen": first_seen_str,
                "last_updated": last_updated_str,
                "days_active": days_active,
                "peak_activity": peak_activity,
                "articles": articles,
                "reawakening_count": narrative.get("reawakening_count"),
                "reawakened_from": reawakened_from_str,
                "resurrection_velocity": narrative.get("resurrection_velocity")
            })
        
        return [NarrativeResponse(**n) for n in response_data]
    
    except Exception as e:
        logger.exception(f"Error fetching archived narratives: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch archived narratives")


@router.get("/resurrections", response_model=List[NarrativeResponse])
async def get_resurrected_narratives_endpoint(
    limit: int = Query(20, ge=1, le=100, description="Maximum number of narratives to return"),
    days: int = Query(7, ge=1, le=30, description="Look back X days for resurrected narratives")
):
    """
    Get narratives that have been reactivated (resurrected from dormant state).
    
    Returns narratives with reawakening_count > 0, sorted by most recently
    resurrected (reawakened_from descending). Useful for tracking which narratives
    are coming back to life after periods of dormancy.
    
    Args:
        limit: Maximum number of narratives (1-100, default 20)
        days: Look back X days from now (1-30, default 7)
    
    Returns:
        List of resurrected narrative objects with resurrection metrics:
        - reawakening_count: Number of times reactivated
        - reawakened_from: When narrative went dormant before reactivation
        - resurrection_velocity: Articles per day in last 48h during reactivation
    """
    try:
        narratives = await get_resurrected_narratives(limit=limit, days=days)
        
        if not narratives:
            return []
        
        # Convert to response models and fetch articles
        response_data = []
        for narrative in narratives:
            # Handle both old (updated_at) and new (last_updated) field names
            last_updated = narrative.get("last_updated") or narrative.get("updated_at")
            if last_updated:
                last_updated_str = last_updated.isoformat() if hasattr(last_updated, 'isoformat') else str(last_updated)
            else:
                # Fallback to current time if no timestamp
                from datetime import datetime, timezone as tz
                last_updated_str = datetime.now(tz.utc).isoformat()
            
            first_seen = narrative.get("first_seen") or narrative.get("created_at")
            if first_seen:
                first_seen_str = first_seen.isoformat() if hasattr(first_seen, 'isoformat') else str(first_seen)
            else:
                # Use last_updated as fallback
                first_seen_str = last_updated_str
            
            # Handle reawakened_from timestamp
            reawakened_from = narrative.get("reawakened_from")
            reawakened_from_str = None
            if reawakened_from:
                reawakened_from_str = reawakened_from.isoformat() if hasattr(reawakened_from, 'isoformat') else str(reawakened_from)
            
            # Handle both old (story) and new (summary) field names
            summary = narrative.get("summary") or narrative.get("story", "")
            
            # Get timeline tracking fields
            days_active = narrative.get("days_active", 1)
            peak_activity = narrative.get("peak_activity")
            
            # Fetch articles for this narrative
            article_ids = narrative.get("article_ids", [])
            articles = await get_articles_for_narrative(article_ids, limit=20)
            
            # Get lifecycle fields
            lifecycle_state = narrative.get("lifecycle_state")
            
            # Normalize lifecycle_history
            lifecycle_history_raw = narrative.get("lifecycle_history")
            lifecycle_history = None
            if lifecycle_history_raw:
                lifecycle_history = []
                for entry in lifecycle_history_raw:
                    timestamp = entry.get("timestamp")
                    if hasattr(timestamp, 'isoformat'):
                        timestamp_str = timestamp.isoformat()
                    else:
                        timestamp_str = str(timestamp)
                    
                    velocity = entry.get("velocity", entry.get("mention_velocity", 0.0))
                    
                    lifecycle_history.append({
                        "state": entry.get("state", ""),
                        "timestamp": timestamp_str,
                        "article_count": entry.get("article_count", 0),
                        "velocity": velocity
                    })
            
            # Normalize fingerprint
            fingerprint_raw = narrative.get("fingerprint")
            fingerprint = None
            if fingerprint_raw:
                if isinstance(fingerprint_raw, dict):
                    fingerprint = fingerprint_raw.get("vector")
                elif isinstance(fingerprint_raw, list):
                    fingerprint = fingerprint_raw
            
            response_data.append({
                "_id": str(narrative.get("_id", "")),  # Include MongoDB ObjectId as string
                "theme": narrative.get("theme", ""),
                "title": narrative.get("title", narrative.get("theme", "")),
                "summary": summary,
                "entities": narrative.get("entities", []),
                "article_count": narrative.get("article_count", 0),
                "mention_velocity": narrative.get("mention_velocity", 0.0),
                "lifecycle": narrative.get("lifecycle", "emerging"),
                "lifecycle_state": lifecycle_state,
                "lifecycle_history": lifecycle_history,
                "fingerprint": fingerprint,
                "momentum": narrative.get("momentum", "unknown"),
                "recency_score": narrative.get("recency_score", 0.0),
                "entity_relationships": narrative.get("entity_relationships", []),
                "first_seen": first_seen_str,
                "last_updated": last_updated_str,
                "days_active": days_active,
                "peak_activity": peak_activity,
                "articles": articles,
                "reawakening_count": narrative.get("reawakening_count"),
                "reawakened_from": reawakened_from_str,
                "resurrection_velocity": narrative.get("resurrection_velocity")
            })
        
        return [NarrativeResponse(**n) for n in response_data]
    
    except Exception as e:
        logger.exception(f"Error fetching resurrected narratives: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch resurrected narratives")


@router.get("/{narrative_id}/articles")
async def get_narrative_articles_endpoint(
    narrative_id: str,
    offset: int = Query(0, ge=0, description="Number of articles to skip"),
    limit: int = Query(20, ge=1, le=50, description="Maximum number of articles to return (1-50)")
):
    """
    Get paginated articles for a specific narrative.

    Returns a page of articles with pagination metadata.

    Args:
        narrative_id: MongoDB ObjectId of the narrative (as string)
        offset: Number of articles to skip (default 0)
        limit: Maximum number of articles to return (default 20, max 50)

    Returns:
        Dict with:
        - articles: List of article dicts with title, url, source, published_at
        - total_count: Total number of articles in this narrative
        - offset: Requested offset
        - limit: Requested limit
        - has_more: Boolean indicating if more articles exist

    Raises:
        400: If invalid parameters (offset < 0, limit > 50, invalid narrative ID)
        404: If narrative not found
        500: If database error occurs
    """
    try:
        db = await mongo_manager.get_async_database()
        result = await get_articles_paginated(
            narrative_id=narrative_id,
            offset=offset,
            limit=limit,
            db=db
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching paginated articles: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch articles")


@router.get("/{narrative_id}", response_model=NarrativeResponse)
async def get_narrative_by_id_endpoint(narrative_id: str):
    """
    Get a single narrative by ID with articles.
    
    Returns the full narrative details including recent articles.
    Useful for fetching articles on-demand when a card is expanded.
    
    Args:
        narrative_id: MongoDB ObjectId of the narrative (as string)
    
    Returns:
        Narrative object with articles
    
    Raises:
        404: If narrative not found
        500: If database error occurs
    """
    try:
        # Get database connection
        db = await mongo_manager.get_async_database()
        narratives_collection = db.narratives
        
        # Convert string ID to ObjectId
        try:
            narrative_obj_id = ObjectId(narrative_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid narrative ID format")
        
        # Fetch narrative
        narrative = await narratives_collection.find_one({"_id": narrative_obj_id})
        
        if not narrative:
            raise HTTPException(status_code=404, detail="Narrative not found")
        
        # Handle timestamps
        last_updated = narrative.get("last_updated") or narrative.get("updated_at")
        if last_updated:
            last_updated_str = last_updated.isoformat() if hasattr(last_updated, 'isoformat') else str(last_updated)
        else:
            from datetime import datetime, timezone as tz
            last_updated_str = datetime.now(tz.utc).isoformat()
        
        first_seen = narrative.get("first_seen") or narrative.get("created_at")
        if first_seen:
            first_seen_str = first_seen.isoformat() if hasattr(first_seen, 'isoformat') else str(first_seen)
        else:
            first_seen_str = last_updated_str
        
        # Handle summary
        summary = narrative.get("summary") or narrative.get("story", "")
        
        # Fetch articles
        article_ids = narrative.get("article_ids", [])
        articles = await get_articles_for_narrative(article_ids, limit=20)
        
        # Get lifecycle fields
        lifecycle_state = narrative.get("lifecycle_state")
        
        # Normalize lifecycle_history
        lifecycle_history_raw = narrative.get("lifecycle_history")
        lifecycle_history = None
        if lifecycle_history_raw:
            lifecycle_history = []
            for entry in lifecycle_history_raw:
                timestamp = entry.get("timestamp")
                if hasattr(timestamp, 'isoformat'):
                    timestamp_str = timestamp.isoformat()
                else:
                    timestamp_str = str(timestamp)
                
                velocity = entry.get("velocity", entry.get("mention_velocity", 0.0))
                
                lifecycle_history.append({
                    "state": entry.get("state", ""),
                    "timestamp": timestamp_str,
                    "article_count": entry.get("article_count", 0),
                    "velocity": velocity
                })
        
        # Normalize fingerprint
        fingerprint_raw = narrative.get("fingerprint")
        fingerprint = None
        if fingerprint_raw:
            if isinstance(fingerprint_raw, dict):
                fingerprint = fingerprint_raw.get("vector")
            elif isinstance(fingerprint_raw, list):
                fingerprint = fingerprint_raw
        
        # Handle reawakened_from timestamp
        reawakened_from = narrative.get("reawakened_from")
        reawakened_from_str = None
        if reawakened_from:
            reawakened_from_str = reawakened_from.isoformat() if hasattr(reawakened_from, 'isoformat') else str(reawakened_from)
        
        narrative_id = str(narrative.get("_id", ""))
        response_data = {
            "id": narrative_id,  # Include as 'id' for Pydantic model
            "_id": narrative_id,  # Also include as '_id' for frontend compatibility
            "theme": narrative.get("theme", ""),
            "title": narrative.get("title", narrative.get("theme", "")),
            "summary": summary,
            "entities": narrative.get("entities", []),
            "article_count": narrative.get("article_count", 0),
            "mention_velocity": narrative.get("mention_velocity", 0.0),
            "lifecycle": narrative.get("lifecycle", "emerging"),
            "lifecycle_state": lifecycle_state,
            "lifecycle_history": lifecycle_history,
            "fingerprint": fingerprint,
            "momentum": narrative.get("momentum", "unknown"),
            "recency_score": narrative.get("recency_score", 0.0),
            "entity_relationships": narrative.get("entity_relationships", []),
            "first_seen": first_seen_str,
            "last_updated": last_updated_str,
            "days_active": narrative.get("days_active", 1),
            "peak_activity": narrative.get("peak_activity"),
            "articles": articles,
            "reawakening_count": narrative.get("reawakening_count"),
            "reawakened_from": reawakened_from_str,
            "resurrection_velocity": narrative.get("resurrection_velocity")
        }
        
        return NarrativeResponse(**response_data)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching narrative by ID: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch narrative")


@router.get("/{narrative_id}/timeline", response_model=List[TimelineSnapshot])
async def get_narrative_timeline_endpoint(narrative_id: str):
    """
    Get timeline data for a specific narrative.
    
    Returns daily snapshots showing how the narrative evolved over time,
    including article counts, entities, and velocity metrics.
    
    This data is suitable for charting narrative growth and activity patterns.
    
    Args:
        narrative_id: MongoDB ObjectId of the narrative
    
    Returns:
        List of timeline snapshots, one per day the narrative was active
    
    Raises:
        404: If narrative not found
        500: If database error occurs
    """
    try:
        timeline_data = await get_narrative_timeline(narrative_id)
        
        if timeline_data is None:
            raise HTTPException(status_code=404, detail="Narrative not found")
        
        return [TimelineSnapshot(**snapshot) for snapshot in timeline_data]
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error fetching narrative timeline: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch timeline data")
