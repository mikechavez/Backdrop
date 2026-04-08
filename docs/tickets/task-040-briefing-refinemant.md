---
id: TASK-040
type: feature
status: backlog
priority: medium
complexity: medium
created: 2026-04-08
updated: 2026-04-08
---

# Dataset Capture — Pre/Post Refine Briefing Drafts

## Problem/Opportunity

The self-refine loop in `briefing_agent.py` runs up to 5 LLM calls per briefing but we have no data on whether refinement actually improves quality. Sprint 14's eval system needs paired examples (before vs after refinement) to measure this. Without capturing both drafts now, we'd have to wait another full cycle to collect data.

## Proposed Solution

In `_self_refine`, save both the pre-refine and post-refine `GeneratedBriefing` outputs to a new `briefing_drafts` MongoDB collection, linked by `briefing_id` and the `trace_id` from the gateway response.

## Acceptance Criteria

- [ ] New MongoDB collection `briefing_drafts` created with indexes
- [ ] After initial briefing generation (before self-refine), the draft is saved with `stage="pre_refine"`
- [ ] After each refinement pass, the draft is saved with `stage="post_refine_N"` (where N is iteration number)
- [ ] If no refinement is needed (critique says it's fine), only the `pre_refine` record exists
- [ ] Each draft record contains: `briefing_id`, `trace_id` (from the gateway call that produced it), `stage`, `timestamp`, `model`, and the full `GeneratedBriefing` fields (narrative, key_insights, entities_mentioned, detected_patterns, recommendations, confidence_score)
- [ ] `briefing_id` links all drafts for the same briefing (use the same ID that `_save_briefing` uses)
- [ ] TTL index: 90 days (longer than traces — these are eval datasets)
- [ ] Unit test: mock gateway, run self-refine with 1 iteration, assert 2 draft records saved (pre + post_refine_1)
- [ ] Unit test: mock gateway with critique returning "no refinement needed", assert 1 draft record (pre only)

## Dependencies

- TASK-036 (gateway provides trace_id on each response)
- TASK-038 (briefing_agent must be wired through gateway before draft capture makes sense — trace_ids come from gateway responses)

## Implementation Notes

### Draft document schema

```python
{
    "briefing_id": "ObjectId-or-string",  # Same ID used in _save_briefing
    "trace_id": "uuid-from-gateway",       # Links to llm_traces
    "stage": "pre_refine",                 # or "post_refine_1", "post_refine_2"
    "timestamp": datetime(UTC),
    "model": "claude-sonnet-4-5-20250929",
    "narrative": "Full briefing text...",
    "key_insights": ["insight1", "insight2"],
    "entities_mentioned": ["Bitcoin", "SEC"],
    "detected_patterns": ["pattern1"],
    "recommendations": [{"action": "...", "reason": "..."}],
    "confidence_score": 0.85,
    "critique": None,                       # Populated on post_refine stages
}
```

### File: `src/crypto_news_aggregator/llm/draft_capture.py`

```python
"""
Briefing draft capture for eval dataset building.

Saves pre-refine and post-refine briefing outputs to MongoDB
for Sprint 14 quality evaluation.
"""

import logging
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

COLLECTION_NAME = "briefing_drafts"
TTL_DAYS = 90


async def ensure_draft_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create indexes on briefing_drafts collection."""
    collection = db[COLLECTION_NAME]
    await collection.create_index("timestamp", expireAfterSeconds=TTL_DAYS * 86400)
    await collection.create_index("briefing_id")
    await collection.create_index([("briefing_id", 1), ("stage", 1)])
    logger.info("briefing_drafts indexes ensured")


async def save_draft(
    db: AsyncIOMotorDatabase,
    briefing_id: str,
    trace_id: str,
    stage: str,
    model: str,
    generated,  # GeneratedBriefing dataclass
    critique: str | None = None,
) -> None:
    """Save a briefing draft to the collection."""
    try:
        collection = db[COLLECTION_NAME]
        await collection.insert_one({
            "briefing_id": briefing_id,
            "trace_id": trace_id,
            "stage": stage,
            "timestamp": datetime.now(timezone.utc),
            "model": model,
            "narrative": generated.narrative,
            "key_insights": generated.key_insights,
            "entities_mentioned": generated.entities_mentioned,
            "detected_patterns": generated.detected_patterns,
            "recommendations": generated.recommendations,
            "confidence_score": generated.confidence_score,
            "critique": critique,
        })
        logger.info(f"Saved draft: briefing_id={briefing_id}, stage={stage}")
    except Exception as e:
        logger.error(f"Failed to save draft: {e}")
        # Don't raise — draft capture is observability, not critical path
```

### Changes to `briefing_agent.py`

In `generate_briefing`, after initial generation and parsing (around line 355-360):

```python
# After: generated = self._parse_briefing_response(response_text)
# Add:
from crypto_news_aggregator.llm.draft_capture import save_draft

# briefing_id must be generated BEFORE _self_refine so it can be shared
import bson
briefing_id = str(bson.ObjectId())

db = await mongo_manager.get_async_database()
await save_draft(
    db=db,
    briefing_id=briefing_id,
    trace_id=gateway_response.trace_id,  # from the generate call
    stage="pre_refine",
    model=BRIEFING_PRIMARY_MODEL,
    generated=generated,
)
```

In `_self_refine`, after each successful refinement parse (around line 422):

```python
# After: current = self._parse_briefing_response(refined_response)
# Add:
await save_draft(
    db=db,
    briefing_id=briefing_id,
    trace_id=refine_gateway_response.trace_id,
    stage=f"post_refine_{iteration + 1}",
    model=BRIEFING_PRIMARY_MODEL,
    generated=current,
    critique=critique_response,
)
```

**Note:** This requires `_self_refine` to receive `briefing_id` and `db` as parameters, and `_call_llm` wrapper to return the full `GatewayResponse` (not just `response.text`). The `_call_llm` signature change:

```python
async def _call_llm(...) -> GatewayResponse:  # was -> str
```

Callers that only need text use `response.text`.

### Test file: `tests/test_draft_capture.py`

1. `test_pre_refine_saved` — mock gateway, run generate_briefing, query briefing_drafts for stage="pre_refine", assert 1 record
2. `test_post_refine_saved` — mock gateway + critique returning "needs work", assert both pre_refine and post_refine_1 records exist
3. `test_no_refine_only_pre` — mock critique returning "looks good", assert only pre_refine exists
4. `test_draft_linked_by_briefing_id` — assert all drafts for one briefing share the same briefing_id

## Open Questions

- [ ] Should `_call_llm` return `GatewayResponse` everywhere or only when draft capture needs it? Recommendation: return `GatewayResponse` everywhere — the trace_id is useful metadata even outside draft capture. Callers that only need text just do `response.text`.

## Completion Summary
- Actual complexity:
- Key decisions made:
- Deviations from plan: