"""LLM trace signal source for BugOps."""

from typing import List
from ..models import BugAlertEventCreate, BugAlertSeverity


class LLMTraceSignalSource:
    """Monitor LLM trace logs for operational signals."""

    source_type = "llm_traces"

    async def collect(self) -> List[BugAlertEventCreate]:
        """Collect signals from LLM traces."""
        # TODO: Implement LLM trace ingestion
        return []
