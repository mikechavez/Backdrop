"""
Explicit, operator-gated rollout of the entity_mentions unique index
(BUG-108, review follow-up).

The article_entity_type_primary_unique index backs the idempotent,
concurrency-safe mention writer (create_entity_mentions_batch_idempotent in
entity_mentions.py). It is deliberately NOT included in
MongoManager.initialize_indexes()'s auto-created ENTITY_MENTIONS_INDEXES
list, and is NOT created automatically on application startup, for two
reasons:

1. Blast radius: initialize_indexes() runs inside the FastAPI startup
   lifespan and re-raises on failure, so an index creation failure there
   crashes the entire application startup -- not just entity_mentions
   functionality. A unique index creation is uniquely likely to fail this
   way if the collection already contains duplicate keys (routine before
   this ticket, since nothing enforced this uniqueness previously).
2. Correctness of the concurrency guarantee needs verification BEFORE the
   index exists, not an assumption that it will always succeed at some
   future startup.

Required rollout sequence (all steps here are read-only or explicitly
opt-in; nothing in this module runs unless called):

  1. check_for_duplicate_mentions() -- read-only. Counts existing documents
     that violate the intended uniqueness key. Safe to run anytime,
     including against production, under the ticket's read-only
     authorization.
  2. If duplicates are found, they must be resolved (deduplicated) by the
     operator before step 3 can succeed; this module does not delete or
     modify any document.
  3. create_unique_index() -- creates the index. Requires explicit operator
     authorization before running against production (per BUG-108's
     authorization boundary); safe to run in local/dev/test at any time.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from motor.motor_asyncio import AsyncIOMotorCollection

logger = logging.getLogger(__name__)

UNIQUE_INDEX_NAME = "article_entity_type_primary_unique"
UNIQUE_INDEX_KEYS = [
    ("article_id", 1),
    ("entity", 1),
    ("entity_type", 1),
    ("is_primary", 1),
]
_GROUP_KEY_FIELDS = ["article_id", "entity", "entity_type", "is_primary"]


@dataclass
class DuplicateCheckReport:
    scanned_groups: int = 0
    duplicate_groups: int = 0
    duplicate_documents: int = 0
    sample_keys: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def safe_to_create_index(self) -> bool:
        return self.duplicate_groups == 0


async def check_for_duplicate_mentions(
    collection: AsyncIOMotorCollection,
    sample_limit: int = 20,
) -> DuplicateCheckReport:
    """Read-only preflight: count documents that would violate the intended
    (article_id, entity, entity_type, is_primary) uniqueness constraint.

    Must be run (and show duplicate_groups == 0, or duplicates resolved)
    before create_unique_index() can succeed. Never deletes or modifies
    data; safe to run against production under the ticket's read-only
    authorization.
    """
    report = DuplicateCheckReport()

    pipeline = [
        {
            "$group": {
                "_id": {field: f"${field}" for field in _GROUP_KEY_FIELDS},
                "count": {"$sum": 1},
            }
        },
        {"$match": {"count": {"$gt": 1}}},
    ]

    async for group in collection.aggregate(pipeline):
        report.duplicate_groups += 1
        report.duplicate_documents += group["count"]
        if len(report.sample_keys) < sample_limit:
            report.sample_keys.append(group["_id"])

    report.scanned_groups = await collection.count_documents({})

    logger.info(
        "Entity mentions duplicate preflight: duplicate_groups=%d duplicate_documents=%d "
        "safe_to_create_index=%s",
        report.duplicate_groups,
        report.duplicate_documents,
        report.safe_to_create_index,
    )
    return report


async def verify_unique_index_exists_and_valid(collection: AsyncIOMotorCollection) -> tuple[bool, str]:
    """Verify the unique index exists and has the correct definition.

    Checks:
    1. Index exists by name
    2. Index key fields match UNIQUE_INDEX_KEYS in the correct order
    3. Index is marked unique=True

    Returns: (is_valid, diagnostic_message)
    - (True, "") if index exists and is valid
    - (False, reason) if index is missing, invalid, or verification failed
    """
    try:
        indexes = await collection.index_information()
    except Exception as e:
        return False, f"Could not read index information: {e}"

    if UNIQUE_INDEX_NAME not in indexes:
        return False, f"Index {UNIQUE_INDEX_NAME} does not exist"

    index_def = indexes[UNIQUE_INDEX_NAME]

    expected_keys = [key[0] for key in UNIQUE_INDEX_KEYS]
    actual_keys = [key[0] for key in index_def.get("key", [])]

    if actual_keys != expected_keys:
        return False, f"Index key fields {actual_keys} do not match expected {expected_keys}"

    if not index_def.get("unique", False):
        return False, f"Index {UNIQUE_INDEX_NAME} is not marked unique"

    return True, ""


async def create_unique_index(collection: AsyncIOMotorCollection) -> bool:
    """Explicitly create the article_entity_type_primary_unique index.

    Must only be called after check_for_duplicate_mentions() reports
    safe_to_create_index=True; does not run the preflight itself, so a
    caller cannot accidentally skip it silently -- callers must show they
    checked. Requires explicit operator authorization before use against
    production. Idempotent: if the index already exists, this is a no-op.

    Returns True if the index was created or already existed, False if it
    could not be created (e.g. duplicates still present -- caller should
    have run the preflight and resolved them first).
    """
    existing = await collection.index_information()
    if UNIQUE_INDEX_NAME in existing:
        logger.info("Index %s already exists; nothing to do", UNIQUE_INDEX_NAME)
        return True

    try:
        await collection.create_index(
            UNIQUE_INDEX_KEYS,
            name=UNIQUE_INDEX_NAME,
            unique=True,
            background=True,
        )
        logger.info("Created unique index %s", UNIQUE_INDEX_NAME)
        return True
    except Exception as e:
        logger.error(
            "Failed to create unique index %s (likely duplicate keys still "
            "present; run check_for_duplicate_mentions() first): %s",
            UNIQUE_INDEX_NAME,
            e,
        )
        return False
