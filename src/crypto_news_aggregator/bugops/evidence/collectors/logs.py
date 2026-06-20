"""LogCollector for Railway log excerpts with redaction."""

import logging
from datetime import datetime, timedelta

from ...clients.railway import RailwayClient
from ...models import BugCase, EvidenceReferenceAllocator, LogExcerptSection
from ...store import BugOpsStore
from ..base import EvidenceCollectorBase
from ..redaction import LogRedactor

logger = logging.getLogger(__name__)

SERVICES = ["fastapi", "celery_worker", "celery_scheduler"]


class LogCollector:
    """Collects Railway log excerpts with redaction."""

    collector_name = "logs"

    def __init__(
        self,
        railway_client: RailwayClient,
        redactor: LogRedactor,
        settings,
    ):
        """Initialize the collector."""
        self.railway = railway_client
        self.redactor = redactor
        self.settings = settings

    async def collect(
        self,
        bugcase: BugCase,
        pack_id: str,
        store: BugOpsStore,
        ref_allocator: EvidenceReferenceAllocator,
    ) -> None:
        """
        Collect log excerpts from Railway for all services.

        Window: first_seen_at ± window_minutes to last_seen_at ± window_minutes.
        Lines redacted before storage. Truncation metadata recorded per service.
        """
        window_minutes = self.settings.BUGOPS_LOG_WINDOW_MINUTES
        line_cap = self.settings.BUGOPS_LOG_LINE_CAP

        # Expand window around the full incident duration
        window_start = bugcase.first_seen_at - timedelta(minutes=window_minutes)
        window_end = (
            (bugcase.last_seen_at or bugcase.first_seen_at)
            + timedelta(minutes=window_minutes)
        )

        log_sections = []
        total_redactions = 0
        missing_sections = []

        for service in SERVICES:
            try:
                lines, was_truncated = await self.railway.get_logs(
                    service_name=service,
                    start_time=window_start,
                    end_time=window_end,
                    line_cap=line_cap,
                )

                redacted_lines, redaction_count = self.redactor.redact_lines(lines)
                total_redactions += redaction_count

                section = LogExcerptSection(
                    service=service,
                    lines_fetched=len(lines),
                    lines_stored=len(redacted_lines),
                    truncated=was_truncated,
                    window_start=window_start,
                    window_end=window_end,
                    excerpts=redacted_lines,
                )
                log_sections.append(section.model_dump())

            except Exception as e:
                missing_sections.append(
                    {
                        "section": f"logs.{service}",
                        "reason": f"Railway API error: {type(e).__name__}: {str(e)[:100]}",
                        "attempted_at": datetime.utcnow().isoformat(),
                    }
                )
                logger.error(f"LogCollector: failed to fetch logs for {service}: {e}")

        section_data = {
            "log_excerpts": log_sections,
            "redactions_applied": total_redactions,
        }

        if missing_sections:
            section_data["sections_missing"] = missing_sections

        # Add one evidence reference for logs overall
        if log_sections:
            ref_id = ref_allocator.next_ref()
            total_lines = sum(s["lines_stored"] for s in log_sections)
            truncated_services = [s["service"] for s in log_sections if s["truncated"]]
            ref_description = (
                f"Log excerpts: {total_lines} lines across {len(log_sections)} services"
                + (
                    f" (truncated: {', '.join(truncated_services)})"
                    if truncated_services
                    else ""
                )
            )
            section_data["evidence_references"] = {
                ref_id: {
                    "description": ref_description,
                    "section": "log_excerpts",
                }
            }

        await store.update_evidence_pack_section(pack_id, section_data)

        logger.info(
            f"LogCollector: collected {len(log_sections)} service logs, "
            f"{total_redactions} redactions"
        )
