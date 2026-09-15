"""
Article service for handling article-related operations including deduplication.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta
import hashlib
import re
from unidecode import unidecode
from bson import ObjectId
import inspect

from ..models.article import (
    ArticleInDB,
    ArticleCreate,
    ArticleUpdate,
)
from ..models.sentiment import SentimentAnalysis
from ..db.mongodb import PyObjectId
from ..db.mongodb import mongo_manager, COLLECTION_ARTICLES
from ..core.config import get_settings
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
# from ..core.sentiment_analyzer import SentimentAnalyzer  # DISABLED: Causes Railway deployment crash

logger = logging.getLogger(__name__)
# settings = get_settings()  # Removed top-level settings; use lazy initialization in methods as needed.


class ArticleService:
    """Service for handling article operations."""

    def __init__(
        self,
        db: Optional[AsyncIOMotorDatabase] = None,
        collection: Optional[AsyncIOMotorCollection] = None,
    ):
        self.collection_name = COLLECTION_ARTICLES
        # Optional injected resources for tests or specialized usage
        self._db: Optional[AsyncIOMotorDatabase] = db
        self._collection: Optional[AsyncIOMotorCollection] = collection

    async def _get_collection(self) -> Any:
        """Get the MongoDB collection for articles."""
        if getattr(self, "_collection", None) is not None:
            return self._collection
        # Prefer injected DB when provided
        if self._db is not None:
            self._collection = self._db[self.collection_name]
            return self._collection
        # Fallback to global mongo_manager
        self._collection = await mongo_manager.get_async_collection(
            self.collection_name
        )
        return self._collection

    async def ping(self) -> bool:
        """Check MongoDB connectivity for this service."""
        try:
            if self._db is not None:
                await self._db.client.admin.command("ping")
                return True
            return await mongo_manager.ping()
        except Exception as e:
            logger.error(f"MongoDB ping failed in ArticleService: {e}")
            return False

    async def close(self) -> None:
        """Close MongoDB resources owned by this service instance.

        Does NOT close the shared mongo_manager client—that is owned by the application.
        Only closes a test-injected database if one was provided.
        """
        try:
            # Do NOT close mongo_manager—it is a shared singleton owned by the application.
            # This service only manages its own _db reference (for testing).
            # If _db was set by tests, it will be cleaned up by the test framework.
            pass
        except Exception as e:
            logger.warning(f"Error closing MongoDB resources in ArticleService: {e}")

    async def _generate_fingerprint(self, title: str, content: str) -> str:
        """
        Generate a fingerprint for an article to help with deduplication.

        Args:
            title: Article title
            content: Article content

        Returns:
            str: A fingerprint string
        """

        # Normalize text: lowercase, remove extra whitespace, and unidecode
        def normalize_text(text: str) -> str:
            if not text:
                return ""
            # Remove URLs, special chars, and extra whitespace
            text = re.sub(r"http\S+", "", text)
            text = re.sub(r"[^\w\s]", "", text)
            text = " ".join(text.split())
            return unidecode(text.lower())

        # Use first 100 chars of title and first 200 chars of content
        normalized = normalize_text(title)[:100] + "\n" + normalize_text(content)[:200]

        # Create a hash of the normalized text
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

    async def _is_duplicate(
        self, title: str, content: str, source_id: str, published_at: datetime
    ) -> Tuple[bool, Optional[ObjectId]]:
        """
        Check if an article is an exact duplicate of an existing one.

        Only considers articles with identical fingerprints as duplicates.
        Different articles about the same topic will not be considered duplicates.

        Args:
            title: Article title
            content: Article content
            source_id: Source ID (not used in comparison, kept for interface compatibility)
            published_at: Publication timestamp (not used in comparison, kept for interface compatibility)

        Returns:
            Tuple of (is_duplicate, original_article_id)
        """
        # Generate fingerprint for the article
        fingerprint = await self._generate_fingerprint(title, content)

        # Look for exact matches by fingerprint only
        collection = await self._get_collection()
        existing = await collection.find_one({"fingerprint": fingerprint})

        if existing:
            logger.debug(f"Found duplicate article with fingerprint {fingerprint}")
            return True, existing["_id"]

        return False, None

    async def create_article(
        self, article_data: Dict[str, Any]
    ) -> Optional[ArticleInDB]:
        """
        Create a new article with deduplication.

        Args:
            article_data: Article data including title, content, source, etc.

        Returns:
            ArticleInDB if created, None if it was a duplicate
        """
        # Check for duplicates
        is_duplicate, original_id = await self._is_duplicate(
            title=article_data.get("title", ""),
            content=article_data.get("text", ""),  # Changed from "content" to "text"
            source_id=article_data.get("source_id", ""),
            published_at=article_data.get("published_at", datetime.now(timezone.utc)),
        )

        if is_duplicate:
            logger.info(f"Duplicate article detected. Original ID: {original_id}")
            # Update the original article's metadata if needed
            await self._update_duplicate_metadata(original_id, article_data)
            return None

        # Generate fingerprint for the article
        fingerprint = await self._generate_fingerprint(
            article_data.get("title", ""),
            article_data.get("text", ""),  # Changed from "content" to "text"
        )

        # Add fingerprint and timestamps
        article_data["fingerprint"] = fingerprint
        article_data["created_at"] = datetime.now(timezone.utc)
        article_data["updated_at"] = datetime.now(timezone.utc)

        # Compute sentiment for the article content/title
        # DISABLED: SentimentAnalyzer causes Railway deployment crash
        # Return default neutral sentiment instead
        sentiment_payload = {
            "score": 0.0,
            "magnitude": 0.0,
            "label": "neutral",
            "subjectivity": 0.0,
        }
        article_data["sentiment"] = sentiment_payload

        # Create the article in MongoDB
        collection = await self._get_collection()
        result = await collection.insert_one(article_data)

        if result.inserted_id:
            # Return the created article
            created = await collection.find_one({"_id": result.inserted_id})
            return ArticleInDB(**created)

        return None

    async def _update_duplicate_metadata(
        self, article_id: ObjectId, new_data: Dict[str, Any]
    ) -> None:
        """
        Update metadata for a duplicate article.

        Args:
            article_id: ID of the original article
            new_data: New article data that might contain updates
        """
        update_fields = {}

        # Update the updated_at timestamp
        update_fields["updated_at"] = datetime.now(timezone.utc)

        # If the new article has a higher quality image, update it
        if new_data.get("image_url") and not new_data.get("image_url", "").endswith(
            "placeholder.jpg"
        ):
            update_fields["image_url"] = new_data["image_url"]

        # If the new article has more complete content, update it
        if (
            new_data.get("text") and len(new_data.get("text", "")) > 100
        ):  # Arbitrary threshold
            update_fields["text"] = new_data["text"]

        # Only perform the update if we have fields to update
        if update_fields:
            collection = await self._get_collection()
            await collection.update_one({"_id": article_id}, {"$set": update_fields})

    async def get_article(self, article_id: str) -> Optional[ArticleInDB]:
        """Get an article by ID."""
        try:
            collection = await self._get_collection()
            article = await collection.find_one({"_id": ObjectId(article_id)})
            return ArticleInDB(**article) if article else None
        except Exception as e:
            logger.error(f"Error getting article {article_id}: {str(e)}")
            return None

    async def list_articles(
        self,
        skip: int = 0,
        limit: int = 10,
        source_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        keywords: Optional[List[str]] = None,
        min_sentiment: Optional[float] = None,
        max_sentiment: Optional[float] = None,
    ) -> Tuple[List[ArticleInDB], int]:
        """
        List articles with filtering and pagination.

        Args:
            skip: Number of documents to skip
            limit: Maximum number of documents to return
            source_id: Filter by source ID
            start_date: Filter by published date (greater than or equal)
            end_date: Filter by published date (less than or equal)
            keywords: Filter by keywords
            min_sentiment: Minimum sentiment score (-1 to 1)
            max_sentiment: Maximum sentiment score (-1 to 1)

        Returns:
            Tuple of (list of articles, total count)
        """
        query = {}

        # Apply filters
        if source_id:
            query["source.id"] = source_id

        if start_date or end_date:
            query["published_at"] = {}
            if start_date:
                query["published_at"]["$gte"] = start_date
            if end_date:
                query["published_at"]["$lte"] = end_date

        if keywords:
            query["keywords"] = {"$in": keywords}

        if min_sentiment is not None or max_sentiment is not None:
            query["sentiment.score"] = {}
            if min_sentiment is not None:
                query["sentiment.score"]["$gte"] = min_sentiment
            if max_sentiment is not None:
                query["sentiment.score"]["$lte"] = max_sentiment

        # Get the MongoDB collection
        collection = await self._get_collection()

        # Get total count (await only if needed)
        total_call = collection.count_documents(query)
        total = await total_call if inspect.isawaitable(total_call) else total_call

        # Get the cursor from find (handle both awaitable and direct return)
        find_result = collection.find(query)
        cursor = await find_result if inspect.isawaitable(find_result) else find_result
        # Chain cursor methods
        cursor = cursor.sort("published_at", -1).skip(skip).limit(limit)

        # Execute the query and get results
        to_list_call = cursor.to_list(length=limit)
        articles_data = (
            await to_list_call if inspect.isawaitable(to_list_call) else to_list_call
        )
        articles = [ArticleInDB(**doc) for doc in articles_data]

        return articles, total

    async def search_articles(
        self,
        query: str,
        skip: int = 0,
        limit: int = 10,
        source_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Tuple[List[ArticleInDB], int]:
        """
        Search articles by text.

        Args:
            query: Search query string
            skip: Number of documents to skip
            limit: Maximum number of documents to return
            source_id: Filter by source ID
            start_date: Filter by published date (greater than or equal)
            end_date: Filter by published date (less than or equal)

        Returns:
            Tuple of (list of articles, total count)
        """
        # Build the text search query
        text_search = {"$text": {"$search": query, "$caseSensitive": False}}

        # Build the filter query
        filter_query = {}
        if source_id:
            filter_query["source.id"] = source_id

        if start_date or end_date:
            filter_query["published_at"] = {}
            if start_date:
                filter_query["published_at"]["$gte"] = start_date
            if end_date:
                filter_query["published_at"]["$lte"] = end_date

        # Combine text search with filters
        query = {"$and": [text_search]}
        if filter_query:
            query["$and"].append(filter_query)
        else:
            query = text_search

        collection = await self._get_collection()

        # Get total count
        total_call = collection.count_documents(query)
        total = await total_call if inspect.isawaitable(total_call) else total_call

        # Get search results with text score for sorting
        pipeline = [
            {"$match": query},
            {"$addFields": {"score": {"$meta": "textScore"}}},
            {"$sort": {"score": {"$meta": "textScore"}}},
            {"$skip": skip},
            {"$limit": limit},
        ]

        # Execute aggregation and convert to list
        agg_result = collection.aggregate(pipeline)
        cursor = await agg_result if inspect.isawaitable(agg_result) else agg_result
        to_list_call = cursor.to_list(length=limit)
        articles_data = (
            await to_list_call if inspect.isawaitable(to_list_call) else to_list_call
        )
        articles = [ArticleInDB(**doc) for doc in articles_data]

        return articles, total

    async def update_article_sentiment(
        self, article_id: str, sentiment: SentimentAnalysis
    ) -> bool:
        """
        Update the sentiment analysis for an article.

        Args:
            article_id: Article ID
            sentiment: Sentiment analysis data

        Returns:
            bool: True if updated successfully, False otherwise
        """
        try:
            collection = await self._get_collection()
            result = await collection.update_one(
                {"_id": ObjectId(article_id)},
                {
                    "$set": {
                        "sentiment": sentiment.model_dump(),
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating article {article_id} sentiment: {str(e)}")
            return False

    async def get_average_sentiment_for_symbols(
        self, symbols: List[str], days_ago: int = 7
    ) -> Dict[str, Optional[float]]:
        """
        Calculate the average sentiment score for a list of symbols from recent articles.

        Args:
            symbols: A list of symbols (e.g., ['BTC', 'ETH']).
            days_ago: How many days back to include articles from.

        Returns:
            A dictionary mapping each symbol to its average sentiment score or None.
        """
        if not symbols:
            return {}

        collection = await self._get_collection()
        start_date = datetime.now(timezone.utc) - timedelta(days=days_ago)

        # Prepare the aggregation pipeline
        pipeline = [
            {
                "$match": {
                    "keywords": {"$in": symbols},
                    "published_at": {"$gte": start_date},
                    "sentiment.score": {"$ne": None},
                }
            },
            {"$unwind": "$keywords"},
            {"$match": {"keywords": {"$in": symbols}}},
            {
                "$group": {
                    "_id": "$keywords",
                    "average_sentiment": {"$avg": "$sentiment.score"},
                }
            },
            {"$project": {"symbol": "$_id", "average_sentiment": 1, "_id": 0}},
        ]

        try:
            cursor = collection.aggregate(pipeline)
            results = await cursor.to_list(length=len(symbols))

            sentiment_map = {res["symbol"]: res["average_sentiment"] for res in results}

            # Ensure all requested symbols are in the output dict
            for symbol in symbols:
                if symbol not in sentiment_map:
                    sentiment_map[symbol] = (
                        None  # No articles found or no sentiment score
                    )

            return sentiment_map
        except Exception as e:
            logger.error(
                f"Error calculating average sentiment for symbols {symbols}: {e}",
                exc_info=True,
            )
            # Return an empty dict to indicate failure without crashing
            return {}

    async def get_top_articles_for_symbols(
        self,
        symbols: List[str],
        *,
        hours: int = 48,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Fetch top recent articles related to the provided symbols.

        Args:
            symbols: List of symbols or keywords to match (e.g., ['BTC', 'Bitcoin']).
            hours: Lookback window in hours.
            limit: Maximum number of articles to return.

        Returns:
            A list of article dictionaries with relevance and sentiment metadata.
        """
        if not symbols or limit <= 0:
            return []

        search_terms = sorted({s for s in symbols if s})
        if not search_terms:
            return []

        try:
            collection = await self._get_collection()
        except Exception as e:
            logger.error(
                f"Unable to access MongoDB collection for top articles: {e}",
                exc_info=True,
            )
            return []

        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=hours)

        or_conditions = [{"keywords": {"$in": search_terms}}]
        for term in search_terms:
            escaped = re.escape(term)
            regex = {"$regex": escaped, "$options": "i"}
            or_conditions.extend(
                [
                    {"title": regex},
                    {"text": regex},
                    {"content": regex},
                ]
            )

        query: Dict[str, Any] = {"published_at": {"$gte": start_time}}
        if or_conditions:
            query["$or"] = or_conditions

        candidate_limit = max(limit * 3, limit)

        try:
            cursor = (
                collection.find(query).sort("published_at", -1).limit(candidate_limit)
            )
            docs = await cursor.to_list(length=candidate_limit)
            logger.info(
                f"DEBUG: Found {len(docs)} candidate documents for symbols {symbols}"
            )
        except Exception as e:
            logger.error(
                f"Error querying top articles for symbols {symbols}: {e}", exc_info=True
            )
            return []

        ranked: List[Dict[str, Any]] = []
        for doc in docs:
            try:
                # Debug: check what doc actually is
                if not isinstance(doc, dict):
                    logger.warning(f"Document is not a dict, it's {type(doc)}: {doc}")
                    continue

                published_at = doc.get("published_at")
                if isinstance(published_at, str):
                    try:
                        # Handle various datetime string formats
                        if published_at.endswith("Z"):
                            published_at_dt = datetime.fromisoformat(
                                published_at.replace("Z", "+00:00")
                            )
                        else:
                            published_at_dt = datetime.fromisoformat(published_at)
                        # Make timezone-aware if it's not
                        if published_at_dt.tzinfo is None:
                            published_at_dt = published_at_dt.replace(
                                tzinfo=timezone.utc
                            )
                    except (ValueError, TypeError):
                        published_at_dt = now
                elif isinstance(published_at, datetime):
                    published_at_dt = published_at
                    # Make timezone-aware if it's not
                    if published_at_dt.tzinfo is None:
                        published_at_dt = published_at_dt.replace(tzinfo=timezone.utc)
                else:
                    published_at_dt = now

                hours_old = max(0.0, (now - published_at_dt).total_seconds() / 3600)
                recency_weight = max(0.0, 1 - (hours_old / max(hours, 1)))

                base_relevance = float(doc.get("relevance_score") or 0.0)

                # Handle sentiment data safely
                sentiment_node = doc.get("sentiment")
                if sentiment_node and isinstance(sentiment_node, dict):
                    sentiment_score = float(sentiment_node.get("score") or 0.0)
                    sentiment_label = sentiment_node.get("label") or "neutral"
                elif sentiment_node and isinstance(sentiment_node, str):
                    # Handle case where sentiment is stored as string
                    try:
                        import json

                        parsed_sentiment = json.loads(sentiment_node)
                        sentiment_score = float(parsed_sentiment.get("score") or 0.0)
                        sentiment_label = parsed_sentiment.get("label") or "neutral"
                    except (json.JSONDecodeError, AttributeError):
                        sentiment_score = 0.0
                        sentiment_label = "neutral"
                else:
                    sentiment_score = 0.0
                    sentiment_label = "neutral"

                sentiment_weight = 0.5 + 0.5 * abs(sentiment_score)

                composite_score = (
                    0.5 * base_relevance + 0.3 * recency_weight + 0.2 * sentiment_weight
                )

                ranked.append(
                    {
                        "title": doc.get("title") or "Untitled",
                        "source": doc.get("source_name")
                        or (
                            doc.get("source", {}).get("name")
                            if isinstance(doc.get("source"), dict)
                            else doc.get("source")
                        )
                        or "Unknown",
                        "url": doc.get("url"),
                        "published_at": published_at_dt,
                        "relevance_score": round(composite_score, 4),
                        "raw_relevance": base_relevance,
                        "sentiment_score": sentiment_score,
                        "sentiment_label": sentiment_label.lower(),
                        "keywords": doc.get("keywords", []),
                    }
                )
            except Exception as parse_error:
                logger.warning(
                    f"Skipping article during scoring: {parse_error}, doc type: {type(doc)}, doc: {doc}"
                )
                continue

        logger.info(
            f"DEBUG: After scoring, {len(ranked)} articles remain for symbols {symbols}"
        )
        ranked.sort(key=lambda item: item.get("relevance_score", 0.0), reverse=True)

        return ranked[:limit]


# Singleton instance
article_service = ArticleService()


def get_article_service() -> ArticleService:
    """Get the singleton ArticleService instance."""
    return article_service
