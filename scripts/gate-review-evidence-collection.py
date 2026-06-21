#!/usr/bin/env python
"""
Evidence Collection Phase for TASK-114C.

Runs real EvidenceCollector against reconstructed BugCases.
Generates Evidence Packs and writes blind diagnoses BEFORE ground truth comparison.
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

# Override MONGODB_URI for gate review
import os
os.environ['MONGODB_URI'] = 'mongodb://localhost:27017/bugops_gate_review'

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from crypto_news_aggregator.bugops.models import BugCase, AlertSeverity, CaseStatus
from crypto_news_aggregator.bugops.evidence.collector import EvidenceCollector
from crypto_news_aggregator.bugops.store import BugOpsStore
from crypto_news_aggregator.core.config import get_settings


class EvidenceCollectionPhase:
    """Runs real EvidenceCollector on reconstructed cases."""

    def __init__(self):
        self.async_client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.store: Optional[BugOpsStore] = None
        self.collector: Optional[EvidenceCollector] = None
        self.settings = None
        self.results = []
        self.diagnoses = []

    async def initialize(self):
        """Initialize async MongoDB connection and collectors."""
        self.async_client = AsyncIOMotorClient('mongodb://localhost:27017/')
        self.db = self.async_client['bugops_gate_review']
        self.settings = get_settings()
        self.store = BugOpsStore(db=self.db)
        self.collector = EvidenceCollector(
            store=self.store,
            settings=self.settings,
            db=self.db
        )
        print("✅ Async MongoDB connection established")
        print(f"✅ EvidenceCollector initialized with {len(self.collector.collectors)} collectors")

    async def collect_for_case(self, case_id: str) -> dict:
        """Collect evidence for a single reconstructed case."""

        print(f"\n{'='*70}")
        print(f"COLLECTING EVIDENCE: {case_id}")
        print(f"{'='*70}")

        # Fetch case from database
        case_doc = await self.db['bug_cases'].find_one({'case_id': case_id})
        if not case_doc:
            print(f"❌ Case {case_id} not found in database")
            return None

        # Convert ObjectId to string for Pydantic
        if '_id' in case_doc:
            case_doc['_id'] = str(case_doc['_id'])

        # Reconstruct BugCase
        bugcase = BugCase(**case_doc)
        print(f"\n📋 BugCase loaded:")
        print(f"   case_id: {bugcase.case_id}")
        print(f"   root_subsystem: {bugcase.root_subsystem}")
        print(f"   severity: {bugcase.severity}")
        print(f"   status: {bugcase.status}")
        print(f"   first_seen_at: {bugcase.first_seen_at}")
        print(f"   last_seen_at: {bugcase.last_seen_at}")

        # Check eligibility
        print(f"\n🔍 Checking eligibility...")
        is_eligible = await self.collector.is_eligible(bugcase)
        if not is_eligible:
            print(f"❌ Case not eligible for collection")
            print(f"   (Likely reasons: manually_closed, existing pack, settling window not elapsed)")
            return None

        print(f"✅ Case eligible for collection")

        # Collect evidence
        print(f"\n📊 Running EvidenceCollector.collect()...")
        try:
            pack = await self.collector.collect(bugcase)

            print(f"\n✅ Evidence Pack generated successfully")
            print(f"   pack_id: {pack.pack_id}")
            print(f"   collection_status: {pack.collection_status}")
            print(f"   created_at: {pack.created_at}")

            print(f"\n📋 Collectors executed:")
            for section_name in pack.sections_collected:
                print(f"   ✅ {section_name}")

            if pack.sections_missing:
                print(f"\n⚠️  Sections missing:")
                for section_name, reason in pack.sections_missing.items():
                    print(f"   {section_name}: {reason}")

            if pack.collection_errors:
                print(f"\n⚠️  Collection errors ({len(pack.collection_errors)}):")
                for error in pack.collection_errors:
                    print(f"   [{error.collector_name}] {error.error_message}")

            # Evidence references
            if pack.evidence_references:
                print(f"\n🔗 Evidence references ({len(pack.evidence_references)}):")
                for ref_id, ref in list(pack.evidence_references.items())[:5]:
                    desc = ref.get('description', 'N/A')[:70]
                    print(f"   {ref_id}: {desc}...")

            return pack.model_dump()

        except Exception as e:
            print(f"❌ Collection failed with exception: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def write_blind_diagnosis(self, case_id: str, pack_data: dict) -> str:
        """
        Write a blind diagnosis based ONLY on the Evidence Pack.
        DO NOT refer to ground truth yet.
        """

        print(f"\n{'='*70}")
        print(f"BLIND DIAGNOSIS (Written before ground truth comparison)")
        print(f"Case: {case_id}")
        print(f"Timestamp: {datetime.utcnow().isoformat()}Z")
        print(f"{'='*70}")

        # Extract only what's in the Evidence Pack
        pack = pack_data

        diagnosis = f"""## BLIND DIAGNOSIS — {case_id}

**Timestamp:** {datetime.utcnow().isoformat()}Z
**Source:** Evidence Pack only (no ground truth reference)

### Available Evidence

**Sections Collected:**
{json.dumps(pack.get('sections_collected', []), indent=2)}

**Sections Missing:**
{json.dumps(pack.get('sections_missing', {}), indent=2)}

**Collection Errors:**
{f"- {len(pack.get('collection_errors', []))} error(s) recorded" if pack.get('collection_errors') else "- None"}

**Evidence References:** {len(pack.get('evidence_references', {}))} items

### Diagnosis Based on Available Evidence

"""

        # Build diagnosis from Evidence Pack contents
        if 'metrics_evidence' in pack and pack['metrics_evidence']:
            diagnosis += f"\n**Metrics Signal:**\n"
            metrics = pack['metrics_evidence']
            if 'subsystem_health' in metrics:
                diagnosis += f"- Subsystem health: {metrics['subsystem_health']}\n"

        if 'system_state_evidence' in pack and pack['system_state_evidence']:
            diagnosis += f"\n**System State:**\n"
            state = pack['system_state_evidence']
            if 'healthy_signals' in state and state['healthy_signals']:
                diagnosis += f"- Healthy signals: {', '.join(state['healthy_signals'][:5])}\n"

        if 'llm_trace_summary' in pack and pack['llm_trace_summary']:
            diagnosis += f"\n**LLM Trace Summary:**\n"
            traces = pack['llm_trace_summary']
            if 'total_cost' in traces:
                diagnosis += f"- Total cost: ${traces['total_cost']:.4f}\n"
            if 'total_calls' in traces:
                diagnosis += f"- Total calls: {traces['total_calls']}\n"
            if 'operation_breakdown' in traces:
                diagnosis += f"- Operations: {list(traces['operation_breakdown'].keys())}\n"

        if 'config_evidence' in pack and pack['config_evidence']:
            diagnosis += f"\n**Configuration Evidence:**\n"
            config = pack['config_evidence']
            for key, value in config.items():
                if key != 'collected_at':
                    diagnosis += f"- {key}: {value}\n"

        if 'related_cases' in pack and pack['related_cases'].get('cases'):
            diagnosis += f"\n**Related Cases Found:**\n"
            for related in pack['related_cases']['cases'][:3]:
                diagnosis += f"- {related.get('case_id', 'unknown')}: {related.get('title', 'N/A')}\n"

        if 'deploy_context' in pack and pack['deploy_context'].get('deployments'):
            diagnosis += f"\n**Recent Deployments:**\n"
            for dep in pack['deploy_context']['deployments'][:3]:
                diagnosis += f"- {dep.get('service_name', 'unknown')}: {dep.get('status', 'unknown')}\n"

        diagnosis += f"""

### Root Cause Hypothesis

Based ONLY on what's in this Evidence Pack, the likely root cause is:

[DIAGNOSIS TO BE FILLED IN BY BLIND ANALYSIS]

### Confidence Level

[HIGH / MEDIUM / LOW]

### Evidence Supporting This Hypothesis

[List specific evidence items that led to this diagnosis]

---
"""

        # Store for later
        self.diagnoses.append({
            'case_id': case_id,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'diagnosis': diagnosis,
            'pack_data': pack_data,
        })

        return diagnosis

    async def run_all_collections(self):
        """Run evidence collection for all three reconstructed cases."""

        case_ids = [
            'BUG-064-RECONSTRUCTION',
            'BUG-073-RECONSTRUCTION',
            'BUG-084-RECONSTRUCTION',
        ]

        print("="*70)
        print("TASK-114C: EVIDENCE COLLECTION PHASE")
        print("="*70)
        print(f"\nCollecting evidence from {len(case_ids)} reconstructed cases")
        print(f"Database: bugops_gate_review")
        print()

        for case_id in case_ids:
            # Collect evidence
            pack = await self.collect_for_case(case_id)

            if pack:
                self.results.append({
                    'case_id': case_id,
                    'pack_id': pack.get('pack_id'),
                    'status': pack.get('collection_status'),
                    'pack': pack,
                })

                # Write blind diagnosis
                diagnosis_text = await self.write_blind_diagnosis(case_id, pack)
                print(diagnosis_text[:500] + "...\n")
            else:
                print(f"\n⚠️  Skipped {case_id} (collection failed or not eligible)")

        # Summary
        print("\n" + "="*70)
        print("COLLECTION SUMMARY")
        print("="*70)
        print(f"\n✅ Successfully collected: {len(self.results)} Evidence Packs")

        for result in self.results:
            print(f"\n   {result['case_id']}:")
            print(f"      pack_id: {result['pack_id']}")
            print(f"      status: {result['status']}")

        return self.results


async def main():
    """Main entry point."""

    collector_phase = EvidenceCollectionPhase()
    await collector_phase.initialize()

    results = await collector_phase.run_all_collections()

    # Save results for next phase
    print("\n" + "="*70)
    print("RESULTS SAVED")
    print("="*70)
    print(f"\n✅ {len(results)} Evidence Packs collected")
    print(f"✅ {len(collector_phase.diagnoses)} Blind diagnoses generated (timestamps recorded)")
    print("\n📝 Next step: Manually fill in each blind diagnosis, then compare to ground truth")

    return results, collector_phase.diagnoses


if __name__ == '__main__':
    results, diagnoses = asyncio.run(main())
