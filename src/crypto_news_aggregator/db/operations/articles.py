import logging
from typing import List
from datetime import datetime, timezone
from pymongo.errors import DuplicateKeyError
from crypto_news_aggregator.models.article import ArticleCreate, ArticleInDB
from crypto_news_aggregator.db.mongodb import mongo_manager
from crypto_news_aggregator.services.article_service import get_article_service

logger = logging.getLogger(__name__)


async def create_or_update_articles(articles: List[ArticleCreate]):
    """Creates new articles or updates existing ones in the database.

    Handles duplicate URL errors gracefully so a single E11000 error does not
    prevent the entire RSS cycle from reaching entity extraction.
    """
    db = await mongo_manager.get_async_database()
    collection = db.articles
    article_service = get_article_service()

    failed_articles = []
    succeeded_count = 0

    for article in articles:
        try:
            # Ensure URL is a string before database operations
            if hasattr(article, "url") and not isinstance(article.url, str):
                article.url = str(article.url)
            existing_article = await collection.find_one({"source_id": article.source_id})
            if existing_article:
                # Update metrics if the article already exists
                await collection.update_one(
                    {"_id": existing_article["_id"]},
                    {"$set": {"metrics": article.metrics.model_dump()}},
                )
                succeeded_count += 1
            else:
                # Insert new article
                # Prepare article data for database insertion
                article_data = article.model_dump()
                # Add required fields for database storage
                article_data.update(
                    {
                        "created_at": datetime.now(timezone.utc),
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
                # Use ArticleService for proper fingerprinting and deduplication
                # This will:
                # 1. Generate fingerprint (MD5 hash of normalized title + content)
                # 2. Check for duplicates by fingerprint
                # 3. Only insert if not a duplicate
                # 4. Update duplicate metadata if duplicate exists
                await article_service.create_article(article_data)
                succeeded_count += 1
        except DuplicateKeyError as e:
            # E11000 error: unique constraint violation.
            # Expected only for duplicate URLs (url_unique index per mongodb.py line 88).
            # Check error details to distinguish expected from unexpected violations.

            # DuplicateKeyError details: try structured error details first
            violated_index = None
            if hasattr(e, 'details') and e.details and isinstance(e.details, dict):
                # MongoDB error response includes keyPattern or index information
                violated_index = e.details.get('index') or e.details.get('keyPattern')

            # Only URL duplicates are expected (url_unique index);
            # treat as success since article is already stored
            is_url_duplicate = False
            if violated_index and 'url' in str(violated_index).lower():
                is_url_duplicate = True
            elif not violated_index and 'url_unique' in str(e):
                # Message-based detection when details unavailable
                is_url_duplicate = True

            if is_url_duplicate:
                logger.debug(
                    "Duplicate URL detected. Article already in database; skipping."
                )
                succeeded_count += 1
            else:
                # Unexpected unique constraint (not URL) - propagate for investigation
                logger.error(
                    "Unexpected unique constraint violation. Propagating."
                )
                failed_articles.append((article, "unique_constraint_error"))
                raise

    if failed_articles:
        logger.error(
            f"Failed to ingest {len(failed_articles)}/{len(articles)} articles. "
            f"Succeeded: {succeeded_count}. See prior logs for specific failures."
        )
        raise RuntimeError(f"Article ingestion failed for {len(failed_articles)} articles")
    else:
        logger.info(f"✅ Successfully ingested {succeeded_count} articles")
