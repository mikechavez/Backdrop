#!/usr/bin/env python3
"""
TASK-098 Phase 1: Read-Only Discovery
- Identify current top UI narratives
- Verify trust status under FEATURE-060
- Verify API display-mode behavior
"""
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
FRESH_START_CUTOFF = "2026-05-10T00:00:00Z"

if not MONGODB_URI:
    print(json.dumps({"error": "MONGODB_URI not set"}), file=__import__('sys').stderr)
    exit(1)

client = MongoClient(MONGODB_URI)
db = client["crypto_news"]
narratives = db["narratives"]

print("=" * 80)
print("TASK-098 PHASE 1: READ-ONLY DISCOVERY")
print("=" * 80)

# Phase 1.1: Identify Current Top UI Narratives
print("\n[1.1] CURRENT TOP UI NARRATIVES (active lifecycle states)")
print("-" * 80)

cursor = narratives.find(
    {"lifecycle_state": {"$in": ["hot", "emerging", "rising", "reactivated"]}},
    {
        "_id": 1,
        "title": 1,
        "lifecycle_state": 1,
        "first_seen": 1,
        "last_updated": 1,
        "last_summary_generated_at": 1,
        "_fresh_start_validated_at": 1,
        "article_count": 1,
        "needs_summary_update": 1,
        "display_title": 1,
        "display_summary": 1,
        "display_mode": 1,
    }
).sort("last_updated", -1).limit(20)

narratives_list = list(cursor)
print(f"Found {len(narratives_list)} active narratives (limiting display to first 10 for readability)\n")

# Phase 1.2: Verify Trust Status
print("[1.2] TRUST STATUS ANALYSIS (FEATURE-060)")
print("-" * 80)

from datetime import timezone
cutoff_dt = datetime(2026, 5, 10, 0, 0, 0, tzinfo=timezone.utc)

trusted_count = 0
untrusted_count = 0

for i, n in enumerate(narratives_list, 1):
    narrative_id = str(n.get("_id"))
    title = n.get("title", "")
    lifecycle = n.get("lifecycle_state", "unknown")

    first_seen = n.get("first_seen")
    last_summary_gen = n.get("last_summary_generated_at")
    fresh_start_val = n.get("_fresh_start_validated_at")

    # Trust rule: first_seen >= cutoff OR last_summary_generated_at >= cutoff OR _fresh_start_validated_at >= cutoff
    # Handle both aware and naive datetimes
    def is_after_cutoff(dt):
        if not dt:
            return False
        # Remove timezone info for comparison if present
        if dt.tzinfo:
            dt = dt.replace(tzinfo=None)
        return dt >= datetime(2026, 5, 10, 0, 0, 0)

    is_trusted = (
        is_after_cutoff(first_seen) or
        is_after_cutoff(last_summary_gen) or
        is_after_cutoff(fresh_start_val)
    )

    if is_trusted:
        trusted_count += 1
    else:
        untrusted_count += 1

    trust_status = "✅ TRUSTED" if is_trusted else "❌ UNTRUSTED"

    print(f"\n{i}. {title[:70]}")
    print(f"   ID: {narrative_id}")
    print(f"   Lifecycle: {lifecycle}")
    print(f"   Trust Status: {trust_status}")
    print(f"   first_seen: {first_seen}")
    print(f"   last_summary_generated_at: {last_summary_gen}")
    print(f"   _fresh_start_validated_at: {fresh_start_val}")
    print(f"   article_count: {n.get('article_count', 0)}")
    print(f"   needs_summary_update: {n.get('needs_summary_update', None)}")

print("\n" + "-" * 80)
print(f"Summary: {trusted_count} trusted, {untrusted_count} untrusted")

# Phase 1.3: API Display Mode
print("\n[1.3] API DISPLAY MODE FIELDS")
print("-" * 80)

for i, n in enumerate(narratives_list[:5], 1):
    title = n.get("title", "")
    display_mode = n.get("display_mode")
    display_title = n.get("display_title")
    display_summary = n.get("display_summary")

    print(f"\n{i}. {title[:70]}")
    print(f"   display_mode: {display_mode}")
    print(f"   display_title: {display_title[:50] if display_title else None}...")
    print(f"   display_summary present: {bool(display_summary)}")

# Phase 1.4: Identify Safe Refresh Mechanism
print("\n[1.4] SAFE REFRESH MECHANISM INSPECTION")
print("-" * 80)

import inspect
import importlib.util

backend_path = "/Users/mc/dev-projects/crypto-news-aggregator/src/services/narrative_refresh.py"
if os.path.exists(backend_path):
    spec = importlib.util.spec_from_file_location("narrative_refresh", backend_path)
    module = importlib.util.module_from_spec(spec)

    with open(backend_path) as f:
        content = f.read()
        print(f"Found narrative_refresh.py ({len(content)} bytes)")

        # Look for refresh functions
        if "def refresh" in content:
            print("✅ Contains refresh functions")
        if "narrative_generate" in content:
            print("✅ Calls narrative_generate operation")
        if "last_summary_generated_at" in content:
            print("✅ Updates last_summary_generated_at")
        if "needs_summary_update" in content:
            print("✅ Manages needs_summary_update flag")
else:
    print(f"❌ {backend_path} not found")

print("\n" + "=" * 80)
print("PHASE 1 DISCOVERY COMPLETE")
print("=" * 80)
