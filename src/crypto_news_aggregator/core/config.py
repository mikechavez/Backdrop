from pydantic_settings import BaseSettings
from pydantic import model_validator
from functools import lru_cache
from typing import Optional, List


class Settings(BaseSettings):
    # Core settings
    DEBUG: bool = False
    TESTING: bool = False
    TESTING_MODE: bool = False  # New flag for mock data
    PROJECT_NAME: str = "Crypto News Aggregator"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    BASE_URL: str = (
        "http://localhost:8001"  # Base URL for generating absolute URLs in emails
    )
    PORT: int = 8000  # Port for the Uvicorn server

    # PostgreSQL settings (kept for backward compatibility)
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "crypto_news"
    POSTGRES_URL: Optional[str] = None

    # MongoDB settings
    # Default to local MongoDB instance if env var is not provided
    MONGODB_URI: str  # override with env var MONGODB_URI
    MONGODB_NAME: str = "crypto_news"
    MONGODB_MAX_POOL_SIZE: int = 10  # Default pool size for MongoDB connections
    MONGODB_MIN_POOL_SIZE: int = (
        1  # Default min pool size for MongoDB connections  # Default database name
    )

    # For backward compatibility
    DATABASE_URL: Optional[str] = None

    # API Keys (these will be loaded from environment variables)
    LLM_PROVIDER: str = "anthropic"  # Default provider, will be overridden by .env
    OPENAI_API_KEY: str = ""  # OpenAI API key for LLM operations (deprecated)
    NEWS_API_KEY: str = ""  # Kept for backward compatibility
    TWITTER_BEARER_TOKEN: str = ""
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_DEFAULT_MODEL: str = "claude-haiku-4-5-20251001"
    ANTHROPIC_ENTITY_MODEL: str = "claude-haiku-4-5-20251001"
    # DEPRECATED by BUG-039: Entity extraction no longer falls back to Sonnet.
    # This config was removed from extract_entities_batch() to prevent silent 5x cost escalation.
    # ANTHROPIC_ENTITY_FALLBACK_MODEL: str = "claude-sonnet-4-5-20250929"
    ANTHROPIC_ENTITY_INPUT_COST_PER_1K_TOKENS: float = 0.80
    ANTHROPIC_ENTITY_OUTPUT_COST_PER_1K_TOKENS: float = 4.0
    ENTITY_EXTRACTION_BATCH_SIZE: int = 10
    POLYMARKET_API_KEY: str = ""

    # Reddit settings
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = ""
    REDDIT_SUBREDDITS: List[str] = [
        "CryptoCurrency",
        "Bitcoin",
        "ethereum",
        "ethtrader",
    ]

    # Telegram settings
    TELEGRAM_API_ID: Optional[int] = None
    TELEGRAM_API_HASH: Optional[str] = None
    TELEGRAM_SESSION_NAME: str = "telegram_session"
    TELEGRAM_CHANNEL: str = "WatcherGuru"

    # Realtime NewsAPI settings
    REALTIME_NEWSAPI_URL: str = (
        "http://localhost:3000"  # URL of the self-hosted realtime-newsapi
    )
    REALTIME_NEWSAPI_TIMEOUT: int = 30  # Request timeout in seconds
    REALTIME_NEWSAPI_MAX_RETRIES: int = 3  # Max retries for API calls

    # Redis settings (for direct Redis protocol - optional)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # Upstash Redis REST API settings
    UPSTASH_REDIS_REST_URL: str = ""  # e.g., "https://your-instance.upstash.io"
    UPSTASH_REDIS_TOKEN: str = ""  # Your Upstash REST token

    # Celery settings (using Redis for local development)
    # Allow override via environment variable for production deployments (e.g., Railway)
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    # Security settings
    SECRET_KEY: str  # Change this to a secure secret key
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30  # 30 minutes
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # 7 days
    API_KEY: str = "test-api-key"  # For testing purposes

    # CORS settings
    CORS_ORIGINS: str = "*"  # In production, replace with specific origins

    # Email Settings
    SMTP_SERVER: str = "smtp.mailtrap.io"  # SMTP server address
    SMTP_PORT: int = 2525  # 587 for TLS, 465 for SSL
    SMTP_USERNAME: str = "snotboogy"  # SMTP auth username
    SMTP_PASSWORD: str = "01Mc0066$$420"  # SMTP auth password or app password
    SMTP_USE_TLS: bool = True  # Use TLS for encryption
    SMTP_TIMEOUT: int = 10  # Connection timeout in seconds

    # Email Sender Information
    EMAIL_FROM: str = (
        "snotboogy@cryptochime.com"  # Sender email address (defaults to SMTP_USERNAME if empty)
    )
    EMAIL_FROM_NAME: str = "Crypto News Aggregator"  # Sender display name
    SUPPORT_EMAIL: str = "support@example.com"  # Support contact email
    ALERT_EMAIL: str = ""  # Email address for receiving test alerts
    EMAIL_DOMAIN: str = "cryptonewsaggregator.com"  # Domain for Message-ID

    # Email Tracking & Links
    EMAIL_TRACKING_ENABLED: bool = True
    EMAIL_TRACKING_PIXEL_URL: str = "{BASE_URL}/api/v1/emails/track/open/{message_id}"
    EMAIL_TRACKING_CLICK_URL: str = (
        "{BASE_URL}/api/v1/emails/track/click/{message_id}/{link_hash}"
    )
    EMAIL_UNSUBSCRIBE_URL: str = "{BASE_URL}/api/v1/emails/unsubscribe/{token}"

    # Email Rate Limiting
    EMAIL_RATE_LIMIT: int = 100  # Max emails per hour
    EMAIL_RATE_LIMIT_WINDOW: int = 3600  # 1 hour in seconds

    # Email Retry Settings
    EMAIL_MAX_RETRIES: int = 3  # Max retry attempts for failed sends
    EMAIL_RETRY_DELAY: int = 60  # Delay between retries in seconds

    # Alert Settings
    ALERT_COOLDOWN_MINUTES: int = 60  # 1 hour between alerts for same condition
    PRICE_CHECK_INTERVAL: int = 300  # 5 minutes between price checks
    PRICE_CHANGE_THRESHOLD: float = 1.0  # 1% change to trigger alerts

    # CoinGecko API settings
    COINGECKO_API_URL: str = "https://api.coingecko.com/api/v3"
    coingecko_api_key: str = ""  # Optional API key for higher rate limits

    # News source settings
    ENABLED_NEWS_SOURCES: list[str] = ["coindesk", "bloomberg"]
    NEWS_FETCH_INTERVAL: int = 300  # 5 minutes in seconds
    MAX_ARTICLES_PER_SOURCE: int = 20
    TWEET_FETCH_INTERVAL: int = 900  # 15 minutes in seconds

    # ChainGPT settings
    CHAINGPT_RSS_URL: str = "https://api.chaingpt.org/news/rss"

    # Source-specific settings
    COINDESK_API_KEY: str = ""  # Optional API key for CoinDesk
    BLOOMBERG_RATE_LIMIT: int = 10  # Max requests per minute

    # Article processing
    MIN_ARTICLE_LENGTH: int = 100  # Minimum characters for an article to be processed
    MAX_ARTICLE_AGE_DAYS: int = 7  # Ignore articles older than this

    # Cache settings
    CACHE_EXPIRE: int = 3600  # 1 hour

    # Database sync settings
    ENABLE_DB_SYNC: bool = False  # Enable/disable database synchronization

    @model_validator(mode="after")
    def build_postgres_url(self) -> "Settings":
        if self.POSTGRES_URL is None:
            self.POSTGRES_URL = f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}/{self.POSTGRES_DB}"
        if self.DATABASE_URL is None:
            self.DATABASE_URL = self.POSTGRES_URL

        # Build Celery URLs with fallback to localhost for local development
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        if not self.CELERY_RESULT_BACKEND:
            self.CELERY_RESULT_BACKEND = f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

        return self

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# Create a settings instance for direct import
settings = get_settings()
