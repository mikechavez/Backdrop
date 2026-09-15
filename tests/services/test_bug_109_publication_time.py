"""
Behavioral tests for BUG-109: Signals must measure article publication time,
not mention processing time, so reprocessing an old article cannot surface
it as fresh news.

These tests exercise the real aggregation pipelines in signal_service.py
and the API-level article-list helpers in signals.py against a live test
MongoDB (mongo_db fixture), not mocks -- correctness here is about actual
query semantics, not source text assertions.
"""

from datetime import datetime, timezone, timedelta

import pytest

from crypto_news_aggregator.services.signal_service import (
    calculate_mentions_and_velocity,
    calculate_source_diversity,
    compute_trending_signals,
)
from crypto_news_aggregator.api.v1.endpoints.signals import (
    get_recent_articles_for_entity,
)
from crypto_news_aggregator.services.rss_service import RSSService
from bson import ObjectId


async def _insert_article(db, published_at, source="coindesk", relevance_tier=None):
    doc = {
        "title": "Test article",
        "text": "Test body",
        "url": f"https://example.com/{ObjectId()}",
        "source": source,
        "source_id": str(ObjectId()),
        "lang": "en",
        "metrics": {},
        "keywords": [],
        "raw_data": {},
        "published_at": published_at,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    if relevance_tier is not None:
        doc["relevance_tier"] = relevance_tier
    result = await db.articles.insert_one(doc)
    return result.inserted_id


async def _insert_mention(
    db,
    entity,
    article_id,
    published_at,
    processed_at=None,
    source="coindesk",
    is_primary=True,
):
    """Insert a mention the way create_entity_mentions_batch_idempotent does:
    published_at set once from the article, created_at/timestamp stamped at
    processing time. `processed_at` lets tests simulate reprocessing an old
    article "today" while its publication date stays in the past.
    """
    processed_at = processed_at or datetime.now(timezone.utc)
    await db.entity_mentions.insert_one(
        {
            "entity": entity,
            "entity_type": "ticker",
            "article_id": str(article_id),
            "sentiment": "neutral",
            "confidence": 1.0,
            "is_primary": is_primary,
            "source": source,
            "timestamp": processed_at,
            "created_at": processed_at,
            "published_at": published_at,
            "metadata": {},
        }
    )


@pytest.mark.asyncio
async def test_weeks_old_article_processed_today_excluded_from_24h(mongo_db):
    """An article published weeks ago but enriched/processed today must not
    contribute to the 24h current-period count -- this is the core BUG-109
    scenario (a reprocessing run backfilling old articles)."""
    now = datetime.now(timezone.utc)
    old_publication = now - timedelta(days=20)
    article_id = await _insert_article(mongo_db, published_at=old_publication)

    # Mention processed "just now" (simulating reprocessing today) but the
    # article's own publication time is 20 days old.
    await _insert_mention(
        mongo_db,
        entity="BUG109_OLD",
        article_id=article_id,
        published_at=old_publication,
        processed_at=now,
    )

    result = await calculate_mentions_and_velocity("BUG109_OLD", timeframe_hours=24)
    assert result["mentions"] == 0.0


@pytest.mark.asyncio
async def test_recently_published_article_processed_today_included(mongo_db):
    """An article published 2 hours ago and processed now must count in the
    24h window."""
    now = datetime.now(timezone.utc)
    recent_publication = now - timedelta(hours=2)
    article_id = await _insert_article(mongo_db, published_at=recent_publication)

    await _insert_mention(
        mongo_db,
        entity="BUG109_RECENT",
        article_id=article_id,
        published_at=recent_publication,
        processed_at=now,
    )

    result = await calculate_mentions_and_velocity("BUG109_RECENT", timeframe_hours=24)
    assert result["mentions"] == 1.0


@pytest.mark.asyncio
async def test_missing_null_malformed_dates_excluded(mongo_db):
    """Mentions with no known publication time (None, missing field) must
    never be substituted with processing/current time and must not
    contribute to any window."""
    now = datetime.now(timezone.utc)
    article_id = await _insert_article(mongo_db, published_at=None)

    # published_at explicitly None
    await _insert_mention(
        mongo_db,
        entity="BUG109_NULLDATE",
        article_id=article_id,
        published_at=None,
        processed_at=now,
    )

    # published_at field entirely missing (legacy mention shape)
    await mongo_db.entity_mentions.insert_one(
        {
            "entity": "BUG109_NULLDATE",
            "entity_type": "ticker",
            "article_id": str(article_id),
            "sentiment": "neutral",
            "confidence": 1.0,
            "is_primary": True,
            "source": "coindesk",
            "timestamp": now,
            "created_at": now,
            "metadata": {},
        }
    )

    result = await calculate_mentions_and_velocity("BUG109_NULLDATE", timeframe_hours=24)
    assert result["mentions"] == 0.0

    trending = await compute_trending_signals(timeframe="24h", limit=50)
    assert not any(s["entity"] == "BUG109_NULLDATE" for s in trending)


@pytest.mark.asyncio
async def test_future_dated_articles_excluded(mongo_db):
    """A mention whose publication time is in the future must be excluded
    from both current and previous windows."""
    now = datetime.now(timezone.utc)
    future_publication = now + timedelta(hours=5)
    article_id = await _insert_article(mongo_db, published_at=future_publication)

    await _insert_mention(
        mongo_db,
        entity="BUG109_FUTURE",
        article_id=article_id,
        published_at=future_publication,
        processed_at=now,
    )

    result = await calculate_mentions_and_velocity("BUG109_FUTURE", timeframe_hours=24)
    assert result["mentions"] == 0.0


@pytest.mark.asyncio
async def test_utc_offset_normalized_correctly():
    """A feed entry with a non-UTC offset must be normalized to the correct
    UTC instant, not shifted by the host machine's local timezone (the
    time.mktime bug this ticket fixes)."""
    import feedparser

    # 2026-01-01T10:00:00-05:00 == 2026-01-01T15:00:00Z
    entry_xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <title>Offset Test</title>
        <link>https://example.com/offset-test</link>
        <description>body</description>
        <pubDate>Thu, 01 Jan 2026 10:00:00 -0500</pubDate>
      </item>
    </channel></rss>
    """
    feed = feedparser.parse(entry_xml)
    service = RSSService()
    articles = service.parse_feed(feed, "coindesk")

    assert len(articles) == 1
    published_at = articles[0].published_at
    assert published_at is not None
    assert published_at.tzinfo is not None
    expected = datetime(2026, 1, 1, 15, 0, 0, tzinfo=timezone.utc)
    assert published_at == expected


@pytest.mark.asyncio
async def test_missing_rss_date_not_fabricated():
    """A feed entry with no pubDate must leave published_at unset rather
    than substituting the current time."""
    import feedparser

    entry_xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <title>No Date Test</title>
        <link>https://example.com/no-date-test</link>
        <description>body</description>
      </item>
    </channel></rss>
    """
    feed = feedparser.parse(entry_xml)
    service = RSSService()
    articles = service.parse_feed(feed, "coindesk")

    assert len(articles) == 1
    assert articles[0].published_at is None


@pytest.mark.asyncio
async def test_exact_window_boundaries(mongo_db):
    """A mention published exactly at now-24h belongs to the current
    period; one published exactly at now-48h belongs to the previous
    period boundary and must not double count."""
    now = datetime.now(timezone.utc)
    # A few seconds of slack account for the small delay between computing
    # this boundary here and calculate_mentions_and_velocity() computing
    # its own "now" moments later -- without it, a boundary_current set to
    # exactly now-24h could land a hair before the function's own
    # current_period_start and be misclassified as "previous" by a race
    # against the clock rather than by the logic under test.
    boundary_current = now - timedelta(hours=24) + timedelta(seconds=5)
    boundary_previous = now - timedelta(hours=48) + timedelta(seconds=5)

    article_current = await _insert_article(mongo_db, published_at=boundary_current)
    article_previous = await _insert_article(mongo_db, published_at=boundary_previous)

    await _insert_mention(
        mongo_db, "BUG109_BOUNDARY", article_current, published_at=boundary_current
    )
    await _insert_mention(
        mongo_db, "BUG109_BOUNDARY", article_previous, published_at=boundary_previous
    )

    result = await calculate_mentions_and_velocity("BUG109_BOUNDARY", timeframe_hours=24)
    # now-24h is >= current_period_start, so it belongs to current.
    # now-48h is exactly previous_period_start, included via $gte in the
    # combined match but assigned to "previous" bucket since it is < current start.
    assert result["mentions"] == 1.0


@pytest.mark.asyncio
async def test_previous_period_and_velocity_use_publication_time(mongo_db):
    """Velocity must be computed from publication-time buckets, not
    processing time -- reprocessing all articles "now" must not collapse
    the current/previous distinction."""
    now = datetime.now(timezone.utc)

    # 3 articles published in the current 24h window
    for i in range(3):
        article_id = await _insert_article(
            mongo_db, published_at=now - timedelta(hours=1 + i)
        )
        await _insert_mention(
            mongo_db,
            "BUG109_VELOCITY",
            article_id,
            published_at=now - timedelta(hours=1 + i),
            processed_at=now,  # all processed "now"
        )

    # 1 article published in the previous 24-48h window, also processed "now"
    old_article_id = await _insert_article(
        mongo_db, published_at=now - timedelta(hours=30)
    )
    await _insert_mention(
        mongo_db,
        "BUG109_VELOCITY",
        old_article_id,
        published_at=now - timedelta(hours=30),
        processed_at=now,
    )

    result = await calculate_mentions_and_velocity("BUG109_VELOCITY", timeframe_hours=24)
    assert result["mentions"] == 3.0
    # previous=1, current=3 -> (3-1)/1*100 = 200%
    assert result["velocity"] == pytest.approx(200.0, abs=0.01)


@pytest.mark.asyncio
async def test_source_diversity_uses_publication_time_scope(mongo_db):
    """Source diversity for a given window must only count sources whose
    mentions fall in that publication-time window."""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=24)

    recent_article = await _insert_article(mongo_db, published_at=now - timedelta(hours=1))
    await _insert_mention(
        mongo_db, "BUG109_DIVERSITY", recent_article, published_at=now - timedelta(hours=1), source="coindesk"
    )

    old_article = await _insert_article(mongo_db, published_at=now - timedelta(days=10))
    await _insert_mention(
        mongo_db, "BUG109_DIVERSITY", old_article, published_at=now - timedelta(days=10), source="decrypt"
    )

    diversity_in_window = await calculate_source_diversity(
        "BUG109_DIVERSITY", start_time=window_start
    )
    assert diversity_in_window == 1


@pytest.mark.asyncio
async def test_explicit_7d_and_30d_windows(mongo_db):
    """Explicit 7d/30d timeframes must apply the same publication-time
    semantics as 24h."""
    now = datetime.now(timezone.utc)

    # Published 10 days ago: excluded from 7d, included in 30d.
    article_id = await _insert_article(mongo_db, published_at=now - timedelta(days=10))
    await _insert_mention(
        mongo_db, "BUG109_7D30D", article_id, published_at=now - timedelta(days=10)
    )

    result_7d = await calculate_mentions_and_velocity("BUG109_7D30D", timeframe_hours=168)
    assert result_7d["mentions"] == 0.0

    result_30d = await calculate_mentions_and_velocity("BUG109_7D30D", timeframe_hours=720)
    assert result_30d["mentions"] == 1.0


@pytest.mark.asyncio
async def test_reprocessing_does_not_move_news_date_or_duplicate(mongo_db):
    """Idempotent mention upsert must preserve the originally recorded
    published_at on retry and must not create a second contribution for
    the same (article, entity) pair."""
    from crypto_news_aggregator.db.operations.entity_mentions import (
        create_entity_mentions_batch_idempotent,
    )

    now = datetime.now(timezone.utc)
    old_publication = now - timedelta(days=15)
    article_id = ObjectId()
    await mongo_db.articles.insert_one(
        {
            "_id": article_id,
            "title": "Reprocessed article",
            "text": "body",
            "url": f"https://example.com/{article_id}",
            "source": "coindesk",
            "source_id": str(article_id),
            "lang": "en",
            "metrics": {},
            "keywords": [],
            "raw_data": {},
            "published_at": old_publication,
            "created_at": now,
            "updated_at": now,
        }
    )

    mention = {
        "entity": "BUG109_REPROCESS",
        "entity_type": "ticker",
        "article_id": str(article_id),
        "sentiment": "neutral",
        "confidence": 1.0,
        "is_primary": True,
        "source": "coindesk",
        "published_at": old_publication,
    }

    # First write. (Called without article_id/owner_token: the
    # non-transactional path, since transactions require a replica-set
    # deployment not available in this test environment. The behavior
    # under test -- $setOnInsert preserving published_at across retries --
    # is identical on both paths; they share _upsert_mention.)
    await create_entity_mentions_batch_idempotent([mention])
    # Simulate a later reprocessing pass that (incorrectly, if the bug
    # were present) might try to stamp a fresh published_at.
    replay_mention = dict(mention)
    replay_mention["published_at"] = now  # attacker/bug scenario: fresh date
    await create_entity_mentions_batch_idempotent([replay_mention])

    docs = await mongo_db.entity_mentions.find(
        {"entity": "BUG109_REPROCESS", "article_id": str(article_id)}
    ).to_list(length=10)

    assert len(docs) == 1  # no duplicate contribution
    stored_published_at = docs[0]["published_at"]
    # Stored as naive UTC by the driver; compare on the UTC wall-clock value.
    if stored_published_at.tzinfo is None:
        stored_published_at = stored_published_at.replace(tzinfo=timezone.utc)
    # BSON datetimes are millisecond-precision, so compare with a small
    # tolerance rather than exact equality; the point under test is that
    # the date did not move forward to `now`, not sub-millisecond fidelity.
    assert abs((stored_published_at - old_publication).total_seconds()) < 1


@pytest.mark.asyncio
async def test_legacy_mentions_without_published_at_excluded_safely(mongo_db):
    """Legacy mentions written before this field existed (no published_at
    key at all) must be excluded from computation, not repaired or
    fabricated, and must not raise errors."""
    now = datetime.now(timezone.utc)
    article_id = await _insert_article(mongo_db, published_at=now - timedelta(hours=3))

    # Legacy-shaped document: no published_at key at all.
    await mongo_db.entity_mentions.insert_one(
        {
            "entity": "BUG109_LEGACY",
            "entity_type": "ticker",
            "article_id": str(article_id),
            "sentiment": "neutral",
            "confidence": 1.0,
            "is_primary": True,
            "source": "coindesk",
            "timestamp": now,
            "created_at": now,
            "metadata": {},
        }
    )

    # Should not raise, and should not surface the entity.
    result = await calculate_mentions_and_velocity("BUG109_LEGACY", timeframe_hours=24)
    assert result["mentions"] == 0.0
    trending = await compute_trending_signals(timeframe="24h", limit=50)
    assert not any(s["entity"] == "BUG109_LEGACY" for s in trending)


@pytest.mark.asyncio
async def test_orphaned_mention_with_malformed_article_id_handled_safely(mongo_db):
    """A mention whose article_id cannot be resolved (malformed/orphaned)
    must not crash publication-time computation; published_at is what
    gates inclusion, and it will simply be absent for such records."""
    now = datetime.now(timezone.utc)
    await mongo_db.entity_mentions.insert_one(
        {
            "entity": "BUG109_ORPHAN",
            "entity_type": "ticker",
            "article_id": "not-a-valid-object-id",
            "sentiment": "neutral",
            "confidence": 1.0,
            "is_primary": True,
            "source": "coindesk",
            "timestamp": now,
            "created_at": now,
            "published_at": None,
            "metadata": {},
        }
    )

    result = await calculate_mentions_and_velocity("BUG109_ORPHAN", timeframe_hours=24)
    assert result["mentions"] == 0.0


@pytest.mark.asyncio
async def test_malformed_article_id_does_not_abort_article_list_aggregation(mongo_db):
    """A malformed article_id must not raise a MongoDB $toObjectId
    conversion error and abort the whole aggregation for an entity that
    also has legitimate, resolvable mentions -- $lookup pipelines that
    join entity_mentions to articles must degrade that one record
    gracefully (excluded), not 500 the whole request.
    """
    now = datetime.now(timezone.utc)

    good_article_id = await _insert_article(mongo_db, published_at=now - timedelta(hours=1))
    await _insert_mention(
        mongo_db,
        "BUG109_MALFORMED_ID",
        good_article_id,
        published_at=now - timedelta(hours=1),
    )

    # A mention with an article_id that cannot be parsed as an ObjectId at
    # all (not just missing/orphaned) -- this is what triggers $toObjectId
    # to throw and abort the whole aggregation if not handled defensively.
    await mongo_db.entity_mentions.insert_one(
        {
            "entity": "BUG109_MALFORMED_ID",
            "entity_type": "ticker",
            "article_id": "not-a-valid-object-id",
            "sentiment": "neutral",
            "confidence": 1.0,
            "is_primary": True,
            "source": "coindesk",
            "timestamp": now,
            "created_at": now,
            "published_at": None,
            "metadata": {},
        }
    )

    # Must not raise.
    articles = await get_recent_articles_for_entity(
        "BUG109_MALFORMED_ID", limit=10, days=7
    )

    good_doc = await mongo_db.articles.find_one({"_id": good_article_id})
    urls_returned = {a["url"] for a in articles}
    assert good_doc["url"] in urls_returned
    assert len(articles) == 1


@pytest.mark.asyncio
async def test_related_article_list_excludes_undated_and_old_reprocessed(mongo_db):
    """The entity-articles endpoint helper must exclude undated articles
    and must window on the article's own published_at, not mention
    processing time, so a reprocessed old article does not appear as a
    'recent mention'."""
    now = datetime.now(timezone.utc)

    fresh_article_id = await _insert_article(mongo_db, published_at=now - timedelta(hours=1))
    await _insert_mention(
        mongo_db, "BUG109_ARTICLES", fresh_article_id, published_at=now - timedelta(hours=1)
    )

    old_article_id = await _insert_article(mongo_db, published_at=now - timedelta(days=20))
    await _insert_mention(
        mongo_db,
        "BUG109_ARTICLES",
        old_article_id,
        published_at=now - timedelta(days=20),
        processed_at=now,  # reprocessed today
    )

    undated_article_id = await _insert_article(mongo_db, published_at=None)
    await _insert_mention(
        mongo_db, "BUG109_ARTICLES", undated_article_id, published_at=None, processed_at=now
    )

    articles = await get_recent_articles_for_entity("BUG109_ARTICLES", limit=10, days=7)

    urls_returned = {a["url"] for a in articles}
    fresh_doc = await mongo_db.articles.find_one({"_id": fresh_article_id})
    old_doc = await mongo_db.articles.find_one({"_id": old_article_id})
    undated_doc = await mongo_db.articles.find_one({"_id": undated_article_id})

    assert fresh_doc["url"] in urls_returned
    assert old_doc["url"] not in urls_returned
    assert undated_doc["url"] not in urls_returned
