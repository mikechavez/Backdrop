"""Celery tasks for news collection and processing."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple

from celery import shared_task

from ..core.news_collector import NewsCollector
from ..core.config import get_settings

logger = logging.getLogger(__name__)
# settings = get_settings()  # Removed top-level settings; use lazy initialization in functions as needed.


@shared_task(
    bind=True,
    name="fetch_news",
    max_retries=3,
    default_retry_delay=300,  # 5 minutes
    acks_late=True,
    time_limit=1800,  # 30 minutes
    soft_time_limit=1500,  # 25 minutes
)
def fetch_news(
    self, source_name: Optional[str] = None, days: int = 1
) -> Dict[str, Any]:
    """
    Fetch news from all sources or a specific source.

    Args:
        source_name: Optional name of the source to fetch from. If None, fetches from all sources.
        days: Number of days of articles to fetch (default: 1).

    Returns:
        Dict containing status and results of the fetch operation.
    """
    task_id = self.request.id
    logger.info(
        f"Starting news fetch task {task_id} for source: {source_name or 'all'}"
    )

    collector = NewsCollector()
    start_time = datetime.now(timezone.utc)

    async def _fetch() -> Tuple[bool, Dict[str, Any]]:
        """Async function to perform the actual collection."""
        try:
            if source_name:
                logger.info(
                    f"Collecting articles from source: {source_name} for the last {days} days"
                )
                count = await collector.collect_from_source(source_name, days=days)
                return True, {
                    "status": "success",
                    "message": f"Successfully collected {count} new articles from {source_name}",
                    "source": source_name,
                    "articles_collected": count,
                    "metrics": collector.get_metrics(),
                }
            else:
                logger.info(
                    f"Collecting articles from all sources for the last {days} days"
                )
                count = await collector.collect_all_sources()
                return True, {
                    "status": "success",
                    "message": f"Successfully collected {count} new articles from all sources",
                    "source": "all",
                    "articles_collected": count,
                    "metrics": collector.get_metrics(),
                }

        except Exception as e:
            logger.error(f"Error in _fetch: {str(e)}", exc_info=True)
            return False, {
                "status": "error",
                "message": f"Failed to collect articles: {str(e)}",
                "source": source_name or "all",
                "articles_collected": 0,
                "error": str(e),
            }

    try:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Run the async function and get the result
        success, result = loop.run_until_complete(_fetch())

        # Calculate duration
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        result["duration_seconds"] = round(duration, 2)

        if success:
            logger.info(
                f"Successfully completed news fetch task {task_id} in {duration:.2f}s. "
                f"Collected {result['articles_collected']} articles."
            )
        else:
            logger.error(
                f"Failed news fetch task {task_id} after {duration:.2f}s. "
                f"Error: {result.get('error', 'Unknown error')}"
            )

        return result

    except Exception as e:
        error_msg = f"Unexpected error in fetch_news task {task_id}: {str(e)}"
        logger.exception(error_msg)

        # Check if we should retry
        retries = self.request.retries
        if retries < self.max_retries:
            logger.warning(
                f"Retrying task {task_id} (attempt {retries + 1}/{self.max_retries})"
            )
            raise self.retry(exc=e, countdown=60 * (2**retries))  # Exponential backoff

        # Max retries reached
        return {
            "status": "error",
            "message": f"Failed after {retries} retries: {str(e)}",
            "source": source_name or "all",
            "articles_collected": 0,
            "error": str(e),
            "retries": retries,
        }

    finally:
        # Clean up the event loop
        if "loop" in locals() and loop is not None:
            try:
                loop.close()
            except Exception as e:
                logger.warning(f"Error closing event loop: {str(e)}")


@shared_task(
    bind=True, max_retries=3, default_retry_delay=60, acks_late=True  # 1 minute
)
def analyze_sentiment(self, article_id: str) -> Dict[str, Any]:
    """
    Analyze sentiment for a single article.

    Args:
        article_id: ID of the article to analyze

    Returns:
        Dict containing sentiment analysis results
    """
    logger.info(f"Analyzing sentiment for article {article_id}")

    # TODO: Implement actual sentiment analysis
    # For now, just return a placeholder
    return {
        "status": "success",
        "article_id": article_id,
        "sentiment_score": 0.0,
        "sentiment_label": "neutral",
        "confidence": 0.0,
    }


@shared_task(
    bind=True, max_retries=2, default_retry_delay=30, acks_late=True  # 30 seconds
)
def process_article(self, article_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a single article - save to DB and trigger analysis.

    Args:
        article_data: Article data to process

    Returns:
        Dict containing processing results
    """
    logger.info(f"Processing article: {article_data.get('title', 'Untitled')}")

    try:
        # TODO: Implement actual article processing
        # For now, just return a success response
        return {
            "status": "success",
            "message": "Article processed successfully",
            "article_id": article_data.get("id", "unknown"),
            "title": article_data.get("title", "Untitled"),
        }

    except Exception as e:
        logger.error(f"Error processing article: {str(e)}", exc_info=True)

        # Check if we should retry
        retries = self.request.retries
        if retries < self.max_retries:
            logger.warning(
                f"Retrying article processing (attempt {retries + 1}/{self.max_retries})"
            )
            raise self.retry(exc=e, countdown=30 * (2**retries))

        # Max retries reached
        return {
            "status": "error",
            "message": f"Failed to process article after {retries} retries: {str(e)}",
            "article_id": article_data.get("id", "unknown"),
            "error": str(e),
            "retries": retries,
        }
