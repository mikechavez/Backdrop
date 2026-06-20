"""MetricsCollector for subsystem freshness metrics."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from ...models import BugCase, SectionMetrics, EvidenceReferenceAllocator, BugOpsSubsystem
from ...store import BugOpsStore
from ..base import EvidenceCollectorBase
from ....core.config import get_settings

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects subsystem freshness metrics from MongoDB."""

    collector_name = "metrics"

    def __init__(self):
        """Initialize the collector."""
        self.settings = get_settings()

    async def collect(
        self,
        bugcase: BugCase,
        pack_id: str,
        store: BugOpsStore,
        ref_allocator: EvidenceReferenceAllocator,
    ) -> None:
        """
        Collect subsystem metrics for the Evidence Pack.

        Queries MongoDB for each subsystem in the BugCase to get:
        - Most recent artifact timestamp
        - Count of recent artifacts within the freshness window
        - Human-readable freshness indicator

        Args:
            bugcase: The BugCase being investigated
            pack_id: The Evidence Pack ID to write to
            store: BugOpsStore instance for persisting evidence
            ref_allocator: Allocator for collision-free reference IDs
        """
        db = await store.mongo_manager.get_async_database()

        # Determine which subsystems to collect metrics for
        subsystems_to_check = set(bugcase.blast_radius or [])
        if bugcase.root_subsystem:
            subsystems_to_check.add(bugcase.root_subsystem)

        # Mapping of subsystem to MongoDB collection and timestamp field
        subsystem_config = {
            BugOpsSubsystem.ARTICLES.value: ("articles", "created_at"),
            BugOpsSubsystem.SIGNALS.value: ("signals", "last_updated"),
            BugOpsSubsystem.NARRATIVES.value: ("narratives", "last_summary_generated_at"),
            BugOpsSubsystem.BRIEFINGS.value: ("briefings", "generated_at"),
        }

        metrics_list: list[SectionMetrics] = []
        evidence_references = {}

        # Get the freshness window in minutes
        freshness_window_minutes = self.settings.BUGOPS_ARTICLE_FRESHNESS_WINDOW_MINUTES
        freshness_cutoff = datetime.utcnow() - timedelta(minutes=freshness_window_minutes)

        # Collect metrics for each subsystem
        for subsystem in subsystems_to_check:
            if subsystem not in subsystem_config:
                # Subsystem has no MongoDB collection (scheduler, worker, database, ingestion)
                continue

            collection_name, timestamp_field = subsystem_config[subsystem]
            try:
                collection = db[collection_name]

                # Get most recent artifact
                recent = await collection.find_one(
                    sort=[(timestamp_field, -1)],
                    projection={timestamp_field: 1},
                )

                last_artifact_at: Optional[datetime] = None
                if recent and timestamp_field in recent:
                    last_artifact_at = recent[timestamp_field]

                # Count recent artifacts within freshness window
                count = 0
                if last_artifact_at and last_artifact_at >= freshness_cutoff:
                    # Only count if the most recent is within the window
                    count = await collection.count_documents(
                        {timestamp_field: {"$gte": freshness_cutoff}}
                    )

                # Build freshness indicator
                if last_artifact_at is None:
                    freshness_indicator = "no artifacts found"
                elif last_artifact_at >= freshness_cutoff:
                    freshness_indicator = "within window"
                else:
                    # Calculate elapsed time
                    elapsed = datetime.utcnow() - last_artifact_at
                    minutes = int(elapsed.total_seconds() / 60)
                    if minutes < 60:
                        freshness_indicator = f"{minutes} minutes ago"
                    else:
                        hours = int(minutes / 60)
                        freshness_indicator = f"{hours} hours ago"

                # Build SectionMetrics
                metric = SectionMetrics(
                    subsystem=subsystem,
                    last_artifact_at=last_artifact_at,
                    artifact_count=count if count > 0 else None,
                    freshness_indicator=freshness_indicator,
                )
                metrics_list.append(metric)

                # Add evidence reference
                ref_id = ref_allocator.next_ref()
                evidence_references[ref_id] = {
                    "description": f"Last {subsystem} artifact timestamp and count",
                    "section": "subsystem_metrics",
                    "subsystem": subsystem,
                }

                logger.debug(
                    f"Metrics collector: {subsystem} - "
                    f"last_at={last_artifact_at}, count={count}, indicator={freshness_indicator}"
                )

            except Exception as e:
                logger.error(f"Metrics collector failed for {subsystem}: {e}", exc_info=True)
                raise

        # Write to Evidence Pack
        await store.update_evidence_pack_section(
            pack_id,
            {
                "subsystem_metrics": [m.model_dump() for m in metrics_list],
                "subsystem_metrics_collected_at": datetime.utcnow(),
                "evidence_references": evidence_references,
            },
        )

        logger.info(
            f"MetricsCollector: collected metrics for {len(metrics_list)} subsystems"
        )
