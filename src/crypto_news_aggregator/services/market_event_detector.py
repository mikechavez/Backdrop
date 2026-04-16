"""
Market Event Detector for identifying high-impact market shocks.

Detects critical market events like liquidation cascades and flash crashes
that should be prioritized in briefings despite lower recency scores.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from math import exp

from crypto_news_aggregator.db.mongodb import mongo_manager
from crypto_news_aggregator.db.operations.narratives import upsert_narrative

logger = logging.getLogger(__name__)


class MarketEventDetector:
    """Detects market shock events that warrant special briefing inclusion."""

    # Thresholds for market event detection
    LIQUIDATION_ARTICLE_THRESHOLD = 4  # Min articles in 24h window
    LIQUIDATION_VOLUME_THRESHOLD = 500_000_000  # $500M minimum
    MULTI_ENTITY_THRESHOLD = 3  # Articles affecting 3+ coins
    EVENT_DETECTION_WINDOW_HOURS = 24
    EVENT_RECENCY_BOOST = 1.0  # Boost recency score by this amount

    # Keywords for different event types
    LIQUIDATION_KEYWORDS = {
        "liquidation", "liquidations", "liquidated", "cascade", "cascading",
        "margin call", "forced liquidation", "flash crash", "market crash",
        "sell-off", "massive liquidations", "capitulation"
    }

    CRASH_KEYWORDS = {
        "crash", "crashed", "plunge", "plunged", "collapse", "collapsed",
        "flash crash", "market crash", "sharp decline", "severe drop"
    }

    EXPLOIT_KEYWORDS = {
        "exploit", "exploited", "vulnerability", "hacked", "hack", "breach",
        "security incident", "stolen", "lost funds", "stolen funds"
    }

    async def detect_market_events(self) -> List[Dict[str, Any]]:
        """
        Detect market shock events from recent articles.

        Returns:
            List of detected market events with details

        NOTE: DISABLED (BUG-083). The detection logic has six compounding
        failures — OR keyword matching, no relevance validation, blind volume
        extraction, low thresholds, missing narrative metadata, and force-boosted
        ranking — that cause phantom narratives with fabricated financial figures
        to lead every briefing. Disabled until a proper rebuild (TASK-072).
        """
        logger.info("Market event detector disabled (BUG-083). Returning empty list.")
        return []

        # --- DISABLED CODE BELOW (BUG-083) ---
        db = await mongo_manager.get_async_database()
        articles_collection = db.articles
        now = datetime.now(timezone.utc)

        detected_events = []

        # Check for liquidation cascades
        liquidation_event = await self._detect_liquidation_cascade(
            articles_collection, now
        )
        if liquidation_event:
            detected_events.append(liquidation_event)
            logger.info(
                f"Detected liquidation cascade: ${liquidation_event['estimated_volume']:,.0f} "
                f"({liquidation_event['article_count']} articles)"
            )

        # Check for flash crashes
        crash_event = await self._detect_market_crash(articles_collection, now)
        if crash_event:
            detected_events.append(crash_event)
            logger.info(
                f"Detected market crash event: {crash_event['article_count']} articles"
            )

        # Check for exploits
        exploit_event = await self._detect_exploit_event(articles_collection, now)
        if exploit_event:
            detected_events.append(exploit_event)
            logger.info(
                f"Detected exploit event: {exploit_event['article_count']} articles"
            )

        return detected_events

    async def _detect_liquidation_cascade(
        self, articles_collection, now: datetime
    ) -> Optional[Dict[str, Any]]:
        """Detect high-velocity liquidation events."""
        window_start = now - timedelta(hours=self.EVENT_DETECTION_WINDOW_HOURS)

        # Search for liquidation mentions in recent articles
        query = {
            "published_at": {"$gte": window_start},
            "$text": {"$search": " ".join(self.LIQUIDATION_KEYWORDS)},
        }

        articles = await articles_collection.find(query).to_list(length=100)

        if len(articles) < self.LIQUIDATION_ARTICLE_THRESHOLD:
            return None

        # Extract entities and estimate volume
        entities = set()
        estimated_volume = 0

        for article in articles:
            # Collect entities (entities can be strings or dicts with 'name' field)
            if article.get("entities"):
                for entity in article["entities"][:5]:
                    if isinstance(entity, dict):
                        entity_name = entity.get("name") or entity.get("entity", "")
                    else:
                        entity_name = str(entity)
                    if entity_name:
                        entities.add(entity_name)

            # Estimate volume from content (look for dollar amounts)
            title = article.get("title", "")
            summary = article.get("summary", "")
            text = f"{title} {summary}".lower()

            # Very simple volume extraction - look for patterns like "$XXM" or "$XXB"
            import re

            amounts = re.findall(r"\$(\d+(?:\.?\d+)?)\s*[mb]", text)
            for amount_str in amounts:
                try:
                    amount = float(amount_str)
                    # Convert to actual dollars (M = million, B = billion)
                    if "b" in text[: text.lower().find(amount_str) + 10].lower():
                        amount *= 1_000_000_000
                    else:
                        amount *= 1_000_000
                    estimated_volume += amount
                except ValueError:
                    pass

        # Only create event if we have sufficient data
        if estimated_volume < self.LIQUIDATION_VOLUME_THRESHOLD or len(entities) < self.MULTI_ENTITY_THRESHOLD:
            logger.debug(
                f"Liquidation detection: {len(articles)} articles, ${estimated_volume:,.0f}, "
                f"{len(entities)} entities. Below threshold."
            )
            return None

        # Get article IDs
        article_ids = [str(a["_id"]) for a in articles]

        return {
            "type": "liquidation_cascade",
            "theme": "market_shock_liquidation",
            "title": f"Major Market Liquidation Event - ${estimated_volume / 1_000_000_000:.1f}B Cascade",
            "article_ids": article_ids,
            "article_count": len(articles),
            "entities": list(entities),
            "estimated_volume": estimated_volume,
            "detected_at": now,
        }

    async def _detect_market_crash(
        self, articles_collection, now: datetime
    ) -> Optional[Dict[str, Any]]:
        """Detect market-wide crash events."""
        window_start = now - timedelta(hours=self.EVENT_DETECTION_WINDOW_HOURS)

        query = {
            "published_at": {"$gte": window_start},
            "$text": {"$search": " ".join(self.CRASH_KEYWORDS)},
        }

        articles = await articles_collection.find(query).to_list(length=50)

        # Need fewer articles for crash detection (distinct event)
        if len(articles) < 3:
            return None

        # Check if multiple major entities are affected
        entities = set()
        for article in articles:
            if article.get("entities"):
                for entity in article["entities"][:3]:
                    if isinstance(entity, dict):
                        entity_name = entity.get("name") or entity.get("entity", "")
                    else:
                        entity_name = str(entity)
                    if entity_name:
                        entities.add(entity_name)

        if len(entities) < 2:  # Need at least 2 major entities affected
            return None

        article_ids = [str(a["_id"]) for a in articles]

        return {
            "type": "market_crash",
            "theme": "market_shock_crash",
            "title": f"Market-Wide Flash Crash - {len(entities)} Major Assets Affected",
            "article_ids": article_ids,
            "article_count": len(articles),
            "entities": list(entities),
            "detected_at": now,
        }

    async def _detect_exploit_event(
        self, articles_collection, now: datetime
    ) -> Optional[Dict[str, Any]]:
        """Detect major security exploit events."""
        window_start = now - timedelta(hours=self.EVENT_DETECTION_WINDOW_HOURS)

        query = {
            "published_at": {"$gte": window_start},
            "$text": {"$search": " ".join(self.EXPLOIT_KEYWORDS)},
        }

        articles = await articles_collection.find(query).to_list(length=50)

        # Need fewer articles but more significant threshold
        if len(articles) < 2:
            return None

        entities = set()
        estimated_loss = 0

        for article in articles:
            if article.get("entities"):
                for entity in article["entities"][:3]:
                    if isinstance(entity, dict):
                        entity_name = entity.get("name") or entity.get("entity", "")
                    else:
                        entity_name = str(entity)
                    if entity_name:
                        entities.add(entity_name)

            # Extract loss amounts
            title = article.get("title", "")
            summary = article.get("summary", "")
            text = f"{title} {summary}".lower()

            import re

            amounts = re.findall(r"\$(\d+(?:\.?\d+)?)\s*[mb]", text)
            for amount_str in amounts:
                try:
                    amount = float(amount_str)
                    if "b" in text[: text.lower().find(amount_str) + 10].lower():
                        amount *= 1_000_000_000
                    else:
                        amount *= 1_000_000
                    estimated_loss += amount
                except ValueError:
                    pass

        article_ids = [str(a["_id"]) for a in articles]

        return {
            "type": "security_exploit",
            "theme": "market_shock_exploit",
            "title": f"Major Security Incident - {len(entities)} Platforms Affected",
            "article_ids": article_ids,
            "article_count": len(articles),
            "entities": list(entities),
            "estimated_loss": estimated_loss,
            "detected_at": now,
        }

    async def create_or_update_market_event_narrative(
        self, event: Dict[str, Any]
    ) -> str:
        """
        Create or update a narrative for a detected market event.

        Args:
            event: Detected market event data

        Returns:
            Narrative ID
        """
        theme = event["theme"]
        title = event["title"]
        article_ids = event["article_ids"]
        article_count = event["article_count"]
        entities = event["entities"]

        # Build summary based on event type
        if event["type"] == "liquidation_cascade":
            summary = (
                f"Major liquidation cascade affecting {len(entities)} major cryptocurrencies "
                f"totaling approximately ${event['estimated_volume'] / 1_000_000_000:.1f}B. "
                f"Articles report on the cascade timing, affected entities, and market implications. "
                f"Multiple major assets experienced forced liquidations within a 24-hour window."
            )
        elif event["type"] == "market_crash":
            summary = (
                f"Market-wide crash affecting {len(entities)} major assets. "
                f"Flash crash event with sharp declines across multiple cryptocurrencies. "
                f"Articles cover the extent of the decline and market implications."
            )
        else:  # exploit
            summary = (
                f"Major security incident affecting {len(entities)} platforms. "
                f"Articles report on the security breach, affected platforms, "
                f"and estimated losses of ${event.get('estimated_loss', 0) / 1_000_000:.0f}M."
            )

        # Market shock narratives start in "hot" state for immediate prominence
        narrative_id = await upsert_narrative(
            theme=theme,
            title=title,
            summary=summary,
            entities=entities[:8],  # Top 8 entities
            article_ids=article_ids,
            article_count=article_count,
            mention_velocity=float(article_count) / 1.0,  # Articles per day
            lifecycle="hot",  # Market shocks are hot narratives
            lifecycle_state="hot",
            momentum="growing",
            recency_score=1.0,  # Maximum recency for immediate inclusion
            first_seen=event["detected_at"],
        )

        logger.info(f"Created market event narrative: {theme} (ID: {narrative_id})")
        return narrative_id

    async def boost_market_event_in_briefing(
        self, narratives: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Ensure market shock narratives are included in top narratives for briefing.

        Modifies narrative list to:
        1. Always include market shocks if detected
        2. Prioritize them appropriately

        Args:
            narratives: List of narratives ranked by recency

        Returns:
            Modified narrative list with market shocks guaranteed inclusion
        """
        # Separate market shocks from regular narratives
        market_shocks = [
            n
            for n in narratives
            if n.get("theme", "").startswith("market_shock_")
        ]
        regular_narratives = [
            n
            for n in narratives
            if not n.get("theme", "").startswith("market_shock_")
        ]

        # If there are market shocks, boost their recency for ranking
        for shock in market_shocks:
            current_recency = shock.get("_fresh_recency", 0)
            boosted_recency = min(1.0, current_recency + self.EVENT_RECENCY_BOOST)
            shock["_fresh_recency"] = boosted_recency
            shock["_market_shock"] = True

        # Re-combine and re-sort: market shocks should naturally rank higher now
        combined = market_shocks + regular_narratives
        combined.sort(key=lambda x: x.get("_fresh_recency", 0), reverse=True)

        return combined


# Global instance
_detector_instance = None


def get_market_event_detector() -> MarketEventDetector:
    """Get or create the market event detector instance."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = MarketEventDetector()
    return _detector_instance
