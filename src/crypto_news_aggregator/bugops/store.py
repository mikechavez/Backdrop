"""BugOps alert and case storage."""

import logging
from datetime import datetime, timedelta
from typing import Optional
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from .models import (
    BugAlertEventCreate,
    BugAlertEvent,
    BugCaseCreate,
    BugCase,
    NotificationAttemptCreate,
    NotificationAttempt,
    EvidencePackCreate,
    EvidencePack,
    EvidencePackStatus,
)

logger = logging.getLogger(__name__)


def _normalize_mongo_doc(doc: dict | None) -> dict | None:
    """Normalize Mongo document for Pydantic model hydration.

    Converts ObjectId._id values to strings for safe Pydantic validation.
    """
    if doc is None:
        return None

    normalized = dict(doc)

    if "_id" in normalized and isinstance(normalized["_id"], ObjectId):
        normalized["_id"] = str(normalized["_id"])

    return normalized


class BugOpsStore:
    """Store and retrieve BugOps alert events and cases."""

    def __init__(self, db: AsyncIOMotorDatabase):
        """Initialize store with Motor async database."""
        self.db = db
        self.alert_events_collection = db["bug_alert_events"]
        self.cases_collection = db["bug_cases"]
        self.case_events_collection = db["bug_case_events"]
        self.tool_calls_collection = db["bug_tool_calls"]
        self.notification_attempts_collection = db["notification_attempts"]
        self.evidence_packs_collection = db["evidence_packs"]

    async def create_alert_event(self, event: BugAlertEventCreate) -> BugAlertEvent:
        """Create a new alert event in the database."""
        event_dict = event.model_dump(by_alias=False, exclude_none=False)
        result = await self.alert_events_collection.insert_one(event_dict)
        event_dict["_id"] = result.inserted_id
        event_dict = _normalize_mongo_doc(event_dict)
        return BugAlertEvent(**event_dict)

    async def find_open_case_by_dedupe_key(self, dedupe_key: str) -> Optional[BugCase]:
        """Find an open case by dedupe key (ignores resolved/closed cases)."""
        doc = await self.cases_collection.find_one({
            "dedupe_key": dedupe_key,
            "status": "open"
        })
        if doc:
            doc = _normalize_mongo_doc(doc)
            return BugCase(**doc)
        return None

    async def find_open_case_by_root_subsystem(self, root_subsystem: str) -> Optional[BugCase]:
        """Find an open BugCase by root_subsystem."""
        doc = await self.cases_collection.find_one({
            "root_subsystem": root_subsystem,
            "status": "open"
        })
        if doc:
            doc = _normalize_mongo_doc(doc)
            return BugCase(**doc)
        return None

    async def create_case_from_alert(self, event: BugAlertEvent) -> BugCase:
        """Create a new case from an alert event."""
        case_create = BugCaseCreate(
            case_id=event.case_id or f"case_{event.alert_id}",
            status="open",
            severity=event.severity,
            alert_type=event.alert_type,
            title=event.title,
            summary=event.summary,
            dedupe_key=event.dedupe_key,
            source_types=[event.source_type],
            alert_ids=[event.alert_id],
            correlation_keys=event.correlation_keys,
            metric=event.metric,
        )
        case_dict = case_create.model_dump(by_alias=False, exclude_none=False)
        result = await self.cases_collection.insert_one(case_dict)
        case_dict["_id"] = result.inserted_id
        case_dict = _normalize_mongo_doc(case_dict)
        return BugCase(**case_dict)

    async def create_case_direct(self, case: BugCaseCreate) -> BugCase:
        """Create a BugCase directly from a BugCaseCreate, without a BugAlertEvent."""
        case_dict = case.model_dump(by_alias=False, exclude_none=False)
        result = await self.cases_collection.insert_one(case_dict)
        case_dict["_id"] = result.inserted_id
        case_dict = _normalize_mongo_doc(case_dict)
        return BugCase(**case_dict)

    async def attach_observation_to_case(
        self,
        case_id: str,
        last_seen_at: datetime,
        affected_subsystems: Optional[list[str]] = None
    ) -> BugCase:
        """Attach a new observation to an existing case.

        Increments observation_count, updates last_seen_at, and optionally
        adds to affected_subsystems without duplicating existing ones.
        """
        update_dict = {
            "$inc": {"observation_count": 1},
            "$set": {
                "last_seen_at": last_seen_at,
                "updated_at": datetime.utcnow()
            }
        }

        if affected_subsystems and len(affected_subsystems) > 0:
            update_dict["$addToSet"] = {
                "affected_subsystems": {"$each": affected_subsystems}
            }

        result = await self.cases_collection.find_one_and_update(
            {"case_id": case_id},
            update_dict,
            return_document=ReturnDocument.AFTER
        )

        if result:
            result = _normalize_mongo_doc(result)
            return BugCase(**result)
        raise ValueError(f"Case {case_id} not found")

    async def attach_alert_to_case(self, case_id: str, alert_id: str) -> BugCase:
        """Attach an alert event to an existing case."""
        result = await self.cases_collection.find_one_and_update(
            {"case_id": case_id},
            {
                "$addToSet": {"alert_ids": alert_id},
                "$set": {"updated_at": __import__("datetime").datetime.utcnow()}
            },
            return_document=True
        )
        if result:
            result = _normalize_mongo_doc(result)
            return BugCase(**result)
        raise ValueError(f"Case {case_id} not found")

    async def get_case(self, case_id: str) -> Optional[BugCase]:
        """Get a case by case_id."""
        doc = await self.cases_collection.find_one({"case_id": case_id})
        if doc:
            doc = _normalize_mongo_doc(doc)
            return BugCase(**doc)
        return None

    async def process_alert_event(self, event: BugAlertEventCreate) -> tuple[BugCase, bool]:
        """Process alert event: create alert, find or create case by dedupe_key.

        Returns:
            Tuple of (case, is_new) where is_new is True only if a new case was created
        """
        alert = await self.create_alert_event(event)
        case = await self.find_open_case_by_dedupe_key(alert.dedupe_key)
        is_new = case is None
        if is_new:
            case = await self.create_case_from_alert(alert)
        else:
            case = await self.attach_alert_to_case(case.case_id, alert.alert_id)
        return case, is_new

    async def get_alert_events_for_case(self, case_id: str) -> list[BugAlertEvent]:
        """Get all alert events for a case."""
        docs = await self.alert_events_collection.find({"case_id": case_id}).to_list(None)
        return [BugAlertEvent(**_normalize_mongo_doc(doc)) for doc in docs]

    async def save_case_report(self, case_id: str, report: str) -> BugCase:
        """Save a deterministic report to a case."""
        result = await self.cases_collection.find_one_and_update(
            {"case_id": case_id},
            {
                "$set": {
                    "deterministic_report": report,
                    "updated_at": __import__("datetime").datetime.utcnow()
                }
            },
            return_document=True
        )
        if result:
            result = _normalize_mongo_doc(result)
            return BugCase(**result)
        raise ValueError(f"Case {case_id} not found")

    async def resolve_case(self, case_id: str) -> BugCase:
        """Resolve a BugCase (auto-resolution)."""
        result = await self.cases_collection.find_one_and_update(
            {"case_id": case_id},
            {
                "$set": {
                    "status": "resolved",
                    "resolved_at": datetime.utcnow(),
                    "recovery_candidate_at": None,
                    "updated_at": datetime.utcnow()
                }
            },
            return_document=ReturnDocument.AFTER
        )
        if result:
            result = _normalize_mongo_doc(result)
            return BugCase(**result)
        raise ValueError(f"Case {case_id} not found")

    async def update_recovery_candidate(
        self, case_id: str, recovery_candidate_at: Optional[datetime]
    ) -> BugCase:
        """Update recovery_candidate_at timestamp (can be None to clear)."""
        result = await self.cases_collection.find_one_and_update(
            {"case_id": case_id},
            {
                "$set": {
                    "recovery_candidate_at": recovery_candidate_at,
                    "updated_at": datetime.utcnow()
                }
            },
            return_document=ReturnDocument.AFTER
        )
        if result:
            result = _normalize_mongo_doc(result)
            return BugCase(**result)
        raise ValueError(f"Case {case_id} not found")

    async def get_open_freshness_cases(self) -> list[BugCase]:
        """Get all open BugCases from freshness detectors (identified by dedupe_key containing ':')."""
        docs = await self.cases_collection.find({
            "status": "open",
            "dedupe_key": {"$regex": ":"}
        }).to_list(None)
        return [BugCase(**_normalize_mongo_doc(doc)) for doc in docs]

    async def update_notification_state(self, case_id: str, last_notified_at: datetime) -> BugCase:
        """Update notification state: set last_notified_at and increment notification_count.

        Used when a notification is actually sent or logged (digest).
        For suppressed notifications, use update_last_notified_at_only() instead.
        """
        result = await self.cases_collection.find_one_and_update(
            {"case_id": case_id},
            {
                "$set": {
                    "last_notified_at": last_notified_at,
                    "updated_at": datetime.utcnow()
                },
                "$inc": {"notification_count": 1}
            },
            return_document=ReturnDocument.AFTER
        )
        if result:
            result = _normalize_mongo_doc(result)
            return BugCase(**result)
        raise ValueError(f"Case {case_id} not found")

    async def update_last_notified_at_only(self, case_id: str, last_notified_at: datetime) -> BugCase:
        """Update last_notified_at without incrementing notification_count.

        Used for suppressed notifications (muted/snoozed) to reset the throttle window
        without counting the suppressed event as a delivered notification.
        """
        result = await self.cases_collection.find_one_and_update(
            {"case_id": case_id},
            {
                "$set": {
                    "last_notified_at": last_notified_at,
                    "updated_at": datetime.utcnow()
                }
            },
            return_document=ReturnDocument.AFTER
        )
        if result:
            result = _normalize_mongo_doc(result)
            return BugCase(**result)
        raise ValueError(f"Case {case_id} not found")

    async def create_notification_attempt(
        self, attempt: NotificationAttemptCreate
    ) -> Optional[NotificationAttempt]:
        """Create a notification attempt record.

        Returns:
            NotificationAttempt on success, None if storage fails.
            Errors are logged but not propagated to the caller.
        """
        try:
            attempt_dict = attempt.model_dump(by_alias=False, exclude_none=False)
            result = await self.notification_attempts_collection.insert_one(attempt_dict)
            attempt_dict["_id"] = result.inserted_id
            attempt_dict = _normalize_mongo_doc(attempt_dict)
            return NotificationAttempt(**attempt_dict)
        except Exception as e:
            logger.error(f"Failed to create notification attempt: {e}", exc_info=True)
            return None

    async def mute_case(self, case_id: str, muted_until: datetime) -> BugCase:
        """Mute a BugCase until the specified timestamp."""
        result = await self.cases_collection.find_one_and_update(
            {"case_id": case_id},
            {
                "$set": {
                    "muted_until": muted_until,
                    "updated_at": datetime.utcnow()
                }
            },
            return_document=ReturnDocument.AFTER
        )
        if result:
            result = _normalize_mongo_doc(result)
            return BugCase(**result)
        raise ValueError(f"Case {case_id} not found")

    async def snooze_case(self, case_id: str, snoozed_until: datetime) -> BugCase:
        """Snooze a BugCase until the specified timestamp."""
        result = await self.cases_collection.find_one_and_update(
            {"case_id": case_id},
            {
                "$set": {
                    "snoozed_until": snoozed_until,
                    "updated_at": datetime.utcnow()
                }
            },
            return_document=ReturnDocument.AFTER
        )
        if result:
            result = _normalize_mongo_doc(result)
            return BugCase(**result)
        raise ValueError(f"Case {case_id} not found")

    async def get_cases_active_during_window(
        self,
        window_start: datetime,
        severities: list[str],
    ) -> list[BugCase]:
        """Return BugCases with matching severity created or updated during window.

        Queries cases where created_at >= window_start and severity is in severities list.
        """
        docs = await self.cases_collection.find({
            "severity": {"$in": severities},
            "created_at": {"$gte": window_start}
        }).to_list(None)
        return [BugCase(**_normalize_mongo_doc(doc)) for doc in docs]

    async def create_evidence_pack(self, pack: EvidencePackCreate) -> EvidencePack:
        """Insert a new Evidence Pack. Returns persisted EvidencePack with id."""
        pack_dict = pack.model_dump(by_alias=False, exclude_none=False)
        result = await self.evidence_packs_collection.insert_one(pack_dict)
        pack_dict["_id"] = result.inserted_id
        pack_dict = _normalize_mongo_doc(pack_dict)
        return EvidencePack(**pack_dict)

    async def get_evidence_pack(self, pack_id: str) -> Optional[EvidencePack]:
        """Retrieve an Evidence Pack by pack_id."""
        doc = await self.evidence_packs_collection.find_one({"pack_id": pack_id})
        if doc:
            doc = _normalize_mongo_doc(doc)
            return EvidencePack(**doc)
        return None

    async def get_evidence_pack_for_case(self, bugcase_id: str) -> Optional[EvidencePack]:
        """Retrieve the Evidence Pack attached to a BugCase. Returns None if not yet collected."""
        doc = await self.evidence_packs_collection.find_one({"bugcase_id": bugcase_id})
        if doc:
            doc = _normalize_mongo_doc(doc)
            return EvidencePack(**doc)
        return None

    async def update_evidence_pack_section(
        self,
        pack_id: str,
        section_data: dict,
        updated_at: Optional[datetime] = None
    ) -> Optional[EvidencePack]:
        """
        Update one or more fields on an existing Evidence Pack.
        Used by collectors to write their section after collection completes.
        section_data is a flat dict of field names to values.
        Sets updated_at to now if not provided.
        Returns updated EvidencePack.

        MERGE SEMANTICS:
        - evidence_references: merged with individual keys set (multiple collectors)
        - sections_missing: appended to list (multiple collectors add entries)
        - All other fields: overwritten with $set
        """
        if updated_at is None:
            updated_at = datetime.utcnow()

        update_dict: dict = {"$set": {"updated_at": updated_at}}

        # Make a copy to avoid modifying the caller's dict
        section_data_copy = dict(section_data)
        # Separate fields with special merge semantics
        evidence_refs = section_data_copy.pop("evidence_references", None)
        sections_missing = section_data_copy.pop("sections_missing", None)
        healthy_signals = section_data_copy.pop("healthy_signals", None)

        # Add all other fields directly
        if section_data_copy:
            update_dict["$set"].update(section_data_copy)

        # Add evidence_references using dot-notation for merge semantics
        if evidence_refs:
            for ref_key, ref_value in evidence_refs.items():
                update_dict["$set"][f"evidence_references.{ref_key}"] = ref_value

        # Add sections_missing using $push for append semantics (multiple collectors)
        if sections_missing:
            if "$push" not in update_dict:
                update_dict["$push"] = {}
            update_dict["$push"]["sections_missing"] = {"$each": sections_missing}

        # Add healthy_signals using $push for append semantics (multiple collectors)
        if healthy_signals:
            if "$push" not in update_dict:
                update_dict["$push"] = {}
            update_dict["$push"]["healthy_signals"] = {"$each": healthy_signals}

        result = await self.evidence_packs_collection.find_one_and_update(
            {"pack_id": pack_id},
            update_dict,
            return_document=ReturnDocument.AFTER
        )

        if result:
            result = _normalize_mongo_doc(result)
            return EvidencePack(**result)
        return None

    async def mark_evidence_pack_complete(
        self,
        pack_id: str,
        collection_completed_at: datetime,
        collection_duration_ms: int,
        sections_collected: list[str],
        total_chars: int
    ) -> Optional[EvidencePack]:
        """
        Mark an Evidence Pack as complete after all collectors have run.
        Sets collection_status to:
          COMPLETE if collection_errors is empty AND sections_missing is empty
          PARTIAL if collection_errors is non-empty OR sections_missing is non-empty
        """
        # First, fetch the current pack to check error and missing sections state
        current_pack = await self.get_evidence_pack(pack_id)
        if not current_pack:
            return None

        # Determine status based on current state
        has_errors = len(current_pack.collection_errors) > 0
        has_missing = len(current_pack.sections_missing) > 0
        status = EvidencePackStatus.PARTIAL if (has_errors or has_missing) else EvidencePackStatus.COMPLETE

        update_dict = {
            "$set": {
                "collection_completed_at": collection_completed_at,
                "collection_duration_ms": collection_duration_ms,
                "sections_collected": sections_collected,
                "total_chars": total_chars,
                "collection_status": status,
                "updated_at": datetime.utcnow()
            }
        }

        result = await self.evidence_packs_collection.find_one_and_update(
            {"pack_id": pack_id},
            update_dict,
            return_document=ReturnDocument.AFTER
        )

        if result:
            result = _normalize_mongo_doc(result)
            return EvidencePack(**result)
        return None

    async def get_related_cases(
        self,
        bugcase_id: str,
        subsystems: list[str],
        lookback_days: int = 7,
        limit: int = 10,
    ) -> list[BugCase]:
        """
        Find BugCases sharing subsystems with the current case.

        Query: cases where root_subsystem OR any value in affected_subsystems
        is in the provided subsystems list, AND first_seen_at >= (now - lookback_days),
        AND case_id != bugcase_id.

        Returns up to limit cases sorted by first_seen_at descending (most recent first).

        Args:
            bugcase_id: ID of the current BugCase to exclude from results
            subsystems: List of subsystem names to search for
            lookback_days: Number of days to look back (default 7)
            limit: Maximum number of cases to return (default 10)

        Returns:
            List of related BugCases sorted by first_seen_at descending
        """
        if not subsystems:
            return []

        lookback_cutoff = datetime.utcnow() - timedelta(days=lookback_days)

        docs = await self.cases_collection.find(
            {
                "$or": [
                    {"root_subsystem": {"$in": subsystems}},
                    {"affected_subsystems": {"$in": subsystems}},
                    {"blast_radius": {"$in": subsystems}},
                ],
                "first_seen_at": {"$gte": lookback_cutoff},
                "case_id": {"$ne": bugcase_id},
            }
        ).sort("first_seen_at", -1).limit(limit).to_list(None)

        return [BugCase(**_normalize_mongo_doc(doc)) for doc in docs]

    async def get_cases_without_evidence(self) -> list[BugCase]:
        """
        Return BugCases that have no Evidence Pack attached and are eligible for collection.

        Query: cases where status is NOT 'closed' (CaseStatus.CLOSED),
        AND case_id is NOT in evidence_packs.bugcase_id collection.

        Includes both open and resolved cases — resolved cases are still eligible
        if they have no Evidence Pack (see TASK-116 eligibility rules).

        Returns:
            List of BugCases without Evidence Packs
        """
        # Fetch all bugcase_ids that have evidence packs
        evidence_pack_docs = await self.evidence_packs_collection.find(
            {}, {"bugcase_id": 1}
        ).to_list(None)
        bugcase_ids_with_packs = {doc["bugcase_id"] for doc in evidence_pack_docs}

        # Query for cases where status != 'closed' and not in bugcase_ids_with_packs
        docs = await self.cases_collection.find({
            "status": {"$ne": "closed"},
            "case_id": {"$nin": list(bugcase_ids_with_packs)}
        }).to_list(None)

        return [BugCase(**_normalize_mongo_doc(doc)) for doc in docs]
