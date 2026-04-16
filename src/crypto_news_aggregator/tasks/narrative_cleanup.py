"""
Narrative cleanup tasks for fixing invalid article references.

This module provides background tasks to:
1. Validate article IDs in narratives
2. Remove invalid/stale article references
3. Recalculate article counts
4. Update article narrative_id references to survivors
5. Auto-dormant narratives when all source articles are purged
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List

from bson import ObjectId

from ..db.mongodb import mongo_manager

logger = logging.getLogger(__name__)


async def cleanup_invalid_article_references() -> Dict[str, Any]:
    """
    Remove invalid article IDs from all narratives.

    Scans all narratives and removes article IDs that no longer exist
    in the articles collection. This fixes data inconsistencies from
    consolidation/reactivation operations.

    Returns:
        Dict with statistics:
        - narratives_processed: Total narratives checked
        - invalid_references_removed: Total invalid IDs removed
        - narratives_updated: Narratives with changes
        - errors: Any errors encountered
    """
    try:
        db = await mongo_manager.get_async_database()
        narratives_collection = db.narratives
        articles_collection = db.articles

        logger.info("Starting narrative cleanup: validating article references")

        # Get all narratives
        cursor = narratives_collection.find({})
        narratives = await cursor.to_list(length=None)

        narratives_processed = 0
        invalid_references_removed = 0
        narratives_updated = 0
        errors = []

        for narrative in narratives:
            narratives_processed += 1
            narrative_id = narrative.get("_id")
            article_ids = narrative.get("article_ids", [])

            if not article_ids:
                continue

            # Validate article IDs
            valid_ids_to_check = []
            for aid in article_ids:
                try:
                    # Convert to ObjectId if it looks like one
                    if isinstance(aid, str) and len(aid) == 24 and aid.isalnum():
                        valid_ids_to_check.append(ObjectId(aid))
                    else:
                        valid_ids_to_check.append(aid)
                except Exception:
                    # If we can't convert, it's likely invalid
                    invalid_references_removed += 1
                    continue

            # Query for valid articles
            if valid_ids_to_check:
                valid_articles = await articles_collection.distinct(
                    "_id",
                    {"_id": {"$in": valid_ids_to_check}}
                )
                valid_articles_set = set(str(aid) for aid in valid_articles)
            else:
                valid_articles_set = set()

            original_count = len(article_ids)
            new_count = len(valid_articles_set)
            removed = original_count - new_count

            if removed > 0:
                invalid_references_removed += removed
                narratives_updated += 1

                # Update narrative with only valid article IDs
                await narratives_collection.update_one(
                    {"_id": narrative_id},
                    {
                        "$set": {
                            "article_ids": list(valid_articles_set),
                            "article_count": new_count,
                            "last_updated": datetime.now(timezone.utc)
                        }
                    }
                )

                logger.info(
                    f"Cleaned up narrative {narrative_id}: "
                    f"removed {removed} invalid references ({original_count} → {new_count})"
                )

        logger.info(
            f"Narrative cleanup complete: "
            f"processed {narratives_processed}, "
            f"removed {invalid_references_removed} invalid references, "
            f"updated {narratives_updated} narratives"
        )

        return {
            "narratives_processed": narratives_processed,
            "invalid_references_removed": invalid_references_removed,
            "narratives_updated": narratives_updated,
            "errors": errors
        }

    except Exception as e:
        logger.exception(f"Error during narrative cleanup: {e}")
        return {
            "narratives_processed": 0,
            "invalid_references_removed": 0,
            "narratives_updated": 0,
            "errors": [str(e)]
        }


async def update_article_narrative_references(dry_run: bool = False) -> Dict[str, Any]:
    """
    Update article narrative_id references when narratives are merged.

    After consolidation, articles may still reference merged narratives.
    This task updates them to point to the survivor narrative.

    Args:
        dry_run: If True, only report what would be changed without making changes

    Returns:
        Dict with statistics:
        - articles_updated: Number of articles updated
        - narratives_with_merged_refs: Narratives that had merged references
        - errors: Any errors encountered
    """
    try:
        db = await mongo_manager.get_async_database()
        narratives_collection = db.narratives
        articles_collection = db.articles

        logger.info(f"Starting article reference update (dry_run={dry_run})")

        # Find all narratives with merged_into reference
        merged_narratives = await narratives_collection.find(
            {"merged_into": {"$exists": True}}
        ).to_list(length=None)

        logger.info(f"Found {len(merged_narratives)} merged narratives")

        articles_updated = 0
        narratives_with_merged_refs = 0
        errors = []

        for merged_narrative in merged_narratives:
            merged_id = merged_narrative.get("_id")
            survivor_id = merged_narrative.get("merged_into")

            # Find articles referencing the merged narrative
            articles_to_update = await articles_collection.find(
                {"narrative_id": merged_id}
            ).to_list(length=None)

            if articles_to_update:
                narratives_with_merged_refs += 1

                if not dry_run:
                    # Update articles to reference survivor
                    result = await articles_collection.update_many(
                        {"narrative_id": merged_id},
                        {"$set": {"narrative_id": survivor_id}}
                    )
                    articles_updated += result.modified_count

                logger.info(
                    f"Updating {len(articles_to_update)} articles from merged narrative {merged_id} → {survivor_id}"
                )

        logger.info(
            f"Article reference update complete: "
            f"updated {articles_updated} articles, "
            f"fixed {narratives_with_merged_refs} narratives"
        )

        return {
            "articles_updated": articles_updated,
            "narratives_with_merged_refs": narratives_with_merged_refs,
            "errors": errors
        }

    except Exception as e:
        logger.exception(f"Error updating article references: {e}")
        return {
            "articles_updated": 0,
            "narratives_with_merged_refs": 0,
            "errors": [str(e)]
        }


async def validate_narrative_data_integrity() -> Dict[str, Any]:
    """
    Validate overall narrative data integrity.

    Checks:
    - article_count matches len(article_ids)
    - All article IDs reference valid articles
    - No duplicate article IDs within a narrative
    - article_count > 0 for active narratives

    Returns:
        Dict with validation results:
        - total_narratives: Total checked
        - count_mismatches: article_count != len(article_ids)
        - invalid_references: References to non-existent articles
        - duplicates: Narratives with duplicate article IDs
        - empty_narratives: Active narratives with no articles
    """
    try:
        db = await mongo_manager.get_async_database()
        narratives_collection = db.narratives
        articles_collection = db.articles

        logger.info("Starting narrative data integrity validation")

        cursor = narratives_collection.find({})
        narratives = await cursor.to_list(length=None)

        total_narratives = len(narratives)
        count_mismatches = []
        invalid_references = []
        duplicates = []
        empty_narratives = []

        for narrative in narratives:
            narrative_id = narrative.get("_id")
            article_ids = narrative.get("article_ids", [])
            article_count = narrative.get("article_count", 0)

            # Check 1: Count mismatch
            if article_count != len(article_ids):
                count_mismatches.append({
                    "narrative_id": str(narrative_id),
                    "expected": article_count,
                    "actual": len(article_ids)
                })

            # Check 2: Duplicates in article_ids
            if len(article_ids) != len(set(article_ids)):
                duplicates.append({
                    "narrative_id": str(narrative_id),
                    "total": len(article_ids),
                    "unique": len(set(article_ids))
                })

            # Check 3: Invalid references
            if article_ids:
                valid_ids_to_check = []
                for aid in article_ids:
                    try:
                        if isinstance(aid, str) and len(aid) == 24 and aid.isalnum():
                            valid_ids_to_check.append(ObjectId(aid))
                        else:
                            valid_ids_to_check.append(aid)
                    except Exception:
                        pass

                if valid_ids_to_check:
                    valid_articles = await articles_collection.distinct(
                        "_id",
                        {"_id": {"$in": valid_ids_to_check}}
                    )
                    if len(valid_articles) < len(article_ids):
                        invalid_references.append({
                            "narrative_id": str(narrative_id),
                            "total": len(article_ids),
                            "valid": len(valid_articles),
                            "invalid": len(article_ids) - len(valid_articles)
                        })

            # Check 4: Empty active narratives
            lifecycle_state = narrative.get("lifecycle_state", "unknown")
            if lifecycle_state in ["emerging", "rising", "hot"] and len(article_ids) == 0:
                empty_narratives.append({
                    "narrative_id": str(narrative_id),
                    "lifecycle_state": lifecycle_state
                })

        logger.info(
            f"Validation complete: "
            f"{count_mismatches} count mismatches, "
            f"{invalid_references} with invalid references, "
            f"{duplicates} with duplicates, "
            f"{empty_narratives} empty active narratives"
        )

        return {
            "total_narratives": total_narratives,
            "count_mismatches": count_mismatches,
            "invalid_references": invalid_references,
            "duplicates": duplicates,
            "empty_narratives": empty_narratives
        }

    except Exception as e:
        logger.exception(f"Error during validation: {e}")
        return {
            "total_narratives": 0,
            "count_mismatches": [],
            "invalid_references": [],
            "duplicates": [],
            "empty_narratives": [],
            "error": str(e)
        }


async def auto_dormant_zombie_narratives() -> Dict[str, Any]:
    """
    Auto-dormant narratives that have no surviving source articles.

    This task identifies "zombie narratives" - narratives where all referenced
    article_ids have been deleted (e.g., during MongoDB purges). These narratives
    remain lifecycle_state: "hot" indefinitely with summaries that can never be
    re-verified or regenerated. This operation marks them dormant to prevent
    them from appearing in user-facing briefings.

    Logic:
    - Find all hot narratives
    - For each, check if at least one article_id still exists
    - If zero articles survive, mark narrative dormant

    Returns:
        Dict with statistics:
        - hot_narratives_checked: Total hot narratives examined
        - zombie_narratives_found: Narratives with zero surviving articles
        - narratives_dormanted: Successfully marked dormant
        - titles: List of titles of dormanted narratives
        - errors: Any errors encountered
    """
    try:
        db = await mongo_manager.get_async_database()
        narratives_collection = db.narratives
        articles_collection = db.articles

        logger.info("Starting auto-dormant zombie narrative check")

        # Find all hot narratives
        hot_narratives = await narratives_collection.find(
            {"lifecycle_state": "hot"}
        ).to_list(length=None)

        hot_narratives_checked = len(hot_narratives)
        zombie_narratives_found = 0
        narratives_dormanted = 0
        dormanted_titles = []
        errors = []

        for narrative in hot_narratives:
            narrative_id = narrative.get("_id")
            article_ids = narrative.get("article_ids", [])
            title = narrative.get("title", "Unknown")

            # Skip narratives with no articles to check
            if not article_ids:
                logger.debug(f"Narrative {narrative_id} has empty article_ids list")
                continue

            # Convert article IDs to ObjectId format for lookup
            object_ids_to_check = []
            for aid in article_ids:
                try:
                    if isinstance(aid, str) and len(aid) == 24 and aid.isalnum():
                        object_ids_to_check.append(ObjectId(aid))
                    else:
                        object_ids_to_check.append(aid)
                except Exception as e:
                    logger.debug(f"Failed to convert article ID {aid}: {e}")
                    continue

            if not object_ids_to_check:
                logger.debug(f"No valid ObjectIds to check for narrative {narrative_id}")
                continue

            # Query for surviving articles
            surviving_articles = await articles_collection.distinct(
                "_id",
                {"_id": {"$in": object_ids_to_check}}
            )

            # If zero articles survive, mark narrative dormant
            if len(surviving_articles) == 0:
                zombie_narratives_found += 1

                try:
                    now = datetime.now(timezone.utc)
                    result = await narratives_collection.update_one(
                        {"_id": narrative_id},
                        {
                            "$set": {
                                "lifecycle_state": "dormant",
                                "dormant_since": now,
                                "_disabled_by": "TASK-073-auto-cleanup"
                            }
                        }
                    )

                    if result.modified_count > 0:
                        narratives_dormanted += 1
                        dormanted_titles.append(title)
                        logger.info(
                            f"Auto-dormanted zombie narrative: {narrative_id} - {title} "
                            f"({len(article_ids)} articles deleted)"
                        )
                    else:
                        logger.warning(
                            f"Failed to update zombie narrative {narrative_id}: "
                            f"update_one returned modified_count={result.modified_count}"
                        )

                except Exception as e:
                    error_msg = f"Error dormanting narrative {narrative_id}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)

        # Log summary
        if narratives_dormanted > 0:
            logger.warning(
                f"Auto-dormanted {narratives_dormanted} zombie narrative(s) with no surviving source articles: "
                f"{', '.join(dormanted_titles)}"
            )
        else:
            logger.info(
                f"Zombie narrative check complete: "
                f"checked {hot_narratives_checked} hot narratives, "
                f"found {zombie_narratives_found} zombies, "
                f"dormanted {narratives_dormanted}"
            )

        return {
            "hot_narratives_checked": hot_narratives_checked,
            "zombie_narratives_found": zombie_narratives_found,
            "narratives_dormanted": narratives_dormanted,
            "titles": dormanted_titles,
            "errors": errors
        }

    except Exception as e:
        error_msg = f"Error during zombie narrative check: {e}"
        logger.exception(error_msg)
        return {
            "hot_narratives_checked": 0,
            "zombie_narratives_found": 0,
            "narratives_dormanted": 0,
            "titles": [],
            "errors": [error_msg]
        }
