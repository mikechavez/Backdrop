"""
Behavioral tests for the explicit entity_mentions unique-index rollout
(BUG-108, review follow-up: finding 4).

These tests run against a dedicated scratch collection
(mongo_db["entity_mentions_index_rollout_scratch"]) rather than the shared
entity_mentions collection used by test_entity_mentions_idempotent.py.
Creating a real persistent unique index inside the shared collection was
found to race the mongo_db fixture's per-test drop_database/recreate cycle
under sustained local load (a background index build from one test
overlapping the next test's drop_database, causing cross-test data bleed
into unrelated tests). Using a throwaway collection name per file avoids
that interaction entirely, since it carries no state any other test file
depends on.
"""

import asyncio

import pytest

from crypto_news_aggregator.db.operations.entity_mentions import (
    create_entity_mentions_batch_idempotent,
)
from crypto_news_aggregator.db.operations.entity_mentions_index_rollout import (
    UNIQUE_INDEX_NAME,
    check_for_duplicate_mentions,
    create_unique_index,
    verify_unique_index_exists_and_valid,
)

SCRATCH_COLLECTION = "entity_mentions_index_rollout_scratch"


@pytest.fixture
def scratch_collection(mongo_db):
    return mongo_db[SCRATCH_COLLECTION]


@pytest.mark.asyncio
async def test_unique_index_exists_after_explicit_rollout(scratch_collection):
    """The article_entity_type_primary_unique index must actually be
    present once explicitly rolled out. Not auto-created by
    MongoManager.initialize_indexes() -- an automatic unique-index creation
    at application startup risks crashing the whole startup lifespan on
    pre-existing duplicates (see finding 4)."""
    created = await create_unique_index(scratch_collection)
    assert created is True

    indexes = await scratch_collection.index_information()
    assert UNIQUE_INDEX_NAME in indexes
    index_spec = indexes[UNIQUE_INDEX_NAME]
    assert index_spec.get("unique") is True
    key_fields = [field for field, _ in index_spec["key"]]
    assert key_fields == ["article_id", "entity", "entity_type", "is_primary"]


@pytest.mark.asyncio
async def test_initialize_indexes_does_not_auto_create_unique_mention_index(mongo_db):
    """Confirms the unique index is NOT part of the automatic index set
    created by app startup / MongoManager.initialize_indexes() on the real
    entity_mentions collection -- it must only be created via the explicit,
    operator-gated rollout path. Checks entity_mentions directly (not the
    scratch collection) since that is the collection app startup actually
    initializes indexes on."""
    indexes = await mongo_db.entity_mentions.index_information()
    assert UNIQUE_INDEX_NAME not in indexes


@pytest.mark.asyncio
async def test_duplicate_preflight_reports_existing_duplicates(scratch_collection):
    """check_for_duplicate_mentions() must detect pre-existing duplicate
    keys (inserted directly, bypassing the idempotent writer, to simulate
    data from before this ticket's changes) so an operator can resolve them
    before the unique index can be created."""
    dup = {
        "entity": "Bitcoin",
        "entity_type": "project",
        "article_id": "dup-test",
        "is_primary": True,
    }
    await scratch_collection.insert_many([dup, dict(dup)])

    report = await check_for_duplicate_mentions(scratch_collection)

    assert report.duplicate_groups == 1
    assert report.duplicate_documents == 2
    assert report.safe_to_create_index is False


@pytest.mark.asyncio
async def test_duplicate_preflight_clean_collection_is_safe(scratch_collection):
    await scratch_collection.insert_one(
        {
            "entity": "Bitcoin",
            "entity_type": "project",
            "article_id": "clean-test",
            "is_primary": True,
        }
    )

    report = await check_for_duplicate_mentions(scratch_collection)

    assert report.duplicate_groups == 0
    assert report.safe_to_create_index is True


@pytest.mark.asyncio
async def test_create_unique_index_fails_safely_with_existing_duplicates(scratch_collection):
    """If an operator skips the preflight (or runs create_unique_index()
    against a collection with duplicates present), index creation must fail
    cleanly (return False) rather than raise uncaught or silently succeed
    with a non-unique index."""
    dup = {
        "entity": "Bitcoin",
        "entity_type": "project",
        "article_id": "dup-create-test",
        "is_primary": True,
    }
    await scratch_collection.insert_many([dup, dict(dup)])

    created = await create_unique_index(scratch_collection)
    assert created is False

    indexes = await scratch_collection.index_information()
    assert UNIQUE_INDEX_NAME not in indexes


@pytest.mark.asyncio
async def test_create_unique_index_is_idempotent(scratch_collection):
    first = await create_unique_index(scratch_collection)
    second = await create_unique_index(scratch_collection)
    assert first is True
    assert second is True


@pytest.mark.asyncio
async def test_verify_rejects_missing_index(scratch_collection):
    """verify_unique_index_exists_and_valid() must return (False, diagnostic)
    when the index does not exist."""
    is_valid, diagnostic = await verify_unique_index_exists_and_valid(scratch_collection)
    assert is_valid is False
    assert "does not exist" in diagnostic


@pytest.mark.asyncio
async def test_verify_accepts_valid_index(scratch_collection):
    """verify_unique_index_exists_and_valid() must return (True, "") when
    the index exists and is correctly defined."""
    await create_unique_index(scratch_collection)

    is_valid, diagnostic = await verify_unique_index_exists_and_valid(scratch_collection)
    assert is_valid is True
    assert diagnostic == ""


@pytest.mark.asyncio
async def test_verify_rejects_wrong_key_order(scratch_collection):
    """verify_unique_index_exists_and_valid() must reject an index with
    mismatched key field order."""
    wrong_order = [
        ("entity", 1),
        ("article_id", 1),
        ("entity_type", 1),
        ("is_primary", 1),
    ]
    await scratch_collection.create_index(wrong_order, name=UNIQUE_INDEX_NAME, unique=True)

    is_valid, diagnostic = await verify_unique_index_exists_and_valid(scratch_collection)
    assert is_valid is False
    assert "do not match expected" in diagnostic


@pytest.mark.asyncio
async def test_verify_rejects_non_unique_index(scratch_collection):
    """verify_unique_index_exists_and_valid() must reject an index that
    exists but is not marked unique."""
    correct_keys = [
        ("article_id", 1),
        ("entity", 1),
        ("entity_type", 1),
        ("is_primary", 1),
    ]
    await scratch_collection.create_index(correct_keys, name=UNIQUE_INDEX_NAME, unique=False)

    is_valid, diagnostic = await verify_unique_index_exists_and_valid(scratch_collection)
    assert is_valid is False
    assert "not marked unique" in diagnostic


@pytest.mark.asyncio
async def test_concurrent_upserts_for_same_key_do_not_duplicate(mongo_db):
    """Two concurrent writers racing to persist the same mention (e.g. two
    workers that both briefly held a lease before one lost it, or an actual
    retry racing the original attempt) must converge to exactly one
    document, backed by the article_entity_type_primary_unique index -- a
    bare upsert without a unique index cannot guarantee this, since the
    existence check and the insert are not atomic together across two
    concurrent update_one(upsert=True) calls.

    Must exercise create_entity_mentions_batch_idempotent() itself, which
    is hardcoded to the real entity_mentions collection (via
    mongo_manager), not the scratch collection used by the other tests in
    this file -- so this test creates a real index on entity_mentions and
    is deliberately the LAST test defined in this file (pytest runs tests
    in file-definition order by default) so nothing else in this session's
    test suite for this collection runs after it and risks racing the
    index build against a drop_database call."""
    created = await create_unique_index(mongo_db.entity_mentions)
    assert created is True

    mention = {
        "entity": "Bitcoin",
        "entity_type": "project",
        "article_id": "concurrent-abc",
        "sentiment": "positive",
        "confidence": 0.9,
        "source": "coindesk",
        "is_primary": True,
    }

    results = await asyncio.gather(
        create_entity_mentions_batch_idempotent([mention]),
        create_entity_mentions_batch_idempotent([dict(mention, confidence=0.95)]),
    )

    assert all(r == 1 for r in results), "Both concurrent calls should report success"

    stored = await mongo_db.entity_mentions.find({"article_id": "concurrent-abc"}).to_list(length=10)
    assert len(stored) == 1, "Concurrent writers for the same key must not create duplicates"
