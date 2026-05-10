"""
Database operations for the briefing agent.

Handles CRUD operations for:
- daily_briefings: Generated briefings
- briefing_patterns: Detected patterns
- manual_inputs: External sources added by admin
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from crypto_news_aggregator.db.mongodb import mongo_manager


# ============================================================================
# Helper Functions
# ============================================================================

def _get_production_briefings_filter() -> dict:
    """Standard filter for production briefings (excludes smoke tests, invalid, includes historical).

    Uses $or with $exists to safely handle the transition:
    - New smoke tests have `published=False, is_smoke=True`
    - New production briefings have `published=True, is_smoke=False`
    - Historical briefings may lack the `published` field entirely
    - Invalid briefings have `published=False, metadata.invalid_output=True`
    """
    return {
        "$or": [
            {"published": True},
            {"published": {"$exists": False}}  # Include historical briefings
        ],
        "is_smoke": {"$ne": True},
        "metadata.invalid_output": {"$ne": True}  # Exclude invalid briefings
    }


# ============================================================================
# Briefing Operations
# ============================================================================

async def insert_briefing(briefing_data: Dict[str, Any]) -> str:
    """
    Insert a new briefing into the database.

    Args:
        briefing_data: Briefing document to insert

    Returns:
        String ID of the inserted briefing
    """
    db = await mongo_manager.get_async_database()
    collection = db.daily_briefings

    # Ensure timestamps
    now = datetime.now(timezone.utc)
    briefing_data["generated_at"] = briefing_data.get("generated_at", now)
    briefing_data["created_at"] = now

    result = await collection.insert_one(briefing_data)
    return str(result.inserted_id)


async def get_latest_briefing() -> Optional[Dict[str, Any]]:
    """
    Get the most recent briefing (morning or evening).

    Returns:
        Latest briefing document or None
    """
    db = await mongo_manager.get_async_database()
    collection = db.daily_briefings

    cursor = collection.find(_get_production_briefings_filter()).sort("generated_at", -1).limit(1)
    briefing = await cursor.to_list(length=1)

    return briefing[0] if briefing else None


async def get_briefing_by_type_and_date(
    briefing_type: str,
    date: datetime
) -> Optional[Dict[str, Any]]:
    """
    Get a specific briefing by type and date.

    Args:
        briefing_type: "morning" or "evening"
        date: The date to look for

    Returns:
        Briefing document or None
    """
    db = await mongo_manager.get_async_database()
    collection = db.daily_briefings

    # Get start and end of the day
    start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    briefing = await collection.find_one({
        **_get_production_briefings_filter(),
        "type": briefing_type,
        "generated_at": {
            "$gte": start_of_day,
            "$lt": end_of_day
        }
    })

    return briefing


async def get_briefings_last_n_days(days: int = 7) -> List[Dict[str, Any]]:
    """
    Get briefings from the last N days for pattern detection.

    Args:
        days: Number of days to look back (default 7)

    Returns:
        List of briefing documents
    """
    db = await mongo_manager.get_async_database()
    collection = db.daily_briefings

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    cursor = collection.find(
        {
            **_get_production_briefings_filter(),
            "generated_at": {"$gte": cutoff}
        },
        sort=[("generated_at", -1)]
    )

    return await cursor.to_list(length=days * 2 + 2)  # Up to 2 per day + buffer


async def check_briefing_exists_for_slot(
    briefing_type: str,
    date: datetime
) -> bool:
    """
    Check if a briefing already exists for a given slot (prevents duplicates).

    Args:
        briefing_type: "morning" or "evening"
        date: The date to check

    Returns:
        True if briefing exists
    """
    briefing = await get_briefing_by_type_and_date(briefing_type, date)
    return briefing is not None


async def cleanup_old_briefings(retention_days: int = 30) -> int:
    """
    Delete briefings older than retention period.

    Args:
        retention_days: Number of days to keep

    Returns:
        Number of deleted documents
    """
    db = await mongo_manager.get_async_database()
    collection = db.daily_briefings

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    result = await collection.delete_many({
        "generated_at": {"$lt": cutoff}
    })

    return result.deleted_count


# ============================================================================
# Pattern Operations
# ============================================================================

async def insert_pattern(pattern_data: Dict[str, Any]) -> str:
    """
    Insert a detected pattern.

    Args:
        pattern_data: Pattern document to insert

    Returns:
        String ID of the inserted pattern
    """
    db = await mongo_manager.get_async_database()
    collection = db.briefing_patterns

    now = datetime.now(timezone.utc)
    pattern_data["detected_at"] = pattern_data.get("detected_at", now)

    # Convert briefing_id to ObjectId if string
    if isinstance(pattern_data.get("briefing_id"), str):
        pattern_data["briefing_id"] = ObjectId(pattern_data["briefing_id"])

    result = await collection.insert_one(pattern_data)
    return str(result.inserted_id)


async def get_recent_patterns(days: int = 7) -> List[Dict[str, Any]]:
    """
    Get patterns detected in the last N days.

    Args:
        days: Number of days to look back

    Returns:
        List of pattern documents
    """
    db = await mongo_manager.get_async_database()
    collection = db.briefing_patterns

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    cursor = collection.find(
        {"detected_at": {"$gte": cutoff}},
        sort=[("detected_at", -1)]
    )

    return await cursor.to_list(length=100)


async def get_patterns_by_entity(entity: str, days: int = 30) -> List[Dict[str, Any]]:
    """
    Get patterns involving a specific entity.

    Args:
        entity: Entity name to search for
        days: Number of days to look back

    Returns:
        List of pattern documents
    """
    db = await mongo_manager.get_async_database()
    collection = db.briefing_patterns

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    cursor = collection.find(
        {
            "entities": entity,
            "detected_at": {"$gte": cutoff}
        },
        sort=[("detected_at", -1)]
    )

    return await cursor.to_list(length=50)


# ============================================================================
# Manual Input Operations
# ============================================================================

async def insert_manual_input(input_data: Dict[str, Any]) -> str:
    """
    Insert a manual input (external source).

    Args:
        input_data: Manual input document to insert

    Returns:
        String ID of the inserted input
    """
    db = await mongo_manager.get_async_database()
    collection = db.manual_inputs

    now = datetime.now(timezone.utc)
    input_data["added_at"] = now
    input_data["status"] = "pending"
    input_data["expires_at"] = now + timedelta(days=7)  # Auto-expire in 7 days

    result = await collection.insert_one(input_data)
    return str(result.inserted_id)


async def get_pending_manual_inputs() -> List[Dict[str, Any]]:
    """
    Get all pending manual inputs (not yet used or expired).

    Returns:
        List of pending input documents
    """
    db = await mongo_manager.get_async_database()
    collection = db.manual_inputs

    now = datetime.now(timezone.utc)

    cursor = collection.find({
        "status": "pending",
        "expires_at": {"$gt": now}
    }, sort=[("added_at", -1)])

    return await cursor.to_list(length=50)


async def mark_manual_input_used(input_id: str, briefing_id: str) -> bool:
    """
    Mark a manual input as used in a briefing.

    Args:
        input_id: ID of the manual input
        briefing_id: ID of the briefing that used it

    Returns:
        True if updated successfully
    """
    db = await mongo_manager.get_async_database()
    collection = db.manual_inputs

    result = await collection.update_one(
        {"_id": ObjectId(input_id)},
        {
            "$set": {
                "status": "used",
                "used_in_briefing_id": ObjectId(briefing_id)
            }
        }
    )

    return result.modified_count > 0


async def delete_manual_input(input_id: str) -> bool:
    """
    Delete a manual input.

    Args:
        input_id: ID of the input to delete

    Returns:
        True if deleted successfully
    """
    db = await mongo_manager.get_async_database()
    collection = db.manual_inputs

    result = await collection.delete_one({"_id": ObjectId(input_id)})
    return result.deleted_count > 0


async def expire_old_manual_inputs() -> int:
    """
    Mark expired manual inputs.

    Returns:
        Number of inputs marked as expired
    """
    db = await mongo_manager.get_async_database()
    collection = db.manual_inputs

    now = datetime.now(timezone.utc)

    result = await collection.update_many(
        {
            "status": "pending",
            "expires_at": {"$lte": now}
        },
        {"$set": {"status": "expired"}}
    )

    return result.modified_count


# ============================================================================
# Index Creation
# ============================================================================

async def ensure_briefing_indexes():
    """
    Create indexes for briefing collections.

    Should be called on application startup.
    """
    db = await mongo_manager.get_async_database()

    # daily_briefings indexes
    await db.daily_briefings.create_index(
        [("type", 1), ("generated_at", -1)],
        name="type_generated_at"
    )
    await db.daily_briefings.create_index(
        [("generated_at", -1)],
        name="generated_at_desc"
    )

    # briefing_patterns indexes
    await db.briefing_patterns.create_index(
        [("pattern_type", 1), ("detected_at", -1)],
        name="pattern_type_detected_at"
    )
    await db.briefing_patterns.create_index(
        [("entities", 1)],
        name="entities"
    )
    await db.briefing_patterns.create_index(
        [("detected_at", -1)],
        name="detected_at_desc"
    )

    # manual_inputs indexes
    await db.manual_inputs.create_index(
        [("status", 1), ("added_at", -1)],
        name="status_added_at"
    )
    await db.manual_inputs.create_index(
        [("expires_at", 1)],
        name="expires_at",
        expireAfterSeconds=0  # TTL index - MongoDB auto-deletes when expires_at is reached
    )
