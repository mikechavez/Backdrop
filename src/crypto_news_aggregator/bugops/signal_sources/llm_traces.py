"""LLM trace signal source for BugOps."""

from typing import List
from datetime import datetime, timedelta, timezone
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
from ..models import BugAlertEventCreate, AlertSeverity
from ...db.mongodb import mongo_manager
from ...core.config import get_settings

logger = logging.getLogger(__name__)


class LLMTraceCostSignalSource:
    """Monitor LLM traces for cost runaway signals."""

    source_type = "llm_traces"

    async def collect(self) -> List[BugAlertEventCreate]:
        """Collect cost runaway signals from LLM traces."""
        try:
            settings = get_settings()
            db = await mongo_manager.get_async_database()

            now = datetime.now(timezone.utc)
            window_start_5min = now - timedelta(minutes=5)
            window_start_60min = now - timedelta(minutes=60)

            traces_5min = await db.llm_traces.find(
                {"timestamp": {"$gte": window_start_5min}}
            ).to_list(None)

            traces_60min = await db.llm_traces.find(
                {"timestamp": {"$gte": window_start_60min}}
            ).to_list(None)

            if not traces_5min:
                return []

            last_5_min_spend = sum(t.get("cost", 0) for t in traces_5min)
            last_60_min_spend = sum(t.get("cost", 0) for t in traces_60min)
            projected_hourly_spend = (last_5_min_spend / 5) * 60

            threshold_5min = settings.BUGOPS_COST_5MIN_THRESHOLD_USD
            threshold_60min = settings.BUGOPS_PROJECTED_HOURLY_THRESHOLD_USD

            critical_breach = last_5_min_spend >= threshold_5min
            warning_breach = projected_hourly_spend >= threshold_60min and not critical_breach

            if not (critical_breach or warning_breach):
                return []

            severity = AlertSeverity.CRITICAL if critical_breach else AlertSeverity.WARNING

            top_operations = self._get_top_items(traces_5min, "operation")
            top_models = self._get_top_items(traces_5min, "model")

            dedupe_key = self._get_dedupe_key(now)

            alert_id = f"alert_{dedupe_key}_{int(now.timestamp())}"

            correlation_keys = ["domain:llm", "domain:cost"]
            operation = top_operations[0] if top_operations else None
            model = top_models[0] if top_models else None

            if operation:
                correlation_keys.append(f"operation:{operation}")
            if model:
                correlation_keys.append(f"model:{model}")

            metric = {
                "last_5_min_spend": float(last_5_min_spend),
                "last_60_min_spend": float(last_60_min_spend),
                "projected_hourly_spend": float(projected_hourly_spend),
                "threshold_5min": float(threshold_5min),
                "threshold_projected_hourly": float(threshold_60min),
                "top_operations": top_operations,
                "top_models": top_models,
                "window_start": window_start_5min.isoformat(),
                "window_end": now.isoformat(),
            }

            title = f"LLM Cost Runaway ({'Critical' if critical_breach else 'Warning'})"
            summary = f"5min spend: ${last_5_min_spend:.2f}, projected hourly: ${projected_hourly_spend:.2f}"

            event = BugAlertEventCreate(
                alert_id=alert_id,
                source_type="llm_traces",
                source_id="llm_traces.cost_runaway",
                alert_type="cost_runaway",
                severity=severity,
                title=title,
                summary=summary,
                domain=["llm", "cost"],
                operation=operation,
                model=model,
                dedupe_key=dedupe_key,
                correlation_keys=correlation_keys,
                metric=metric,
            )

            return [event]

        except Exception as e:
            logger.error(f"Error collecting LLM cost signals: {e}", exc_info=True)
            return []

    def _get_top_items(self, traces: List[dict], field: str, limit: int = 3) -> List[str]:
        """Get top N items by cost for a given field."""
        items_by_cost = {}
        for trace in traces:
            if field not in trace or trace[field] is None:
                continue
            item = trace[field]
            cost = trace.get("cost", 0)
            items_by_cost[item] = items_by_cost.get(item, 0) + cost

        sorted_items = sorted(items_by_cost.items(), key=lambda x: x[1], reverse=True)
        return [item for item, _ in sorted_items[:limit]]

    def _get_dedupe_key(self, dt: datetime) -> str:
        """Generate UTC hour-based dedupe key."""
        return f"llm_traces:cost_runaway:{dt.strftime('%Y-%m-%d')}:{dt.strftime('%H')}"
