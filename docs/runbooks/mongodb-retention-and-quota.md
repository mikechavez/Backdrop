# MongoDB retention and quota operations

This runbook covers routine retention, index validation, and storage warnings introduced by TASK-128. It is not a substitute for the MongoDB Atlas storage meter: `dbStats` is an estimate and can differ from Atlas quota usage.

## Configuration

Set these as deployment variables (or in a local, untracked `.env`):

| Variable | Default | Meaning |
| --- | ---: | --- |
| `LLM_TRACE_RETENTION_DAYS` | `30` | TTL for LLM traces; must be positive. |
| `LLM_CACHE_RETENTION_DAYS` | `7` | Expiry for disposable LLM cache records. |
| `ARTICLE_TIER3_RETENTION_DAYS` | `0` | Tier-3 article cleanup age; `0` disables deletion. Tier 1/2, unclassified articles, and articles referenced by narratives are not eligible. |
| `MONGODB_CLEANUP_BATCH_SIZE` | `1000` | Maximum IDs selected per collection per cleanup run. |
| `MONGODB_STORAGE_QUOTA_MB` | `512` | Configured comparison value for the dbStats estimate, not Atlas-measured quota. Set to `0` to disable percentage calculations. |
| `MONGODB_STORAGE_WARNING_PERCENT` | `75` | Warning threshold for the estimated percentage. |
| `MONGODB_STORAGE_CRITICAL_PERCENT` | `90` | Critical threshold; must be at least the warning threshold. |

BugOps storage alerts are collected by the BugOps monitor. Confirm `BUGOPS_ENABLED=true` and that the monitor process is running in the target environment; alert events are persisted through BugOps even if Slack delivery is disabled or unavailable.

Never paste, print, or commit `MONGODB_URI`. The application and scripts read it from the environment and must not include it in diagnostics.

## Read-only audit

Run from the repository using an environment that has access to the intended cluster:

```bash
poetry run python scripts/mongodb_storage_audit.py --database crypto_news --show-indexes --show-age
```

Review collection and index sizes, trace/cache age, and TTL metadata. Treat the configured-quota percentage as an estimate only. Confirm actual usage, blocked-write state, and available headroom in MongoDB Atlas before deciding on tier changes or other recovery actions.

## Preview and execute one bounded cleanup batch

The default is a dry run. It reports the matched count and the number of IDs selected, capped at the configured batch size:

```bash
poetry run python scripts/mongodb_retention.py --database crypto_news
```

Review the result and the policy values before executing. Execution requires both flags and deletes only the selected `_id` values:

```bash
poetry run python scripts/mongodb_retention.py --database crypto_news --execute --confirm
```

Run the read-only audit again and compare counts/Atlas usage. Do not change the collection filters to an unbounded deletion. The scheduled Celery task runs one configured batch daily for expired traces and cache. Tier-3 article cleanup is disabled unless `ARTICLE_TIER3_RETENTION_DAYS` is explicitly set above zero; articles linked by any narrative are preserved.

Before enabling tier-3 cleanup, review dry-run counts and the retention window with the data owner. Do not reduce `LLM_TRACE_RETENTION_DAYS` without approval: MongoDB TTL expiration is asynchronous and irreversible; increasing the value later cannot restore deleted traces.

## TTL and application verification

- Check `GET /api/v1/health` for `checks.mongodb_retention`; it should report the configured trace TTL and the cache TTL index (`0` seconds on `expires_at`). A warning means inspect/startup logs and run the audit.
- Verify the indexes in Atlas or with the read-only audit. MongoDB TTL deletion is asynchronous; expiration does not imply immediate deletion.
- Restart/redeploy only through the normal deployment procedure. Confirm the service starts, the database/Redis checks pass, and no index/quota errors are logged.
- If startup cannot create noncritical trace/cache indexes, the API continues in degraded mode but logs an exception; resolve the index failure rather than suppressing it.

## Deployment and rollback

Deploy with defaults first; `ARTICLE_TIER3_RETENTION_DAYS=0` keeps article cleanup off. Confirm the health check and BugOps alert path before changing production retention values. To roll back code, redeploy the previous application version and disable the scheduled cleanup entry in that version if needed. Rollback cannot restore records already expired by TTL or deleted by a cleanup batch. Inspect existing index definitions before changing retention values.

## Escalation

Escalate when Atlas reports actual usage at/above the warning threshold, when usage is rising faster than retention frees it, or when Atlas reports writes blocked. Verify Atlas metrics and index footprint first. Consider upgrading the Atlas tier if normal retained data plus required indexes cannot fit with operational headroom; record approval and expected cost before changing the tier. Do not delete `daily_briefings`, active `narratives`, or BugOps evidence as routine cleanup.
