"""RelatedCaseCollector for finding related BugCases."""

import logging
from datetime import datetime, timedelta

from ...models import BugCase, EvidenceReferenceAllocator
from ...store import BugOpsStore
from ..base import EvidenceCollectorBase

logger = logging.getLogger(__name__)


class RelatedCaseCollector:
    """Collects related BugCases that share subsystems with the current case."""

    collector_name = "related_cases"

    async def collect(
        self,
        bugcase: BugCase,
        pack_id: str,
        store: BugOpsStore,
        ref_allocator: EvidenceReferenceAllocator,
    ) -> None:
        """
        Collect related BugCases for the Evidence Pack.

        Finds cases sharing subsystems within a 7-day lookback window and stores
        a summary of each related case as evidence.

        Args:
            bugcase: The BugCase being investigated
            pack_id: The Evidence Pack ID to write to
            store: BugOpsStore instance for persisting evidence
            ref_allocator: Allocator for collision-free reference IDs
        """
        # Build list of subsystems to search for
        subsystems = list(
            set(
                ([bugcase.root_subsystem] if bugcase.root_subsystem else [])
                + (bugcase.blast_radius or [])
                + (bugcase.affected_subsystems or [])
            )
        )

        try:
            # Query for related cases
            related = await store.get_related_cases(
                bugcase_id=bugcase.case_id,
                subsystems=subsystems,
                lookback_days=7,
                limit=10,
            )

            # Convert BugCase objects to dicts with selected fields
            related_dicts = [
                {
                    "case_id": c.case_id,
                    "root_subsystem": c.root_subsystem,
                    "severity": c.severity,
                    "status": c.status,
                    "first_seen_at": c.first_seen_at.isoformat() if c.first_seen_at else None,
                    "last_seen_at": c.last_seen_at.isoformat() if c.last_seen_at else None,
                    "title": c.title,
                }
                for c in related
            ]

            section_data = {
                "related_cases": related_dicts,
                "related_cases_collected_at": datetime.utcnow(),
            }

            # Add evidence reference only if related cases found
            if related:
                ref_id = ref_allocator.next_ref()
                section_data["evidence_references"] = {
                    ref_id: {
                        "description": f"{len(related)} related BugCases sharing subsystems in past 7 days",
                        "section": "related_cases",
                    }
                }

            await store.update_evidence_pack_section(pack_id, section_data)

            logger.info(
                f"RelatedCaseCollector: found {len(related)} related cases "
                f"for {len(subsystems)} subsystems"
            )

        except Exception as e:
            logger.warning(f"RelatedCaseCollector failed: {e}", exc_info=True)
            # Do NOT raise — collectors must handle errors internally
