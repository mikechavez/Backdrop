# Sprint 020 Alignment Investigation - Findings

Investigation Date: 2026-06-10  
Investigator: Claude Code  
Status: Investigation Only (No Code Changes)

---

## 1. Dedupe Key Format

### Current Implementation

**File & Line:** `src/crypto_news_aggregator/bugops/signal_sources/llm_traces.py:121-123`

```python
def _get_dedupe_key(self, dt: datetime) -> str:
    """Generate UTC hour-based dedupe key."""
    return f"llm_traces:cost_runaway:{dt.strftime('%Y-%m-%d')}:{dt.strftime('%H')}"
```

**Usage in lookup:** `src/crypto_news_aggregator/bugops/store.py:52-61`

```python
async def find_open_case_by_dedupe_key(self, dedupe_key: str) -> Optional[BugCase]:
    """Find an open case by dedupe key (ignores resolved/closed cases)."""
    doc = await self.cases_collection.find_one({
        "dedupe_key": dedupe_key,
        "status": "open"
    })
    if doc:
        doc = _normalize_mongo_doc(doc)
        return BugCase(**doc)
    return None
```

**Alternative format in railway_logs:** `src/crypto_news_aggregator/bugops/signal_sources/railway_logs.py:64-66`

```python
def _dedupe_key(pattern_name: str, ts: datetime) -> str:
    hour_str = ts.strftime("%Y-%m-%d:%H")
    return f"railway_logs:{pattern_name}:None:{hour_str}"
```

### Index Status

**File:** `src/crypto_news_aggregator/db/mongodb.py`

**Finding:** No BugOps-related indexes exist. The mongodb.py file defines indexes only for:
- ARTICLE_INDEXES (lines 87-101)
- ALERT_INDEXES (lines 103-120) — *these are for the legacy alerts collection, NOT bug_cases*
- PRICE_HISTORY_INDEXES (lines 130-142)
- TWEET_INDEXES (lines 122-128)
- ENTITY_MENTIONS_INDEXES (lines 144+)

There is **no `dedupe_key` index** on the `bug_cases` collection. The `find_open_case_by_dedupe_key()` method queries without an index.

### Summary

**What exists:**
- Two different dedupe_key formats active in the codebase:
  - LLM traces: `llm_traces:cost_runaway:YYYY-MM-DD:HH` (7 segments, colon-separated)
  - Railway logs: `railway_logs:pattern_name:None:YYYY-MM-DD:HH` (5 segments, colon-separated)
- No unique constraint or index on dedupe_key in bug_cases collection
- Lookup is a simple equality query without an index

**Gap:** Sprint 020 requires a new format `detector_type:root_subsystem` (e.g., `article_freshness:articles`), which is shorter and lacks the hour bucketing. This is a **breaking conflict** — existing cases use hour-bucketed keys and will not match freshness detector queries under the new format.

**Action Required:**
- Additive: Define dedupe_key format for all Sprint 020 detector types
- Conflicting: Migrate existing cases or add a fallback to old format during a transition period
- Additive: Add unique index on dedupe_key once format is finalized

---

## 2. BugAlertEvent Layer

### BugAlertEvent Model

**File & Lines:** `src/crypto_news_aggregator/bugops/models.py:31-60`

```python
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
```

### BugCase Model

**File & Lines:** `src/crypto_news_aggregator/bugops/models.py:62-89`

```python
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


class BugCase(BugCaseCreate):
    """Case persisted in database."""
    id: Optional[str] = Field(default=None, alias="_id")

    class Config:
        populate_by_name = True
```

### Processing Flow

**File & Lines:** `src/crypto_news_aggregator/bugops/store.py:107-121`

```python
async def process_alert_event(self, event: BugAlertEventCreate) -> tuple[BugCase, bool]:
    """Process alert event: create alert, find or create case by dedupe_key.

    Returns:
        Tuple of (case, is_new) where is_new is True only if a new case was created
    """
    alert = await self.create_alert_event(event)
    case = await self.find_open_case_by_dedupe_key(alert.dedupe_key)
    is_new = case is None
    if is_new:
        case = await self.create_case_from_alert(alert)
    else:
        case = await self.attach_alert_to_case(case.case_id, alert.alert_id)
    return case, is_new
```

**Additional lookup:** `src/crypto_news_aggregator/bugops/store.py:99-105`

```python
async def get_case(self, case_id: str) -> Optional[BugCase]:
    """Get a case by case_id."""
    doc = await self.cases_collection.find_one({"case_id": case_id})
    if doc:
        doc = _normalize_mongo_doc(doc)
        return BugCase(**doc)
    return None
```

### Summary

**What exists:**
- `BugAlertEvent` is mandatory — all signals flow through `process_alert_event()` which creates a `BugAlertEvent` first, then finds or creates a `BugCase`
- The `case_id` field on `BugAlertEvent` is optional (`case_id: Optional[str] = None`) but is populated after the case is found/created
- `BugAlertEvent` and `BugCase` share similar fields: `title`, `summary`, `severity`, `alert_type`, `dedupe_key`, `correlation_keys`, `metric`
- Cases can be retrieved by `case_id` or by `dedupe_key` + status

**Gap:** Sprint 020 freshness detectors will be internal to BugOps and will not follow the external-signal-to-alert-event flow. The question is whether freshness detectors should:
1. Create a `BugAlertEvent` anyway (maintains consistency, adds storage overhead)
2. Skip `BugAlertEvent` and create `BugCase` directly (reduces storage, breaks the uniform flow)

**Current state:** There is **no path to create a BugCase without a BugAlertEvent**. The only way to create a case is:
- `process_alert_event()` → creates alert first → then creates or attaches to case
- `create_case_from_alert()` → requires a `BugAlertEvent` as input

**Action Required:**
- Additive: Add a `create_case_direct()` method to `BugOpsStore` if freshness detectors should bypass `BugAlertEvent`
- Or: Update `process_alert_event()` to accept optional source (allow None for internal detectors) so freshness detectors can still create an event

---

## 3. BugCase Data Model Fields

### Current BugCase Model

**File & Lines:** `src/crypto_news_aggregator/bugops/models.py:62-89` (full definition shown above)

**Current fields:**
- `case_id: str` — unique case identifier
- `status: CaseStatus` — one of {OPEN, RESOLVED, CLOSED}
- `severity: AlertSeverity` — one of {INFO, WARNING, HIGH, CRITICAL}
- `alert_type: str` — e.g., "cost_runaway", "db_connection_error"
- `title: str` — human-readable title
- `summary: str` — brief description
- `dedupe_key: str` — used to find existing open cases
- `source_types: list[str]` — which signal sources contributed (e.g., ["llm_traces", "railway_logs"])
- `alert_ids: list[str]` — attached alert IDs
- `correlation_keys: list[str]` — tags for correlation (e.g., ["domain:llm", "operation:enrichment"])
- `metric: dict` — arbitrary metrics/measurements
- `suggested_manual_check: Optional[str]` — note for operator
- `created_at: datetime` — case creation timestamp
- `updated_at: datetime` — last update timestamp
- `resolved_at: Optional[datetime]` — when resolved
- `closed_at: Optional[datetime]` — when closed
- `deterministic_report: Optional[str]` — analysis report

### MongoDB Indexes

**Finding:** No indexes defined for bug_cases or bug_alert_events collections. The index initialization in `mongodb.py:541-607` does not reference BugOps collections.

### Missing Fields from Sprint 020 Requirements

Sprint 020 requires:
- `root_subsystem: string`
- `affected_subsystems: list of strings`
- `blast_radius: list of strings`
- `recovery_candidate_at: timestamp | null`
- `observation_count: integer`
- `resolution_type: string | null`
- `confidence: float | null`
- `correlation_reason: string | null`

**Existing fields that partially satisfy:**
- `correlation_keys: list[str]` — can store subsystem references, but is unstructured
- `metric: dict` — can store arbitrary counts, but `observation_count` should be a first-class field for efficient querying/sorting

### Observation Count Tracking

**Current approach:** No explicit `observation_count` field. The count is implicitly tracked by the length of `alert_ids` list (number of attached alerts).

**Code evidence:** `src/crypto_news_aggregator/bugops/store.py:84-97`

```python
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
        result = _normalize_mongo_doc(result)
        return BugCase(**result)
    raise ValueError(f"Case {case_id} not found")
```

The `alert_ids` list tracks all alerts attached to a case via `$addToSet`.

### Last Seen / First Seen Tracking

**Finding:** No explicit `first_seen_at` or `last_seen_at` fields. Only `created_at` (case creation) and `updated_at` (last modification) are tracked.

**Gap:** If Sprint 020 needs to know when a detector last fired (for "recovery_candidate_at" calculation), this information is not available unless stored as a separate field.

### Summary

**What exists:**
- 15 fields on BugCase covering severity, status, routing, and timeline
- Implicit observation count via `alert_ids` list length
- Generic `metric: dict` for extensibility
- Created/updated timestamps but no explicit "last observed" tracking

**What is missing — all additive:**
- `root_subsystem: string` — not present
- `affected_subsystems: list[str]` — not present
- `blast_radius: list[str]` — not present
- `recovery_candidate_at: Optional[datetime]` — not present
- `observation_count: int` — tracked implicitly via `len(alert_ids)`, should be explicit
- `resolution_type: Optional[str]` — not present (status is enough for now, but resolution type may differ from status)
- `confidence: Optional[float]` — not present
- `correlation_reason: Optional[str]` — not present (correlation_keys exist but are unstructured tags)

**MongoDB indexes:** None exist for bug_cases or bug_alert_events. Will need to define indexes on:
- `dedupe_key` (likely unique or compound with status)
- `status` and `created_at` (for listing open/resolved cases)
- `root_subsystem` (once added, for filtering by subsystem)

**Action Required:**
- Additive: Add 8 new fields to BugCaseCreate and BugCase models
- Additive: Decide whether `observation_count` should be:
  - Denormalized (stored explicitly, updated on each alert attach)
  - Computed on read (from `len(alert_ids)`)
- Additive: Add MongoDB indexes for bug_cases (dedupe_key, status+created_at, root_subsystem once added)
- Consider: Add `first_observed_at` and `last_observed_at` for freshness detector lifecycle tracking

---

## Alignment Summary Table

| Area | Current | Sprint 020 Required | Gap Type | Effort |
|------|---------|-------------------|----------|--------|
| Dedupe Key Format | `source:type:YYYY-MM-DD:HH` | `detector:subsystem` | Conflicting | High |
| Dedupe Key Index | None | Recommend unique/compound | Additive | Low |
| BugAlertEvent Layer | Mandatory flow | Optional for internal detectors | Additive | Medium |
| BugCase Direct Creation | Not possible | Required | Additive | Low |
| Root Subsystem | Missing | Required | Additive | Low |
| Affected Subsystems | Missing | Required | Additive | Low |
| Blast Radius | Missing | Required | Additive | Low |
| Recovery Candidate At | Missing | Required | Additive | Low |
| Observation Count | Implicit (alert_ids) | Explicit field | Additive | Low |
| Resolution Type | Missing | Required | Additive | Low |
| Confidence | Missing | Required | Additive | Low |
| Correlation Reason | Missing | Required | Additive | Low |
| BugOps Indexes | None | Needed | Additive | Low |

---

## Next Steps for Implementation

### Phase 1: Data Model Extension (Low Risk, Additive)
1. Add 8 new fields to BugCase model
2. Add MongoDB indexes for bug_cases and bug_alert_events
3. Add `create_case_direct()` method for internal detectors

### Phase 2: Dedupe Key Migration (High Risk, Requires Planning)
1. Define dedupe_key formats for all detector types (freshness, cascade, etc.)
2. Decide on migration strategy for existing hour-bucketed keys
3. Update all signal sources to use new format
4. Consider: grace period allowing both old and new formats during transition

### Phase 3: Freshness Detector Integration (Depends on Phase 1-2)
Implement freshness detectors using extended model and direct case creation path

