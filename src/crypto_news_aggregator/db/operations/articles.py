from typing import List
from datetime import datetime, timezone
from crypto_news_aggregator.models.article import ArticleCreate, ArticleInDB
from crypto_news_aggregator.db.mongodb import mongo_manager
from crypto_news_aggregator.services.article_service import get_article_service


async def create_or_update_articles(articles: List[ArticleCreate]):
    """Creates new articles or updates existing ones in the database."""
    db = await mongo_manager.get_async_database()
    collection = db.articles
    article_service = get_article_service()

    for article in articles:
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
