"""BugOps monitor entrypoint."""

import asyncio
import logging
import os
import signal
import sys
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

        self.settings = get_bugops_settings()
        self.store = None
        self.signal_sources: List["SignalSource"] = [
            LLMTraceCostSignalSource(),
            RailwayLogSignalSource(),
        ]
        self.running = False

    async def run(self) -> None:
        """Run the BugOps monitor loop."""
        from .slack import send_case_notification
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
                    if is_new:
                        await send_case_notification(case)
            except Exception as e:
                logger.error(
                    f"Error collecting signals from {source.source_type}: {e}",
                    exc_info=True
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
