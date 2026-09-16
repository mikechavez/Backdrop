"""Tests for the MongoDB-backed distributed scheduler lock (BUG-110).

Covers acquisition, contention between replicas, expiry/recovery from a
crashed owner, and ownership-fenced release/renewal.
"""

from datetime import datetime, timedelta, timezone

import pytest

from crypto_news_aggregator.db.operations.scheduler_lock import (
    acquire_lock,
    release_lock,
    renew_lock,
)


@pytest.mark.asyncio
async def test_acquire_lock_succeeds_when_unheld(mongo_db):
    await mongo_db.scheduler_locks.delete_many({})

    lock = await acquire_lock(mongo_db.scheduler_locks, "rss_fetch", ttl_seconds=60)

    assert lock is not None
    assert lock.job_name == "rss_fetch"
    assert lock.owner_token

    doc = await mongo_db.scheduler_locks.find_one({"_id": "rss_fetch"})
    assert doc is not None
    assert doc["owner_token"] == lock.owner_token


@pytest.mark.asyncio
async def test_second_replica_cannot_acquire_live_lock(mongo_db):
    """Contention: a live (unexpired) lock blocks a second acquirer."""
    await mongo_db.scheduler_locks.delete_many({})

    first = await acquire_lock(mongo_db.scheduler_locks, "rss_fetch", ttl_seconds=60)
    assert first is not None

    second = await acquire_lock(mongo_db.scheduler_locks, "rss_fetch", ttl_seconds=60)

    assert second is None

    # The original owner's lock document must be untouched.
    doc = await mongo_db.scheduler_locks.find_one({"_id": "rss_fetch"})
    assert doc["owner_token"] == first.owner_token


@pytest.mark.asyncio
async def test_lock_can_be_reacquired_after_expiry(mongo_db):
    """Expiry/recovery: a crashed replica's lease must not block forever."""
    await mongo_db.scheduler_locks.delete_many({})

    now = datetime.now(timezone.utc)
    # Simulate a lock held by a crashed replica whose lease already expired.
    await mongo_db.scheduler_locks.insert_one(
        {
            "_id": "rss_fetch",
            "owner_token": "dead-replica-token",
            "acquired_at": now - timedelta(seconds=120),
            "expires_at": now - timedelta(seconds=1),
        }
    )

    new_lock = await acquire_lock(mongo_db.scheduler_locks, "rss_fetch", ttl_seconds=60)

    assert new_lock is not None
    assert new_lock.owner_token != "dead-replica-token"

    doc = await mongo_db.scheduler_locks.find_one({"_id": "rss_fetch"})
    assert doc["owner_token"] == new_lock.owner_token


@pytest.mark.asyncio
async def test_release_lock_only_when_owned(mongo_db):
    """Ownership-safe release: releasing with a stale/foreign token is a no-op."""
    await mongo_db.scheduler_locks.delete_many({})

    lock = await acquire_lock(mongo_db.scheduler_locks, "rss_fetch", ttl_seconds=60)
    assert lock is not None

    # A foreign token must not be able to release someone else's lock.
    released_by_foreign_owner = await release_lock(
        mongo_db.scheduler_locks, "rss_fetch", owner_token="not-the-real-owner"
    )
    assert released_by_foreign_owner is False

    doc = await mongo_db.scheduler_locks.find_one({"_id": "rss_fetch"})
    assert doc is not None
    assert doc["owner_token"] == lock.owner_token

    # The real owner can release it.
    released = await release_lock(mongo_db.scheduler_locks, "rss_fetch", owner_token=lock.owner_token)
    assert released is True

    doc_after = await mongo_db.scheduler_locks.find_one({"_id": "rss_fetch"})
    assert doc_after is None


@pytest.mark.asyncio
async def test_renew_lock_extends_expiry_for_current_owner(mongo_db):
    await mongo_db.scheduler_locks.delete_many({})

    lock = await acquire_lock(mongo_db.scheduler_locks, "rss_fetch", ttl_seconds=10)
    assert lock is not None

    renewed = await renew_lock(
        mongo_db.scheduler_locks, "rss_fetch", owner_token=lock.owner_token, ttl_seconds=600
    )
    assert renewed is True

    doc = await mongo_db.scheduler_locks.find_one({"_id": "rss_fetch"})
    remaining = (doc["expires_at"].replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).total_seconds()
    assert remaining > 500  # extended well beyond the original 10s TTL


@pytest.mark.asyncio
async def test_renew_lock_fails_for_reclaimed_lease(mongo_db):
    """A replica that lost its lease (already reclaimed) must not be able to
    renew it back into existence and clobber the new owner's lock."""
    await mongo_db.scheduler_locks.delete_many({})

    now = datetime.now(timezone.utc)
    await mongo_db.scheduler_locks.insert_one(
        {
            "_id": "rss_fetch",
            "owner_token": "new-owner-token",
            "acquired_at": now,
            "expires_at": now + timedelta(seconds=60),
        }
    )

    renewed = await renew_lock(
        mongo_db.scheduler_locks, "rss_fetch", owner_token="stale-owner-token", ttl_seconds=60
    )

    assert renewed is False

    doc = await mongo_db.scheduler_locks.find_one({"_id": "rss_fetch"})
    assert doc["owner_token"] == "new-owner-token"
