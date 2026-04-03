"""Celery Beat schedule configuration."""

from datetime import timedelta
from celery.schedules import crontab
from ..core.config import get_settings

# settings = get_settings()  # Removed top-level settings; use lazy initialization in functions as needed.


# The beat schedule is a dictionary that contains the schedule of periodic tasks
# See: https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
def get_schedule():
    """Get the beat schedule configuration.

    This function allows for dynamic schedule configuration based on settings.
    """
    settings = get_settings()
    schedule = {
        # Fetch news from all RSS sources every 3 hours
        # RSS feeds don't update frequently; 3-hour interval = 8 cycles/day, 100-500 articles/cycle
        # Task name must match @shared_task(name="fetch_news") decorator in tasks/news.py
        "fetch-news-every-3-hours": {
            "task": "fetch_news",
            "schedule": timedelta(hours=3),
            "args": (None,),  # None means fetch from all enabled sources
            "options": {
                "expires": 600,  # 10 minutes to prevent duplicate tasks
                "time_limit": 1800,  # 30 minutes hard limit
            },
        },
        # Check and process price alerts every 5 minutes
        "check-price-alerts": {
            "task": "check_price_alerts",  # Task registered with short name in tasks/__init__.py
            "schedule": timedelta(seconds=settings.PRICE_CHECK_INTERVAL),
            "options": {
                "expires": 240,  # 4 minutes
                "time_limit": 240,  # 4 minutes
                "queue": "alerts",
            },
        },
        # ============================================================
        # Briefing Tasks - Daily crypto briefings at 8 AM and 8 PM EST
        # Afternoon briefing available via manual API trigger only
        # ============================================================
        # Morning briefing at 8:00 AM EST (13:00 UTC, or 12:00 UTC during DST)
        # Using America/New_York timezone for automatic DST handling
        "generate-morning-briefing": {
            "task": "generate_morning_briefing",
            "schedule": crontab(
                hour=8,
                minute=0,
                # Note: Celery uses the configured timezone (UTC by default)
                # 8 AM EST = 13:00 UTC (or 12:00 UTC during EDT)
                # For production, set celery timezone to America/New_York
            ),
            "kwargs": {"force": False},  # Prevent duplicates for scheduled tasks
            "options": {
                "expires": 3600,  # 1 hour
                "time_limit": 600,  # 10 minutes
            },
        },
        # Evening briefing at 8:00 PM EST (01:00 UTC next day, or 00:00 UTC during DST)
        "generate-evening-briefing": {
            "task": "generate_evening_briefing",
            "schedule": crontab(
                hour=20,
                minute=0,
            ),
            "kwargs": {"force": False},  # Prevent duplicates for scheduled tasks
            "options": {
                "expires": 3600,  # 1 hour
                "time_limit": 600,  # 10 minutes
            },
        },
        # Weekly cleanup of old briefings (every Sunday at 3 AM EST)
        "cleanup-old-briefings": {
            "task": "cleanup_old_briefings",
            "schedule": crontab(
                hour=3,
                minute=0,
                day_of_week="sunday",
            ),
            "args": (30,),  # Keep 30 days of briefings
            "options": {
                "expires": 3600,  # 1 hour
                "time_limit": 300,  # 5 minutes
            },
        },
        # Consolidate duplicate narratives every hour
        "consolidate-narratives": {
            "task": "consolidate_narratives",  # Task registered with short name in tasks/__init__.py
            "schedule": crontab(minute=0),  # Every hour at :00
            "options": {
                "expires": 3600,  # 1 hour timeout
                "time_limit": 3600,  # 1 hour
            },
        },
        # Warm entity articles cache every 10 minutes
        "warm-entity-articles-cache": {
            "task": "warm_cache",  # Task registered with short name in tasks/__init__.py
            "schedule": crontab(minute="*/10"),  # Every 10 minutes
            "options": {
                "expires": 600,  # 10 minutes
                "time_limit": 300,  # 5 minutes max execution
            },
        },
        # Send daily pipeline digest via Slack at 9:00 AM EST (after morning briefing)
        "send-daily-digest": {
            "task": "send_daily_digest",
            "schedule": crontab(hour=9, minute=0),  # 9:00 AM Eastern
            "options": {
                "expires": 3600,  # 1 hour
                "queue": "default",
            },
        },
    }

    return schedule
