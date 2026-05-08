# BugOps Observability

**Date:** 2026-05-08  
**Version:** Sprint 018  
**Audience:** Developers, on-call operators

---

## Logging

BugOps logs to the standard application logger under the module path `crypto_news_aggregator.bugops`.

### Log Patterns

All log entries follow a structured format:

```
{timestamp} - {module} - {level} - {message}
```

### Key Events

#### Monitor Startup

```
2026-05-08 14:05:00,123 - crypto_news_aggregator.bugops.monitor - INFO - bugops:monitor:startup enabled_sources=2 poll_interval_sec=60
```

Signals:
- `enabled_sources` = number of active signal sources
- `poll_interval_sec` = polling interval from config

#### Signal Collection

```
2026-05-08 14:05:30,456 - crypto_news_aggregator.bugops.signal_sources.llm_traces - INFO - bugops:signal_source:collect source=llm_traces alert_count=1 duration_ms=123
```

Signals:
- `source` = signal source name
- `alert_count` = number of alerts detected this cycle
- `duration_ms` = time to run `collect()`

#### Alert Processing

```
2026-05-08 14:05:31,789 - crypto_news_aggregator.bugops.store - INFO - bugops:alert:process dedupe_key=llm_traces:cost_runaway:2026-05-08:14 case_state=NEW
```

Signals:
- `dedupe_key` = alert dedupe key
- `case_state` = `NEW` (new case created) or `EXISTING` (attached to open case)

#### Case Creation

```
2026-05-08 14:05:31,890 - crypto_news_aggregator.bugops.store - INFO - bugops:case:created case_id=...ObjectId... dedupe_key=llm_traces:cost_runaway:2026-05-08:14 severity=critical
```

Signals:
- `case_id` = MongoDB ObjectId of new case
- `dedupe_key` = case dedupe key
- `severity` = alert severity

#### Alert Attachment (Existing Case)

```
2026-05-08 14:10:15,234 - crypto_news_aggregator.bugops.store - INFO - bugops:case:attached case_id=...ObjectId... alert_id=...ObjectId... count_attached=2
```

Signals:
- `case_id` = case being updated
- `alert_id` = alert being attached
- `count_attached` = total alerts now attached to case

#### Slack Notification Sent

```
2026-05-08 14:05:32,567 - crypto_news_aggregator.bugops.slack - INFO - bugops:slack:sent case_id=...ObjectId... severity=critical duration_ms=234
```

Signals:
- `case_id` = case notified
- `severity` = case severity
- `duration_ms` = HTTP request duration

#### Slack Notification Error

```
2026-05-08 14:05:33,890 - crypto_news_aggregator.bugops.slack - ERROR - bugops:slack:error case_id=...ObjectId... error=timeout duration_ms=10000
```

Signals:
- `case_id` = case notification failed
- `error` = error type (timeout, connection, http_error, webhook_not_configured)
- `duration_ms` = request duration (if applicable)

**Critical:** Slack errors are non-fatal. Case is still created; monitor continues.

#### Report Generation

```
2026-05-08 14:05:34,123 - crypto_news_aggregator.bugops.reports - INFO - bugops:report:generated case_id=...ObjectId... report_length=2456
```

Signals:
- `case_id` = case for which report was generated
- `report_length` = length of generated Markdown report

---

## Metrics (Future)

Sprint 018 does not emit metrics; future sprints may add:

- `bugops.signal.alerts_detected` (counter)
- `bugops.case.created` (counter)
- `bugops.case.alert_attached` (counter)
- `bugops.slack.notification_sent` (counter)
- `bugops.slack.notification_failed` (counter)
- `bugops.poll_cycle_duration_ms` (histogram)

---

## Error Handling

Errors in BugOps do not crash the monitor. All error conditions log and continue:

| Error | Log Level | Recovery |
|-------|-----------|----------|
| Signal source fails | ERROR | Skip source, continue with next |
| Store operation fails | ERROR | Skip alert, continue with next |
| Slack notification fails | ERROR | Case still created, continue |
| Missing config on startup | FATAL | Monitor exits; requires manual restart |
| Invalid dedupe_key format | WARN | Process alert anyway, use as-is |

### Startup Errors (Fatal)

Monitor exits if:
- `BUGOPS_ENABLED=true` but `BUGOPS_SLACK_WEBHOOK_URL` is missing/invalid
- MongoDB connection fails during store initialization
- Settings validation fails

---

## Debugging

To debug a specific issue:

1. **Enable debug logging:** Set `LOG_LEVEL=DEBUG` to see all log entries
2. **Check BugOps logs:** `grep "bugops:" application.log`
3. **Query the database:** Check `bug_alert_events` and `bug_cases` collections
4. **Review deterministic report:** Check `bug_cases.deterministic_report` field
5. **Test signal source:** Run signal source `collect()` manually in Python REPL

### Common Issues

**No alerts being detected:**
- Confirm `BUGOPS_ENABLED=true`
- Confirm signal sources are enabled in config
- Check `bugops:signal_source:collect` log entries
- Verify thresholds in signal source (e.g., cost must exceed $0.25 for critical)

**Case not created:**
- Confirm alert was detected (check logs)
- Confirm `bug_alert_events` collection has the alert
- Check dedupe_key format matches expected pattern
- Confirm store connection is working

**Slack notification not sent:**
- Confirm `BUGOPS_SLACK_ENABLED=true`
- Confirm `BUGOPS_SLACK_WEBHOOK_URL` is valid
- Check `bugops:slack:error` log entries for error details
- Test webhook manually: `curl -X POST $BUGOPS_SLACK_WEBHOOK_URL -d '{"text": "test"}'`

**No deterministic report:**
- Confirm `bugops:report:generated` log entry exists
- Check `bug_cases.deterministic_report` field is populated
- Confirm `bug_alert_events` has alerts attached to case

---

## Related Documents

- `00-bugops-system-overview.md` — System design
- `10-bugops-runtime-model.md` — Runtime behavior
- `20-bugops-data-model.md` — Data schema
- `80-bugops-use-cases.md` — Example workflows
- `90-bugops-critiques-and-open-questions.md` — Known limitations
