"""Daily digest Celery task."""

import asyncio
import logging
import time

from celery import shared_task

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run async code with proper event loop handling for Celery workers."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        asyncio.set_event_loop(None)
        loop.close()


async def _send_daily_digest_async():
    """Build and send daily pipeline health digest to Slack."""
    from crypto_news_aggregator.core.config import get_settings
    from crypto_news_aggregator.db.mongodb import mongo_manager
    from crypto_news_aggregator.services.daily_digest import (
        build_digest,
        format_slack_message,
        send_to_slack,
    )

    start_time = time.time()
    settings = get_settings()

    if not settings.SLACK_WEBHOOK_URL:
        logger.warning("SLACK_WEBHOOK_URL not set, skipping daily digest")
        return

    try:
        db = await mongo_manager.get_async_database()
        digest = await build_digest(db)
        message = format_slack_message(digest)
        success = await send_to_slack(settings.SLACK_WEBHOOK_URL, message)

        duration = time.time() - start_time

        if success:
            logger.info(
                f"Daily digest sent in {duration:.2f}s: {digest['article_count_24h']} articles, "
                f"{digest['briefing_count_24h']} briefings, storage: {digest['storage_mb']} MB"
            )
        else:
            logger.error(f"Failed to send daily digest to Slack (took {duration:.2f}s)")

    except Exception as e:
        duration = time.time() - start_time
        logger.exception(f"Error building/sending daily digest (took {duration:.2f}s): {e}")


@shared_task(name="send_daily_digest", ignore_result=True)
def send_daily_digest_task():
    """Build and send daily pipeline health digest to Slack.

    Scheduled to run at 9:00 AM EST via Celery Beat.
    """
    return _run_async(_send_daily_digest_async())
