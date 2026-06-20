"""Evidence collection orchestrator."""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional
from ..models import (
    BugCase,
    CaseStatus,
    AlertSeverity,
    CollectionError,
    EvidencePackCreate,
    EvidencePack,
    EvidenceReferenceAllocator,
)
from ..store import BugOpsStore
from .base import EvidenceCollectorBase
from .collectors.metrics import MetricsCollector
from .collectors.system_state import SystemStateCollector
from .collectors.related_cases import RelatedCaseCollector
from .collectors.deploy_context import DeployContextCollector
from .collectors.config_evidence import ConfigEvidenceCollector

logger = logging.getLogger(__name__)


class EvidenceCollector:
    """
    Orchestrates evidence collection for a BugCase.

    Creates an Evidence Pack, runs all registered collectors in isolation,
    and marks the pack complete. One failure does not halt other collectors.
    """

    def __init__(self, store: BugOpsStore, settings):
        """Initialize with store and settings."""
        self.store = store
        self.settings = settings
        self.collectors: list[EvidenceCollectorBase] = []

        # Import RailwayClient for DeployContextCollector
        from ..clients.railway import RailwayClient
        from ...services import cost_tracker

        # Register built-in collectors
        self.register_collector(MetricsCollector())
        self.register_collector(SystemStateCollector())
        self.register_collector(RelatedCaseCollector())
        self.register_collector(DeployContextCollector(RailwayClient(settings)))
        self.register_collector(ConfigEvidenceCollector(settings, cost_tracker))

    def register_collector(self, collector: EvidenceCollectorBase) -> None:
        """Register a collector. Called during monitor initialization."""
        self.collectors.append(collector)

    async def is_eligible(self, bugcase: BugCase) -> bool:
        """
        Check if a BugCase is eligible for evidence collection.

        Eligible when:
        - Status is NOT manually closed (CaseStatus.CLOSED)
        - No Evidence Pack already attached
        - Settling window has elapsed since first_seen_at OR severity is Critical

        Resolved BugCases ARE eligible if they have no Evidence Pack and the
        settling window has elapsed. Short-lived failures that auto-resolved
        still need Evidence Packs for the operational corpus.
        Only CaseStatus.CLOSED excludes a case.
        """
        # Manually closed cases never eligible
        if bugcase.status == CaseStatus.CLOSED:
            return False

        # Check if Evidence Pack already exists for this case
        existing_pack = await self.store.get_evidence_pack_for_case(bugcase.case_id)
        if existing_pack is not None:
            return False

        # Check settling window
        if not self._is_settling_window_elapsed(bugcase):
            return False

        return True

    async def collect(self, bugcase: BugCase) -> Optional[EvidencePack]:
        """
        Main entry point for evidence collection.

        Creates Evidence Pack, runs all registered collectors,
        marks complete. Returns completed EvidencePack or None if not eligible.

        Rules:
        - Check eligibility first. Return None if not eligible.
        - Create Evidence Pack immediately on eligibility confirmation.
        - Create one EvidenceReferenceAllocator per collection cycle.
        - Run each collector in sequence inside independent try/except.
        - Record CollectionError for any collector that raises.
        - Call store.mark_evidence_pack_complete() after all collectors run.
        - Never raise — log errors and return partial pack.
        """
        # Check eligibility
        if not await self.is_eligible(bugcase):
            return None

        # Create Evidence Pack immediately with snapshot from BugCase
        pack_id = self._generate_pack_id(bugcase.case_id)
        pack_create = EvidencePackCreate(
            pack_id=pack_id,
            bugcase_id=bugcase.case_id,
            incident_first_seen_at=bugcase.first_seen_at,
            incident_last_seen_at=bugcase.last_seen_at,
            root_subsystem=bugcase.root_subsystem,
            severity=bugcase.severity,
            blast_radius=bugcase.blast_radius,
            primary_signal=bugcase.summary,
        )
        pack = await self.store.create_evidence_pack(pack_create)
        logger.info(f"Created Evidence Pack {pack_id} for case {bugcase.case_id}")

        # Track collection timing and results
        collection_start = time.time()
        ref_allocator = EvidenceReferenceAllocator()
        sections_collected: list[str] = []
        collection_errors: list[dict] = []

        # Run each collector in isolation
        for collector in self.collectors:
            try:
                logger.debug(f"Running collector: {collector.collector_name}")
                await collector.collect(bugcase, pack_id, self.store, ref_allocator)
                sections_collected.append(collector.collector_name)
                logger.debug(f"Collector {collector.collector_name} completed")
            except Exception as e:
                error = CollectionError(
                    source=collector.collector_name,
                    error_type=type(e).__name__,
                    error_message=str(e)[:200],
                )
                collection_errors.append(error.model_dump())
                logger.error(
                    f"EvidenceCollector: {collector.collector_name} failed: {e}",
                    exc_info=True,
                )

        # Record all collected errors to Evidence Pack after all collectors have run
        if collection_errors:
            await self.store.update_evidence_pack_section(
                pack_id,
                {"collection_errors": collection_errors},
            )

        # Mark pack complete
        collection_duration_ms = int((time.time() - collection_start) * 1000)
        completed_pack = await self.store.mark_evidence_pack_complete(
            pack_id=pack_id,
            collection_completed_at=datetime.utcnow(),
            collection_duration_ms=collection_duration_ms,
            sections_collected=sections_collected,
            total_chars=0,  # Calculated by collectors or truncation logic
        )

        logger.info(
            f"Evidence Pack {pack_id} collection complete: "
            f"{len(sections_collected)} sections, "
            f"{len(collection_errors)} errors, "
            f"{collection_duration_ms}ms"
        )

        return completed_pack

    def _is_settling_window_elapsed(self, bugcase: BugCase) -> bool:
        """
        Check if settling window has elapsed or if severity is Critical.

        Returns True if:
        - Severity is CRITICAL (collect immediately), OR
        - BUGOPS_EVIDENCE_SETTLING_WINDOW_MINUTES have elapsed since first_seen_at
        """
        if bugcase.severity == AlertSeverity.CRITICAL:
            return True

        if bugcase.first_seen_at is None:
            return False

        settling_minutes = self.settings.BUGOPS_EVIDENCE_SETTLING_WINDOW_MINUTES
        elapsed = datetime.utcnow() - bugcase.first_seen_at
        return elapsed >= timedelta(minutes=settling_minutes)

    def _generate_pack_id(self, bugcase_id: str) -> str:
        """Generate unique pack_id: ep_{bugcase_id}_{unix_timestamp}."""
        timestamp = int(datetime.utcnow().timestamp())
        return f"ep_{bugcase_id}_{timestamp}"
