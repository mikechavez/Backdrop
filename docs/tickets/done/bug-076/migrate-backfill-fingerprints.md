"""
Migration: Backfill fingerprints on articles that predate BUG-076 fix.

Commit 28f65db (2026-04-13) routed RSS ingest through ArticleService.create_article(),
which generates fingerprints. Articles inserted before that commit have no fingerprint
field and cannot participate in deduplication.

This script:
  1. Finds all articles missing a fingerprint field.
  2. Generates the fingerprint using ArticleService._generate_fingerprint() — the same
     logic the live path uses — so backfilled values are format-identical.
  3. Checks whether another article already holds that fingerprint (a true duplicate
     that slipped through before the fix).
  4. If a duplicate is found: logs it and tags the article with duplicate_of=<original_id>.
     Does NOT delete — review and delete manually.
  5. If no duplicate: writes the fingerprint to the document via $set.
  6. Prints a summary when done.

Usage:
    python migrate_backfill_fingerprints.py

Run from the project root with the same environment as the app (Railway env vars or
a local .env). Safe to run multiple times — already-fingerprinted articles are skipped.
"""

import asyncio
import logging
from datetime import datetime, timezone

from crypto_news_aggregator.db.mongodb import mongo_manager
from crypto_news_aggregator.services.article_service import get_article_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def backfill_fingerprints() -> None:
    db = await mongo_manager.get_async_database()
    collection = db.articles
    article_service = get_article_service()

    # Step 1: Find every article missing a fingerprint.
    cursor = collection.find({"fingerprint": {"$exists": False}})
    articles = await cursor.to_list(length=None)

    total = len(articles)
    if total == 0:
        logger.info("No articles missing fingerprints. Nothing to do.")
        return

    logger.info(f"Found {total} article(s) without a fingerprint. Starting backfill...")

    written = 0
    duplicates = 0
    errors = 0

    for article in articles:
        article_id = article["_id"]
        title = article.get("title") or ""
        # RSS ingest stores body in 'text'; fall back to 'content' for older documents.
        text = article.get("text") or article.get("content") or ""
        source = article.get("source", "unknown")

        try:
            # Step 2: Generate fingerprint using the same method as the live path.
            fingerprint = await article_service._generate_fingerprint(title, text)

            # Step 3: Check whether another document already holds this fingerprint.
            existing = await collection.find_one(
                {
                    "fingerprint": fingerprint,
                    "_id": {"$ne": article_id},  # exclude the article itself
                }
            )

            if existing:
                # Step 4: Duplicate found — tag it, do not delete.
                duplicates += 1
                logger.warning(
                    f"DUPLICATE | _id={article_id} | title='{title[:60]}' | source={source} "
                    f"| original_id={existing['_id']}"
                )
                await collection.update_one(
                    {"_id": article_id},
                    {
                        "$set": {
                            "fingerprint": fingerprint,
                            "duplicate_of": existing["_id"],
                            "updated_at": datetime.now(timezone.utc),
                        }
                    },
                )
            else:
                # Step 5: No duplicate — write the fingerprint.
                written += 1
                logger.info(
                    f"FINGERPRINTED | _id={article_id} | title='{title[:60]}' | source={source}"
                )
                await collection.update_one(
                    {"_id": article_id},
                    {
                        "$set": {
                            "fingerprint": fingerprint,
                            "updated_at": datetime.now(timezone.utc),
                        }
                    },
                )

        except Exception as exc:
            errors += 1
            logger.error(
                f"ERROR | _id={article_id} | title='{title[:60]}' | source={source} | {exc}"
            )

    # Step 6: Summary.
    logger.info("=" * 60)
    logger.info(f"Backfill complete.")
    logger.info(f"  Total processed : {total}")
    logger.info(f"  Fingerprints set: {written}")
    logger.info(f"  Duplicates found: {duplicates}  (tagged with duplicate_of, not deleted)")
    logger.info(f"  Errors          : {errors}")
    logger.info("=" * 60)

    if duplicates:
        logger.info(
            "Review duplicates with:\n"
            "  db.articles.find({ duplicate_of: { $exists: true } }, "
            "{ title: 1, source: 1, duplicate_of: 1 })"
        )


if __name__ == "__main__":
    asyncio.run(backfill_fingerprints())