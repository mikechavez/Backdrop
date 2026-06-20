"""ConfigEvidenceCollector for incident-relevant configuration values."""

import logging
from datetime import datetime
from types import ModuleType

from ...models import BugCase, EvidenceReferenceAllocator
from ...store import BugOpsStore
from ..base import EvidenceCollectorBase

logger = logging.getLogger(__name__)


class ConfigEvidenceCollector:
    """Collects incident-relevant configuration values."""

    collector_name = "config_evidence"

    def __init__(self, settings, cost_tracker_module: ModuleType):
        """
        Initialize the collector.

        Args:
            settings: The get_settings() instance
            cost_tracker_module: Imported cost_tracker module for reading CRITICAL_OPERATIONS
        """
        self.settings = settings
        self.cost_tracker = cost_tracker_module

    async def collect(
        self,
        bugcase: BugCase,
        pack_id: str,
        store: BugOpsStore,
        ref_allocator: EvidenceReferenceAllocator,
    ) -> None:
        """
        Collect configuration evidence for the Evidence Pack.

        Gathers LLM budget settings, CRITICAL_OPERATIONS list, and BugOps
        thresholds from configuration. This is deterministic — no Railway API,
        no database queries, no LLM calls.

        Args:
            bugcase: The BugCase being investigated
            pack_id: The Evidence Pack ID to write to
            store: BugOpsStore instance for persisting evidence
            ref_allocator: Allocator for collision-free reference IDs
        """
        config = {
            "llm_daily_soft_limit": getattr(self.settings, "LLM_DAILY_SOFT_LIMIT", None),
            "llm_daily_hard_limit": getattr(self.settings, "LLM_DAILY_HARD_LIMIT", None),
            "critical_operations": sorted(
                list(getattr(self.cost_tracker, "CRITICAL_OPERATIONS", set()))
            ),
            "bugops_thresholds": {
                "article_freshness_window_minutes": getattr(
                    self.settings, "BUGOPS_ARTICLE_FRESHNESS_WINDOW_MINUTES", None
                ),
                "signal_freshness_window_minutes": getattr(
                    self.settings, "BUGOPS_SIGNAL_FRESHNESS_WINDOW_MINUTES", None
                ),
                "narrative_freshness_window_minutes": getattr(
                    self.settings, "BUGOPS_NARRATIVE_FRESHNESS_WINDOW_MINUTES", None
                ),
                "recovery_window_minutes": getattr(
                    self.settings, "BUGOPS_RECOVERY_WINDOW_MINUTES", None
                ),
                "evidence_settling_window_minutes": getattr(
                    self.settings, "BUGOPS_EVIDENCE_SETTLING_WINDOW_MINUTES", None
                ),
            },
            "investigation_config": {
                "investigation_model": getattr(
                    self.settings, "BUGOPS_INVESTIGATION_MODEL", None
                ),
                "investigation_max_input_tokens": getattr(
                    self.settings, "BUGOPS_INVESTIGATION_MAX_INPUT_TOKENS", None
                ),
                "evidence_max_total_chars": getattr(
                    self.settings, "BUGOPS_EVIDENCE_MAX_TOTAL_CHARS", None
                ),
            },
        }

        # Add two evidence references:
        # One for budget threshold (relevant to cost-control failures like BUG-064)
        # One for critical_operations list (relevant to operation classification failures)
        ref_budget = ref_allocator.next_ref()
        ref_ops = ref_allocator.next_ref()

        evidence_references = {
            ref_budget: {
                "description": f"LLM daily soft limit: {config['llm_daily_soft_limit']}",
                "section": "config_evidence",
                "field": "llm_daily_soft_limit",
            },
            ref_ops: {
                "description": f"Critical operations list: {config['critical_operations']}",
                "section": "config_evidence",
                "field": "critical_operations",
            },
        }

        await store.update_evidence_pack_section(
            pack_id,
            {
                "config_evidence": config,
                "config_evidence_collected_at": datetime.utcnow(),
                "evidence_references": evidence_references,
            },
        )

        logger.info("ConfigEvidenceCollector: collected configuration evidence")
