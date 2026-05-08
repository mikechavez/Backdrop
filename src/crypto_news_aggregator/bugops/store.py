"""BugOps alert and case storage."""

import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from .models import (
    BugAlertEventCreate,
    BugAlertEvent,
    BugCaseCreate,
    BugCase,
)

logger = logging.getLogger(__name__)


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
        return BugAlertEvent(**event_dict)

    async def find_open_case_by_dedupe_key(self, dedupe_key: str) -> Optional[BugCase]:
        """Find an open case by dedupe key (ignores resolved/closed cases)."""
        doc = await self.cases_collection.find_one({
            "dedupe_key": dedupe_key,
            "status": "open"
        })
        if doc:
            return BugCase(**doc)
        return None

    async def create_case_from_alert(self, event: BugAlertEvent) -> BugCase:
        """Create a new case from an alert event."""
        case_create = BugCaseCreate(
            case_id=event.case_id or f"case_{event.alert_id}",
            status="open",
            severity=event.severity,
            title=event.title,
            summary=event.summary,
            dedupe_key=event.dedupe_key,
            source_types=[event.source_type],
            alert_ids=[event.alert_id],
            correlation_keys=event.correlation_keys,
        )
        case_dict = case_create.model_dump(by_alias=False, exclude_none=False)
        result = await self.cases_collection.insert_one(case_dict)
        case_dict["_id"] = result.inserted_id
        return BugCase(**case_dict)

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
            return BugCase(**result)
        raise ValueError(f"Case {case_id} not found")

    async def get_case(self, case_id: str) -> Optional[BugCase]:
        """Get a case by case_id."""
        doc = await self.cases_collection.find_one({"case_id": case_id})
        if doc:
            return BugCase(**doc)
        return None
