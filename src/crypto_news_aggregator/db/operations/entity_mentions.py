import logging
from typing import List, Dict, Any
from datetime import datetime, timezone
from pymongo.errors import DuplicateKeyError
from crypto_news_aggregator.db.mongodb import mongo_manager
from crypto_news_aggregator.db.models import EntityType

logger = logging.getLogger(__name__)


class OwnershipLostError(Exception):
    """Raised when the fenced ownership write inside the mention-persistence
    transaction matches zero documents, meaning the caller's lease was
    reclaimed by another worker. Used internally to abort the transaction;
    callers see it converted to a normal `0 mentions written` return."""


async def create_entity_mention(
    entity: str,
    entity_type: str,
    article_id: str,
    sentiment: str,
    confidence: float = 1.0,
    is_primary: bool = None,
    source: str = None,
    metadata: Dict[str, Any] = None,
) -> str:
    """
    Creates a new entity mention record in the database.

    Args:
        entity: The entity name/value (e.g., "$BTC", "Bitcoin", "regulation")
        entity_type: Type of entity (one of EntityType values)
        article_id: ID of the article where entity was mentioned
        sentiment: Sentiment of the mention (positive, negative, neutral)
        confidence: Confidence score of the extraction (0.0-1.0)
        is_primary: Whether this is a primary entity (auto-determined if None)
        source: Source of the article (e.g., "CoinDesk", "Cointelegraph")
        metadata: Additional metadata about the mention

    Returns:
        The ID of the created entity mention
    """
    db = await mongo_manager.get_async_database()
    collection = db.entity_mentions

    # Auto-determine is_primary if not provided
    if is_primary is None:
        is_primary = EntityType.is_primary(entity_type)

    mention_data = {
        "entity": entity,
        "entity_type": entity_type,
        "article_id": article_id,
        "sentiment": sentiment,
        "confidence": confidence,
        "is_primary": is_primary,
        "source": source or "unknown",
        "timestamp": datetime.now(timezone.utc),
        "created_at": datetime.now(timezone.utc),
        "metadata": metadata or {},
    }

    result = await collection.insert_one(mention_data)
    return str(result.inserted_id)


async def create_entity_mentions_batch(mentions: List[Dict[str, Any]]) -> List[str]:
    """
    Creates multiple entity mention records in a single batch operation.

    Args:
        mentions: List of mention dicts with keys: entity, entity_type, article_id, sentiment, confidence, source (optional), is_primary (optional)

    Returns:
        List of created mention IDs
    """
    db = await mongo_manager.get_async_database()
    collection = db.entity_mentions

    now = datetime.now(timezone.utc)
    mention_docs = []

    for mention in mentions:
        entity_type = mention["entity_type"]
        # Auto-determine is_primary if not provided
        is_primary = mention.get("is_primary")
        if is_primary is None:
            is_primary = EntityType.is_primary(entity_type)

        mention_doc = {
            "entity": mention["entity"],
            "entity_type": entity_type,
            "article_id": mention["article_id"],
            "sentiment": mention.get("sentiment", "neutral"),
            "confidence": mention.get("confidence", 1.0),
            "is_primary": is_primary,
            "source": mention.get("source", "unknown"),
            "timestamp": now,
            "created_at": now,
            "metadata": mention.get("metadata", {}),
        }
        mention_docs.append(mention_doc)

    if mention_docs:
        result = await collection.insert_many(mention_docs)
        return [str(id) for id in result.inserted_ids]
    return []


async def _upsert_mention(collection, mention: Dict[str, Any], now: datetime, session=None) -> bool:
    """Upsert a single mention within the given session (or no session).
    Returns True if the mention was inserted or matched an existing doc."""
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
            session=session,
        )
        return result.upserted_id is not None or result.matched_count > 0
    except DuplicateKeyError:
        # Lost a concurrent upsert race on the unique index: another
        # writer inserted this key between our existence check and our
        # insert attempt. The document now exists; converge to it with
        # a plain update instead of treating this as a failure.
        result = await collection.update_one(key, {"$set": update_fields}, session=session)
        return result.matched_count > 0


async def create_entity_mentions_batch_idempotent(
    mentions: List[Dict[str, Any]],
    article_id: Any = None,
    owner_token: str = None,
    _after_fence_hook=None,
    _before_fence_hook=None,
    _after_first_mention_hook=None,
) -> int:
    """
    Idempotently upsert entity mentions, with atomic ownership enforcement.

    Uniqueness key: (article_id, entity, entity_type, is_primary), backed by
    the article_entity_type_primary_unique index. Without a unique index,
    two concurrent upsert=True calls can both see "not found" and both insert.
    With the index, the second gets DuplicateKeyError, caught here and
    retried as a plain update for idempotency.

    OWNERSHIP GUARANTEE (BUG-108 defect 1 fix, corrected):
    When article_id and owner_token are provided, ownership enforcement uses
    a real MongoDB multi-document transaction. Inside that transaction we
    first perform a *conditional write* (not a read) to the article's
    enrichment.updated_at field, fenced on {status: in_progress, owner_token},
    then persist the mentions -- all in the same session. If a competing
    worker has already reclaimed the lease (changed owner_token or status),
    the fenced write matches zero documents; we abort the transaction and no
    mentions are written. A read-only ownership check before separate writes
    (the prior implementation) cannot provide this guarantee: MongoDB can
    still interleave another worker's takeover between the check and the
    writes, or between individual mention writes. A transaction closes that
    window because the fenced write and every mention write commit or abort
    together as a single atomic unit. Empirically verified (see
    tests/background/test_rss_fetcher_worker_state.py::
    test_real_writer_blocks_takeover_that_overlaps_live_transaction) against
    a real replica set: WiredTiger takes a document-level lock for the
    transaction's fenced write, so a concurrent non-transactional writer
    attempting the same document either (a) started before this fenced
    write was staged, in which case this fenced write correctly evaluates
    against the document as that writer left it and fails to match if
    ownership changed, or (b) started after, in which case it blocks until
    this transaction commits or aborts, then proceeds against the
    now-committed state. There is no interleaving in which a competing
    writer's change is invisible to this fenced write yet this fenced write
    still commits -- the two orderings above are exhaustive.

    Requires a replica set (or sharded cluster) deployment; standalone
    mongod does not support transactions. Callers must ensure the configured
    MongoDB deployment supports them when passing article_id/owner_token.

    Args:
        mentions: List of mention dicts with keys: entity, entity_type,
            article_id, sentiment, confidence, source (optional),
            is_primary (optional)
        article_id: (optional) Article ID to enforce ownership of before writing.
        owner_token: (optional) Owner token. If provided, ownership is
            enforced atomically with mention writes via a transaction.

    Returns:
        Number of mentions upserted (matched + newly inserted). Returns 0
        without writing anything if ownership has been lost.
    """
    if not mentions:
        return 0

    db = await mongo_manager.get_async_database()
    collection = db.entity_mentions
    articles_collection = db.articles

    now = datetime.now(timezone.utc)

    if article_id is None or owner_token is None:
        upserted_count = 0
        for mention in mentions:
            if await _upsert_mention(collection, mention, now):
                upserted_count += 1
        return upserted_count

    client = await mongo_manager.get_async_client()
    upserted_count = 0
    try:
        async with await client.start_session() as session:
            async def _txn(session):
                nonlocal upserted_count
                upserted_count = 0

                if _before_fence_hook is not None:
                    # TEST-ONLY instrumentation point: fires inside the live
                    # transaction, before the fenced ownership write is even
                    # attempted, so a concurrent writer can be given a head
                    # start to actually acquire the document's write lock
                    # first (proving this transaction correctly loses a
                    # genuine race rather than always winning because it
                    # staged its write before any competitor started).
                    # Production callers never pass this.
                    await _before_fence_hook()

                # Conditional WRITE (not a read) to the article's ownership
                # record, fenced on still owning the in-progress lease. This
                # is what makes the guarantee atomic: a competing takeover
                # must either happen-before or happen-after this write
                # within the transaction's snapshot, never interleaved with
                # the mention writes below.
                fence_result = await articles_collection.update_one(
                    {
                        "_id": article_id,
                        "enrichment.status": "in_progress",
                        "enrichment.owner_token": owner_token,
                    },
                    {"$set": {"enrichment.updated_at": now}},
                    session=session,
                )
                if fence_result.matched_count == 0:
                    # Ownership lost (lease reclaimed or article already
                    # completed/failed). Abort: raising inside the callback
                    # triggers with_transaction's abort-and-do-not-retry
                    # path for this non-transient condition.
                    raise OwnershipLostError()

                if _after_fence_hook is not None:
                    # TEST-ONLY instrumentation point: fires inside the live
                    # transaction, after the fenced ownership write has been
                    # staged but before the transaction commits or any
                    # mention write happens. Lets tests signal a second,
                    # concurrent session to attempt a takeover while this
                    # transaction is still open, rather than only sequencing
                    # a takeover before this call starts. The hook itself
                    # must not block waiting on that concurrent attempt to
                    # finish -- MongoDB's own conflict handling (the
                    # concurrent writer blocking on this transaction, or this
                    # transaction aborting on conflict) is what is under
                    # test, and blocking here would deadlock against a
                    # concurrent writer that is itself waiting on this
                    # transaction to resolve. Production callers never pass
                    # this.
                    await _after_fence_hook()

                for idx, mention in enumerate(mentions):
                    if await _upsert_mention(collection, mention, now, session=session):
                        upserted_count += 1
                    if idx == 0 and _after_first_mention_hook is not None:
                        # TEST-ONLY instrumentation point: fires inside the
                        # live transaction, immediately after the FIRST
                        # mention write has been staged but before any
                        # subsequent mention write or commit. Lets tests
                        # force a failure partway through a multi-mention
                        # batch to verify the transaction leaves no partial
                        # mention writes -- i.e. that this first write is
                        # rolled back along with everything else, not just
                        # left uncommitted-but-visible. Production callers
                        # never pass this.
                        await _after_first_mention_hook()

            await session.with_transaction(_txn)
    except OwnershipLostError:
        return 0

    return upserted_count


async def get_entity_mentions(
    entity: str = None,
    entity_type: str = None,
    article_id: str = None,
    sentiment: str = None,
    is_primary: bool = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Retrieves entity mentions based on filters.

    Args:
        entity: Filter by specific entity
        entity_type: Filter by entity type
        article_id: Filter by article ID
        sentiment: Filter by sentiment
        is_primary: Filter by primary entity flag
        limit: Maximum number of results

    Returns:
        List of entity mention documents
    """
    db = await mongo_manager.get_async_database()
    collection = db.entity_mentions

    query = {}
    if entity:
        query["entity"] = entity
    if entity_type:
        query["entity_type"] = entity_type
    if article_id:
        query["article_id"] = article_id
    if sentiment:
        query["sentiment"] = sentiment
    if is_primary is not None:
        query["is_primary"] = is_primary

    cursor = collection.find(query).sort("timestamp", -1).limit(limit)
    mentions = []
    async for mention in cursor:
        mention["_id"] = str(mention["_id"])
        mentions.append(mention)

    return mentions


async def get_entity_stats(entity: str) -> Dict[str, Any]:
    """
    Gets aggregated statistics for a specific entity.

    Args:
        entity: The entity to get stats for

    Returns:
        Dict with mention count, sentiment distribution, and recent mentions
    """
    db = await mongo_manager.get_async_database()
    collection = db.entity_mentions

    # Count total mentions
    total_count = await collection.count_documents({"entity": entity})

    # Get sentiment distribution
    pipeline = [
        {"$match": {"entity": entity}},
        {"$group": {"_id": "$sentiment", "count": {"$sum": 1}}},
    ]
    sentiment_dist = {}
    async for result in collection.aggregate(pipeline):
        sentiment_dist[result["_id"]] = result["count"]

    # Get recent mentions
    recent_cursor = collection.find({"entity": entity}).sort("timestamp", -1).limit(10)
    recent_mentions = []
    async for mention in recent_cursor:
        mention["_id"] = str(mention["_id"])
        recent_mentions.append(mention)

    return {
        "entity": entity,
        "total_mentions": total_count,
        "sentiment_distribution": sentiment_dist,
        "recent_mentions": recent_mentions,
    }


async def delete_entity_mentions_for_article(article_id: str) -> int:
    """
    Delete all entity mentions associated with a specific article.
    
    This should be called when an article is deleted to prevent orphaned mentions.
    
    Args:
        article_id: The ID of the article whose mentions should be deleted
    
    Returns:
        Number of entity mentions deleted
    """
    db = await mongo_manager.get_async_database()
    collection = db.entity_mentions
    
    result = await collection.delete_many({"article_id": article_id})
    return result.deleted_count


async def delete_entity_mentions_for_articles(article_ids: List[str]) -> int:
    """
    Delete all entity mentions associated with multiple articles.
    
    This should be called when articles are deleted in batch to prevent orphaned mentions.
    
    Args:
        article_ids: List of article IDs whose mentions should be deleted
    
    Returns:
        Number of entity mentions deleted
    """
    db = await mongo_manager.get_async_database()
    collection = db.entity_mentions
    
    result = await collection.delete_many({"article_id": {"$in": article_ids}})
    return result.deleted_count
