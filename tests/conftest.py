import os

os.environ.setdefault(
    "MONGODB_URI", "mongodb://localhost:27017/crypto_news"
)
os.environ.setdefault("MONGODB_NAME", "crypto_news")

"""Pytest configuration and fixtures for testing the Crypto News Aggregator."""
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import AsyncGenerator, Dict, Any, Callable, Generator, Optional

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import sessionmaker
from src.crypto_news_aggregator.core.config import get_settings
from src.crypto_news_aggregator.db.session import get_session
from src.crypto_news_aggregator.services.user_service import UserService
from src.crypto_news_aggregator.services.alert_service import AlertService

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import settings first to configure the environment
from src.crypto_news_aggregator.core.config import Settings

# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define a constant for the test API key
TEST_API_KEY = "testapikey123"


# Create a test settings class that inherits from Settings
class TestSettings(Settings):
    API_KEYS: str = "testapikey123"

    # Core settings
    TESTING: bool = True
    PROJECT_NAME: str = "Crypto News Aggregator Test"
    VERSION: str = "0.1.0"
    DEBUG: bool = True

    # Database settings
    FORCE_SQLITE: bool = True

    # MongoDB settings
    MONGODB_URI: str = "mongodb://localhost:27017/crypto_news"
    MONGODB_NAME: str = "crypto_news"
    MONGODB_URI_SYNC: str = "mongodb://localhost:27017/crypto_news"

    # News API settings
    NEWS_API_KEY: str = "test_api_key"
    NEWSAPI_RATE_LIMIT: int = 0  # No rate limiting in tests

    # Redis settings
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # Celery settings
    CELERY_BROKER_URL: str = "memory://"  # Use in-memory broker for tests
    CELERY_RESULT_BACKEND: str = (
        "cache+memory://"  # Use in-memory result backend for tests
    )
    CELERY_TASK_ALWAYS_EAGER: bool = True  # Run tasks synchronously in tests
    CELERY_TASK_EAGER_PROPAGATES: bool = True  # Propagate exceptions in eager mode

    # Real-time news API settings
    REALTIME_NEWSAPI_URL: str = "http://test-server:3000"
    REALTIME_NEWSAPI_TIMEOUT: int = 30
    REALTIME_NEWSAPI_MAX_RETRIES: int = 3

    # Upstash Redis settings
    UPSTASH_REDIS_REST_URL: str = "https://test-upstash-redis.example.com"
    UPSTASH_REDIS_TOKEN: str = "test-upstash-token"

    # Email/SMTP settings
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_SENDER: str = ""

    # Cache settings
    CACHE_EXPIRE: int = 300  # 5 minutes for tests

    # Database sync settings
    ENABLE_DB_SYNC: bool = False  # Disable database sync for tests

    # Task status settings
    ENABLE_TASK_STATUS_CACHE: bool = False  # Disable task status cache for tests
    TASK_STATUS_CACHE_EXPIRE: int = 300  # 5 minutes

    # Twitter API settings
    TWITTER_BEARER_TOKEN: str = "test-twitter-bearer-token"

    # Polymarket API settings
    POLYMARKET_API_KEY: str = "test-polymarket-api-key"

    # PostgreSQL settings (for backward compatibility)
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "test_crypto_news"
    POSTGRES_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost/test_crypto_news"
    )

    def __init__(self, **data):
        # Set default values if not provided
        defaults = {
            "MONGODB_URI": "mongodb://localhost:27017/crypto_news",
            "MONGODB_NAME": "crypto_news",
            "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "CELERY_BROKER_URL": "redis://localhost:6379/0",
            "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
        }

        # Update with any provided values, but don't override with None
        for key, value in defaults.items():
            if key not in data and getattr(self, key, None) is None:
                data[key] = value

        super().__init__(**data)


def get_test_settings():
    return TestSettings()


# Ensure the settings are properly set for testing
os.environ["MONGODB_URI"] = "mongodb://localhost:27017/crypto_news"
os.environ["MONGODB_NAME"] = "crypto_news"

# Import the FastAPI app
from src.crypto_news_aggregator.main import app

# Override the settings with our test settings
# This ensures that any part of the app that calls get_settings()
# will receive the test settings.
app.dependency_overrides[get_settings] = get_test_settings

# Now import the rest of the application
from src.crypto_news_aggregator.db.base import Base
from src.crypto_news_aggregator.db.session import get_sessionmaker, get_session
from src.crypto_news_aggregator.db import models
from src.crypto_news_aggregator.services.article_service import (
    ArticleService,
    article_service,
)

# Clear any existing tables
Base.metadata.clear()

# Import models after clearing metadata
from src.crypto_news_aggregator.db import models


# MongoDB client for testing
@pytest_asyncio.fixture(scope="function")
async def mongo_client() -> AsyncGenerator[AsyncIOMotorClient, None]:
    """Create a MongoDB client for testing with automatic cleanup.

    This fixture:
    1. Creates a new MongoDB client
    2. Tests the connection
    3. Drops the test database if it exists
    4. Yields the client for testing
    5. Cleans up after the test
    """
    from src.crypto_news_aggregator.db.mongodb import mongo_manager

    # Get test settings
    settings = get_test_settings()
    client = None

    try:
        # Initialize the client
        client = AsyncIOMotorClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=2000,  # 2 second timeout
            connectTimeoutMS=2000,
            socketTimeoutMS=10000,
        )

        # Test the connection
        await client.admin.command("ping")
        logger.info("✅ Successfully connected to MongoDB")

        # Drop the test database if it exists
        await client.drop_database(settings.MONGODB_NAME)
        logger.info(f"Dropped test database: {settings.MONGODB_NAME}")

        yield client

    except Exception as e:
        logger.error(f"❌ Failed to connect to MongoDB: {e}")
        raise

    finally:
        # Clean up
        cleanup_errors = []

        try:
            if client:
                client.close()
                logger.info("Closed MongoDB connection")
        except Exception as e:
            cleanup_errors.append(f"Error closing MongoDB client: {e}")

        try:
            if hasattr(mongo_manager, "close"):
                await mongo_manager.close()
                logger.info("Closed MongoDB manager")
        except Exception as e:
            cleanup_errors.append(f"Error closing MongoDB manager: {e}")

        if cleanup_errors:
            logger.error("❌ Errors during cleanup: " + "; ".join(cleanup_errors))


@pytest_asyncio.fixture(scope="function")
async def mongo_db(
    mongo_client: AsyncIOMotorClient,
) -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    """Get the test database with automatic cleanup.

    This fixture provides a clean database for each test function.
    The database is automatically dropped and recreated for each test.
    """
    from src.crypto_news_aggregator.db.mongodb import mongo_manager

    settings = get_test_settings()

    try:
        # Ensure the database is empty
        await mongo_client.drop_database(settings.MONGODB_NAME)
        logger.info(f"Cleaned test database: {settings.MONGODB_NAME}")

        # Get a fresh database reference
        db = mongo_client[settings.MONGODB_NAME]

        # Initialize the mongo_manager with the test client and db name
        mongo_manager._async_client = mongo_client
        mongo_manager.db_name = settings.MONGODB_NAME
        mongo_manager._db = db
        mongo_manager._sync_client = mongo_manager.sync_client
        mongo_manager._sync_db = mongo_manager._sync_client[settings.MONGODB_NAME]
        mongo_manager._initialized = True

        # Initialize the database with required collections and indexes
        await mongo_manager.initialize_indexes(force_recreate=True)

        yield db

    except Exception as e:
        logger.error(f"❌ Error setting up test database: {e}")
        raise

    finally:
        # Clean up
        try:
            # Drop the database to ensure a clean state for the next test
            await mongo_client.drop_database(settings.MONGODB_NAME)
            logger.info(f"✅ Cleaned up test database: {settings.MONGODB_NAME}")
        except Exception as e:
            logger.warning(f"Warning: Failed to clean up test database: {e}")

        # Ensure all connections are closed
        mongo_client.close()


@pytest_asyncio.fixture(scope="function")
async def article_service(mongo_db: AsyncIOMotorDatabase):
    """Create an ArticleService instance with a test database connection.

    This fixture provides a clean ArticleService instance for each test,
    ensuring proper cleanup after each test.
    """
    from src.crypto_news_aggregator.services.article_service import ArticleService

    try:
        # Initialize the service with test database
        service = ArticleService(mongo_db)

        # Verify the service can connect to the database
        await service.ping()
        logger.info("✅ ArticleService initialized with test database")

        yield service

    except Exception as e:
        logger.error(f"❌ Failed to initialize ArticleService: {e}")
        raise

    finally:
        # Clean up any resources if needed
        if hasattr(service, "close"):
            try:
                await service.close()
            except Exception as e:
                logger.warning(f"Warning: Error closing ArticleService: {e}")


# Removed session-scoped event_loop fixture to allow pytest-asyncio to manage event loops
# Using asyncio_mode = "auto" instead for better compatibility


# Import the Base and all models to ensure tables are created
from src.crypto_news_aggregator.db.base import Base
from src.crypto_news_aggregator.db.models import (
    Alert,
    User,
    Source,
    Article,
    Sentiment,
    Trend,
)


@pytest_asyncio.fixture(scope="session")
async def db_connection() -> AsyncGenerator[AsyncConnection, None]:
    """Create a single database connection for the test session with a pre-initialized schema."""
    import tempfile
    import os

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    database_url = f"sqlite+aiosqlite:///{db_path}"

    engine = create_async_engine(database_url, echo=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.connect() as conn:
        yield conn

    await engine.dispose()
    os.unlink(db_path)


@pytest_asyncio.fixture(scope="function")
async def db_session(
    db_connection: AsyncConnection,
) -> AsyncGenerator[AsyncSession, None]:
    """Create a new database session for testing, running within a nested transaction."""
    await db_connection.begin_nested()

    async_session_factory = async_sessionmaker(
        bind=db_connection, expire_on_commit=False, class_=AsyncSession
    )
    session = async_session_factory()

    try:
        yield session
    finally:
        await session.close()
        await db_connection.rollback()


@pytest.fixture
def override_get_db(db_session: AsyncSession):
    """Override the get_db dependency for testing."""

    def _get_db():
        yield db_session

    app.dependency_overrides[get_session] = _get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def mock_user_service() -> UserService:
    """Mock the user service for testing."""
    from unittest.mock import AsyncMock

    return AsyncMock(spec=UserService)


@pytest.fixture
def mock_alert_service() -> AlertService:
    """Mock the alert service for testing."""
    from unittest.mock import AsyncMock

    return AsyncMock(spec=AlertService)


@pytest.fixture
def client(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    mock_user_service: UserService,
    mock_alert_service: AlertService,
) -> Generator[TestClient, None, None]:
    """
    Create a test client that uses the test database session.

    This fixture ensures that:
    1. The test client uses a non-persistent, in-memory database.
    2. The API key is properly configured for authenticated requests.
    """
    TEST_API_KEY = "testapikey123"

    def override_get_session() -> Generator[AsyncSession, None, None]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[UserService] = lambda: mock_user_service
    app.dependency_overrides[AlertService] = lambda: mock_alert_service

    monkeypatch.setenv("API_KEYS", TEST_API_KEY)

    with TestClient(app) as c:
        c.headers.update({"X-API-Key": TEST_API_KEY})
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def mock_newsapi() -> Dict[str, Any]:
    """Return a mock NewsAPI response."""
    return {
        "status": "ok",
        "totalResults": 1,
        "articles": [
            {
                "source": {"id": "test-source", "name": "Test Source"},
                "author": "Test Author",
                "title": "Test Article",
                "description": "Test description",
                "url": "https://example.com/test-article",
                "urlToImage": "https://example.com/image.jpg",
                "publishedAt": "2025-01-01T12:00:00Z",
                "content": "Test content",
            }
        ],
    }


@pytest.fixture
def mock_article_data() -> Dict[str, Any]:
    """Return mock article data."""
    return {
        "source": {"id": "test-source", "name": "Test Source"},
        "author": "Test Author",
        "title": "Test Article",
        "description": "Test description",
        "url": "https://example.com/test-article",
        "urlToImage": "https://example.com/image.jpg",
        "publishedAt": "2025-01-01T12:00:00Z",
        "content": "Test content",
    }


# Configure pytest to use asyncio
pytest_plugins = ("pytest_asyncio",)


@pytest.fixture(scope="session", autouse=True)
def configure_test_environment():
    """Configure the test environment before any tests run."""
    import os
    from celery import current_app

    # Set environment variables for the entire test session
    os.environ["TESTING"] = "True"
    os.environ["MONGODB_URI"] = "mongodb://localhost:27017/test_crypto_news_aggregator"
    os.environ["MONGODB_NAME"] = "test_crypto_news_aggregator"
    os.environ["REDIS_URL"] = "redis://localhost:6379/1"  # Use a different DB for tests
    os.environ["NEWS_API_KEY"] = "test-api-key"
    os.environ["SECRET_KEY"] = "test-secret-key-for-session"
    os.environ["API_KEYS"] = "testapikey123"

    # Configure Celery for testing
    os.environ["CELERY_BROKER_URL"] = "memory://"
    os.environ["CELERY_RESULT_BACKEND"] = "cache+memory://"
    os.environ["CELERY_TASK_ALWAYS_EAGER"] = "True"
    os.environ["CELERY_TASK_EAGER_PROPAGATES"] = "True"

    # Store original config
    original_config = {
        "broker_url": current_app.conf.get("broker_url"),
        "result_backend": current_app.conf.get("result_backend"),
        "task_always_eager": current_app.conf.get("task_always_eager"),
        "task_eager_propagates": current_app.conf.get("task_eager_propagates"),
    }

    # Apply test configuration
    current_app.conf.update(
        broker_url="memory://",
        result_backend="cache+memory://",
        task_always_eager=True,
        task_eager_propagates=True,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
    )

    yield

    # Restore original configuration
    current_app.conf.update(**original_config)


@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing."""
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017/test_db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("NEWS_API_KEY", "test-api-key")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    # Use the same test API key that's used in the test client
    monkeypatch.setenv("API_KEYS", TEST_API_KEY)


def pytest_configure(config):
    """Configure pytest with custom markers and asyncio mode."""
    # Configure asyncio mode for pytest-asyncio
    config.option.asyncio_mode = "auto"

    config.addinivalue_line(
        "markers", "asyncio: mark test as async so it can use async/await"
    )
    config.addinivalue_line(
        "markers",
        "integration: mark test as an integration test that may start subprocesses or external services",
    )
