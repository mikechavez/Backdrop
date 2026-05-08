"""BugOps alert storage."""

import logging
from typing import List
from .models import BugAlertEventCreate

logger = logging.getLogger(__name__)


class BugAlertStore:
    """Store and retrieve bug alert events."""

    async def store_alert(self, alert: BugAlertEventCreate) -> None:
        """Store a single alert event."""
        logger.info(
            f"BugOps alert: [{alert.severity}] {alert.title}",
            extra={"source": alert.source, "metadata": alert.metadata}
        )

    async def store_alerts(self, alerts: List[BugAlertEventCreate]) -> None:
        """Store multiple alert events."""
        for alert in alerts:
            await self.store_alert(alert)
