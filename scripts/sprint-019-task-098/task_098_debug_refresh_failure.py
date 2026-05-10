#!/usr/bin/env python3
"""
TASK-098: Debug Refresh Failure

Investigate why refresh task didn't complete all 5 narratives.
"""
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId

load_dotenv()
MONGODB_URI = os.getenv("MONGODB_URI")
client = MongoClient(MONGODB_URI)
db = client["crypto_news"]
llm_traces = db["llm_traces"]
narratives = db["narratives"]

print("=" * 120)
print("TASK-098: DEBUG REFRESH FAILURE")
print("=" * 120)

# Check LLM traces
print("\n[1] CHECKING LLM TRACES FOR ERRORS DURING REFRESH")
print("-" * 120)

recent = datetime.now(timezone.utc) - timedelta(minutes=10)

traces = list(llm_traces.find({
    "operation": "narrative_generate",
    "timestamp": {"$gte": recent}
}).sort("timestamp", -1).limit(20))

if traces:
    print(f"Found {len(traces)} narrative_generate calls in last 10 minutes:\n")
    total_cost = 0
    for i, trace in enumerate(traces, 1):
        timestamp = trace.get("timestamp")
        cost = trace.get("cost", 0)
        error = trace.get("error")
        model = trace.get("model")
        total_cost += cost

        status = f"ERROR: {error}" if error else "✅ OK"
        print(f"  {i}. {timestamp}: {status} | Cost: ${cost:.6f} | Model: {model}")
    print(f"\nTotal LLM cost: ${total_cost:.4f}")
else:
    print("❌ NO narrative_generate traces found in last 10 minutes!")
    print("   This means refresh_flagged_narratives either:")
    print("   1. Did not execute at all")
    print("   2. Did not call LLM (failed before that step)")
    print("   3. Task was queued but not processed by worker")

# Check narrative state
print("\n[2] CURRENT NARRATIVE FLAGGING STATE")
print("-" * 120)

APPROVED_IDS = [
    "695eb4b3ce758d67abd6e8f4",
    "698baa105278ec9e19bf2a19",
    "68f32d197082f49df56956c6",
    "68f03343bc9ab7390ca7af71",
    "68f03350bc9ab7390ca7af78",
]

object_ids = [ObjectId(nid) for nid in APPROVED_IDS]

cursor = narratives.find(
    {"_id": {"$in": object_ids}},
    {"_id": 1, "title": 1, "needs_summary_update": 1, "article_ids": 1, "last_summary_generated_at": 1}
).sort("last_updated", -1)

flagged_count = 0
for i, n in enumerate(cursor, 1):
    nid = str(n.get("_id"))
    title = n.get("title", "")[:60]
    needs_update = n.get("needs_summary_update")
    article_count = len(n.get("article_ids", []))
    last_gen = n.get("last_summary_generated_at")

    if needs_update:
        flagged_count += 1
        status = "⏳ STILL FLAGGED"
    else:
        status = "✓ Flag cleared"

    print(f"  {i}. {status} | {article_count:2d} articles | last_gen={last_gen} | {title}")

print(f"\nStill flagged for refresh: {flagged_count}/5")

# Hypothesis
print("\n[3] DIAGNOSIS")
print("-" * 120)

if len(traces) == 0:
    print("""
❌ No LLM activity detected. Likely causes:

1. Celery broker (Redis) not running
   → Task was accepted but never processed by worker

2. Celery worker not running
   → Task queued but no worker to execute it

3. Task failed immediately (before LLM)
   → Check application error logs

4. Task executed successfully but didn't call LLM
   → Possible data issue (empty article_ids, dormant narratives, etc.)

NEXT STEPS:
1. Verify Redis is running: redis-cli ping
2. Verify Celery worker is running: ps aux | grep celery
3. Check Railway logs for application errors
4. Manually run refresh_flagged_narratives via Python
""")
elif len(traces) < 5:
    print(f"""
⚠️  Only {len(traces)}/5 narratives attempted LLM generation.

Possible reasons:
1. Some narratives had no articles (article_ids empty)
2. Some narratives were dormant
3. Some narratives failed during processing
4. Task hit budget limit and stopped
5. Task crashed mid-execution

NEXT STEPS:
1. Check the {5 - len(traces)} narratives without LLM traces
2. Verify they have article_ids populated
3. Check task execution logs
""")
else:
    print(f"""
✅ All {len(traces)} narratives attempted LLM generation.

But they didn't set last_summary_generated_at. Possible reasons:
1. LLM responses were null/empty
2. Update operation failed after LLM generation
3. Data was generated but reverted

NEXT STEPS:
1. Check LLM response quality
2. Check MongoDB update errors
3. Review task logs for exceptions
""")

print("\n" + "=" * 120)
