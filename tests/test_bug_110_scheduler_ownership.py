"""Repository-level regression tests for BUG-110.

Covers:
- The canonical production RSS ingestion scheduler is the FastAPI lifespan
  asyncio task (not Celery Beat), and Beat's fetch-news entry stays absent
  from the effective schedule so there is no duplicate-run risk.
- The two `fetch_news`-named Celery tasks that previously collided in the
  Celery task registry now register under distinct names.
- The FastAPI lifespan wires up the RSS fetch schedule via schedule_rss_fetch.

These tests require no Railway credentials, no live MongoDB/Redis, and no
production access.
"""

import ast
import inspect
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src" / "crypto_news_aggregator"


def test_beat_schedule_has_no_fetch_news_entry():
    """Celery Beat must not own RSS ingestion.

    fetch-news-every-3-hours was intentionally disabled (BUG-057) because
    its underlying sources are dead; production RSS ingestion is owned by
    the FastAPI lifespan schedule instead. If a "fetch-news*" entry
    reappears in the effective beat schedule, that's a silent second
    scheduler and must be caught here rather than discovered in production.
    """
    from crypto_news_aggregator.tasks.beat_schedule import get_schedule

    schedule = get_schedule()
    fetch_news_entries = [name for name in schedule if "fetch-news" in name]
    assert fetch_news_entries == [], (
        "Celery Beat schedule must not contain a fetch-news entry unless "
        "explicit duplicate-run protection against the FastAPI lifespan "
        "RSS scheduler has been added and documented (see BUG-110)."
    )


def test_celery_fetch_news_task_names_are_unique():
    """Regression test: tasks/news.py and tasks/fetch_news.py previously
    both registered a Celery task under the name "fetch_news", silently
    shadowing one another depending on import order. Only one may use that
    name; if others exist they must be distinctly named.
    """
    from crypto_news_aggregator.tasks.news import fetch_news as news_fetch_news
    from crypto_news_aggregator.tasks.fetch_news import fetch_news as source_fetch_news

    assert news_fetch_news.name == "fetch_news"
    assert source_fetch_news.name != "fetch_news"
    assert source_fetch_news.name == "fetch_news_source_based"


def test_fastapi_lifespan_owns_rss_fetch_schedule():
    """The FastAPI lifespan (main.py) must be the process that schedules
    background.rss_fetcher.schedule_rss_fetch. This is a static source
    check (not an import of main.py, which requires app settings/Sentry
    config) so it stays safe to run without production configuration.
    """
    main_source = (SRC / "main.py").read_text()
    assert "schedule_rss_fetch" in main_source
    assert "from .background.rss_fetcher import schedule_rss_fetch" in main_source


def test_worker_asyncio_main_is_not_referenced_by_procfile():
    """worker.py's asyncio main() independently schedules RSS fetch too,
    but must not be the process Railway actually runs, or ingestion would
    run twice with no duplicate-run protection. The Procfile's `worker`
    entry must invoke the Celery worker, not `python -m
    crypto_news_aggregator.worker`.
    """
    procfile = (REPO_ROOT / "Procfile").read_text()
    assert "crypto_news_aggregator.worker" not in procfile, (
        "worker.py's asyncio scheduler must not be started by Railway "
        "alongside the FastAPI lifespan scheduler without explicit "
        "duplicate-run protection (see BUG-110)."
    )
    worker_lines = [line for line in procfile.splitlines() if line.startswith("worker:")]
    assert len(worker_lines) == 1
    assert "celery" in worker_lines[0]
