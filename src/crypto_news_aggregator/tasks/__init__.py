# Initialize Sentry error monitoring (must be before Celery app creation)
try:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from crypto_news_aggregator.core.config import get_settings
    _sentry_settings = get_settings()
    if _sentry_settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=_sentry_settings.SENTRY_DSN,
            integrations=[CeleryIntegration()],
            traces_sample_rate=0.1,
            environment="production",
        )
except ImportError:
    # sentry_sdk not installed, skip initialization
    pass

from celery import Celery
from .celery_config import *
from .celery_config import get_beat_schedule

# Import all tasks to ensure they're registered
from .news import fetch_news, analyze_sentiment
from .process_article import process_article, process_new_articles
from .trends import update_trends, calculate_article_keywords
from .narrative_consolidation import consolidate_narratives_task
from .briefing_tasks import (
    generate_morning_briefing_task,
    generate_evening_briefing_task,
    cleanup_old_briefings_task,
    force_generate_briefing_task,
)

# FIXED: Import missing task modules
from .alert_tasks import check_price_alerts
from .fetch_news import fetch_news as fetch_news_task
from .warm_cache import warm_cache_task

app = Celery("crypto_news_aggregator")
app.config_from_object("crypto_news_aggregator.tasks.celery_config")

# Set the beat schedule after creating the app
app.conf.beat_schedule = get_beat_schedule()

# Explicitly import tasks to ensure they're registered
__all__ = [
    "app",
    "fetch_news",
    "analyze_sentiment",
    "process_article",
    "process_new_articles",
    "update_trends",
    "calculate_article_keywords",
    "generate_morning_briefing_task",
    "generate_evening_briefing_task",
    "cleanup_old_briefings_task",
    "force_generate_briefing_task",
    "consolidate_narratives_task",
    "check_price_alerts",
    "fetch_news_task",
    "warm_cache_task",
]

# FIXED: Auto-discover ALL task modules
app.autodiscover_tasks(
    [
        "crypto_news_aggregator.tasks.news",
        "crypto_news_aggregator.tasks.trends",
        "crypto_news_aggregator.tasks.briefing_tasks",
        "crypto_news_aggregator.tasks.alert_tasks",
        "crypto_news_aggregator.tasks.fetch_news",
        "crypto_news_aggregator.tasks.process_article",
        "crypto_news_aggregator.tasks.narrative_consolidation",
        "crypto_news_aggregator.tasks.warm_cache",
    ]
)

# This will be used by the worker and beat processes
if __name__ == "__main__":
    app.start()