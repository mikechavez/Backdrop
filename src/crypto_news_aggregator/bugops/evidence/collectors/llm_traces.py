"""LLMTraceCollector for LLM activity and cost evidence."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from ...models import BugCase, EvidenceReferenceAllocator, LLMTraceSummary
from ...store import BugOpsStore
from ..base import EvidenceCollectorBase

logger = logging.getLogger(__name__)

LOOKBACK_MINUTES = 60


class LLMTraceCollector:
    """Collects LLM trace and cost evidence from the llm_traces collection."""

    collector_name = "llm_traces"

    def __init__(self, db):
        """
        Initialize the collector.

        Args:
            db: Motor async database instance
        """
        self.db = db

    async def collect(
        self,
        bugcase: BugCase,
        pack_id: str,
        store: BugOpsStore,
        ref_allocator: EvidenceReferenceAllocator,
    ) -> None:
        """
        Collect LLM trace and cost evidence for the Evidence Pack.

        Queries the llm_traces collection for the window surrounding the BugCase.
        This is deterministic — no LLM calls, no complex computation.

        Args:
            bugcase: The BugCase being investigated
            pack_id: The Evidence Pack ID to write to
            store: BugOpsStore instance for persisting evidence
            ref_allocator: Allocator for collision-free reference IDs
        """
        # Extend window further back — LLM activity precedes failures
        window_start = bugcase.first_seen_at - timedelta(minutes=LOOKBACK_MINUTES)
        window_end = bugcase.last_seen_at or bugcase.first_seen_at

        # Query llm_traces using "timestamp" field (NOT "created_at")
        traces_cursor = self.db["llm_traces"].find({
            "timestamp": {
                "$gte": window_start,
                "$lte": window_end,
            }
        }).sort("timestamp", -1)

        traces = await traces_cursor.to_list(length=500)

        if not traces:
            # No traces in window — write empty summary, still an evidence section
            summary = LLMTraceSummary(
                window_start=window_start,
                window_end=window_end,
            )
            await store.update_evidence_pack_section(
                pack_id,
                {
                    "llm_trace_summary": summary.model_dump(),
                    "llm_trace_summary_collected_at": datetime.utcnow(),
                },
            )
            return

        # Aggregate stats
        total_cost = sum(t.get("cost", 0.0) for t in traces)  # "cost" not "cost_usd"
        total_input = sum(t.get("input_tokens", 0) for t in traces)
        total_output = sum(t.get("output_tokens", 0) for t in traces)
        cached_calls = sum(1 for t in traces if t.get("cached", False))

        # Per-operation breakdown
        operations: dict[str, dict] = {}
        for trace in traces:
            op = trace.get("operation", "unknown")
            if op not in operations:
                operations[op] = {"calls": 0, "cost": 0.0, "last_at": None}
            operations[op]["calls"] += 1
            operations[op]["cost"] += trace.get("cost", 0.0)
            ts = trace.get("timestamp")
            if ts and (operations[op]["last_at"] is None or ts > operations[op]["last_at"]):
                operations[op]["last_at"] = ts

        # Convert datetime to isoformat for storage
        for op_data in operations.values():
            if isinstance(op_data.get("last_at"), datetime):
                op_data["last_at"] = op_data["last_at"].isoformat()

        # Recent traces (last 10, sorted most recent first by MongoDB sort)
        recent_traces = [
            {
                "operation": t.get("operation", "unknown"),
                "model": t.get("model", "unknown"),
                "cost": t.get("cost", 0.0),
                "input_tokens": t.get("input_tokens", 0),
                "output_tokens": t.get("output_tokens", 0),
                "cached": t.get("cached", False),
                "timestamp": t["timestamp"].isoformat() if isinstance(t.get("timestamp"), datetime) else str(t.get("timestamp", "")),
            }
            for t in traces[:10]
        ]

        summary = LLMTraceSummary(
            window_start=window_start,
            window_end=window_end,
            total_calls=len(traces),
            total_cost=round(total_cost, 6),
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            cached_calls=cached_calls,
            operation_breakdown=operations,
            recent_traces=recent_traces,
        )

        # Add evidence references
        ref_cost = ref_allocator.next_ref()
        ref_ops = ref_allocator.next_ref()
        evidence_references = {
            ref_cost: {
                "description": f"LLM spend in window: ${total_cost:.4f} across {len(traces)} calls",
                "section": "llm_trace_summary",
                "field": "total_cost",
            },
            ref_ops: {
                "description": f"Operations in window: {list(operations.keys())}",
                "section": "llm_trace_summary",
                "field": "operation_breakdown",
            },
        }

        await store.update_evidence_pack_section(
            pack_id,
            {
                "llm_trace_summary": summary.model_dump(),
                "llm_trace_summary_collected_at": datetime.utcnow(),
                "evidence_references": evidence_references,
            },
        )

        logger.info(f"LLMTraceCollector: collected {len(traces)} traces, total cost ${total_cost:.4f}")
