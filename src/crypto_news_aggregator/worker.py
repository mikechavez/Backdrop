import asyncio
import logging
from datetime import datetime, timezone, timedelta

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from crypto_news_aggregator.background.rss_fetcher import schedule_rss_fetch
from crypto_news_aggregator.core.config import get_settings
from crypto_news_aggregator.db.mongodb import initialize_mongodb, mongo_manager
from crypto_news_aggregator.services.signal_service import calculate_signal_score
from crypto_news_aggregator.db.operations.signal_scores import upsert_signal_score
from crypto_news_aggregator.services.narrative_service import detect_narratives
from crypto_news_aggregator.db.operations.narratives import upsert_narrative
from crypto_news_aggregator.services.entity_alert_service import detect_alerts
from crypto_news_aggregator.services.entity_normalization import normalize_entity_name
from crypto_news_aggregator.services.narrative_deduplication import deduplicate_narratives
from crypto_news_aggregator.tasks.narrative_cleanup import auto_dormant_zombie_narratives

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


async def update_signal_scores(run_immediately: bool = False):
    """
    Update signal scores for trending entities.
    
    Runs every 2 minutes to calculate signal scores for entities
    mentioned in the last 30 minutes.
    
    Args:
        run_immediately: If True, run first update immediately on startup
    """
    logger.info("Starting signal score update task")
    
    if not run_immediately:
        # Wait before first run if not immediate
        await asyncio.sleep(120)
    
    while True:
        try:
            db = await mongo_manager.get_async_database()
            entity_mentions_collection = db.entity_mentions
            
            # Get entities mentioned in the last 30 minutes
            # Use naive datetime to match MongoDB storage
            thirty_min_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=30)
            
            # Fetch all recent primary entity mentions
            cursor = entity_mentions_collection.find({
                "created_at": {"$gte": thirty_min_ago},
                "is_primary": True
            })
            
            # Normalize entities and group by canonical name
            entity_map = {}  # canonical_name -> entity_type
            async for mention in cursor:
                raw_entity = mention.get("entity")
                entity_type = mention.get("entity_type")
                
                # Normalize to canonical name
                canonical_entity = normalize_entity_name(raw_entity)
                
                # Track unique canonical entities
                if canonical_entity not in entity_map:
                    entity_map[canonical_entity] = entity_type
                    
                    # Log normalization for debugging
                    if canonical_entity != raw_entity:
                        logger.debug(f"Signal calculation: normalized '{raw_entity}' -> '{canonical_entity}'")
            
            # Convert to list format expected by downstream code
            entities_to_score = [
                {"entity": entity, "entity_type": entity_type}
                for entity, entity_type in list(entity_map.items())[:100]  # Limit to 100
            ]
            
            if not entities_to_score:
                logger.debug("No recent entities to score")
                await asyncio.sleep(120)  # 2 minutes
                continue
            
            # Calculate scores for each entity
            scored_entities = []
            for entity_info in entities_to_score:
                entity = entity_info["entity"]
                entity_type = entity_info["entity_type"]
                
                try:
                    # Calculate signal scores for all three timeframes
                    signal_24h = await calculate_signal_score(entity, timeframe_hours=24)
                    signal_7d = await calculate_signal_score(entity, timeframe_hours=168)  # 7 days
                    signal_30d = await calculate_signal_score(entity, timeframe_hours=720)  # 30 days
                    
                    # Also calculate legacy score for backward compatibility
                    signal_legacy = await calculate_signal_score(entity)
                    
                    # Get first_seen timestamp (primary mentions only)
                    first_mention = await entity_mentions_collection.find_one(
                        {"entity": entity, "is_primary": True},
                        sort=[("created_at", 1)]
                    )
                    first_seen = first_mention["created_at"] if first_mention else datetime.now(timezone.utc)
                    
                    # Store the signal score with all timeframes
                    await upsert_signal_score(
                        entity=entity,
                        entity_type=entity_type,
                        score=signal_legacy["score"],
                        velocity=signal_legacy["velocity"],
                        source_count=signal_legacy["source_count"],
                        sentiment=signal_legacy["sentiment"],
                        narrative_ids=signal_legacy.get("narrative_ids", []),
                        is_emerging=signal_legacy.get("is_emerging", False),
                        first_seen=first_seen,
                        # Multi-timeframe data
                        score_24h=signal_24h["score"],
                        score_7d=signal_7d["score"],
                        score_30d=signal_30d["score"],
                        velocity_24h=signal_24h["velocity"],
                        velocity_7d=signal_7d["velocity"],
                        velocity_30d=signal_30d["velocity"],
                        mentions_24h=signal_24h.get("mentions", 0),
                        mentions_7d=signal_7d.get("mentions", 0),
                        mentions_30d=signal_30d.get("mentions", 0),
                        recency_24h=signal_24h.get("recency_factor", 0.0),
                        recency_7d=signal_7d.get("recency_factor", 0.0),
                        recency_30d=signal_30d.get("recency_factor", 0.0),
                    )
                    
                    scored_entities.append({
                        "entity": entity,
                        "score": signal_legacy["score"],
                        "score_24h": signal_24h["score"],
                        "score_7d": signal_7d["score"],
                        "score_30d": signal_30d["score"],
                    })
                    
                except Exception as exc:
                    logger.error(f"Failed to score entity {entity}: {exc}")
            
            # Sort by score and log top entity
            if scored_entities:
                scored_entities.sort(key=lambda x: x["score"], reverse=True)
                top_entity = scored_entities[0]
                
                logger.info(
                    f"Signal scores updated: {len(scored_entities)} entities scored, "
                    f"top entity: {top_entity['entity']} "
                    f"(24h: {top_entity['score_24h']}, 7d: {top_entity['score_7d']}, 30d: {top_entity['score_30d']})"
                )
            
        except asyncio.CancelledError:
            logger.info("Signal score update task cancelled")
            raise
        except Exception as exc:
            logger.exception(f"Error in signal score update: {exc}")
        
        # Wait 2 minutes before next update
        await asyncio.sleep(120)



async def update_narratives():
    """
    Update narrative clusters from trending entities.
    
    Runs narrative detection, deduplicates similar narratives,
    and upserts results to the database.
    Scheduled to run every 10 minutes.
    """
    try:
        logger.info("Starting narrative update cycle...")
        narratives = await detect_narratives()
        
        if not narratives:
            logger.info("No narratives detected in this cycle")
            return
        
        # Deduplicate similar narratives
        deduplicated_narratives, num_merged = deduplicate_narratives(narratives, threshold=0.7)
        
        if num_merged > 0:
            logger.info(f"Merged {num_merged} duplicate narratives")
        
        # Upsert each deduplicated narrative to database
        for narrative in deduplicated_narratives:
            await upsert_narrative(
                theme=narrative["theme"],
                title=narrative["title"],
                summary=narrative["summary"],
                entities=narrative["entities"],
                article_ids=narrative["article_ids"],
                article_count=narrative["article_count"],
                mention_velocity=narrative["mention_velocity"],
                lifecycle=narrative["lifecycle"],
                momentum=narrative.get("momentum", "unknown"),
                recency_score=narrative.get("recency_score", 0.0),
                first_seen=narrative.get("first_seen")
            )
        
        logger.info(f"Updated {len(deduplicated_narratives)} narratives")
    except Exception as e:
        logger.exception(f"Error updating narratives: {e}")


async def schedule_narrative_updates(interval_seconds: int, run_immediately: bool = False) -> None:
    """Continuously run narrative updates on a fixed interval.
    
    Args:
        interval_seconds: Time to wait between narrative update cycles
        run_immediately: If True, run first update immediately on startup
    """
    logger.info("Starting narrative update schedule with interval %s seconds", interval_seconds)
    
    if run_immediately:
        logger.info("Running initial narrative detection on startup...")
        try:
            await update_narratives()
        except Exception as exc:
            logger.exception("Initial narrative update failed: %s", exc)
    
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await update_narratives()
        except asyncio.CancelledError:
            logger.info("Narrative update schedule cancelled")
            raise
        except Exception as exc:
            logger.exception("Narrative update cycle failed: %s", exc)


async def check_alerts():
    """
    Check for entity alerts based on trending signals.

    Runs alert detection and creates new alerts in the database.
    Scheduled to run every 2 minutes.
    """
    try:
        logger.info("Starting alert detection cycle...")
        triggered_alerts = await detect_alerts()

        if triggered_alerts:
            logger.info(f"Triggered {len(triggered_alerts)} new alerts")
        else:
            logger.info("No new alerts triggered in this cycle")
    except Exception as e:
        logger.exception(f"Error checking alerts: {e}")


async def check_zombie_narratives():
    """
    Check for and dormant zombie narratives with no surviving source articles.

    Runs auto-dormant check to identify narratives where all referenced
    article_ids have been deleted (e.g., during MongoDB purges).
    Scheduled to run daily or after RSS ingestion cycles.
    """
    try:
        logger.info("Starting zombie narrative check...")
        result = await auto_dormant_zombie_narratives()

        checked = result.get("hot_narratives_checked", 0)
        found = result.get("zombie_narratives_found", 0)
        dormanted = result.get("narratives_dormanted", 0)

        if dormanted > 0:
            logger.warning(
                f"Zombie narrative check complete: "
                f"checked {checked}, found {found}, dormanted {dormanted}"
            )
        else:
            logger.info(
                f"Zombie narrative check complete: "
                f"checked {checked}, found {found}, dormanted {dormanted}"
            )
    except Exception as e:
        logger.exception(f"Error checking zombie narratives: {e}")


async def schedule_alert_checks(interval_seconds: int, run_immediately: bool = False) -> None:
    """Continuously run alert checks on a fixed interval.

    Args:
        interval_seconds: Time to wait between alert check cycles
        run_immediately: If True, run first check immediately on startup
    """
    logger.info("Starting alert check schedule with interval %s seconds", interval_seconds)

    if run_immediately:
        logger.info("Running initial alert check on startup...")
        try:
            await check_alerts()
        except Exception as exc:
            logger.exception("Initial alert check failed: %s", exc)

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await check_alerts()
        except asyncio.CancelledError:
            logger.info("Alert check schedule cancelled")
            raise
        except Exception as exc:
            logger.exception("Alert check cycle failed: %s", exc)


async def schedule_zombie_narrative_checks(interval_seconds: int, run_immediately: bool = False) -> None:
    """Continuously run zombie narrative checks on a fixed interval.

    Args:
        interval_seconds: Time to wait between zombie narrative check cycles
        run_immediately: If True, run first check immediately on startup
    """
    logger.info("Starting zombie narrative check schedule with interval %s seconds", interval_seconds)

    if run_immediately:
        logger.info("Running initial zombie narrative check on startup...")
        try:
            await check_zombie_narratives()
        except Exception as exc:
            logger.exception("Initial zombie narrative check failed: %s", exc)

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await check_zombie_narratives()
        except asyncio.CancelledError:
            logger.info("Zombie narrative check schedule cancelled")
            raise
        except Exception as exc:
            logger.exception("Zombie narrative check cycle failed: %s", exc)


async def main():
    """Initializes and runs all background tasks."""
    logger.info("--- Starting background worker process ---")
    settings = get_settings()
    await initialize_mongodb()
    logger.info("MongoDB connection initialized for worker.")

    tasks = []
    if not settings.TESTING:
        # Lazy import to avoid triggering tasks/__init__.py which imports celery
        from crypto_news_aggregator.tasks.price_monitor import get_price_monitor
        
        price_monitor = get_price_monitor()
        logger.info("Starting price monitor task...")
        tasks.append(asyncio.create_task(price_monitor.start()))
        logger.info("Price monitor task created.")

        rss_interval = 60 * 30  # 30 minutes
        logger.info("Starting RSS ingestion schedule (every %s seconds)", rss_interval)
        tasks.append(asyncio.create_task(schedule_rss_fetch(rss_interval)))
        logger.info("RSS ingestion task created.")
        
        # Signal score update task is DISABLED - signals are now computed on-demand
        # when the API is called (compute-on-read pattern). This eliminates staleness
        # issues and reduces background computation load. See ADR-001.
        # tasks.append(asyncio.create_task(update_signal_scores()))
        logger.info("Signal score update task DISABLED (using compute-on-read pattern)")
        
        narrative_interval = 60 * 10  # 10 minutes
        logger.info("Starting narrative update schedule (every %s seconds)", narrative_interval)
        tasks.append(asyncio.create_task(schedule_narrative_updates(narrative_interval)))
        logger.info("Narrative update task created.")
        
        alert_interval = 60 * 2  # 2 minutes
        logger.info("Starting alert check schedule (every %s seconds)", alert_interval)
        tasks.append(asyncio.create_task(schedule_alert_checks(alert_interval)))
        logger.info("Alert check task created.")

        zombie_check_interval = 60 * 60  # 1 hour (daily check at scale)
        logger.info("Starting zombie narrative check schedule (every %s seconds)", zombie_check_interval)
        tasks.append(asyncio.create_task(schedule_zombie_narrative_checks(zombie_check_interval)))
        logger.info("Zombie narrative check task created.")

    if not tasks:
        logger.warning("No background tasks to run. Worker will exit.")
        return

    logger.info(f"{len(tasks)} background task(s) are running.")

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Worker process received cancellation request.")
    finally:
        logger.info("Shutting down worker process...")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await mongo_manager.aclose()
        logger.info("Worker process shut down gracefully.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker process stopped by user.")
