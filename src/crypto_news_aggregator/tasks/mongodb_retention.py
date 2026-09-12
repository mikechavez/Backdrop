"""Scheduled/manual MongoDB retention maintenance task."""

import asyncio
import logging

from celery import shared_task

from ..core.config import get_settings
from ..db.mongodb import mongo_manager
from ..services.mongodb_retention import run_retention_cleanup

logger = logging.getLogger(__name__)


@shared_task(name="mongodb_retention_cleanup")
def cleanup_mongodb_retention(dry_run: bool = True, confirm: bool = False) -> dict:
    """Clean one bounded batch per collection; manual destructive runs require confirm=True."""
    if not dry_run and not confirm:
        raise ValueError("Destructive cleanup requires confirm=True; dry_run defaults to True")

    async def run() -> dict:
        await mongo_manager.initialize()
        db = await mongo_manager.get_async_database()
        return await run_retention_cleanup(db, get_settings(), dry_run=dry_run)

    result = asyncio.run(run())
    logger.info("Mongo retention task complete dry_run=%s", dry_run)
    return result
