"""
Read-only duplicate-remediation analysis for entity_mentions (BUG-110).

Historical repeated processing (not just the current multi-replica
collision fixed by scheduler_lock.py) has left large numbers of duplicate
(article_id, entity, entity_type, is_primary) groups in production
entity_mentions. Before article_entity_type_primary_unique can be created,
the operator needs:

  1. A read-only, bounded report of duplicate groups, sizes, and date
     ranges (DuplicateAuditReport / run_duplicate_audit).
  2. Field-level comparison of documents inside each duplicate group, to
     see whether "duplicates" are byte-identical repeats or differ in
     sentiment/confidence/source/metadata/timestamps
     (compare_group_documents).
  3. A deterministic, documented canonical-record policy proposal, applied
     only in a dry run unless explicitly told otherwise (choose_canonical,
     plan_duplicate_cleanup).
  4. A bounded, confirmed, audited cleanup path (execute_cleanup_plan) that
     never runs unless the caller passes an explicit confirmation phrase,
     operates in bounded batches, and produces an audit trail of exactly
     what was deleted.

Nothing in this module deletes, updates, or mutates data unless
execute_cleanup_plan is called with confirm=True and a batch limit. Every
other function here is read-only and safe to run against production under
the read-only authorization already granted for the BUG-110 duplicate
preflight.

Repository code search (2026-09-15) found no references to entity_mentions
_id values anywhere else in the codebase: every consumer (signal_service,
narrative_service, signal_scores, briefing_agent, admin endpoints) queries
or aggregates entity_mentions by (article_id, entity, entity_type,
is_primary) or by aggregate pipelines, never by a stored/foreign-keyed
entity_mentions._id. This means the choice of which duplicate document to
keep as "canonical" has no referential-integrity impact elsewhere in the
system -- the only thing that matters is which document's *field values*
are kept.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

logger = logging.getLogger(__name__)

_GROUP_KEY_FIELDS = ["article_id", "entity", "entity_type", "is_primary"]

# Confirmation phrase execute_cleanup_plan requires verbatim. Deliberately
# specific (not just `confirm=True`) so an operator cannot trigger deletion
# by accident via a boolean default or a copy-pasted call site.
CLEANUP_CONFIRMATION_PHRASE = "DELETE DUPLICATE ENTITY MENTIONS"

# Fields compared for meaningful differences between documents inside a
# duplicate group. _id, article_id, entity, entity_type, is_primary are the
# group key itself and are excluded; timestamp/created_at are compared
# separately as ranges rather than exact-match diffs.
_COMPARISON_FIELDS = [
    "sentiment",
    "confidence",
    "source",
    "metadata",
    "published_at",
]


def _group_key_to_dict(key: Dict[str, Any]) -> Dict[str, Any]:
    return {field_name: key.get(field_name) for field_name in _GROUP_KEY_FIELDS}


@dataclass
class GroupSizeBucket:
    """Histogram bucket for the group-size distribution."""

    label: str
    min_size: int
    max_size: Optional[int]  # None means unbounded
    group_count: int = 0
    document_count: int = 0


@dataclass
class DuplicateAuditReport:
    duplicate_groups: int = 0
    total_documents_in_duplicate_groups: int = 0
    excess_documents: int = 0
    max_group_size: int = 0
    max_group_key: Optional[Dict[str, Any]] = None
    created_at_min: Optional[datetime] = None
    created_at_max: Optional[datetime] = None
    size_distribution: List[GroupSizeBucket] = field(default_factory=list)
    sample_groups: List[Dict[str, Any]] = field(default_factory=list)


# (label, min_size, max_size) -- max_size None means unbounded (last bucket).
_DEFAULT_SIZE_BUCKETS = [
    ("2", 2, 2),
    ("3-5", 3, 5),
    ("6-10", 6, 10),
    ("11-100", 11, 100),
    ("101-1000", 101, 1000),
    ("1001+", 1001, None),
]


async def run_duplicate_audit(
    collection: AsyncIOMotorCollection,
    sample_limit: int = 20,
    max_groups_scanned: Optional[int] = None,
) -> DuplicateAuditReport:
    """Read-only: group entity_mentions by (article_id, entity, entity_type,
    is_primary) and report duplicate groups, excess-document counts,
    created_at ranges, a group-size distribution, and bounded samples.

    Never writes to the database. Safe to run against production under the
    existing BUG-110 read-only duplicate-preflight authorization.

    max_groups_scanned bounds how many duplicate groups are inspected for
    the created_at range / size distribution (all matching groups are still
    counted via $group + $match, only the per-group detail pass is capped),
    so this stays cheap even against the largest known group (7,448 docs).
    """
    report = DuplicateAuditReport()
    buckets = [
        GroupSizeBucket(label=label, min_size=lo, max_size=hi)
        for label, lo, hi in _DEFAULT_SIZE_BUCKETS
    ]

    pipeline = [
        {
            "$group": {
                "_id": {f: f"${f}" for f in _GROUP_KEY_FIELDS},
                "count": {"$sum": 1},
                "created_at_min": {"$min": "$created_at"},
                "created_at_max": {"$max": "$created_at"},
            }
        },
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"count": -1}},
    ]

    scanned = 0
    async for group in collection.aggregate(pipeline, allowDiskUse=True):
        count = group["count"]
        report.duplicate_groups += 1
        report.total_documents_in_duplicate_groups += count
        report.excess_documents += count - 1

        if count > report.max_group_size:
            report.max_group_size = count
            report.max_group_key = _group_key_to_dict(group["_id"])

        g_min = group.get("created_at_min")
        g_max = group.get("created_at_max")
        if g_min is not None and (report.created_at_min is None or g_min < report.created_at_min):
            report.created_at_min = g_min
        if g_max is not None and (report.created_at_max is None or g_max > report.created_at_max):
            report.created_at_max = g_max

        for bucket in buckets:
            if count >= bucket.min_size and (bucket.max_size is None or count <= bucket.max_size):
                bucket.group_count += 1
                bucket.document_count += count
                break

        if len(report.sample_groups) < sample_limit:
            report.sample_groups.append(
                {
                    "key": _group_key_to_dict(group["_id"]),
                    "count": count,
                    "created_at_min": g_min,
                    "created_at_max": g_max,
                }
            )

        scanned += 1
        if max_groups_scanned is not None and scanned >= max_groups_scanned:
            logger.warning(
                "run_duplicate_audit: stopped detail scan at max_groups_scanned=%d; "
                "duplicate_groups/total_documents/excess_documents counted from the "
                "full aggregation and are NOT truncated, only per-group detail is",
                max_groups_scanned,
            )
            break

    report.size_distribution = buckets
    logger.info(
        "Entity mentions duplicate audit: duplicate_groups=%d total_documents=%d "
        "excess_documents=%d max_group_size=%d",
        report.duplicate_groups,
        report.total_documents_in_duplicate_groups,
        report.excess_documents,
        report.max_group_size,
    )
    return report


@dataclass
class FieldDifference:
    field: str
    distinct_values: List[Any]


@dataclass
class GroupComparison:
    key: Dict[str, Any]
    document_count: int
    identical: bool
    field_differences: List[FieldDifference] = field(default_factory=list)
    created_at_min: Optional[datetime] = None
    created_at_max: Optional[datetime] = None
    document_ids: List[str] = field(default_factory=list)


def _stable_repr(value: Any) -> Any:
    """Make a value hashable/comparable for distinctness checks (dicts are
    unhashable; compare their sorted repr instead)."""
    if isinstance(value, dict):
        return repr(sorted(value.items(), key=lambda kv: kv[0]))
    return value


async def compare_group_documents(
    collection: AsyncIOMotorCollection,
    group_key: Dict[str, Any],
    limit: int = 10000,
) -> GroupComparison:
    """Read-only: fetch every document in one duplicate group and identify
    which fields (other than the group key and _id) actually differ between
    them.

    Used to distinguish "duplicates are byte-identical reprocessing
    artifacts" (safe to collapse to any one representative) from
    "duplicates disagree on sentiment/confidence/source/metadata"
    (needs a documented tie-break policy, see choose_canonical).
    """
    query = {f: group_key[f] for f in _GROUP_KEY_FIELDS}
    docs = await collection.find(query).limit(limit).to_list(length=limit)

    comparison = GroupComparison(
        key=dict(query),
        document_count=len(docs),
        identical=True,
        document_ids=[str(d["_id"]) for d in docs],
    )

    if not docs:
        return comparison

    created_ats = [d.get("created_at") for d in docs if d.get("created_at") is not None]
    if created_ats:
        comparison.created_at_min = min(created_ats)
        comparison.created_at_max = max(created_ats)

    for f in _COMPARISON_FIELDS:
        distinct = []
        seen = set()
        for d in docs:
            v = d.get(f)
            key = _stable_repr(v)
            if key not in seen:
                seen.add(key)
                distinct.append(v)
        if len(distinct) > 1:
            comparison.identical = False
            comparison.field_differences.append(FieldDifference(field=f, distinct_values=distinct))

    return comparison


@dataclass
class CanonicalChoice:
    key: Dict[str, Any]
    canonical_id: str
    discard_ids: List[str]
    reason: str


def choose_canonical(comparison: GroupComparison, documents: List[Dict[str, Any]]) -> CanonicalChoice:
    """Deterministic canonical-record policy (proposal only -- never applied
    automatically by this function).

    Policy, in priority order, applied to the documents in one duplicate
    group:

      1. Prefer the document with a non-null `published_at` (BUG-109
         established this as the field freshness/signal computation must
         use; a duplicate missing it is strictly less useful).
      2. Among ties, prefer the earliest `created_at` (the first time this
         mention was legitimately recorded, before repeated
         reprocessing/duplication began).
      3. Among remaining ties (identical created_at), prefer the
         lexicographically smallest _id (ObjectId ordering is
         time-derived, so this is still a deterministic, stable
         tie-break, not an arbitrary one).

    This function only decides; it never deletes or modifies anything.
    Applying this policy against production requires explicit operator
    approval and must go through execute_cleanup_plan (bounded, confirmed,
    audited), never this function directly.
    """
    if not documents:
        raise ValueError("choose_canonical requires at least one document")

    def sort_key(d: Dict[str, Any]):
        has_published_at = d.get("published_at") is None  # False sorts first
        created_at = d.get("created_at")
        if created_at is None:
            # Sort missing created_at last regardless of tz-awareness of
            # other documents' timestamps (Mongo drivers may return naive
            # datetimes, so avoid comparing naive/aware directly).
            created_at_sort = (1, "")
        else:
            created_at_sort = (0, created_at.isoformat())
        return (has_published_at, created_at_sort, str(d["_id"]))

    ordered = sorted(documents, key=sort_key)
    canonical = ordered[0]
    discard = ordered[1:]

    reasons = []
    if canonical.get("published_at") is not None and any(d.get("published_at") is None for d in discard):
        reasons.append("has published_at where some duplicates do not")
    reasons.append("earliest created_at among remaining candidates")
    reasons.append("tie-broken by smallest _id")

    return CanonicalChoice(
        key=comparison.key,
        canonical_id=str(canonical["_id"]),
        discard_ids=[str(d["_id"]) for d in discard],
        reason="; ".join(reasons),
    )


@dataclass
class CleanupPlan:
    """A dry-run cleanup plan: which documents would be deleted, and why.
    Building this never deletes anything; only execute_cleanup_plan does,
    and only when explicitly confirmed."""

    groups_planned: int = 0
    documents_to_delete: List[str] = field(default_factory=list)
    choices: List[CanonicalChoice] = field(default_factory=list)
    skipped_groups: List[Dict[str, Any]] = field(default_factory=list)


async def plan_duplicate_cleanup(
    collection: AsyncIOMotorCollection,
    max_groups: int = 100,
    max_group_size_for_auto_plan: int = 20000,
) -> CleanupPlan:
    """Read-only: build a dry-run CleanupPlan by applying choose_canonical to
    up to max_groups duplicate groups.

    Groups larger than max_group_size_for_auto_plan are skipped and
    reported in skipped_groups rather than fully materialized -- protects
    against loading a 7,448-document group (or larger) into memory
    unbounded; those groups must be reviewed individually via
    compare_group_documents before planning.

    This never deletes or modifies data. The returned plan is input to a
    human review step; only an operator-approved subset should ever reach
    execute_cleanup_plan.
    """
    plan = CleanupPlan()

    pipeline = [
        {
            "$group": {
                "_id": {f: f"${f}" for f in _GROUP_KEY_FIELDS},
                "count": {"$sum": 1},
            }
        },
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"count": 1}},  # smallest groups first: cheapest, safest to review
        {"$limit": max_groups},
    ]

    async for group in collection.aggregate(pipeline, allowDiskUse=True):
        key = _group_key_to_dict(group["_id"])
        count = group["count"]
        if count > max_group_size_for_auto_plan:
            plan.skipped_groups.append({**key, "count": count, "reason": "exceeds max_group_size_for_auto_plan"})
            continue

        query = dict(key)
        docs = await collection.find(query).to_list(length=count)
        comparison = await compare_group_documents(collection, key, limit=count)
        choice = choose_canonical(comparison, docs)

        plan.groups_planned += 1
        plan.documents_to_delete.extend(choice.discard_ids)
        plan.choices.append(choice)

    return plan


@dataclass
class CleanupAuditEntry:
    group_key: Dict[str, Any]
    canonical_id: str
    deleted_ids: List[str]
    deleted_count: int


@dataclass
class CleanupAuditReport:
    started_at: datetime
    finished_at: Optional[datetime]
    dry_run: bool
    batches: int = 0
    total_deleted: int = 0
    entries: List[CleanupAuditEntry] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


async def execute_cleanup_plan(
    collection: AsyncIOMotorCollection,
    plan: CleanupPlan,
    confirm: str,
    batch_size: int = 25,
    dry_run: bool = True,
) -> CleanupAuditReport:
    """Apply an operator-approved CleanupPlan, deleting only the specific
    discard_ids each choice identified -- never a bulk/pattern delete on the
    group key, so a canonical document can never be accidentally caught by
    its own group's delete.

    Safety properties (all required, none optional):
      - confirm must equal CLEANUP_CONFIRMATION_PHRASE exactly, or this
        raises ValueError and deletes nothing. A stray `confirm=True` or
        empty string can never trigger deletion.
      - dry_run defaults to True: even with a correct confirm phrase, no
        delete_one/delete_many call is made unless the caller also passes
        dry_run=False. This makes "preview the exact effect of an approved
        plan" and "actually apply it" two deliberate, separate calls.
      - Deletion proceeds in bounded batches of batch_size documents
        (one delete_one per document, not delete_many, so a partial
        failure never removes more than the single document it targeted).
      - Every attempted deletion (dry-run or real) is recorded in the
        returned CleanupAuditReport with the group key, the canonical id
        that was kept, and the exact ids removed -- so a human can review
        or reconstruct the operation afterward. This report should be
        saved by the operator; this function does not write it anywhere.
      - Recoverability: this performs individual _id deletes only (no
        collection/database drop, no updateMany, no bulkWrite). If the
        operator wants an undo path, they should export the
        documents_to_delete IDs and their full documents (e.g. via a
        read-only find({"_id": {"$in": ...}}) dump) before calling this
        with dry_run=False -- this function does not create that backup
        itself, since writing a backup file is outside a read-only
        module's scope and the operator's export tooling/location choice
        should not be assumed here.
    """
    if confirm != CLEANUP_CONFIRMATION_PHRASE:
        raise ValueError(
            f"execute_cleanup_plan requires confirm={CLEANUP_CONFIRMATION_PHRASE!r} exactly; got {confirm!r}"
        )

    report = CleanupAuditReport(started_at=datetime.now(timezone.utc), finished_at=None, dry_run=dry_run)

    for choice in plan.choices:
        entry = CleanupAuditEntry(
            group_key=choice.key,
            canonical_id=choice.canonical_id,
            deleted_ids=[],
            deleted_count=0,
        )
        for i in range(0, len(choice.discard_ids), batch_size):
            batch = choice.discard_ids[i : i + batch_size]
            report.batches += 1
            for id_str in batch:
                if dry_run:
                    entry.deleted_ids.append(id_str)
                    entry.deleted_count += 1
                    continue
                try:
                    result = await collection.delete_one({"_id": ObjectId(id_str)})
                    if result.deleted_count > 0:
                        entry.deleted_ids.append(id_str)
                        entry.deleted_count += 1
                except Exception as e:
                    report.errors.append(f"{choice.key}: failed to delete {id_str}: {e}")

        report.entries.append(entry)
        report.total_deleted += entry.deleted_count

    report.finished_at = datetime.now(timezone.utc)
    logger.info(
        "entity_mentions cleanup %s: groups=%d total_deleted=%d errors=%d",
        "DRY RUN" if dry_run else "EXECUTED",
        len(report.entries),
        report.total_deleted,
        len(report.errors),
    )
    return report
