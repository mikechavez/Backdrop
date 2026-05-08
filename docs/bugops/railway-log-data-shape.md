# Railway Log Data Shape — Spike Notes

**Date:** 2026-05-08
**Service:** `crypto-news-aggregator` (single Railway service, production environment)
**Commands run:**

```bash
railway logs --lines 200
railway logs --lines 200 --service crypto-news-aggregator
railway logs --lines 200 --filter "@level:error"
railway logs --lines 200 --json
railway logs --help
```

Service flags `--service web`, `--service worker`, `--service beat` all returned "Service not found".
The project uses a single Railway service named `crypto-news-aggregator`.

---

## Analysis Questions

### Does output include service/process metadata?

Partially. The Python logger name embedded in the message includes a module path that maps to the logical service role (e.g., `src.crypto_news_aggregator.worker`, `crypto_news_aggregator.services.entity_alert_service`). The Railway CLI itself does not inject a separate `service` field into plain-text output. With `--json`, the schema is `{"message": "...", "timestamp": "...", "level": "..."}` — no Railway-side service/replica field beyond that.

Gunicorn startup lines use a different format: `[timestamp] [pid] [LEVEL] message`.

### Does output include timestamps?

Yes, in two formats:

1. **Gunicorn/uvicorn startup lines:** `[2026-05-08 20:19:22 +0000] [pid] [LEVEL] message`
2. **Python app logs:** `YYYY-MM-DD HH:MM:SS,mmm - logger_name - LEVEL - message`
3. **JSON mode (`--json`):** ISO 8601 nanosecond-precision `timestamp` field, e.g. `"2026-05-08T20:24:54.394057592Z"`. This is the most reliable timestamp for ingestion.
4. **Railway platform messages** (rate limit warnings): no timestamp — bare text only.

### Are multiline stack traces preserved or split line-by-line?

**Split line-by-line.** Each line of a Python traceback arrives as a separate log entry with the same `level: info`. The `Traceback (most recent call last):` anchor line and the final `ExceptionClass: message` line are separate entries. A consumer must correlate contiguous non-timestamped lines following a traceback anchor to reconstruct the full trace.

### Can logs be fetched by time window or only by line count?

Line count only via the `--lines` / `--tail` flag (`-n`). No `--since` or `--until` flags exist in the current CLI version. The `--filter` flag supports attribute filters (`@level:error`) and keyword search but not time ranges. Time-window fetching is not supported by the Railway CLI; it would require the Railway API directly.

### Can the command run non-interactively in a Railway service?

No. `railway logs` requires local Railway CLI authentication (`railway login`) and an active project link. It cannot run inside a Railway service container. For now, log access is local/manual only. Future Railway log ingestion would need to use the Railway GraphQL or REST API with a service token.

### What fields can map directly into `bug_alert_events`?

| Log field | Maps to |
|---|---|
| Timestamp (Python format or JSON ISO) | `created_at` |
| `LEVEL` token (`WARNING`, `ERROR`) | `severity` (after mapping) |
| Logger name (e.g., `cost_tracker`, `worker`) | `service` (inferred) |
| Message text | `raw_sample_ref` / description |

### What fields are missing and would need inference?

| Missing field | Inference strategy |
|---|---|
| `source_id` | Pattern match on message text → named pattern slug |
| `alert_type` | Regex classifier on message: `AutoReconnect` → `db_connection_error`, `Budget cache stale` → `budget_warning`, `rate limit` → `platform_warning`, etc. |
| `domain` | Logger module path → map module prefix to domain list |
| `operation` | None or inferred from logger name suffix (e.g., `narrative_service` → `narrative_detection`) |
| `dedupe_key` | Constructed: `railway_logs:<pattern_name>:<service>:<YYYY-MM-DD>:<HH>` |

### What are the first 3 log patterns worth monitoring later?

1. **`pymongo.errors.AutoReconnect`** — MongoDB connection drops. Terminal line of a multiline stack trace. High-severity; indicates Atlas connectivity loss. Pattern: match `AutoReconnect:` in message.
2. **`Soft limit active`** — LLM budget enforcement activating. Appears in `cost_tracker` WARNING lines. Blocks narrative detection and other non-critical operations. Pattern: match `Soft limit active` or `blocking non-critical`.
3. **`Railway rate limit of 500 logs/sec reached`** — Platform-level log dropping. Means log output is being suppressed; errors may be invisible. Pattern: match `Railway rate limit`.

---

## Normalized Mapping Proposal

```python
source_type = "railway_logs"

# Pattern: MongoDB AutoReconnect
source_id     = "railway_logs.mongo_autoreconnect"
alert_type    = "db_connection_error"
severity      = "high"
domain        = ["infrastructure", "database"]
service       = None  # single-service project; could add when multi-service
operation     = None  # not reliably extractable from these lines
raw_sample_ref = "pymongo.errors.AutoReconnect: <MONGO_HOST>:27017: connection closed ..."
dedupe_key    = "railway_logs:mongo_autoreconnect:None:2026-05-08:20"

# Pattern: LLM budget soft-limit blocking
source_id     = "railway_logs.budget_soft_limit"
alert_type    = "budget_warning"
severity      = "warning"
domain        = ["llm", "cost"]
service       = None
operation     = "narrative_detection"  # extractable from log message
raw_sample_ref = "Soft limit active (monthly_soft_limit): blocking non-critical 'narrative_detection'"
dedupe_key    = "railway_logs:budget_soft_limit:None:2026-05-08:20"

# Pattern: Railway platform log-rate-limit
source_id     = "railway_logs.platform_log_rate_limit"
alert_type    = "platform_warning"
severity      = "warning"
domain        = ["infrastructure"]
service       = None
operation     = None
raw_sample_ref = "Railway rate limit of 500 logs/sec reached for replica. Messages dropped: 406"
dedupe_key    = "railway_logs:platform_log_rate_limit:None:2026-05-08:20"
```

---

## SignalSource Interface Compatibility

`RailwayLogSignalSource` satisfies `SignalSource` as-is (has `source_type` and async `collect()`). No interface changes required.

Gaps to address in the future implementation ticket:

- **Log fetch:** needs Railway API token (not CLI) for non-interactive use.
- **Stack trace reconstruction:** multiline grouping by time proximity required before pattern matching.
- **Timestamp parsing:** must handle both Python `%Y-%m-%d %H:%M:%S,%f` and gunicorn `[%Y-%m-%d %H:%M:%S +0000]` formats; JSON mode is preferred.
- **Duplicate suppression:** the same error floods repeatedly (e.g., 4× per minute for worker replicas); dedupe_key hourly bucketing is essential.
- **Bare platform messages:** Railway rate-limit warnings carry no timestamp and arrive as plain text — they need special-cased detection.

---

## Raw Sample

See `tests/bugops/fixtures/railway_logs_sample.txt`.
