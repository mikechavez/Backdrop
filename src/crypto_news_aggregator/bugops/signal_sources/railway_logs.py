"""Railway log signal source for BugOps."""

from typing import List
from ..models import BugAlertEventCreate


class RailwayLogSignalSource:
    """Monitor Railway deployment logs for operational signals."""

    source_type = "railway_logs"

    async def collect(self) -> List[BugAlertEventCreate]:
        """Collect signals from Railway logs."""
        # TODO: Implement Railway log ingestion (requires Railway API access)
        return []
