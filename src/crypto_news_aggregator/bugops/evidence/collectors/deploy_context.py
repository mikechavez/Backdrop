"""DeployContextCollector for collecting deployment history from Railway."""

import logging
from datetime import datetime, timedelta

from ...clients.railway import RailwayClient
from ...models import BugCase, EvidenceReferenceAllocator
from ...store import BugOpsStore
from ..base import EvidenceCollectorBase

logger = logging.getLogger(__name__)


class DeployContextCollector:
    """Collects deployment context from Railway for all services."""

    collector_name = "deploy_context"
    SERVICES = ["fastapi", "celery_worker", "celery_scheduler"]
    LOOKBACK_HOURS = 24

    def __init__(self, railway_client: RailwayClient):
        self.railway = railway_client

    async def collect(
        self,
        bugcase: BugCase,
        pack_id: str,
        store: BugOpsStore,
        ref_allocator: EvidenceReferenceAllocator,
    ) -> None:
        """
        Collect deployment context from Railway.

        Fetches recent deployments for all three services within 24 hours
        before the incident first_seen_at. Records absence of deployments
        explicitly as evidence.

        Args:
            bugcase: The BugCase being investigated
            pack_id: The Evidence Pack ID to write to
            store: BugOpsStore instance for persisting evidence
            ref_allocator: Allocator for collision-free reference IDs
        """
        window_start = bugcase.first_seen_at - timedelta(hours=self.LOOKBACK_HOURS)

        all_deployments = []
        sections_missing = []

        for service in self.SERVICES:
            try:
                deployments = await self.railway.get_recent_deployments(
                    service_name=service,
                    since=window_start,
                )
                # Add service name to each deployment dict
                for d in deployments:
                    d["service"] = service
                all_deployments.extend(deployments)
            except Exception as e:
                sections_missing.append({
                    "section": f"deploy_context.{service}",
                    "reason": f"Railway API error: {type(e).__name__}: {str(e)[:100]}",
                    "attempted_at": datetime.utcnow().isoformat(),
                })
                logger.warning(
                    f"DeployContextCollector failed for {service}: {e}",
                    exc_info=True,
                )

        # Sort by created_at descending (most recent first)
        all_deployments.sort(
            key=lambda d: d.get("created_at", ""),
            reverse=True,
        )

        # Evidence reference — absence of deployments is itself evidence
        ref_id = ref_allocator.next_ref()
        ref_description = (
            f"No deployments in 24h preceding incident across {', '.join(self.SERVICES)}"
            if not all_deployments
            else f"{len(all_deployments)} deployments in 24h window preceding incident"
        )

        section_data = {
            "deploy_context": all_deployments,
            "deploy_context_collected_at": datetime.utcnow(),
            "evidence_references": {
                ref_id: {
                    "description": ref_description,
                    "section": "deploy_context",
                }
            },
        }

        if sections_missing:
            section_data["sections_missing"] = sections_missing

        await store.update_evidence_pack_section(pack_id, section_data)

        logger.info(
            f"DeployContextCollector: collected {len(all_deployments)} deployments "
            f"across {len(self.SERVICES)} services"
        )
