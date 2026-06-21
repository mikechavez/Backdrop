#!/usr/bin/env python
"""
Blind Diagnosis Phase for TASK-114C.

Reads generated Evidence Packs and writes diagnoses BEFORE ground truth comparison.
Then produces final TASK-114C-REPLAY-RESULTS.md report.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient


BLIND_DIAGNOSIS_TIMESTAMP = datetime.utcnow()


async def fetch_evidence_pack(db, bugcase_id: str) -> dict:
    """Fetch Evidence Pack for a case."""
    pack = await db['evidence_packs'].find_one({'bugcase_id': bugcase_id})
    if pack:
        if '_id' in pack:
            pack['_id'] = str(pack['_id'])
    return pack


async def main():
    """Main: fetch packs and prepare blind diagnosis phase."""

    client = AsyncIOMotorClient('mongodb://localhost:27017/')
    db = client['bugops_gate_review']

    case_ids = [
        'BUG-064-RECONSTRUCTION',
        'BUG-073-RECONSTRUCTION',
        'BUG-084-RECONSTRUCTION',
    ]

    print("="*70)
    print("TASK-114C: BLIND DIAGNOSIS PHASE")
    print("="*70)
    print(f"\nPhase timestamp: {BLIND_DIAGNOSIS_TIMESTAMP.isoformat()}Z")
    print("Source: Evidence Packs only (no ground truth reference)")
    print()

    results_data = {
        'phase': 'blind_diagnosis',
        'timestamp': BLIND_DIAGNOSIS_TIMESTAMP.isoformat() + 'Z',
        'cases': []
    }

    # Fetch all Evidence Packs
    for case_id in case_ids:
        pack = await fetch_evidence_pack(db, case_id)

        if not pack:
            print(f"❌ Evidence Pack not found for {case_id}")
            continue

        print(f"✅ Loaded Evidence Pack for {case_id}")
        print(f"   pack_id: {pack['pack_id']}")
        print(f"   status: {pack['collection_status']}")
        print(f"   collectors succeeded: {len(pack.get('sections_collected', []))}")
        print(f"   sections missing: {len(pack.get('sections_missing', []))}")
        print()

        results_data['cases'].append({
            'case_id': case_id,
            'pack_id': pack['pack_id'],
            'collection_status': pack['collection_status'],
            'pack': pack,
        })

    client.close()

    print("="*70)
    print(f"Ready for blind diagnosis ({len(results_data['cases'])} packs loaded)")
    print("="*70)

    return results_data


if __name__ == '__main__':
    results = asyncio.run(main())

    # Save for next phase
    with open('/tmp/evidence_packs_raw.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n✅ Evidence Packs data saved to /tmp/evidence_packs_raw.json")
    print(f"✅ Ready to generate blind diagnoses")
