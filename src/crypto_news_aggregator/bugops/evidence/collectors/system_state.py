"""SystemStateCollector for system health and pipeline status."""

import logging
import httpx
from datetime import datetime
from typing import Optional

from ...models import BugCase, EvidenceReferenceAllocator
from ...store import BugOpsStore
from ..base import EvidenceCollectorBase
from ....core.config import get_settings

logger = logging.getLogger(__name__)


class SystemStateCollector:
    """Collects system state from /api/v1/health endpoint."""

    collector_name = "system_state"

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
        Collect system state from the health endpoint.

        Calls GET /api/v1/health to retrieve:
        - MongoDB and Redis connectivity status
        - LLM gateway status
        - Pipeline heartbeat status

        Derives healthy_signals list from passing checks.
        Records Celery worker/scheduler as sections_missing (not available until TASK-119).

        Args:
            bugcase: The BugCase being investigated
            pack_id: The Evidence Pack ID to write to
            store: BugOpsStore instance for persisting evidence
            ref_allocator: Allocator for collision-free reference IDs
        """
        health_endpoint = f"{self.settings.BUGOPS_HEALTH_ENDPOINT_URL}/api/v1/health"
        system_state = {}
        healthy_signals = []
        sections_missing_entries = []

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(health_endpoint, timeout=10.0)
                response.raise_for_status()
                health_data = response.json()

                # Extract checks from response
                checks = health_data.get("checks", {})

                # Copy the entire checks dict to system_state
                system_state = checks

                # Database check
                if "database" in checks:
                    db_check = checks["database"]
                    if db_check.get("status") in ("ok", "healthy"):
                        latency = db_check.get("latency_ms", "unknown")
                        healthy_signals.append(f"MongoDB reachable ({latency}ms)")

                # Redis check
                if "redis" in checks:
                    redis_check = checks["redis"]
                    if redis_check.get("status") in ("ok", "healthy"):
                        latency = redis_check.get("latency_ms", "unknown")
                        healthy_signals.append(f"Redis reachable ({latency}ms)")

                # LLM check
                if "llm" in checks:
                    llm_check = checks["llm"]
                    if llm_check.get("status") in ("ok", "healthy"):
                        healthy_signals.append("LLM gateway healthy")

                # Pipeline checks
                if "pipeline" in checks:
                    pipeline_checks = checks["pipeline"]

                    # fetch_news check
                    if "fetch_news" in pipeline_checks:
                        fetch_check = pipeline_checks["fetch_news"]
                        if fetch_check.get("status") in ("ok", "healthy"):
                            healthy_signals.append("RSS fetch pipeline healthy")

                    # generate_briefing check
                    if "generate_briefing" in pipeline_checks:
                        briefing_check = pipeline_checks["generate_briefing"]
                        if briefing_check.get("status") in ("ok", "healthy"):
                            healthy_signals.append("Briefing pipeline healthy")

                # FastAPI overall status (from top-level status field if available)
                if "status" in health_data and health_data["status"] == "healthy":
                    healthy_signals.append("FastAPI healthy")

                logger.debug(f"System state collected: {len(healthy_signals)} healthy signals")

        except httpx.TimeoutException as e:
            logger.warning(f"Health endpoint timeout: {e}")
            sections_missing_entries.append(
                {
                    "section": "system_state",
                    "reason": "Health endpoint timeout",
                    "attempted_at": datetime.utcnow().isoformat(),
                }
            )
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if hasattr(e, 'response') and e.response else "unknown"
            logger.warning(f"Health endpoint HTTP error: {status_code}")
            sections_missing_entries.append(
                {
                    "section": "system_state",
                    "reason": f"Health endpoint returned {status_code}",
                    "attempted_at": datetime.utcnow().isoformat(),
                }
            )
        except Exception as e:
            logger.warning(f"Failed to collect system state: {e}")
            sections_missing_entries.append(
                {
                    "section": "system_state",
                    "reason": f"Error calling health endpoint: {str(e)[:100]}",
                    "attempted_at": datetime.utcnow().isoformat(),
                }
            )

        # Always record Celery worker and scheduler as sections_missing
        # (not available until TASK-119 when Railway API client is ready)
        sections_missing_entries.extend(
            [
                {
                    "section": "system_state.celery_worker",
                    "reason": "Railway client not available until TASK-119; worker status deferred",
                    "attempted_at": datetime.utcnow().isoformat(),
                },
                {
                    "section": "system_state.celery_scheduler",
                    "reason": "Railway client not available until TASK-119; scheduler status deferred",
                    "attempted_at": datetime.utcnow().isoformat(),
                },
            ]
        )

        # Build update payload
        update_payload = {
            "system_state": system_state,
            "system_state_collected_at": datetime.utcnow(),
            "healthy_signals": healthy_signals,
        }

        # Add sections_missing entries if any
        if sections_missing_entries:
            update_payload["sections_missing"] = sections_missing_entries

        # Add evidence reference
        ref_id = ref_allocator.next_ref()
        evidence_references = {
            ref_id: {
                "description": "System state at collection time — MongoDB, Redis, FastAPI, pipeline heartbeats",
                "section": "system_state",
                "field": "checks",
            }
        }
        update_payload["evidence_references"] = evidence_references

        # Write to Evidence Pack
        await store.update_evidence_pack_section(pack_id, update_payload)

        logger.info(
            f"SystemStateCollector: collected with {len(healthy_signals)} healthy signals"
        )
