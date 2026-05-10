#!/usr/bin/env python3
"""
TASK-098 Phase 0: Verify Display-Mode Behavior

For the current top UI narratives, call the public API and inspect:
- What display_mode is being returned?
- For untrusted narratives, is it "article_cluster"?
- Is the frontend rendering the display fields correctly?
"""
import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient
import httpx
import asyncio

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
API_BASE = os.getenv("API_BASE", "https://context-owl-production.up.railway.app")

if not MONGODB_URI:
    print("❌ MONGODB_URI not set")
    exit(1)

client = MongoClient(MONGODB_URI)
db = client["crypto_news"]
narratives_col = db["narratives"]

async def main():
    print("=" * 120)
    print("TASK-098 PHASE 0: VERIFY DISPLAY-MODE BEHAVIOR")
    print("=" * 120)

    # Phase 0.1: Get top active narratives from DB
    print("\n[0.1] FETCHING TOP ACTIVE NARRATIVES FROM DATABASE")
    print("-" * 120)

    cursor = narratives_col.find(
        {"lifecycle_state": {"$in": ["hot", "emerging", "rising", "reactivated"]}},
        {
            "_id": 1,
            "title": 1,
            "summary": 1,
            "lifecycle_state": 1,
            "first_seen": 1,
            "last_updated": 1,
            "last_summary_generated_at": 1,
            "_fresh_start_validated_at": 1,
            "display_mode": 1,
            "display_title": 1,
            "display_summary": 1,
            "article_count": 1,
        }
    ).sort("last_updated", -1).limit(10)

    db_narratives = list(cursor)
    print(f"Found {len(db_narratives)} active narratives in DB\n")

    # Helper: compute trust status
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

    # Phase 0.2: Call public narratives API
    print("[0.2] CALLING PUBLIC NARRATIVES API")
    print("-" * 120)

    api_url = f"{API_BASE}/api/v1/narratives/active"
    print(f"Endpoint: {api_url}\n")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client_http:
            response = await client_http.get(api_url)
            response.raise_for_status()
            api_narratives = response.json()

            if isinstance(api_narratives, dict) and "data" in api_narratives:
                api_narratives = api_narratives["data"]

            print(f"✅ API returned {len(api_narratives)} narratives\n")
    except Exception as e:
        print(f"❌ API call failed: {e}")
        print(f"   (Is the app running on {API_BASE}?)")
        print(f"   Continuing with DB data only...\n")
        api_narratives = []

    # Phase 0.3: Compare and report
    print("[0.3] DISPLAY-MODE ANALYSIS FOR TOP NARRATIVES")
    print("-" * 120)

    for i, db_narrative in enumerate(db_narratives[:10], 1):
        narrative_id = str(db_narrative.get("_id"))
        title = db_narrative.get("title", "")[:80]
        lifecycle = db_narrative.get("lifecycle_state", "")
        trust = is_trusted(db_narrative)
        trust_str = "✅ TRUSTED" if trust else "❌ UNTRUSTED"

        print(f"\n{i}. {title}")
        print(f"   ID: {narrative_id}")
        print(f"   Lifecycle: {lifecycle} | Trust: {trust_str}")

        # DB fields
        print(f"\n   [DATABASE FIELDS]")
        print(f"   display_mode: {db_narrative.get('display_mode')}")
        print(f"   display_title: {db_narrative.get('display_title', 'N/A')[:100] if db_narrative.get('display_title') else 'None'}...")
        display_summary = db_narrative.get("display_summary")
        if display_summary:
            print(f"   display_summary: {str(display_summary)[:100]}...")
        else:
            print(f"   display_summary: None")
        print(f"   last_summary_generated_at: {db_narrative.get('last_summary_generated_at')}")

        # API fields (if available)
        api_narrative = None
        if api_narratives:
            for api_n in api_narratives:
                if isinstance(api_n, dict):
                    if str(api_n.get("_id")) == narrative_id or api_n.get("id") == narrative_id:
                        api_narrative = api_n
                        break

        if api_narrative:
            print(f"\n   [API RESPONSE FIELDS]")
            print(f"   display_mode: {api_narrative.get('display_mode')}")
            print(f"   display_title: {api_narrative.get('display_title', 'N/A')[:100] if api_narrative.get('display_title') else 'None'}...")
            api_summary = api_narrative.get("display_summary")
            if api_summary:
                print(f"   display_summary: {str(api_summary)[:100]}...")
            else:
                print(f"   display_summary: None")
            print(f"   recent_article_count: {api_narrative.get('recent_article_count')}")
        else:
            print(f"\n   [API RESPONSE] Not found in API results (check if filtering/pagination excluded it)")

        # Analysis
        print(f"\n   [ANALYSIS]")
        if not trust:
            print(f"   ✓ Narrative is UNTRUSTED (no fresh summary)")
            if api_narrative and api_narrative.get("display_mode") == "article_cluster":
                print(f"   ✓ API correctly returns display_mode='article_cluster'")
                print(f"   ? QUESTION: Is frontend rendering display_title/display_summary from this?")
            elif api_narrative:
                print(f"   ⚠️  API returns display_mode='{api_narrative.get('display_mode')}' (expected 'article_cluster' for untrusted)")
            else:
                print(f"   ⚠️  Cannot verify API display_mode (API call failed)")
        else:
            print(f"   ✓ Narrative is TRUSTED (has fresh summary)")
            if api_narrative and api_narrative.get("display_mode") == "summary":
                print(f"   ✓ API correctly returns display_mode='summary'")
            elif api_narrative:
                print(f"   ⚠️  API returns display_mode='{api_narrative.get('display_mode')}' (expected 'summary' for trusted)")

    # Phase 0.4: Summary and questions
    print("\n" + "=" * 120)
    print("PHASE 0 SUMMARY")
    print("=" * 120)

    untrusted_count = sum(1 for n in db_narratives[:10] if not is_trusted(n))
    trusted_count = 10 - untrusted_count

    print(f"""
CURRENT STATE:
  - Trusted narratives: {trusted_count}
  - Untrusted narratives: {untrusted_count}

KEY QUESTIONS TO ANSWER:
  1. API display_mode fields: Are they being computed and returned for untrusted narratives?
  2. Frontend consumption: Is the frontend actually using display_title/display_summary from the API?
  3. If API shows display_mode='article_cluster' but UI shows generated summary:
     → Does UI have old cached bundle deployed?
     → Or is API not computing display fields correctly?

NEXT STEP (Phase 1):
  Once we understand display-mode behavior, proceed to Phase 1 (Select top 5).
""")

    print("=" * 120)

if __name__ == "__main__":
    asyncio.run(main())
