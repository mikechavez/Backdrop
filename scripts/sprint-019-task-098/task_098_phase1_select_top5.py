#!/usr/bin/env python3
"""
TASK-098 Phase 1: Select Top 5 Narratives for Refresh

Report on the approved 5 narratives:
- _id
- lifecycle_state
- first_seen
- last_updated
- last_summary_generated_at
- needs_summary_update
- article_count
- current trust status
- eligible for refresh_flagged_narratives
"""
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")

if not MONGODB_URI:
    print("❌ MONGODB_URI not set")
    exit(1)

client = MongoClient(MONGODB_URI)
db = client["crypto_news"]
narratives = db["narratives"]

# The 5 approved narratives for Phase 1
APPROVED_IDS = [
    "695eb4b3ce758d67abd6e8f4",  # Senate Banking Committee
    "698baa105278ec9e19bf2a19",  # LayerZero Exploit
    "68f32d197082f49df56956c6",  # Bitcoin Holds 75K
    "68f03343bc9ab7390ca7af71",  # SEC Regulatory Framework
    "68f03350bc9ab7390ca7af78",  # Coinbase Infrastructure
]

print("=" * 120)
print("TASK-098 PHASE 1: SELECT TOP 5 NARRATIVES FOR FIRST REFRESH")
print("=" * 120)

object_ids = [ObjectId(nid) for nid in APPROVED_IDS]

cursor = narratives.find(
    {"_id": {"$in": object_ids}},
    {
        "_id": 1,
        "title": 1,
        "lifecycle_state": 1,
        "first_seen": 1,
        "last_updated": 1,
        "last_summary_generated_at": 1,
        "needs_summary_update": 1,
        "article_count": 1,
        "_fresh_start_validated_at": 1,
        "article_ids": 1,
    }
).sort("last_updated", -1)

narratives_list = list(cursor)

print(f"\n📋 APPROVED NARRATIVES FOR PHASE 1 REFRESH\n")

def is_trusted(narrative):
    cutoff = datetime(2026, 5, 10, 0, 0, 0, tzinfo=timezone.utc)

    first_seen = narrative.get("first_seen")
    if first_seen and isinstance(first_seen, datetime):
        if first_seen.tzinfo is None:
            first_seen = first_seen.replace(tzinfo=timezone.utc)
        if first_seen >= cutoff:
            return True

    last_gen = narrative.get("last_summary_generated_at")
    if last_gen and isinstance(last_gen, datetime):
        if last_gen.tzinfo is None:
            last_gen = last_gen.replace(tzinfo=timezone.utc)
        if last_gen >= cutoff:
            return True

    fresh_val = narrative.get("_fresh_start_validated_at")
    if fresh_val and isinstance(fresh_val, datetime):
        if fresh_val.tzinfo is None:
            fresh_val = fresh_val.replace(tzinfo=timezone.utc)
        if fresh_val >= cutoff:
            return True

    return False

for i, n in enumerate(narratives_list, 1):
    narrative_id = str(n.get("_id"))
    title = n.get("title", "")
    lifecycle = n.get("lifecycle_state", "unknown")
    first_seen = n.get("first_seen")
    last_updated = n.get("last_updated")
    last_gen = n.get("last_summary_generated_at")
    needs_update = n.get("needs_summary_update", False)
    article_count = n.get("article_count", 0)
    article_ids = n.get("article_ids", [])
    is_dormant = lifecycle == "dormant"
    trust_status = "✅ TRUSTED" if is_trusted(n) else "❌ UNTRUSTED"

    print(f"{i}. {title}")
    print(f"   ID: {narrative_id}")
    print(f"   Lifecycle: {lifecycle} | Dormant: {is_dormant} | Trust: {trust_status}")
    print(f"   first_seen: {first_seen}")
    print(f"   last_updated: {last_updated}")
    print(f"   last_summary_generated_at: {last_gen}")
    print(f"   needs_summary_update: {needs_update}")
    print(f"   article_count: {article_count}")
    print(f"   article_ids: {len(article_ids)} articles")

    # Eligibility check
    eligible = not is_dormant and article_count > 0 and len(article_ids) > 0
    status = "✅ ELIGIBLE" if eligible else "❌ NOT ELIGIBLE"
    print(f"   Refresh eligibility: {status}")
    if not eligible:
        if is_dormant:
            print(f"      → Reason: Dormant lifecycle")
        if article_count == 0:
            print(f"      → Reason: No articles")
        if len(article_ids) == 0:
            print(f"      → Reason: No article_ids")
    print()

print("=" * 120)
print("PHASE 1 SUMMARY")
print("=" * 120)

eligible_count = sum(
    1 for n in narratives_list
    if n.get("lifecycle_state") != "dormant"
    and n.get("article_count", 0) > 0
    and len(n.get("article_ids", [])) > 0
)
untrusted_count = sum(1 for n in narratives_list if not is_trusted(n))

print(f"""
NARRATIVES IDENTIFIED:
  - Count: {len(narratives_list)} found from {len(APPROVED_IDS)} approved IDs
  - Trusted: {len(narratives_list) - untrusted_count}
  - Untrusted: {untrusted_count}
  - Eligible for refresh: {eligible_count}/{len(narratives_list)}

NEXT STEP (Phase 2):
  Dry-run refresh selection without mutations
""")

print("=" * 120)
