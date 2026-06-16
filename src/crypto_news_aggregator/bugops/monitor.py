"""BugOps monitor entrypoint."""

import asyncio
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .signal_sources.base import SignalSource

logger = logging.getLogger(__name__)


def _is_bugops_enabled_from_env() -> bool:
    """Check if BugOps is enabled via environment variable."""
    return os.getenv("BUGOPS_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


class BugOpsMonitor:
    """Independent BugOps monitoring service."""

    def __init__(self):
        # Import heavy settings only after enabled check is confirmed at process entry
        from .config import get_bugops_settings
        from .store import BugOpsStore
        from .signal_sources.llm_traces import LLMTraceCostSignalSource
        from .signal_sources.railway_logs import RailwayLogSignalSource
        from .signal_sources.article_freshness import ArticleFreshnessSignalSource
        from .signal_sources.signal_freshness import SignalFreshnessSignalSource
        from .signal_sources.narrative_freshness import NarrativeFreshnessSignalSource
        from .signal_sources.briefing_freshness import BriefingFreshnessSignalSource
        from .dependency_graph import DependencyGraph

        self.settings = get_bugops_settings()
        self.store = None
        self.signal_sources: List["SignalSource"] = [
            LLMTraceCostSignalSource(),
            RailwayLogSignalSource(),
        ]
        self.dependency_graph = DependencyGraph()
        self.freshness_detectors = [
            ArticleFreshnessSignalSource(),
            SignalFreshnessSignalSource(),
            NarrativeFreshnessSignalSource(),
            BriefingFreshnessSignalSource(),
        ]
        self.detector_by_subsystem = {d.root_subsystem: d for d in self.freshness_detectors}
        self.is_first_poll = True
        self.running = False

    async def run(self) -> None:
        """Run the BugOps monitor loop."""
        from .store import BugOpsStore
        from ..db.mongodb import mongo_manager

        logger.info("BugOps monitor starting")

        if not self.settings.BUGOPS_ENABLED:
            logger.info("BugOps is disabled (BUGOPS_ENABLED=false)")
            return

        try:
            # Initialize Mongo connection
            success = await mongo_manager.initialize()
            if not success:
                logger.error("Failed to initialize MongoDB connection")
                return

            logger.info("MongoDB connection initialized")
            db = await mongo_manager.get_async_database()
            self.store = BugOpsStore(db)

            logger.info(
                f"BugOps monitor running with poll interval: {self.settings.BUGOPS_POLL_INTERVAL_SECONDS}s"
            )

            self.running = True
            while self.running:
                await self._poll_signals()
                await self._poll_freshness_detectors()
                await self._run_auto_resolution()
                await asyncio.sleep(self.settings.BUGOPS_POLL_INTERVAL_SECONDS)

        except Exception as e:
            logger.error(f"BugOps monitor error: {e}", exc_info=True)
            raise
        finally:
            logger.info("BugOps monitor shutting down")
            await mongo_manager.aclose()

    async def _poll_signals(self) -> None:
        """Collect signals from all sources."""
        for source in self.signal_sources:
            try:
                events = await source.collect()
                for event in events:
                    case, is_new = await self.store.process_alert_event(event)
                    if is_new and self.settings.BUGOPS_SLACK_ENABLED:
                        try:
                            from .slack import send_case_notification

                            sent = await send_case_notification(case)
                            if not sent:
                                logger.warning(
                                    f"BugOps Slack notification was not sent for case_id={case.case_id}"
                                )
                        except Exception:
                            logger.exception(
                                f"BugOps Slack notification failed for case_id={case.case_id}"
                            )
            except Exception as e:
                logger.error(
                    f"Error collecting signals from {source.source_type}: {e}",
                    exc_info=True
                )

    async def _poll_freshness_detectors(self) -> None:
        """Poll freshness detectors with cascade suppression.

        Processing order (deterministic):
        1. Detector observes failure condition
        2. Check for open upstream BugCase → attach if found
        3. Check for open BugCase with same dedupe_key → attach if found
        4. Create new BugCase

        Notification sending deferred to TASK-111 to preserve separation of responsibilities.
        """
        from ..db.mongodb import mongo_manager
        from .models import BugCaseCreate
        from .signal_sources.severity import DETECTOR_SEVERITY

        db = await mongo_manager.get_async_database()
        now = datetime.utcnow()

        for detector in self.freshness_detectors:
            start = time.monotonic()
            try:
                failure = await detector.check_failure(db)
                if not failure:
                    continue

                # Step 2: Check for open upstream BugCase
                upstream_nodes = self.dependency_graph.get_upstream_nodes(
                    detector.root_subsystem
                )
                upstream_case = None
                for node in upstream_nodes:
                    upstream_case = await self.store.find_open_case_by_root_subsystem(node)
                    if upstream_case:
                        break

                if upstream_case:
                    await self.store.attach_observation_to_case(
                        upstream_case.case_id,
                        last_seen_at=now,
                        affected_subsystems=[detector.root_subsystem],
                    )
                    logger.info(
                        "Cascade suppression: attached to upstream case",
                        extra={
                            "detector": detector.source_type,
                            "upstream_case_id": upstream_case.case_id,
                            "upstream_subsystem": upstream_case.root_subsystem,
                        }
                    )
                    continue

                # Step 3: Check for open BugCase with same dedupe_key
                existing = await self.store.find_open_case_by_dedupe_key(
                    detector.dedupe_key
                )
                if existing:
                    await self.store.attach_observation_to_case(
                        existing.case_id, last_seen_at=now
                    )
                    logger.info(
                        "Case idempotency: attached to existing case",
                        extra={
                            "detector": detector.source_type,
                            "case_id": existing.case_id,
                            "dedupe_key": detector.dedupe_key,
                        }
                    )
                    continue

                # Step 4: Create new BugCase
                detection_type = "startup" if self.is_first_poll else "runtime"
                blast_radius = self.dependency_graph.get_downstream_nodes(
                    detector.root_subsystem
                )
                case_create = BugCaseCreate(
                    case_id=f"bc_{detector.root_subsystem}_{int(now.timestamp())}",
                    severity=DETECTOR_SEVERITY[detector.source_type],
                    alert_type=detector.source_type,
                    title=f"{detector.root_subsystem.capitalize()} Freshness Failure",
                    summary=f"No {detector.root_subsystem} output within expected window.",
                    dedupe_key=detector.dedupe_key,
                    source_types=[detector.source_type],
                    root_subsystem=detector.root_subsystem,
                    blast_radius=blast_radius,
                    affected_subsystems=[],
                    first_seen_at=now,
                    last_seen_at=now,
                    observation_count=1,
                    detection_type=detection_type,
                    suggested_manual_check=detector.suggested_manual_check,
                )
                new_case = await self.store.create_case_direct(case_create)
                logger.info(
                    "New BugCase created from freshness detector",
                    extra={
                        "detector": detector.source_type,
                        "case_id": new_case.case_id,
                        "detection_type": detection_type,
                        "root_subsystem": detector.root_subsystem,
                    }
                )

            except Exception as e:
                duration_ms = int((time.monotonic() - start) * 1000)
                logger.error(
                    "Detector run failed",
                    extra={
                        "detector_name": detector.__class__.__name__,
                        "detector_source_type": detector.source_type,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "duration_ms": duration_ms,
                    }
                )

        # After first complete poll, set is_first_poll = False
        self.is_first_poll = False

    async def _run_auto_resolution(self) -> None:
        """Auto-resolve BugCases when recovery conditions are met and Recovery Window elapses."""
        from ..db.mongodb import mongo_manager
        from .models import CaseStatus

        db = await mongo_manager.get_async_database()
        now = datetime.utcnow()
        recovery_window = timedelta(minutes=self.settings.BUGOPS_RECOVERY_WINDOW_MINUTES)

        open_cases = await self.store.get_open_freshness_cases()

        for case in open_cases:
            # Skip manually closed cases (terminal state)
            if case.status == CaseStatus.CLOSED:
                continue

            # Find the right detector
            detector = self.detector_by_subsystem.get(case.root_subsystem)
            if detector is None:
                logger.warning(f"No detector found for root_subsystem={case.root_subsystem}")
                continue

            try:
                recovered = await detector.check_recovery(db)
            except Exception as e:
                logger.error(f"Recovery check failed for case {case.case_id}: {e}")
                continue

            if recovered:
                if case.recovery_candidate_at is None:
                    # First healthy observation
                    await self.store.update_recovery_candidate(case.case_id, now)
                else:
                    elapsed = now - case.recovery_candidate_at
                    if elapsed >= recovery_window:
                        # Window elapsed — resolve
                        await self.store.resolve_case(case.case_id)
                        logger.info(f"BugCase auto-resolved: case_id={case.case_id}")
                        # No Slack notification on resolution
            else:
                if case.recovery_candidate_at is not None:
                    # Failure recurred before window elapsed
                    await self.store.update_recovery_candidate(case.case_id, None)
                    logger.info(
                        f"Recovery candidate cleared (failure recurred): case_id={case.case_id}"
                    )

    def stop(self) -> None:
        """Stop the monitor gracefully."""
        logger.info("BugOps monitor stop signal received")
        self.running = False


def signal_handler(signum: int, frame) -> None:
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}")
    sys.exit(0)


async def main() -> None:
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Early disabled-mode check: exit cleanly before any heavy imports
    if not _is_bugops_enabled_from_env():
        logger.info("BugOps is disabled (BUGOPS_ENABLED=false)")
        return

    monitor = BugOpsMonitor()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        await monitor.run()
    except KeyboardInterrupt:
        logger.info("BugOps monitor interrupted by user")
    except Exception as e:
        logger.error(f"BugOps monitor failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
