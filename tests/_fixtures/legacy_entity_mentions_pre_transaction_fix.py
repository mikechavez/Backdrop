"""
Verbatim snapshot of the PRE-FIX `create_entity_mentions_batch_idempotent()`
as it existed in the working tree at the start of this session, before the
transaction-based atomic-ownership fix (BUG-108, 2026-09-15).

This is NOT a re-derived or hand-written "unsafe example" -- it is the
literal function body this session found on disk (captured verbatim from
the file read at the start of the session, before any edits), preserved
here so the regression test can prove the actual previous implementation
fails the race it claimed to close, rather than testing a stand-in.

Do not import this into production code. Test-only.
"""

from typing import List, Dict, Any
from datetime import datetime, timezone
from pymongo.errors import DuplicateKeyError
from crypto_news_aggregator.db.mongodb import mongo_manager
from crypto_news_aggregator.db.models import EntityType


async def create_entity_mentions_batch_idempotent_pre_fix(
    mentions: List[Dict[str, Any]],
    article_id: Any = None,
    owner_token: str = None,
) -> int:
    """
    Idempotently upsert entity mentions, with atomic ownership verification.

    Uniqueness key: (article_id, entity, entity_type, is_primary), backed by
    the article_entity_type_primary_unique index. Without a unique index,
    two concurrent upsert=True calls can both see "not found" and both insert.
    With the index, the second gets DuplicateKeyError, caught here and
    retried as a plain update for idempotency.

    OWNERSHIP GUARANTEE (BUG-108 defect 1 fix):
    When article_id and owner_token are provided, ownership is verified AT
    THE SAME TIME as mention persistence (atomic). The article document is
    checked to still be owned by owner_token; if ownership has changed (lease
    was reclaimed), no mentions are written. This prevents stale workers from
    persisting mentions for articles they no longer own.

    Args:
        mentions: List of mention dicts with keys: entity, entity_type,
            article_id, sentiment, confidence, source (optional),
            is_primary (optional)
        article_id: (optional) Article ID to verify ownership of before writing.
        owner_token: (optional) Owner token. If provided, verifies ownership
            atomically with mention writes.

    Returns:
        Number of mentions upserted (matched + newly inserted).
    """
    if not mentions:
        return 0

    db = await mongo_manager.get_async_database()
    collection = db.entity_mentions
    articles_collection = db.articles

    now = datetime.now(timezone.utc)
    upserted_count = 0

    # If ownership token provided, verify it before writing any mentions.
    # This is done once for the batch, not per-mention, for efficiency.
    if article_id is not None and owner_token is not None:
        article = await articles_collection.find_one(
            {
                "_id": article_id,
                "enrichment.status": "in_progress",
                "enrichment.owner_token": owner_token,
            }
        )
        if article is None:
            # Ownership lost (lease reclaimed or article already completed).
            # Do not write any mentions.
            return 0

    for mention in mentions:
        entity_type = mention["entity_type"]
        is_primary = mention.get("is_primary")
        if is_primary is None:
            is_primary = EntityType.is_primary(entity_type)

        key = {
            "article_id": mention["article_id"],
            "entity": mention["entity"],
            "entity_type": entity_type,
            "is_primary": is_primary,
        }

        update_fields = {
            "sentiment": mention.get("sentiment", "neutral"),
            "confidence": mention.get("confidence", 1.0),
            "source": mention.get("source", "unknown"),
            "metadata": mention.get("metadata", {}),
        }

        try:
            result = await collection.update_one(
                key,
                {
                    "$set": update_fields,
                    "$setOnInsert": {
                        "timestamp": now,
                        "created_at": now,
                        **key,
                    },
                },
                upsert=True,
            )
            if result.upserted_id is not None or result.matched_count > 0:
                upserted_count += 1
        except DuplicateKeyError:
            # Lost a concurrent upsert race on the unique index: another
            # writer inserted this key between our existence check and our
            # insert attempt. The document now exists; converge to it with
            # a plain update instead of treating this as a failure.
            result = await collection.update_one(key, {"$set": update_fields})
            if result.matched_count > 0:
                upserted_count += 1

    return upserted_count
