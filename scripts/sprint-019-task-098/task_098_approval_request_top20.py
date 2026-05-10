#!/usr/bin/env python3
"""
TASK-098 Phase 3: Approval Request for Top 20 UI Narratives Refresh

This script displays the exact 20 narrative IDs that will be flagged
for refresh, with their titles and current state.
"""
import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")

if not MONGODB_URI:
    print(json.dumps({"error": "MONGODB_URI not set"}), file=__import__('sys').stderr)
    exit(1)

client = MongoClient(MONGODB_URI)
db = client["crypto_news"]
narratives = db["narratives"]

print("=" * 100)
print("TASK-098 PHASE 3: APPROVAL REQUEST - TOP 20 ACTIVE NARRATIVES")
print("=" * 100)

# Get top 20 active narratives
cursor = narratives.find(
    {"lifecycle_state": {"$in": ["hot", "emerging", "rising", "reactivated"]}},
    {
        "_id": 1,
        "title": 1,
        "lifecycle_state": 1,
        "article_count": 1,
        "needs_summary_update": 1,
    }
).sort("last_updated", -1).limit(20)

narratives_list = list(cursor)

print(f"\n📋 PROPOSED REFRESH TARGET: TOP {len(narratives_list)} ACTIVE NARRATIVES\n")

narrative_ids = []
for i, n in enumerate(narratives_list, 1):
    narrative_id = str(n.get("_id"))
    title = n.get("title", "")
    lifecycle = n.get("lifecycle_state", "")
    article_count = n.get("article_count", 0)

    narrative_ids.append(narrative_id)

    print(f"{i:2d}. {title[:80]:<80} | {lifecycle:10s} | {article_count:2d} articles")
    print(f"    ID: {narrative_id}")

print("\n" + "=" * 100)
print("PROPOSED ACTION")
print("=" * 100)

print(f"""
1. Set needs_summary_update=True for these {len(narrative_ids)} narrative IDs
2. Run refresh_flagged_narratives task (Celery or direct)
3. Task will:
   - Generate fresh summaries for each via LLM
   - Set last_summary_generated_at = now
   - Clear needs_summary_update flag
4. Post-refresh: All {len(narrative_ids)} become trusted (for briefing synthesis)

SCOPE:
  - DB mutations: {len(narrative_ids)} updateOne + {len(narrative_ids)} refresh updates
  - LLM calls: {len(narrative_ids)} × narrative_generate
  - Estimated cost: ~${len(narrative_ids) * 0.002:.2f}
  - Max per-run limit: 20 (this request = 20, uses full budget for one run)
  - Budget safety: check_llm_budget enforced during refresh

EXPECTED OUTCOME:
  - trusted_narratives: 0 → {len(narrative_ids)}
  - Smoke briefing: Can proceed with real trusted summaries
  - Production briefing: Resumable with meaningful content

ROLLBACK:
  - If errors during refresh, needs_summary_update flag clears on error
  - No permanent state damage; narratives remain in pre-refresh state
  - Can re-run if needed

VERIFICATION:
  - After refresh: Run phase 1 discovery to confirm all 20 have last_summary_generated_at >= 2026-05-10
  - Check llm_traces for 20 narrative_generate calls during refresh window
  - Confirm trusted_narratives count = {len(narrative_ids)} via FEATURE-060 logic

""")

print("=" * 100)
print("APPROVAL GATE")
print("=" * 100)

print("""
⚠️  WAITING FOR EXPLICIT APPROVAL

To proceed with Phase 4 (Execute Bounded Refresh), confirm:

[ ] I approve setting needs_summary_update=True for these 20 narratives
[ ] I approve running refresh_flagged_narratives task
[ ] I understand cost is ~$0.04 (within budget)
[ ] I understand this uses the full 20/run limit for this execution

Once approved, next step is:
  Phase 4: Execute bounded refresh via:
    - MongoDB: Set needs_summary_update=True for 20 IDs
    - Celery/Task: Trigger refresh_flagged_narratives
    - Monitor: Watch task logs and LLM traces
  Phase 5: Post-refresh verification
  Phase 6: Briefing readiness decision (smoke vs prod)
""")

print("=" * 100)

# Write IDs to a file for easy copy-paste in the refresh script
ids_json_array = json.dumps(narrative_ids)
print(f"\nNarrative IDs (JSON array for scripting):")
print(ids_json_array)

with open("/tmp/task_098_refresh_ids.txt", "w") as f:
    for nid in narrative_ids:
        f.write(nid + "\n")

print(f"\nIDs written to /tmp/task_098_refresh_ids.txt for copy-paste")
