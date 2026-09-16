"""
Distributed lock for singleton scheduled jobs across multiple process
replicas (BUG-110).

Railway can run more than one `web` replica, and each replica independently
starts the FastAPI lifespan's RSS ingestion schedule. Without a lock, every
replica fetches and processes the same feeds concurrently, producing
duplicate fetch cycles and duplicate upsert/enrichment work (confirmed in
production: overlapping 262-272 article fetch cycles seconds apart).

This module provides a simple MongoDB-backed mutual-exclusion lock using an
atomic `find_one_and_update` compare-and-set (the same pattern already used
for enrichment leasing in `enrichment_state.py`), so only one replica at a
time runs a given job:

    lock = await acquire_lock(collection, job_name="rss_fetch", ttl_seconds=1200)
    if lock is None:
        logger.info("Another replica holds the rss_fetch lock; skipping cycle")
        return
    try:
        ... do work, calling renew_lock(...) periodically for long jobs ...
    finally:
        await release_lock(collection, job_name="rss_fetch", owner_token=lock.owner_token)

A held lock automatically expires after `ttl_seconds` even if the owning
replica crashes without releasing it, so a dead replica can never
permanently block ingestion. `release_lock` and `renew_lock` are fenced by
owner token, so a replica whose lease already expired (and was reclaimed by
another replica) can never clobber the new owner's lock.
"""

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)


def new_owner_token() -> str:
    """Generate an unguessable per-acquisition ownership token."""
    return secrets.token_hex(16)


@dataclass
class SchedulerLock:
    """A held lock. Only valid for the process/coroutine that acquired it."""

    job_name: str
    owner_token: str
    expires_at: datetime


async def acquire_lock(
    collection: AsyncIOMotorCollection,
    job_name: str,
    ttl_seconds: int,
) -> Optional[SchedulerLock]:
    """Attempt to acquire the named lock.

    Succeeds if the lock is unheld, or if the previous holder's lease has
    expired (crashed/killed replica). Returns None if another replica
    currently holds a live lease.
    """
    now = datetime.now(timezone.utc)
    owner_token = new_owner_token()
    expires_at = now + timedelta(seconds=ttl_seconds)

    try:
        await collection.find_one_and_update(
            {
                "_id": job_name,
                "$or": [
                    {"expires_at": {"$lte": now}},
                    {"expires_at": {"$exists": False}},
                ],
            },
            {
                "$set": {
                    "owner_token": owner_token,
                    "acquired_at": now,
                    "expires_at": expires_at,
                }
            },
            upsert=True,
        )
    except DuplicateKeyError:
        # upsert cannot insert when a document with this _id already exists
        # but didn't match the filter (i.e. its lease is still live and held
        # by another owner) -- this is expected lock contention, not an error.
        pass

    # Re-read: distinguishes "we just created/updated it" (we own it now)
    # from "someone else's live lease blocked our filter match" (contention).
    doc = await collection.find_one({"_id": job_name})
    if doc is not None and doc.get("owner_token") == owner_token:
        return SchedulerLock(job_name=job_name, owner_token=owner_token, expires_at=expires_at)

    logger.info(
        "Scheduler lock '%s' held by another owner until %s; skipping this cycle",
        job_name,
        doc.get("expires_at") if doc else "unknown",
    )
    return None


async def renew_lock(
    collection: AsyncIOMotorCollection,
    job_name: str,
    owner_token: str,
    ttl_seconds: int,
) -> bool:
    """Extend the lease for a lock still owned by owner_token.

    Returns False (no-op) if the lease was reclaimed by another owner in the
    meantime; callers must treat that as "stop working" since another
    replica may now be running the same job concurrently.
    """
    now = datetime.now(timezone.utc)
    result = await collection.update_one(
        {"_id": job_name, "owner_token": owner_token},
        {"$set": {"expires_at": now + timedelta(seconds=ttl_seconds)}},
    )
    if result.matched_count == 0:
        logger.warning(
            "Failed to renew scheduler lock '%s': lease no longer owned by this token "
            "(likely expired and reclaimed by another replica)",
            job_name,
        )
        return False
    return True


async def release_lock(
    collection: AsyncIOMotorCollection,
    job_name: str,
    owner_token: str,
) -> bool:
    """Release the lock, only if still owned by owner_token.

    A no-op (returns False) if the lease already expired and was reclaimed
    by another replica, so a late release can never revoke someone else's
    active lock.
    """
    result = await collection.delete_one({"_id": job_name, "owner_token": owner_token})
    return result.deleted_count > 0
