"""Main FastAPI application module."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def setup_logging():
    """Configure logging for the application."""
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    log_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    log_file = os.path.join(log_dir, "app.log")

    # File handler
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=3
    )
    file_handler.setFormatter(log_formatter)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)

    # Configure root logger - clear any existing handlers first to prevent duplication
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Ensure Uvicorn logs propagate to root logger (no explicit handler assignment)
    for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.setLevel(logging.INFO)
        uvicorn_logger.propagate = True

    logger = logging.getLogger(__name__)
    logger.info("--- Logging configured successfully ---")
    return logger


logger = setup_logging()

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.v1 import router as api_router
from .api import openai_compatibility as openai_api
from .api import admin as admin_api
from .core.monitoring import setup_performance_monitoring
from .core.config import get_settings
from .core.auth import API_KEY_NAME
from .core.rate_limiting import RateLimitMiddleware
from .db.mongodb import initialize_mongodb, mongo_manager
from .services.price_service import price_service

logger.info("Attempting to load application settings...")
try:
    settings = get_settings()
    logger.info("Application settings loaded successfully.")
except Exception as e:
    logger.critical(f"CRITICAL: Failed to load settings: {e}", exc_info=True)
    # Exit if settings fail to load, as the app cannot run.
    sys.exit(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage lifespan events for the web server.

    - Initializes MongoDB connection on startup.
    - Starts background worker tasks.
    - Closes MongoDB connection on shutdown.
    """
    logger.info("--- Web Server Lifespan Startup ---")
    await initialize_mongodb()
    logger.info("Web server workers connected to MongoDB.")
    
    # Start background worker tasks
    background_tasks = []
    if not settings.TESTING:
        logger.info("Starting background worker tasks...")
        from .background.rss_fetcher import schedule_rss_fetch
        from .worker import (
            update_signal_scores,
            schedule_narrative_updates,
            schedule_alert_checks
        )
        # Lazy import to avoid triggering tasks/__init__.py which imports celery
        from .tasks.price_monitor import get_price_monitor
        
        # Create background tasks with immediate execution for data availability
        price_monitor = get_price_monitor()
        background_tasks.extend([
            asyncio.create_task(price_monitor.start(), name="price_monitor"),
            asyncio.create_task(schedule_rss_fetch(1800, run_immediately=True), name="rss_fetcher"),
            asyncio.create_task(update_signal_scores(run_immediately=True), name="signal_scores"),
            asyncio.create_task(schedule_narrative_updates(600, run_immediately=True), name="narratives"),
            asyncio.create_task(schedule_alert_checks(120, run_immediately=True), name="alerts")
        ])
        logger.info(f"Started {len(background_tasks)} background worker tasks with immediate data fetch")
    
    yield
    
    # Shutdown
    logger.info("--- Web Server Lifespan Shutdown ---")
    
    # Cancel background tasks
    if background_tasks:
        logger.info(f"Cancelling {len(background_tasks)} background tasks...")
        for task in background_tasks:
            task.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)
        logger.info("Background tasks cancelled")
    
    await mongo_manager.aclose()
    logger.info("Web server MongoDB connections closed.")
    await price_service.close()
    logger.info("Price service client session closed.")


# Create FastAPI application
app = FastAPI(
    title="Crypto News Aggregator API",
    description="API for aggregating and analyzing cryptocurrency news",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    dependencies=None,  # We'll add dependencies to specific routers instead
)

# Rate limiting middleware (must be added before CORS)
app.add_middleware(RateLimitMiddleware)

# CORS middleware configuration
# Use regex pattern to match all localhost, 127.0.0.1, and Vercel deployments
# This avoids conflicts between allow_origins and allow_origin_regex
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(http://(localhost|127\.0\.0\.1):\d+|https://.*\.vercel\.app)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[API_KEY_NAME],
)

# Setup performance monitoring
setup_performance_monitoring(app)


# Add exception handler for 401 Unauthorized
@app.exception_handler(status.HTTP_401_UNAUTHORIZED)
async def unauthorized_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": "Missing or invalid API key"},
        headers={"WWW-Authenticate": "API-Key"},
    )


# Add exception handler for 403 Forbidden
@app.exception_handler(status.HTTP_403_FORBIDDEN)
async def forbidden_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"detail": "Invalid API key"},
        headers={"WWW-Authenticate": "API-Key"},
    )


# Include API routers
app.include_router(api_router)

app.include_router(openai_api.router, prefix="/v1/chat", tags=["OpenAI Compatibility"])

# Admin endpoints for cost monitoring
app.include_router(admin_api.router)


# Root health check for deployment platforms
@app.get("/")
async def root():
    return {"status": "ok", "service": "context-owl"}


# Health check endpoint is now in api/v1/health.py

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
