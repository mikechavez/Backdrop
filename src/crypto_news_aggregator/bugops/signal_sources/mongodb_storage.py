"""MongoDB storage estimate alerts for BugOps."""

import logging
from datetime import datetime, timezone
from typing import List

from ..models import AlertSeverity, BugAlertEventCreate
from ...core.config import get_settings
from ...db.mongodb import mongo_manager
from ...services.mongodb_retention import classify_storage_usage, storage_report

logger = logging.getLogger(__name__)


class MongoStorageSignalSource:
    """Report configurable database storage estimates through the BugOps pipeline."""

    source_type = "mongodb_storage"

    async def collect(self) -> List[BugAlertEventCreate]:
        settings = get_settings()
        try:
            db = await mongo_manager.get_async_database()
            report = await storage_report(db, settings.MONGODB_STORAGE_QUOTA_MB)
        except Exception:
            logger.exception("MongoDB storage estimate unavailable; no quota alert emitted")
            return []

        level = classify_storage_usage(
            report["estimated_percent_used"],
            settings.MONGODB_STORAGE_WARNING_PERCENT,
            settings.MONGODB_STORAGE_CRITICAL_PERCENT,
        )
        if level is None:
            return []

        now = datetime.now(timezone.utc)
        severity = AlertSeverity.CRITICAL if level == "critical" else AlertSeverity.WARNING
        percent = report["estimated_percent_used"]
        day = now.strftime("%Y-%m-%d")
        dedupe_key = f"mongodb_storage:{level}:{day}"
        return [
            BugAlertEventCreate(
                alert_id=f"alert_{dedupe_key}",
                source_type=self.source_type,
                source_id="mongodb.storage_estimate",
                alert_type="storage_threshold",
                severity=severity,
                title=f"MongoDB Storage Estimate {level.title()}",
                summary=(
                    f"MongoDB dbStats estimate is {percent:.1f}% of configured quota. "
                    "Verify authoritative usage in MongoDB Atlas."
                ),
                domain=["database", "storage"],
                dedupe_key=dedupe_key,
                correlation_keys=["domain:database", "domain:storage"],
                metric=report,
            )
        ]
