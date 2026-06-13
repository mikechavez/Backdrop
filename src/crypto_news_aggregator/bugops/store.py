"""BugOps alert and case storage."""

import logging
from datetime import datetime
from typing import Optional
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from .models import (
    BugAlertEventCreate,
    BugAlertEvent,
    BugCaseCreate,
    BugCase,
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
            return_document=True
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
