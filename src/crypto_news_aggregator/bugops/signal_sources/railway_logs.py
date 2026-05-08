"""Railway log signal source for BugOps.

Real log shape observed 2026-05-08 (see docs/bugops/railway-log-data-shape.md):
- Two text formats: Python logging and gunicorn startup lines; JSON mode available via --json.
- JSON schema: {"message": str, "timestamp": ISO8601-nanosecond, "level": str}
- Multiline stack traces arrive line-by-line — no structural grouping from Railway.
- Railway platform warnings (rate-limit) carry no timestamp and are bare text.
- Single Railway service named "crypto-news-aggregator"; no separate web/worker/beat services.
"""

import re
from datetime import datetime, timezone
from typing import List
from ..models import BugAlertEventCreate


# Patterns ordered by monitoring priority (see data-shape doc).
_PATTERNS = [
    {
        # Priority 1: MongoDB connection drop — multiline trace; terminal line is the signal.
        "name": "mongo_autoreconnect",
        "regex": re.compile(r"pymongo\.errors\.AutoReconnect"),
        "alert_type": "db_connection_error",
        "severity": "high",
        "domain": ["infrastructure", "database"],
    },
    {
        # Priority 2: LLM budget soft-limit enforcement blocking operations.
        "name": "budget_soft_limit",
        "regex": re.compile(r"Soft limit active \("),
        "alert_type": "budget_warning",
        "severity": "warning",
        "domain": ["llm", "cost"],
    },
    {
        # Priority 3: Railway platform dropping log lines — errors may go silent.
        "name": "platform_log_rate_limit",
        "regex": re.compile(r"Railway rate limit of \d+ logs/sec reached"),
        "alert_type": "platform_warning",
        "severity": "warning",
        "domain": ["infrastructure"],
    },
]

# Regex for the Python logging timestamp format emitted by the app.
_PY_LOG_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+) - ([\w\.]+) - \w+ - "
)


def _parse_operation(logger_name: str) -> str | None:
    # TODO: Expand map as more logger names are observed.
    _map = {
        "narrative_service": "narrative_detection",
        "entity_alert_service": "alert_detection",
        "cost_tracker": None,
    }
    for key, op in _map.items():
        if key in logger_name:
            return op
    return None


def _dedupe_key(pattern_name: str, ts: datetime) -> str:
    hour_str = ts.strftime("%Y-%m-%d:%H")
    return f"railway_logs:{pattern_name}:None:{hour_str}"


class RailwayLogSignalSource:
    """Monitor Railway deployment logs for operational signals."""

    source_type = "railway_logs"

    async def collect(self) -> List[BugAlertEventCreate]:
        """Collect signals from Railway logs.

        TODO (future ticket): Implement log fetching via Railway API (not CLI).
              The CLI requires local auth and cannot run inside a Railway container.
              Use a Railway API token stored in env and the Railway GraphQL/REST API
              to fetch recent log lines non-interactively.

        TODO: Add multiline stack trace reconstruction — group consecutive lines
              that lack a Python-logging timestamp prefix into a single trace block
              before pattern matching.

        TODO: Handle both timestamp formats:
              - Python app: "YYYY-MM-DD HH:MM:SS,mmm - logger - LEVEL - msg"
              - Gunicorn:   "[YYYY-MM-DD HH:MM:SS +0000] [pid] [LEVEL] msg"
              - JSON mode (preferred): {"message":..., "timestamp": ISO8601, "level":...}

        TODO: Deduplicate — the same error fires 4+ times per minute across replicas.
              Hourly dedupe_key bucketing is required before writing to bug_alert_events.
        """
        # TODO: Replace stub with Railway API call.
        raw_lines: list[str] = []

        events: list[BugAlertEventCreate] = []
        for line in raw_lines:
            for pattern in _PATTERNS:
                if not pattern["regex"].search(line):
                    continue

                m = _PY_LOG_RE.match(line)
                ts = datetime.now(timezone.utc)
                operation = None
                if m:
                    # TODO: parse ts from m.group(1) once fetch is wired up
                    operation = _parse_operation(m.group(2))

                events.append(
                    BugAlertEventCreate(
                        source_type=self.source_type,
                        source_id=f"railway_logs.{pattern['name']}",
                        alert_type=pattern["alert_type"],
                        severity=pattern["severity"],
                        domain=pattern["domain"],
                        service=None,
                        operation=operation,
                        raw_sample_ref=line[:500],
                        dedupe_key=_dedupe_key(pattern["name"], ts),
                    )
                )
                break  # one pattern match per line

        return events
