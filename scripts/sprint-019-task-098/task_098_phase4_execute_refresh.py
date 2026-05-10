#!/usr/bin/env python3
"""
TASK-098 Phase 4: Execute Bounded Refresh

This script:
1. Sets needs_summary_update=True for the 20 approved narrative IDs
2. Waits for refresh_flagged_narratives to complete (polls every 5 seconds)
3. Monitors LLM traces during refresh window
4. Reports success/failure and cost
"""
import os
import json
import asyncio
import time
from datetime import datetime, timezone
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")

if not MONGODB_URI:
    print("❌ MONGODB_URI not set")
    exit(1)

# Top 20 narrative IDs (from approval phase)
REFRESH_IDS = [
    "695eb4b3ce758d67abd6e8f4",
    "698baa105278ec9e19bf2a19",
    "68f32d197082f49df56956c6",
    "68f03343bc9ab7390ca7af71",
    "68f03350bc9ab7390ca7af78",
    "69fe50dabd5313e9062754c7",
    "69fd2d3a03dc7874df10099b",
    "68f7d591549ab51c11335648",
    "68f132da6c15d3927e402274",
    "69e086dcf8bb33f93e1de49c",
    "69f9660a28dc2250fc100945",
    "69cec78faa731a71682e815e",
    "68f038166a64ae154ad352f5",
    "6942c60a9eccade71afccfc2",
    "68f03dd4a58523ef72254235",
    "693bfb2b9eccade71afcc62f",
    "6901de0db3b56c831a0a1550",
    "68ec0da42c74a4887b0b9d48",
    "6900ea1ab3b56c831a0a0bc6",
    "6939da229eccade71afcc21c",
]

client = MongoClient(MONGODB_URI)
db = client["crypto_news"]
narratives = db["narratives"]
llm_traces = db["llm_traces"]

print("=" * 100)
print("TASK-098 PHASE 4: EXECUTE BOUNDED REFRESH")
print("=" * 100)

# Step 1: Flag narratives for refresh
print(f"\n[STEP 1] Setting needs_summary_update=True for {len(REFRESH_IDS)} narratives...")

object_ids = [ObjectId(nid) for nid in REFRESH_IDS]

refresh_start_time = datetime.now(timezone.utc)

try:
    result = narratives.update_many(
        {"_id": {"$in": object_ids}},
        {"$set": {"needs_summary_update": True}}
    )
    print(f"✅ Updated {result.modified_count} documents")
    if result.modified_count != len(REFRESH_IDS):
        print(f"⚠️  WARNING: Expected {len(REFRESH_IDS)}, but got {result.modified_count}")
except Exception as e:
    print(f"❌ Update failed: {e}")
    exit(1)

# Step 2: Trigger refresh task
print(f"\n[STEP 2] Triggering refresh_flagged_narratives task...")
print("⏳ Waiting for task to complete (polling every 5 seconds)...\n")

# This is a placeholder - in production, you'd use Celery to trigger the task
# For this demo, we'll simulate by showing what needs to happen
print("""
NOTE: In a production environment, you would trigger the Celery task:

  from celery import current_app
  from src.crypto_news_aggregator.tasks.narrative_refresh import refresh_flagged_narratives_task

  task = current_app.send_task('refresh_flagged_narratives')
  print(f"Task ID: {task.id}")

For now, please trigger the refresh task via:
  - Celery Beat scheduler (if configured)
  - Direct CLI: celery -A crypto_news_aggregator.celery_app call refresh_flagged_narratives
  - Kubernetes job (if deployed)

Polling for task completion for the next 2 minutes...
""")

# Step 3: Monitor task progress by watching narratives flag status
print("[STEP 3] Monitoring refresh progress (watching needs_summary_update flag)...")

for attempt in range(24):  # 24 * 5 = 120 seconds = 2 minutes
    remaining = narratives.count_documents({
        "_id": {"$in": object_ids},
        "needs_summary_update": True
    })

    if remaining == 0:
        print(f"✅ All {len(REFRESH_IDS)} narratives refreshed!")
        break

    print(f"   [{attempt+1}/24] {remaining}/{len(REFRESH_IDS)} still pending...")
    time.sleep(5)
else:
    print(f"⚠️  Timeout: {remaining} narratives still pending after 2 minutes")
    print("   Task may still be running. Continue to Phase 5 (verification) to check status.")

refresh_end_time = datetime.now(timezone.utc)

# Step 4: Check LLM cost
print(f"\n[STEP 4] Checking LLM traces during refresh window...")

traces = list(llm_traces.find({
    "operation": "narrative_generate",
    "timestamp": {"$gte": refresh_start_time, "$lte": refresh_end_time}
}).sort("timestamp", -1))

total_cost = 0.0
for trace in traces:
    cost = trace.get("cost", 0.0)
    total_cost += cost
    print(f"   {trace['timestamp']}: ${cost:.6f} {trace.get('model', 'unknown')}")

print(f"\n💰 Total LLM cost during refresh: ${total_cost:.4f}")

# Step 5: Verify narratives were updated
print(f"\n[STEP 5] Verifying narrative updates...")

refreshed = list(narratives.find(
    {"_id": {"$in": object_ids}},
    {
        "_id": 1,
        "title": 1,
        "summary": 1,
        "last_summary_generated_at": 1,
        "needs_summary_update": 1,
    }
))

updated_count = 0
for n in refreshed:
    if n.get("last_summary_generated_at") and n.get("last_summary_generated_at") >= datetime(2026, 5, 10, 0, 0, 0, tzinfo=timezone.utc):
        updated_count += 1
        print(f"   ✅ {n.get('title', 'Unknown')[:60]}")

print(f"\n✅ {updated_count}/{len(REFRESH_IDS)} narratives have fresh summaries (last_summary_generated_at >= 2026-05-10)")

print("\n" + "=" * 100)
print("PHASE 4 EXECUTION COMPLETE")
print("=" * 100)

print(f"""
SUMMARY:
  - Narratives flagged for refresh: {len(REFRESH_IDS)}
  - Narratives successfully refreshed: {updated_count}
  - LLM cost: ${total_cost:.4f}
  - Refresh window: {refresh_start_time} to {refresh_end_time}

NEXT STEPS:
  → Phase 5: Post-refresh verification (run phase 1 discovery to confirm trust status)
  → Phase 6: Briefing readiness decision (smoke vs production)
""")
