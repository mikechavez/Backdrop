"""BugOps data models."""

from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from typing import Optional


class BugAlertSeverity(str, Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BugAlertEventCreate(BaseModel):
    """Alert event for BugOps to process."""
    source: str
    severity: BugAlertSeverity
    title: str
    description: str
    metadata: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
