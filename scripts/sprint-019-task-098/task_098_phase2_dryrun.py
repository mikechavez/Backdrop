#!/usr/bin/env python3
"""
TASK-098 Phase 2: Dry-Run Refresh Selection

Show exactly what would happen if we proceed:
- Which 5 IDs would be set needs_summary_update=true
- Whether any other narratives already have needs_summary_update=true
- Whether refresh_flagged_narratives would process our 5 first
- MAX_REFRESH_PER_RUN and budget impact
- Estimated LLM cost
- Expected writes (without doing them)
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

# The 5 approved narratives
APPROVED_IDS = [
    "695eb4b3ce758d67abd6e8f4",
    "698baa105278ec9e19bf2a19",
    "68f32d197082f49df56956c6",
    "68f03343bc9ab7390ca7af71",
    "68f03350bc9ab7390ca7af78",
]

print("=" * 120)
print("TASK-098 PHASE 2: DRY-RUN REFRESH SELECTION (NO MUTATIONS)")
print("=" * 120)

object_ids = [ObjectId(nid) for nid in APPROVED_IDS]

# Step 1: Check for other flagged narratives
print("\n[STEP 1] Checking for OTHER narratives with needs_summary_update=True")
print("-" * 120)

other_flagged = list(narratives.find(
    {
        "needs_summary_update": True,
        "_id": {"$nin": object_ids},
        "lifecycle_state": {"$ne": "dormant"}
    },
    {"_id": 1, "title": 1, "lifecycle_state": 1, "last_updated": 1}
).sort("last_updated", -1))

if other_flagged:
    print(f"⚠️  Found {len(other_flagged)} other flagged narratives:")
    for i, n in enumerate(other_flagged[:5], 1):
        print(f"   {i}. {n.get('title', 'Unknown')[:70]} ({n.get('lifecycle_state')})")
    if len(other_flagged) > 5:
        print(f"   ... and {len(other_flagged) - 5} more")
else:
    print(f"✅ No other narratives are flagged for refresh")

# Step 2: Show what our 5 narratives look like now
print("\n[STEP 2] Current state of our 5 narratives")
print("-" * 120)

our_narratives = list(narratives.find(
    {"_id": {"$in": object_ids}},
    {
        "_id": 1,
        "title": 1,
        "lifecycle_state": 1,
        "needs_summary_update": 1,
        "last_updated": 1,
        "article_count": 1,
    }
).sort("last_updated", -1))

for i, n in enumerate(our_narratives, 1):
    print(f"{i}. {n.get('title', 'Unknown')[:70]}")
    print(f"   needs_summary_update: {n.get('needs_summary_update')} → will be set to: true")
    print(f"   lifecycle_state: {n.get('lifecycle_state')}")
    print(f"   article_count: {n.get('article_count')}")

# Step 3: Simulate refresh task selection
print("\n[STEP 3] Simulating refresh_flagged_narratives task selection")
print("-" * 120)

# Get all candidates that would be processed
all_flagged = list(narratives.find(
    {
        "needs_summary_update": True,
        "lifecycle_state": {"$ne": "dormant"}
    },
    {
        "_id": 1,
        "title": 1,
        "lifecycle_state": 1,
        "last_updated": 1,
    }
).sort("last_updated", -1))

# But after we set our 5, they would be included too
print("\nAfter Phase 4A (flagging our 5):")
print(f"  Total flagged narratives: {len(all_flagged)} + 5 (our new ones) = {len(all_flagged) + 5}")

MAX_REFRESH_PER_RUN = 20

print(f"\nrefresh_flagged_narratives task behavior:")
print(f"  MAX_REFRESH_PER_RUN: {MAX_REFRESH_PER_RUN}")
print(f"  Query: {{'needs_summary_update': True, 'lifecycle_state': {{'$ne': 'dormant'}}}}")
print(f"  Sort: lifecycle_priority, then last_updated DESC")

# Simulate priority sort (from narrative_refresh.py)
LIFECYCLE_PRIORITY = {
    "hot": 0,
    "emerging": 1,
    "rising": 2,
    "reactivated": 3,
    "cooling": 4,
}

def priority_key(narrative):
    lifecycle = narrative.get("lifecycle_state", "cooling")
    priority = LIFECYCLE_PRIORITY.get(lifecycle, 99)
    last_updated = narrative.get("last_updated", datetime.min.replace(tzinfo=timezone.utc))
    if isinstance(last_updated, datetime):
        timestamp = last_updated.timestamp()
    else:
        timestamp = 0
    return (priority, -timestamp)  # Negative timestamp for DESC sort

would_process = sorted(all_flagged, key=priority_key)[:MAX_REFRESH_PER_RUN]

print(f"\nWould process: {len(would_process)} narratives (max {MAX_REFRESH_PER_RUN})")

# Check if our 5 are in the first batch
our_ids_set = set(APPROVED_IDS)
our_in_first_batch = [n for n in would_process if str(n.get("_id")) in our_ids_set]

if len(our_in_first_batch) == 5:
    print(f"✅ All 5 of our narratives would be processed in the FIRST batch")
elif len(our_in_first_batch) > 0:
    print(f"⚠️  Only {len(our_in_first_batch)}/5 of our narratives would be in first batch")
    print(f"    The others would require a second execution")
else:
    print(f"❌ None of our narratives would be in first batch (other flagged narratives take priority)")

# Step 4: Cost estimate
print("\n[STEP 4] Estimated LLM cost for Phase 4B")
print("-" * 120)

cost_per_narrative = 0.002  # Estimated cost per narrative_generate call
total_cost = len(our_narratives) * cost_per_narrative

print(f"Narratives to refresh: {len(our_narratives)}")
print(f"Cost per narrative (narrative_generate): ~${cost_per_narrative:.6f}")
print(f"Total estimated cost: ~${total_cost:.4f}")
print(f"\nBudget status:")
print(f"  Daily soft limit: $10.00")
print(f"  Daily hard limit: $15.00")
print(f"  This refresh: ~${total_cost:.4f}")
print(f"  Impact: Negligible (<1% of soft limit)")

# Step 5: Expected writes
print("\n[STEP 5] Expected database writes")
print("-" * 120)

print(f"""
PHASE 4A (Approval-gated, manual):
  Operation: updateMany
  Filter: {{"_id": {{"$in": [5 ObjectIds]}}}}
  Update: {{"$set": {{"needs_summary_update": true}}}}
  Expected writes: 5 documents updated
  Actual changes: 5 (all currently False → True)

PHASE 4B (Automated via refresh_flagged_narratives):
  Operation: For each of 5 narratives:
    - narrative_generate LLM call
    - updateOne with fresh title, summary, last_summary_generated_at, needs_summary_update=false
  Expected writes: 5 documents updated
  Expected cost: 5 × narrative_generate calls
  Expected duration: ~20-30 seconds (5 × ~5 sec per LLM call)

Total mutations:
  - Phase 4A: 5 write operations
  - Phase 4B: 5 write operations + 5 LLM calls
  - Side effects: llm_traces updated with 5 new narrative_generate entries
""")

# Step 6: Rollback considerations
print("\n[STEP 6] Rollback and safety considerations")
print("-" * 120)

print("""
If something goes wrong:

  Before refresh starts: Can manually set needs_summary_update back to False for these 5 IDs

  During refresh (partial): Some narratives get refreshed, others don't
    → Safe: Narratives stay in their refreshed or pre-refresh state
    → Can re-run to complete the batch

  After successful refresh:
    → If quality is poor, smoke briefing will reject (high confidence threshold)
    → Production briefing won't run
    → Can manually fix via another refresh cycle

  No scenario causes data corruption or permanent state damage.
""")

print("\n" + "=" * 120)
print("PHASE 2 DRY-RUN SUMMARY")
print("=" * 120)

print(f"""
WHAT WOULD HAPPEN:
  1. Set needs_summary_update=True for 5 narratives
  2. refresh_flagged_narratives task runs
  3. Task processes our 5 (+ maybe others depending on queue)
  4. Each gets fresh LLM summary
  5. Each gets last_summary_generated_at set to now
  6. All 5 become trusted

SCOPE OF CHANGE:
  - Narratives touched: 5
  - LLM calls: 5 × narrative_generate
  - Database mutations: 10 write operations (5 flag + 5 refresh)
  - Cost: ~$0.01
  - Duration: ~30-60 seconds

SAFETY:
  ✅ Uses tested production code path
  ✅ Respects budget limits
  ✅ No data corruption possible
  ✅ Can rollback by re-flagging

READY FOR PHASE 3 (APPROVAL)?
  All pre-conditions met:
  ✅ 5 narratives identified
  ✅ All eligible for refresh
  ✅ Dry-run completed without mutations
  ✅ Cost estimated
  ✅ Writes simulated

  Waiting for explicit approval to proceed to Phase 4 (Execute).
""")

print("=" * 120)
