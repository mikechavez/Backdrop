---
id: BUG-057
type: bug
status: completed
priority: low
severity: low
created: 2026-04-03
updated: 2026-04-03
completed: 2026-04-03
---

# Disable dead fetch_news sources (CoinDesk JSON API, Bloomberg scraper) and unused price alerts

## Problem

The `fetch_news` Celery task runs every 3 hours and attempts to fetch articles from two API/scraper-based sources — CoinDesk (JSON API) and Bloomberg (HTML scraper). Both have been failing silently for an unknown period:

- **CoinDesk** (`/v2/news` JSON API): Returns HTTP 200 but the response body is HTML, not JSON. CoinDesk has walled off or deprecated this endpoint. The code detects this gracefully ("blocking detected") but fetches 0 articles.
- **Bloomberg** (`/markets` scraper): Returns HTTP 403 Forbidden. Bloomberg blocks automated requests.

These failures generate noisy error logs every 3 hours but have **zero user impact** because a separate RSS ingestion path (`background/rss_fetcher.py`) successfully fetches articles from CoinDesk (via `/feed`), CoinTelegraph, Decrypt, The Block, bitcoin.com, bitcoinmagazine, and cryptoslate. The articles page shows fresh content continuously.

Additionally, `check_price_alerts` runs every 5 minutes and is a no-op stub ("no-op until price API integrated"). It generates log noise with no value.

## Expected Behavior

- No error logs from dead news sources
- No wasted Celery worker cycles on tasks that produce nothing
- Infrastructure preserved for future API-based sources

## Actual Behavior

Every 3 hours, `fetch_news` logs:
```
WARNING: Could not decode JSON from CoinDesk. The service may be blocking requests.
INFO: Stopping fetch from CoinDesk due to HTML response (blocking detected)
ERROR: Error fetching from bloomberg: Failed to fetch Bloomberg markets page: 403
```

Every 5 minutes, `check_price_alerts` logs:
```
INFO: Price alert check completed (no-op until price API integrated)
```

## Environment

- Environment: production (Railway)
- User impact: none (RSS path covers all ingestion)
- Log noise: ~480 unnecessary log lines/day (fetch_news 8x/day + price_alerts 288x/day)

## Screenshots/Logs

See Celery worker logs from 2026-04-04 in conversation context.

---

## Resolution

### Approach

Option A: Disable dead sources and unused tasks but preserve all infrastructure. No files deleted, no task code removed. Changes are trivially reversible by re-adding schedule entries and updating the config default.

### Changes (3 files)

---

#### File 1: `src/crypto_news_aggregator/core/config.py`

**Change:** Set `ENABLED_NEWS_SOURCES` default to empty list.

**Find (line ~163):**
```python
    ENABLED_NEWS_SOURCES: list[str] = ["coindesk", "bloomberg"]
```

**Replace with:**
```python
    ENABLED_NEWS_SOURCES: list[str] = []  # Disabled: coindesk (JSON API dead), bloomberg (403). RSS covers ingestion.
```

**Why:** This is the safest kill switch. Even if the beat schedule somehow fires, `fetch_news` iterates `settings.ENABLED_NEWS_SOURCES` and will loop over nothing. Also prevents manual API triggers from accidentally hitting dead sources without an explicit `source_id` argument.

---

#### File 2: `src/crypto_news_aggregator/tasks/beat_schedule.py`

**Change 1:** Comment out the `fetch-news-every-3-hours` schedule entry.

**Find (lines ~23-33):**
```python
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
```

**Replace with:**
```python
        # DISABLED (BUG-057): Both sources dead — CoinDesk JSON API returns HTML, Bloomberg returns 403.
        # RSS fetcher (background/rss_fetcher.py) handles all article ingestion.
        # To re-enable: uncomment this block and add working sources to ENABLED_NEWS_SOURCES in config.py.
        # "fetch-news-every-3-hours": {
        #     "task": "fetch_news",
        #     "schedule": timedelta(hours=3),
        #     "args": (None,),
        #     "options": {
        #         "expires": 600,
        #         "time_limit": 1800,
        #     },
        # },
```

**Change 2:** Comment out the `check-price-alerts` schedule entry.

**Find (lines ~34-43):**
```python
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
```

**Replace with:**
```python
        # DISABLED (BUG-057): Price alerts are a no-op stub. No price API integrated yet.
        # To re-enable: uncomment this block when price alert functionality is implemented.
        # "check-price-alerts": {
        #     "task": "check_price_alerts",
        #     "schedule": timedelta(seconds=settings.PRICE_CHECK_INTERVAL),
        #     "options": {
        #         "expires": 240,
        #         "time_limit": 240,
        #         "queue": "alerts",
        #     },
        # },
```

---

#### File 3: `src/crypto_news_aggregator/tasks/beat_schedule.py` (same file, cleanup)

**Change 3:** The `timedelta` import is still needed by other potential uses, but verify no remaining schedule entries use it after commenting out `fetch-news-every-3-hours`. If no entries use `timedelta`, no change needed — keep the import for future re-enablement.

Actually: `timedelta` is not used by any remaining active schedule entries (all others use `crontab`). Leave the import in place — it's harmless and will be needed when re-enabling.

---

### Files Changed

| File | Change |
|------|--------|
| `src/crypto_news_aggregator/core/config.py` | `ENABLED_NEWS_SOURCES` default `[]` |
| `src/crypto_news_aggregator/tasks/beat_schedule.py` | Comment out `fetch-news-every-3-hours` and `check-price-alerts` |

### Files NOT changed (preserved for future use)

| File | Reason kept |
|------|-------------|
| `src/crypto_news_aggregator/tasks/fetch_news.py` | Task code intact; can be re-enabled with new sources |
| `src/crypto_news_aggregator/core/news_sources/__init__.py` | Registry intact |
| `src/crypto_news_aggregator/core/news_sources/coindesk.py` | Source class intact |
| `src/crypto_news_aggregator/core/news_sources/bloomberg.py` | Source class intact |
| `src/crypto_news_aggregator/core/news_sources/base.py` | Base class intact |

### Testing

1. **Deploy and verify no `fetch_news` or `check_price_alerts` tasks appear in worker logs** — monitor for 30 minutes after deploy. Neither task should fire.
2. **Verify RSS ingestion still works** — check articles page for fresh articles after deploy. Should be unaffected since RSS path is a completely separate code path.
3. **Verify briefings still generate** — manually trigger a briefing via `/admin/trigger-briefing?briefing_type=morning&force=true` and confirm it completes.
4. **Verify manual fetch_news still works if called with explicit source** — this should fail gracefully with "no enabled sources" if called without a `source_id`, confirming the config change works.

### Rollback

Re-enable by:
1. Setting `ENABLED_NEWS_SOURCES=coindesk,bloomberg` in Railway env vars (overrides the code default)
2. Uncommenting the two schedule entries in `beat_schedule.py`