"""Tasks for fetching news from various sources."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, AsyncGenerator, Any

from celery import shared_task
from celery.utils.log import get_task_logger

from ..core.config import get_settings
from ..core.news_sources import create_source, get_available_sources
from ..services.article_service import ArticleService, get_article_service

logger = get_task_logger(__name__)
# settings = get_settings()  # Removed top-level settings; use lazy initialization in functions as needed.


async def fetch_articles_from_source(
    source_id: str,
    article_service: ArticleService,
    max_articles: int = 20,
    since: Optional[datetime] = None,
) -> int:
    """Fetch articles from a single news source.

    Args:
        source_id: ID of the news source to fetch from
        article_service: Article service for saving articles
        max_articles: Maximum number of articles to fetch
        since: Only fetch articles newer than this datetime

    Returns:
        Number of new articles fetched and saved
    """
    if since is None:
        settings = get_settings()
        since = datetime.now(timezone.utc) - timedelta(
            days=settings.MAX_ARTICLE_AGE_DAYS
        )

    logger.info(
        f"Fetching up to {max_articles} articles from {source_id} since {since}"
    )

    try:
        settings = get_settings()
        # Create the source instance
        source = create_source(
            source_id,
            **{"api_key": getattr(settings, f"{source_id.upper()}_API_KEY", None)},
        )

        # Fetch and process articles
        count = 0
        async with source:
            async for article in source.fetch_articles(since=since, limit=max_articles):
                # Skip articles that are too short
                if len(article.get("content", "")) < settings.MIN_ARTICLE_LENGTH:
                    logger.debug(f"Skipping short article: {article.get('title')}")
                    continue

                # Save the article
                await article_service.create_or_update_article(article)
                count += 1

                if count >= max_articles:
                    break

        logger.info(f"Fetched {count} new articles from {source_id}")
        return count

    except Exception as e:
        logger.error(f"Error fetching from {source_id}: {str(e)}", exc_info=True)
        raise


@shared_task(
    bind=True,
    name="fetch_news_source_based",
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
    soft_time_limit=600,  # 10 minutes
    time_limit=660,  # 11 minutes (slightly more than soft_time_limit)
)
def fetch_news(self, source_id: Optional[str] = None) -> Dict[str, Any]:
    """Fetch news from one or all enabled sources (NewsSource/ArticleService path).

    NOT the canonical production ingestion path (see BUG-110). Production RSS
    ingestion runs via the FastAPI lifespan's asyncio schedule, which calls
    ``background.rss_fetcher.fetch_and_process_rss_feeds``. This task is not
    referenced by any Celery Beat schedule entry.

    Previously this task and ``tasks.news.fetch_news`` both registered under
    the Celery task name "fetch_news", silently shadowing one another in the
    task registry depending on import order. Renamed to disambiguate.

    Args:
        source_id: Optional source ID to fetch from. If None, fetches from all enabled sources.

    Returns:
        Dict containing status and results for each source
    """
    task_id = self.request.id
    logger.info(f"Starting news fetch task {task_id} for source: {source_id or 'all'}")

    article_service = get_article_service()
    settings = get_settings()
    results = {}

    try:
        # Determine which sources to fetch from
        if source_id:
            sources = [source_id]
        else:
            sources = settings.ENABLED_NEWS_SOURCES

        # Fetch from each source
        for src in sources:
            try:
                count = asyncio.run(fetch_articles_from_source(
                    source_id=src,
                    article_service=article_service,
                    max_articles=settings.MAX_ARTICLES_PER_SOURCE,
                    since=datetime.now(timezone.utc)
                    - timedelta(days=settings.MAX_ARTICLE_AGE_DAYS),
                ))
                results[src] = {"status": "success", "articles_fetched": count}
            except Exception as e:
                logger.error(f"Failed to fetch from {src}: {str(e)}", exc_info=True)
                results[src] = {"status": "error", "error": str(e)}

        return {"status": "completed", "task_id": task_id, "results": results}

    except Exception as e:
        logger.error(f"News fetch task {task_id} failed: {str(e)}", exc_info=True)
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** (self.request.retries - 1)))
