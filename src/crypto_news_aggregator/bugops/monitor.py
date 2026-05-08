"""BugOps monitor entrypoint."""

import asyncio
import logging
import signal
import sys
from typing import List

from .config import get_bugops_settings
from .store import BugOpsStore
from .signal_sources.base import SignalSource
from .signal_sources.llm_traces import LLMTraceSignalSource
from .signal_sources.railway_logs import RailwayLogSignalSource
from ..db.mongodb import mongo_manager

logger = logging.getLogger(__name__)


class BugOpsMonitor:
    """Independent BugOps monitoring service."""

    def __init__(self):
        self.settings = get_bugops_settings()
        self.store = None
        self.signal_sources: List[SignalSource] = [
            LLMTraceSignalSource(),
            RailwayLogSignalSource(),
        ]
        self.running = False

    async def run(self) -> None:
        """Run the BugOps monitor loop."""
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
            db = await mongo_manager.get_database()
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
                    await self.store.create_alert_event(event)
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
