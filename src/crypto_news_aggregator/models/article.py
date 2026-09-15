"""
Article model for storing and processing data from various sources like Twitter, Telegram, etc.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, HttpUrl, ConfigDict
from ..db.mongodb import PyObjectId


class ArticleMetrics(BaseModel):
    """Public metrics for an article."""

    views: int = 0
    likes: int = 0
    replies: int = 0
    # Twitter specific
    retweets: int = 0
    quotes: int = 0


class ArticleAuthor(BaseModel):
    """Author of an article."""

    id: str
    name: str
    username: Optional[str] = None


class ArticleBase(BaseModel):
    """Base model for article data."""

    title: str
    source_id: Optional[str] = Field(
        None,
        unique=True,
        description="The unique ID of the article from its source (e.g., tweet ID).",
    )
    source: Literal[
        "twitter",
        "telegram",
        "rss",
        "reddit",
        "chaingpt",
        "coindesk",
        "cointelegraph",
        "decrypt",
        "bitcoinmagazine",
        "theblock",
        "cryptoslate",
        # "benzinga",  # Excluded - advertising content
        "messari",
        "bitcoin.com",
        "glassnode",
        "bankless",
        "thedefiant",
        "defillama",
        "dune",
        "galaxy",
        "dlnews",
        "watcherguru",
    ] = Field(..., description="The source of the article.")
    text: str
    author: Optional[ArticleAuthor] = None
    url: str
    lang: str = "en"
    metrics: ArticleMetrics
    keywords: List[str] = []
    relevance_score: Optional[float] = None
    relevance_tier: Optional[int] = Field(
        None,
        ge=1,
        le=3,
        description="Relevance tier: 1=high signal, 2=medium, 3=low/exclude"
    )
    relevance_reason: Optional[str] = Field(
        None,
        description="Reason for relevance classification"
    )
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None
    raw_data: Dict[str, Any]  # To store the raw article payload
    published_at: Optional[datetime] = None  # Source publication timestamp.
    # None means unknown/unverifiable -- never substitute ingestion or
    # processing time here (see BUG-109). Consumers computing freshness
    # windows must treat None as "exclude", not as "now".
    
    # Narrative data fields
    actors: Optional[List[str]] = None
    actor_salience: Optional[Dict[str, int]] = None  # {"EntityName": 5, ...}
    nucleus_entity: Optional[str] = None  # Primary entity article is about
    narrative_focus: Optional[str] = None  # 2-5 word phrase describing what's happening (e.g., "price surge", "regulatory enforcement")
    actions: Optional[List[str]] = None
    tensions: Optional[List[str]] = None
    implications: Optional[str] = None
    narrative_summary: Optional[str] = None
    narrative_hash: Optional[str] = None  # Content hash for caching
    narrative_extracted_at: Optional[datetime] = None


class ArticleCreate(ArticleBase):
    """Model for creating a new article document."""

    pass


class ArticleUpdate(BaseModel):
    """Model for updating an existing article document."""

    text: Optional[str] = None
    relevance_score: Optional[float] = None
    relevance_tier: Optional[int] = Field(None, ge=1, le=3)
    relevance_reason: Optional[str] = None
    metrics: Optional[ArticleMetrics] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ArticleInDB(ArticleBase):
    """Model for article data as stored in MongoDB."""

    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={PyObjectId: str, HttpUrl: str},
        json_schema_extra={
            "example": {
                "source_id": "1234567890",
                "source": "twitter",
                "text": "Bitcoin to the moon! $BTC",
                "author": {
                    "id": "123",
                    "name": "Crypto King",
                    "username": "cryptoking",
                },
                "url": "https://twitter.com/cryptoking/status/1234567890",
                "lang": "en",
                "metrics": {
                    "views": 10000,
                    "likes": 500,
                    "retweets": 100,
                    "replies": 20,
                    "quotes": 5,
                },
                "keywords": ["$BTC"],
                "relevance_score": 0.95,
                "raw_data": {},
                "published_at": "2025-09-21T12:00:00Z",
            }
        },
    )
