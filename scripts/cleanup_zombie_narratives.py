#!/usr/bin/env python3
"""
TASK-073 Part 1: One-time cleanup query for zombie narratives.

Identifies narratives where none of the referenced article_ids exist
in the articles collection, and marks them dormant.

This script should be run manually after any article purge operation
(e.g., MongoDB space cleanup, deletion of old articles).

Usage:
    poetry run python scripts/cleanup_zombie_narratives.py [--dry-run]

Examples:
    # Preview what would be dormanted without making changes
    poetry run python scripts/cleanup_zombie_narratives.py --dry-run

    # Actually dormant the zombie narratives
    poetry run python scripts/cleanup_zombie_narratives.py
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone
from typing import Dict, Any, List

from bson import ObjectId

# Setup path for imports
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from crypto_news_aggregator.db.mongodb import initialize_mongodb, mongo_manager
from crypto_news_aggregator.core.config import get_settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def find_zombie_narratives() -> List[Dict[str, Any]]:
    """
    Find all narratives where zero article_ids resolve to existing articles.

    Uses MongoDB aggregation to efficiently identify zombie narratives:
    1. Match all hot narratives
    2. Convert string article_ids to ObjectId
    3. Lookup against articles collection
    4. Filter for narratives with zero surviving articles

    Returns:
        List of zombie narrative documents
    """
    db = await mongo_manager.get_async_database()
    narratives_collection = db.narratives

    logger.info("Running aggregation to find zombie narratives...")

    pipeline = [
        # Match hot narratives
        {"$match": {"lifecycle_state": "hot"}},

        # Convert string article_ids to ObjectId for lookup
        {
            "$addFields": {
                "article_object_ids": {
                    "$map": {
                        "input": "$article_ids",
                        "as": "aid",
                        "in": {
                            "$cond": {
                                "if": {
                                    "$eq": [{"$type": "$$aid"}, "string"]
                                },
                                "then": {
                                    "$convert": {
                                        "input": "$$aid",
                                        "to": "objectId",
                                        "onError": "$$aid"
                                    }
                                },
                                "else": "$$aid"
                            }
                        }
                    }
                }
            }
        },

        # Lookup surviving articles
        {
            "$lookup": {
                "from": "articles",
                "localField": "article_object_ids",
                "foreignField": "_id",
                "as": "surviving_articles"
            }
        },

        # Filter for narratives with zero surviving articles
        {"$match": {"surviving_articles": {"$size": 0}}},

        # Project relevant fields
        {
            "$project": {
                "_id": 1,
                "title": 1,
                "theme": 1,
                "article_ids": 1,
                "article_count": 1,
                "first_seen": 1,
                "lifecycle_state": 1
            }
        }
    ]

    cursor = narratives_collection.aggregate(pipeline)
    zombies = await cursor.to_list(length=None)

    logger.info(f"Found {len(zombies)} zombie narratives")
    return zombies


async def dormant_zombie_narratives(
    zombie_narratives: List[Dict[str, Any]],
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Mark zombie narratives as dormant.

    Args:
        zombie_narratives: List of zombie narrative documents from aggregation
        dry_run: If True, only preview what would be done without making changes

    Returns:
        Dict with operation statistics
    """
    if not zombie_narratives:
        logger.info("No zombie narratives to process")
        return {
            "zombies_found": 0,
            "narratives_dormanted": 0,
            "dry_run": dry_run
        }

    db = await mongo_manager.get_async_database()
    narratives_collection = db.narratives

    zombie_ids = [z["_id"] for z in zombie_narratives]
    narratives_dormanted = 0

    logger.info(f"Processing {len(zombie_narratives)} zombie narratives...")

    if dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
        for zombie in zombie_narratives:
            logger.info(
                f"  Would dormant: {zombie['_id']} - {zombie['title']} "
                f"({len(zombie['article_ids'])} articles deleted)"
            )
    else:
        now = datetime.now(timezone.utc)
        result = await narratives_collection.update_many(
            {"_id": {"$in": zombie_ids}},
            {
                "$set": {
                    "lifecycle_state": "dormant",
                    "dormant_since": now,
                    "_disabled_by": "TASK-073-zombie-cleanup",
                    "last_updated": now
                }
            }
        )

        narratives_dormanted = result.modified_count
        logger.info(f"Successfully dormanted {narratives_dormanted} narratives")

        # Log each dormanted narrative
        for zombie in zombie_narratives:
            logger.info(
                f"  Dormanted: {zombie['_id']} - {zombie['title']} "
                f"({len(zombie['article_ids'])} articles deleted)"
            )

    return {
        "zombies_found": len(zombie_narratives),
        "narratives_dormanted": narratives_dormanted,
        "dry_run": dry_run,
        "titles": [z["title"] for z in zombie_narratives]
    }


async def main():
    """Main entry point for the cleanup script."""
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv

    if dry_run:
        logger.info("Running in DRY RUN mode (no changes will be made)")

    # Initialize settings and database
    settings = get_settings()
    await initialize_mongodb()
    logger.info("MongoDB connection initialized")

    try:
        # Find zombie narratives
        zombies = await find_zombie_narratives()

        if not zombies:
            logger.info("No zombie narratives found - database is clean!")
            return 0

        # Display zombie narratives
        logger.info("\nZombie Narratives Found:")
        logger.info("-" * 80)
        for i, zombie in enumerate(zombies, 1):
            logger.info(
                f"{i}. {zombie['title']} ({zombie['theme']})\n"
                f"   ID: {zombie['_id']}\n"
                f"   First seen: {zombie.get('first_seen', 'N/A')}\n"
                f"   Article refs: {len(zombie.get('article_ids', []))} (all deleted)"
            )

        # Dormant the zombie narratives
        logger.info("\n" + "-" * 80)
        result = await dormant_zombie_narratives(zombies, dry_run=dry_run)

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("CLEANUP SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Zombies found:        {result['zombies_found']}")
        logger.info(f"Narratives dormanted: {result['narratives_dormanted']}")
        logger.info(f"Dry run mode:         {result['dry_run']}")

        if result['narratives_dormanted'] > 0:
            logger.warning(
                f"Auto-dormanted {result['narratives_dormanted']} zombie narrative(s) with no surviving source articles: "
                f"{', '.join(result['titles'])}"
            )

        return 0

    except Exception as e:
        logger.exception(f"Error during cleanup: {e}")
        return 1

    finally:
        await mongo_manager.aclose()
        logger.info("MongoDB connection closed")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
