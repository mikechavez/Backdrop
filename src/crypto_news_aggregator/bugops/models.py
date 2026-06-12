"""BugOps data models."""

from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from typing import Optional


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """Alert event status."""
    NEW = "new"
    ATTACHED = "attached"
    IGNORED = "ignored"


class CaseStatus(str, Enum):
    """Case lifecycle status."""
    OPEN = "open"
    RESOLVED = "resolved"
    CLOSED = "closed"


class BugAlertEventCreate(BaseModel):
    """Create a new alert event."""
    alert_id: str
    case_id: Optional[str] = None
    source_type: str
    source_id: str
    alert_type: str
    severity: AlertSeverity
    status: AlertStatus = AlertStatus.NEW
    title: str
    summary: str
    domain: list[str]
    service: Optional[str] = None
    operation: Optional[str] = None
    model: Optional[str] = None
    dedupe_key: str
    correlation_keys: list[str] = Field(default_factory=list)
    metric: dict = Field(default_factory=dict)
    raw_sample_ref: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class BugAlertEvent(BugAlertEventCreate):
    """Alert event persisted in database."""
    id: Optional[str] = Field(default=None, alias="_id")

    class Config:
        populate_by_name = True


class BugCaseCreate(BaseModel):
    """Create a new case."""
    case_id: str
    status: CaseStatus = CaseStatus.OPEN
    severity: AlertSeverity
    alert_type: str
    title: str
    summary: str
    dedupe_key: str
    source_types: list[str]
    alert_ids: list[str] = Field(default_factory=list)
    correlation_keys: list[str] = Field(default_factory=list)
    metric: dict = Field(default_factory=dict)
    suggested_manual_check: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    deterministic_report: Optional[str] = None
    root_subsystem: Optional[str] = None
    affected_subsystems: list[str] = Field(default_factory=list)
    blast_radius: list[str] = Field(default_factory=list)
    observation_count: int = 1
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    recovery_candidate_at: Optional[datetime] = None
    resolution_type: Optional[str] = None  # reserved: real_issue | false_positive | duplicate | operator_error | expected_idle
    detection_type: Optional[str] = None  # startup | runtime | reopen
    reopen_count: int = 0
    muted_until: Optional[datetime] = None
    snoozed_until: Optional[datetime] = None
    last_notified_at: Optional[datetime] = None
    notification_count: int = 0


class BugCase(BugCaseCreate):
    """Case persisted in database."""
    id: Optional[str] = Field(default=None, alias="_id")

    class Config:
        populate_by_name = True


class BugCaseEventCreate(BaseModel):
    """Create a case event (timeline entry)."""
    case_id: str
    event_type: str
    message: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BugCaseEvent(BugCaseEventCreate):
    """Case event persisted in database."""
    id: Optional[str] = Field(default=None, alias="_id")

    class Config:
        populate_by_name = True


class BugToolCallCreate(BaseModel):
    """Create a tool call record."""
    case_id: str
    tool_name: str
    input_params: dict
    output: dict
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BugToolCall(BugToolCallCreate):
    """Tool call persisted in database."""
    id: Optional[str] = Field(default=None, alias="_id")

    class Config:
        populate_by_name = True
