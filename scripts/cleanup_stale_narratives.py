#!/usr/bin/env python3
"""
Clean up stale October 2025 narratives from MongoDB.

This script removes narratives with last_updated before 2025-12-01.
These narratives no longer surface in queries but add noise to the collection.

TASK-066: Clean up stale October 2025 narratives from collection

Usage:
    # Dry run (show what would be deleted)
    poetry run python scripts/cleanup_stale_narratives.py --dry-run

    # Delete stale narratives
    poetry run python scripts/cleanup_stale_narratives.py --yes
"""

import asyncio
import argparse
import sys
import os
from datetime import datetime, timezone

# Add src to path for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, os.path.join(project_root, "src"))

from crypto_news_aggregator.db.mongodb import mongo_manager


CUTOFF_DATE = datetime(2025, 12, 1, 0, 0, 0, tzinfo=timezone.utc)


async def count_stale_narratives() -> int:
    """Count narratives with last_updated before 2025-12-01."""
    db = await mongo_manager.get_async_database()
    collection = db.narratives

    count = await collection.count_documents({"last_updated": {"$lt": CUTOFF_DATE}})
    return count


async def count_recent_narratives() -> int:
    """Count narratives with last_updated >= 2025-12-01 (should be unaffected)."""
    db = await mongo_manager.get_async_database()
    collection = db.narratives

    count = await collection.count_documents({"last_updated": {"$gte": CUTOFF_DATE}})
    return count


async def delete_stale_narratives(dry_run: bool = True) -> int:
    """
    Delete narratives with last_updated before 2025-12-01.

    Args:
        dry_run: If True, don't actually delete (default True)

    Returns:
        Number of narratives deleted (or would be deleted in dry run)
    """
    db = await mongo_manager.get_async_database()
    collection = db.narratives

    query = {"last_updated": {"$lt": CUTOFF_DATE}}

    if dry_run:
        count = await collection.count_documents(query)
        return count
    else:
        result = await collection.delete_many(query)
        return result.deleted_count


async def main():
    """Main script execution."""
    parser = argparse.ArgumentParser(
        description="Clean up stale October 2025 narratives from MongoDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run (show what would be deleted)
  poetry run python scripts/cleanup_stale_narratives.py --dry-run

  # Delete stale narratives
  poetry run python scripts/cleanup_stale_narratives.py --yes
        """
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting"
    )

    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm deletion (required to actually delete)"
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.dry_run and not args.yes:
        print("❌ Error: Must specify either --dry-run or --yes")
        print("Use --dry-run to see what would be deleted")
        print("Use --yes to confirm deletion")
        sys.exit(1)

    # Initialize MongoDB connection
    print("🔌 Connecting to MongoDB...")
    await mongo_manager.initialize()

    try:
        # Count before
        stale_count = await count_stale_narratives()
        recent_count = await count_recent_narratives()

        print(f"\n📊 Database Status (Before):")
        print(f"   Stale narratives (last_updated < 2025-12-01): {stale_count}")
        print(f"   Recent narratives (last_updated >= 2025-12-01): {recent_count}")
        print(f"   Total: {stale_count + recent_count}")

        if stale_count == 0:
            print("\n✅ No stale narratives to delete")
        else:
            if args.dry_run:
                print(f"\n🔍 DRY RUN: Would delete {stale_count} narratives")
                print("   (Run with --yes to actually delete)")
            else:
                print(f"\n⚠️  WARNING: About to delete {stale_count} narratives")
                print("   This action cannot be undone!")

                confirm = input("\n   Type 'DELETE' to confirm: ")
                if confirm != "DELETE":
                    print("❌ Deletion cancelled")
                    return

                print("\n🗑️  Deleting stale narratives...")
                deleted_count = await delete_stale_narratives(dry_run=False)

                print(f"✅ Successfully deleted {deleted_count} narratives")

                # Verify deletion
                print("\n📊 Database Status (After):")
                stale_after = await count_stale_narratives()
                recent_after = await count_recent_narratives()
                print(f"   Stale narratives: {stale_after}")
                print(f"   Recent narratives: {recent_after}")
                print(f"   Total: {stale_after + recent_after}")

    finally:
        # Close MongoDB connection
        print("\n🔌 Closing MongoDB connection...")
        await mongo_manager.close()

    print("\n✅ Done!")


if __name__ == "__main__":
    asyncio.run(main())
