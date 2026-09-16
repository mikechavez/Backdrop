"""Tests for the read-only entity_mentions duplicate-remediation audit
(BUG-110).

Covers: identical duplicates, duplicates that differ on real fields, large
groups, and dry-run cleanup behavior (including that cleanup refuses to run
without the exact confirmation phrase, and that dry_run=True never deletes
anything).
"""

from datetime import datetime, timedelta, timezone

import pytest

from crypto_news_aggregator.db.operations.entity_mentions_duplicate_audit import (
    CLEANUP_CONFIRMATION_PHRASE,
    choose_canonical,
    compare_group_documents,
    execute_cleanup_plan,
    plan_duplicate_cleanup,
    run_duplicate_audit,
)


def _mention(article_id, entity, entity_type, is_primary, created_at, **overrides):
    doc = {
        "article_id": article_id,
        "entity": entity,
        "entity_type": entity_type,
        "is_primary": is_primary,
        "sentiment": "neutral",
        "confidence": 1.0,
        "source": "unknown",
        "metadata": {},
        "published_at": None,
        "created_at": created_at,
        "timestamp": created_at,
    }
    doc.update(overrides)
    return doc


@pytest.mark.asyncio
async def test_run_duplicate_audit_reports_no_groups_when_all_unique(mongo_db):
    await mongo_db.entity_mentions.delete_many({})
    now = datetime.now(timezone.utc)
    await mongo_db.entity_mentions.insert_many(
        [
            _mention("a1", "Bitcoin", "cryptocurrency", True, now),
            _mention("a2", "Ethereum", "cryptocurrency", True, now),
        ]
    )

    report = await run_duplicate_audit(mongo_db.entity_mentions)

    assert report.duplicate_groups == 0
    assert report.excess_documents == 0


@pytest.mark.asyncio
async def test_run_duplicate_audit_identical_duplicates(mongo_db):
    """Byte-identical duplicates: same group key, same field values."""
    await mongo_db.entity_mentions.delete_many({})
    now = datetime.now(timezone.utc)
    docs = [_mention("a1", "Bitcoin", "cryptocurrency", True, now) for _ in range(3)]
    await mongo_db.entity_mentions.insert_many(docs)

    report = await run_duplicate_audit(mongo_db.entity_mentions)

    assert report.duplicate_groups == 1
    assert report.total_documents_in_duplicate_groups == 3
    assert report.excess_documents == 2
    assert report.max_group_size == 3
    assert report.max_group_key == {
        "article_id": "a1",
        "entity": "Bitcoin",
        "entity_type": "cryptocurrency",
        "is_primary": True,
    }

    comparison = await compare_group_documents(
        mongo_db.entity_mentions,
        {"article_id": "a1", "entity": "Bitcoin", "entity_type": "cryptocurrency", "is_primary": True},
    )
    assert comparison.identical is True
    assert comparison.field_differences == []


@pytest.mark.asyncio
async def test_run_duplicate_audit_differing_field_duplicates(mongo_db):
    """Duplicates that share the group key but disagree on real fields."""
    await mongo_db.entity_mentions.delete_many({})
    now = datetime.now(timezone.utc)
    docs = [
        _mention("a1", "Bitcoin", "cryptocurrency", True, now, sentiment="positive", source="CoinDesk"),
        _mention(
            "a1",
            "Bitcoin",
            "cryptocurrency",
            True,
            now + timedelta(minutes=5),
            sentiment="negative",
            source="Cointelegraph",
            published_at=now,
        ),
    ]
    await mongo_db.entity_mentions.insert_many(docs)

    comparison = await compare_group_documents(
        mongo_db.entity_mentions,
        {"article_id": "a1", "entity": "Bitcoin", "entity_type": "cryptocurrency", "is_primary": True},
    )

    assert comparison.identical is False
    fields_that_differ = {d.field for d in comparison.field_differences}
    assert "sentiment" in fields_that_differ
    assert "source" in fields_that_differ
    assert "published_at" in fields_that_differ

    all_docs = await mongo_db.entity_mentions.find(
        {"article_id": "a1", "entity": "Bitcoin", "entity_type": "cryptocurrency", "is_primary": True}
    ).to_list(length=10)
    choice = choose_canonical(comparison, all_docs)

    # Policy: prefer the document with a non-null published_at.
    canonical_doc = next(d for d in all_docs if str(d["_id"]) == choice.canonical_id)
    assert canonical_doc["published_at"] is not None
    assert len(choice.discard_ids) == 1


@pytest.mark.asyncio
async def test_run_duplicate_audit_large_group(mongo_db):
    """A large duplicate group (analogous to the production 7,448-doc case)
    is still counted correctly and captured in the size distribution."""
    await mongo_db.entity_mentions.delete_many({})
    now = datetime.now(timezone.utc)
    group_size = 250
    docs = [
        _mention("bigarticle", "Bitcoin", "cryptocurrency", True, now + timedelta(seconds=i))
        for i in range(group_size)
    ]
    await mongo_db.entity_mentions.insert_many(docs)

    report = await run_duplicate_audit(mongo_db.entity_mentions)

    assert report.duplicate_groups == 1
    assert report.total_documents_in_duplicate_groups == group_size
    assert report.excess_documents == group_size - 1
    assert report.max_group_size == group_size

    bucket = next(b for b in report.size_distribution if b.label == "101-1000")
    assert bucket.group_count == 1
    assert bucket.document_count == group_size


@pytest.mark.asyncio
async def test_plan_duplicate_cleanup_skips_groups_over_size_limit(mongo_db):
    await mongo_db.entity_mentions.delete_many({})
    now = datetime.now(timezone.utc)
    docs = [_mention("bigarticle", "Bitcoin", "cryptocurrency", True, now) for _ in range(50)]
    await mongo_db.entity_mentions.insert_many(docs)

    plan = await plan_duplicate_cleanup(mongo_db.entity_mentions, max_group_size_for_auto_plan=10)

    assert plan.groups_planned == 0
    assert len(plan.skipped_groups) == 1
    assert plan.skipped_groups[0]["count"] == 50


@pytest.mark.asyncio
async def test_plan_duplicate_cleanup_builds_plan_for_small_groups(mongo_db):
    await mongo_db.entity_mentions.delete_many({})
    now = datetime.now(timezone.utc)
    docs = [_mention("a1", "Bitcoin", "cryptocurrency", True, now) for _ in range(3)]
    await mongo_db.entity_mentions.insert_many(docs)

    plan = await plan_duplicate_cleanup(mongo_db.entity_mentions, max_group_size_for_auto_plan=100)

    assert plan.groups_planned == 1
    assert len(plan.documents_to_delete) == 2  # keep 1, discard 2
    remaining = await mongo_db.entity_mentions.count_documents({"article_id": "a1"})
    assert remaining == 3  # planning must never delete anything


@pytest.mark.asyncio
async def test_execute_cleanup_plan_rejects_wrong_confirmation(mongo_db):
    await mongo_db.entity_mentions.delete_many({})
    now = datetime.now(timezone.utc)
    docs = [_mention("a1", "Bitcoin", "cryptocurrency", True, now) for _ in range(3)]
    await mongo_db.entity_mentions.insert_many(docs)
    plan = await plan_duplicate_cleanup(mongo_db.entity_mentions)

    with pytest.raises(ValueError):
        await execute_cleanup_plan(mongo_db.entity_mentions, plan, confirm="yes please")

    remaining = await mongo_db.entity_mentions.count_documents({"article_id": "a1"})
    assert remaining == 3


@pytest.mark.asyncio
async def test_execute_cleanup_plan_dry_run_deletes_nothing(mongo_db):
    await mongo_db.entity_mentions.delete_many({})
    now = datetime.now(timezone.utc)
    docs = [_mention("a1", "Bitcoin", "cryptocurrency", True, now) for _ in range(3)]
    await mongo_db.entity_mentions.insert_many(docs)
    plan = await plan_duplicate_cleanup(mongo_db.entity_mentions)

    report = await execute_cleanup_plan(
        mongo_db.entity_mentions,
        plan,
        confirm=CLEANUP_CONFIRMATION_PHRASE,
        dry_run=True,
    )

    assert report.dry_run is True
    assert report.total_deleted == 2  # counted as "would delete", nothing actually removed

    remaining = await mongo_db.entity_mentions.count_documents({"article_id": "a1"})
    assert remaining == 3


@pytest.mark.asyncio
async def test_execute_cleanup_plan_execute_deletes_only_discarded_docs(mongo_db):
    await mongo_db.entity_mentions.delete_many({})
    now = datetime.now(timezone.utc)
    docs = [_mention("a1", "Bitcoin", "cryptocurrency", True, now) for _ in range(3)]
    await mongo_db.entity_mentions.insert_many(docs)
    plan = await plan_duplicate_cleanup(mongo_db.entity_mentions)
    canonical_id = plan.choices[0].canonical_id

    report = await execute_cleanup_plan(
        mongo_db.entity_mentions,
        plan,
        confirm=CLEANUP_CONFIRMATION_PHRASE,
        batch_size=1,
        dry_run=False,
    )

    assert report.dry_run is False
    assert report.total_deleted == 2

    remaining = await mongo_db.entity_mentions.find({"article_id": "a1"}).to_list(length=10)
    assert len(remaining) == 1
    assert str(remaining[0]["_id"]) == canonical_id


@pytest.mark.asyncio
async def test_execute_cleanup_plan_batches_deletes(mongo_db):
    """batch_size bounds the operation into multiple batches rather than
    one unbounded delete_many."""
    await mongo_db.entity_mentions.delete_many({})
    now = datetime.now(timezone.utc)
    docs = [_mention("a1", "Bitcoin", "cryptocurrency", True, now) for _ in range(10)]
    await mongo_db.entity_mentions.insert_many(docs)
    plan = await plan_duplicate_cleanup(mongo_db.entity_mentions)

    report = await execute_cleanup_plan(
        mongo_db.entity_mentions,
        plan,
        confirm=CLEANUP_CONFIRMATION_PHRASE,
        batch_size=3,
        dry_run=False,
    )

    assert report.total_deleted == 9
    assert report.batches == 3  # 9 discard_ids / batch_size 3
