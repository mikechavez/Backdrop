---
ticket_id: CHORE-001
title: Disable CoinGecko API requests
priority: medium
severity: low
status: COMPLETED
date_created: 2026-05-17
branch: chore/disable-coingecko-api
effort_estimate: small
---

# CHORE-001: Disable CoinGecko API requests

## Problem Statement

The application was making continuous requests to the CoinGecko API via the background price monitoring task. This was consuming API quota without providing critical value to the current product phase. Need a way to disable these requests while preserving the ability to re-enable them later.

---

## Context

The price monitoring system in `tasks/price_monitor.py` starts automatically during app lifespan and periodically checks cryptocurrency prices. This task was designed for price-based alerting but is not currently being used in the briefing pipeline.

Related files:
- `src/crypto_news_aggregator/main.py` — app lifespan startup
- `src/crypto_news_aggregator/tasks/price_monitor.py` — background task
- `src/crypto_news_aggregator/services/price_service.py` — API calls

---

## Task

Disable CoinGecko API requests with multiple layers of protection:

1. Disable background price monitor startup in app lifespan
2. Add configuration flag to disable API calls at service level
3. Ensure all price service methods return mock data when disabled
4. Include documentation of the changes

---

## Files to Create

None

---

## Files to Modify

```text
src/crypto_news_aggregator/main.py
src/crypto_news_aggregator/core/config.py
src/crypto_news_aggregator/services/price_service.py
```

---

## Do Not Modify

```text
src/crypto_news_aggregator/tasks/price_monitor.py
```

---

## Implementation Requirements

- [x] Comment out `price_monitor.start()` in `main.py` lifespan to prevent background startup
- [x] Add `COINGECKO_API_DISABLED` boolean config flag with environment variable support
- [x] Update `get_bitcoin_price()` to check `COINGECKO_API_DISABLED` and return mock data
- [x] Update `get_prices()` to check `COINGECKO_API_DISABLED` and return mock data
- [x] Update `get_markets_data()` to check `COINGECKO_API_DISABLED` and return mock data
- [x] Update `get_historical_prices()` to check `COINGECKO_API_DISABLED` and return mock data
- [x] Include all modified docs in commit

### Configuration

```text
COINGECKO_API_DISABLED=true  # Set to disable all CoinGecko API requests
```

### Commands to Run

```bash
# Verify the changes compiled
python -c "from crypto_news_aggregator.core.config import get_settings; s = get_settings(); print(f'COINGECKO_API_DISABLED: {s.COINGECKO_API_DISABLED}')"
```

---

## Verification

### Automated Verification

- [x] Code compiles without errors
- [x] Config flag is properly typed and documented
- [x] All price service methods have the disabled check

### Manual Verification

- [x] App starts without attempting CoinGecko API calls
- [x] Price endpoints return mock data when feature disabled
- [x] Flag can be toggled via environment variable

---

## Acceptance Criteria

- [x] Price monitor background task is disabled in app startup
- [x] COINGECKO_API_DISABLED config flag exists and can be set via env var
- [x] All price service methods return mock data when disabled
- [x] No real API calls are made to CoinGecko when disabled
- [x] Code can be easily re-enabled by uncommenting lines or setting env var to false

---

## Impact

**System Impact:**
- Eliminates CoinGecko API quota consumption during development/testing phases
- Preserves ability to re-enable price monitoring without code changes

**User Impact:**
- No impact to end users (price data not used in briefing pipeline)

**Developer Impact:**
- Simplifies local testing by removing external API dependency
- Can set `COINGECKO_API_DISABLED=true` in `.env` for faster startup

---

## Related Tickets

- None

---

## Completion Summary

- **Branch:** `chore/disable-coingecko-api`
- **Commit:** `7ad628a` — chore(api): disable CoinGecko API requests
- **Changes made:**
  - Commented out price_monitor import and startup in `main.py` lifespan
  - Added `COINGECKO_API_DISABLED` boolean config flag with env override
  - Updated 4 price service methods to check flag and return mock data
  - Included all modified documentation files in commit
- **Tests run:** Code compiles, config loads successfully
- **Manual verification:** Price endpoints return mock data, no API calls made
- **Deviations from plan:** None — implementation went smoothly

---

## Re-enabling Instructions

To re-enable CoinGecko API when ready:

**Option 1: Environment variable**
```bash
COINGECKO_API_DISABLED=false
```

**Option 2: Code change**
Uncomment lines 127-132 in `src/crypto_news_aggregator/main.py`

Both options preserve the original functionality without requiring additional refactoring.
