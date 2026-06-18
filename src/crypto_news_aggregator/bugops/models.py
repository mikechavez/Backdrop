"""BugOps data models."""

from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from enum import Enum
from typing import Optional


class BugOpsSubsystem(str, Enum):
    """Canonical BugOps subsystem enum."""
    SCHEDULER = "scheduler"
    INGESTION = "ingestion"
    ARTICLES = "articles"
    SIGNALS = "signals"
    NARRATIVES = "narratives"
    BRIEFINGS = "briefings"
    WORKER = "worker"
    DATABASE = "database"


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

    @field_validator("root_subsystem")
    @classmethod
    def validate_root_subsystem(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in [s.value for s in BugOpsSubsystem]:
            raise ValueError(f"root_subsystem must be a valid BugOpsSubsystem value, got: {v}")
        return v

    @field_validator("affected_subsystems")
    @classmethod
    def validate_affected_subsystems(cls, v: list[str]) -> list[str]:
        valid_values = {s.value for s in BugOpsSubsystem}
        for subsystem in v:
            if subsystem not in valid_values:
                raise ValueError(f"affected_subsystems contains invalid value: {subsystem}. Must be one of: {valid_values}")
        return v

    @field_validator("blast_radius")
    @classmethod
    def validate_blast_radius(cls, v: list[str]) -> list[str]:
        valid_values = {s.value for s in BugOpsSubsystem}
        for subsystem in v:
            if subsystem not in valid_values:
                raise ValueError(f"blast_radius contains invalid value: {subsystem}. Must be one of: {valid_values}")
        return v


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


class NotificationAttemptCreate(BaseModel):
    """Create a notification attempt record."""
    notification_id: str
    bugcase_id: str
    event_type: str  # bugcase_created | bugcase_reopened | severity_escalated | suppression_summary
    channel: str = "slack"
    status: str  # sent | failed | suppressed | skipped
    attempted_at: datetime = Field(default_factory=datetime.utcnow)
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    suppressed_reason: Optional[str] = None


class NotificationAttempt(NotificationAttemptCreate):
    """Notification attempt persisted in database."""
    id: Optional[str] = Field(default=None, alias="_id")

    class Config:
        populate_by_name = True


class EvidencePackStatus(str, Enum):
    """Evidence Pack collection status."""
    COMPLETE = "complete"
    PARTIAL = "partial"


class CollectionError(BaseModel):
    """Records a failure to collect from one evidence source."""
    source: str
    error_type: str
    error_message: str
    attempted_at: datetime = Field(default_factory=datetime.utcnow)


class LogExcerptSection(BaseModel):
    """Log excerpt metadata and content for one service."""
    service: str
    lines_fetched: int
    lines_stored: int
    truncated: bool
    window_start: datetime
    window_end: datetime
    collected_at: datetime = Field(default_factory=datetime.utcnow)
    excerpts: list[str] = Field(default_factory=list)


class SectionMetrics(BaseModel):
    """Freshness and count metrics for one subsystem."""
    subsystem: str
    last_artifact_at: Optional[datetime] = None
    artifact_count: Optional[int] = None
    freshness_indicator: Optional[str] = None


class LLMTraceRecord(BaseModel):
    """Individual LLM operation trace record."""
    timestamp: datetime
    operation: str
    model: str
    cost: float
    input_tokens: int
    output_tokens: int


class LLMTraceSummary(BaseModel):
    """LLM trace and cost summary for incident window."""
    total_cost: float = 0.0
    total_operations: int = 0
    operation_breakdown: dict = Field(default_factory=dict)
    recent_traces: list[LLMTraceRecord] = Field(default_factory=list)


class EvidenceReferenceAllocator:
    """
    Central allocator for evidence reference IDs.
    Prevents collision across collectors.
    One instance per Evidence Pack collection cycle.
    """
    def __init__(self):
        self._counter = 0

    def next_ref(self) -> str:
        """Return next reference ID: E-001, E-002, ..."""
        self._counter += 1
        return f"E-{self._counter:03d}"

    def current_count(self) -> int:
        """Return the current count of allocated references."""
        return self._counter


class EvidencePackCreate(BaseModel):
    """Create a new Evidence Pack."""
    # Identifiers
    pack_id: str
    bugcase_id: str

    # Collection metadata
    collection_started_at: datetime = Field(default_factory=datetime.utcnow)
    collection_completed_at: Optional[datetime] = None
    collection_duration_ms: Optional[int] = None
    collection_status: EvidencePackStatus = EvidencePackStatus.PARTIAL

    # Incident context (snapshot at collection time)
    incident_first_seen_at: Optional[datetime] = None
    incident_last_seen_at: Optional[datetime] = None
    root_subsystem: Optional[str] = None
    severity: Optional[str] = None
    primary_signal: Optional[str] = None
    blast_radius: list[str] = Field(default_factory=list)

    # Evidence sections — each Optional to support partial packs
    subsystem_metrics: list[SectionMetrics] = Field(default_factory=list)
    subsystem_metrics_collected_at: Optional[datetime] = None

    system_state: dict = Field(default_factory=dict)
    system_state_collected_at: Optional[datetime] = None

    healthy_signals: list[str] = Field(default_factory=list)

    related_cases: list[dict] = Field(default_factory=list)
    related_cases_collected_at: Optional[datetime] = None

    deploy_context: list[dict] = Field(default_factory=list)
    deploy_context_collected_at: Optional[datetime] = None

    config_evidence: dict = Field(default_factory=dict)
    config_evidence_collected_at: Optional[datetime] = None

    llm_trace_summary: Optional[LLMTraceSummary] = None
    llm_trace_summary_collected_at: Optional[datetime] = None

    log_excerpts: list[LogExcerptSection] = Field(default_factory=list)

    # Evidence reference index
    evidence_references: dict = Field(default_factory=dict)

    # Collection statistics
    sections_collected: list[str] = Field(default_factory=list)
    sections_missing: list[dict] = Field(default_factory=list)
    redactions_applied: int = 0
    truncation_applied: list[str] = Field(default_factory=list)
    total_chars: int = 0

    # Collection errors
    collection_errors: list[CollectionError] = Field(default_factory=list)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("root_subsystem")
    @classmethod
    def validate_root_subsystem(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in [s.value for s in BugOpsSubsystem]:
            raise ValueError(f"root_subsystem must be a valid BugOpsSubsystem value, got: {v}")
        return v

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in [s.value for s in AlertSeverity]:
            raise ValueError(f"severity must be a valid AlertSeverity value, got: {v}")
        return v

    @field_validator("blast_radius")
    @classmethod
    def validate_blast_radius(cls, v: list[str]) -> list[str]:
        valid_values = {s.value for s in BugOpsSubsystem}
        for subsystem in v:
            if subsystem not in valid_values:
                raise ValueError(f"blast_radius contains invalid value: {subsystem}. Must be one of: {valid_values}")
        return v


class EvidencePack(EvidencePackCreate):
    """Evidence Pack persisted in database."""
    id: Optional[str] = Field(default=None, alias="_id")

    class Config:
        populate_by_name = True
