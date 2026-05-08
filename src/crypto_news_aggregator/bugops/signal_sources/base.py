"""Base signal source interface."""

from typing import Protocol, List
from ..models import BugAlertEventCreate


class SignalSource(Protocol):
    """Thin async interface for signal sources."""

    source_type: str

    async def collect(self) -> List[BugAlertEventCreate]:
        """Collect signals and return alert events."""
        ...
