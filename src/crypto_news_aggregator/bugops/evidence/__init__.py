"""Evidence collection framework for BugOps."""

from .base import EvidenceCollectorBase
from .collector import EvidenceCollector

__all__ = [
    "EvidenceCollectorBase",
    "EvidenceCollector",
]
