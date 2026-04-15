#!/usr/bin/env python3
"""
Diagnostic script to test the MongoDB update_one behavior
in the narrative backfill pipeline.
"""

import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
from bson import ObjectId

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from crypto_news_aggregator.db.mongodb import mongo_manager

async def test_update_diagnostic():
    """Test the update_one behavior to diagnose the issue."""
    db = await mongo_manager.get_async_database()
    articles_collection = db.articles

    print("=" * 70)
    print("NARRATIVE BACKFILL UPDATE DIAGNOSTIC")
    print("=" * 70)

    # Find a recent article (from last 48 hours)
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=48)

    article = await articles_collection.find_one({
        "published_at": {"$gte": cutoff_time},
        "$or": [
            {"narrative_summary": {"$exists": False}},
            {"narrative_summary": None},
        ]
    })

    if not article:
        print("❌ No articles found without narrative_summary in last 48 hours")
        return

    article_id = article.get("_id")
    print(f"\n✅ Found test article: {article_id}")
    print(f"   Title: {article.get('title', 'N/A')[:60]}...")
    print(f"   Current narrative_summary: {article.get('narrative_summary', 'NULL')}")
    print(f"   Current nucleus_entity: {article.get('nucleus_entity', 'NULL')}")

    # Simulate what the backfill does
    print("\n--- Testing update_one behavior ---")

    test_data = {
        "actors": ["Bitcoin", "Ethereum"],
        "actor_salience": {"Bitcoin": 5, "Ethereum": 3},
        "nucleus_entity": "Bitcoin",
        "narrative_focus": "price movement",
        "actions": ["surged", "recovered"],
        "tensions": ["volatility"],
        "implications": "Market volatility continues",
        "narrative_summary": "Test narrative summary from update_one",
        "narrative_hash": "abc123def456",
        "narrative_extracted_at": datetime.now(timezone.utc),
        "status": None,
        "degraded_reason": None
    }

    print(f"\n1. Attempting update_one with filter: {{'_id': ObjectId('{article_id}')}}")
    print(f"2. Data to update (keys): {list(test_data.keys())}")

    try:
        result = await articles_collection.update_one(
            {"_id": article_id},
            {"$set": test_data}
        )

        print(f"\n✅ update_one executed successfully")
        print(f"   Matched count: {result.matched_count}")
        print(f"   Modified count: {result.modified_count}")
        print(f"   Acknowledged: {result.acknowledged}")

        if result.matched_count == 0:
            print("\n❌ PROBLEM: matched_count=0 — the filter didn't match ANY documents!")
            print("   This means: article doesn't exist or _id mismatch")
        elif result.modified_count == 0:
            print("\n⚠️  WARNING: modified_count=0 — matched but didn't modify")
            print("   This could mean: all values were already the same")
        else:
            print(f"\n✅ Successfully updated {result.modified_count} document(s)")

        # Verify the update
        print("\n--- Verifying update ---")
        updated_article = await articles_collection.find_one({"_id": article_id})

        if updated_article:
            print(f"✅ Article still exists in DB")
            print(f"   New narrative_summary: {updated_article.get('narrative_summary', 'NULL')}")
            print(f"   New nucleus_entity: {updated_article.get('nucleus_entity', 'NULL')}")
            print(f"   New narrative_extracted_at: {updated_article.get('narrative_extracted_at', 'NULL')}")
        else:
            print(f"❌ Article disappeared after update!")

    except Exception as e:
        print(f"❌ update_one FAILED with exception:")
        print(f"   {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_update_diagnostic())
