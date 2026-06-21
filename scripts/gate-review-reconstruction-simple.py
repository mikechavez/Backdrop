#!/usr/bin/env python
"""
Historical incident reconstruction harness for TASK-114C Phase A Exit Gate.

Simplest approach: use sync Mongo for case setup, then manually call
collector components to validate Evidence Pack generation.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from bson import ObjectId

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from pymongo import MongoClient

from crypto_news_aggregator.bugops.models import (
    BugCaseCreate,
    BugCase,
    AlertSeverity,
    CaseStatus,
)


class HistoricalReconstructor:
    """Reconstructs documented historical incidents as synthetic BugCases."""

    def __init__(self):
        # Gate review database (local, isolated from production)
        self.client = MongoClient('mongodb://localhost:27017/')
        self.db = self.client['bugops_gate_review']
        self.reconstruction_log = []

    def log_fact(self, category: str, key: str, value: str):
        """Record a documented historical fact."""
        self.reconstruction_log.append({
            'type': 'DOCUMENTED_FACT',
            'category': category,
            'key': key,
            'value': value,
        })

    def log_synthetic(self, category: str, key: str, value: str, rationale: str):
        """Record a synthetic support value with rationale."""
        self.reconstruction_log.append({
            'type': 'SYNTHETIC_SUPPORT',
            'category': category,
            'key': key,
            'value': value,
            'rationale': rationale,
        })

    def print_reconstruction_summary(self, case_id: str):
        """Print summary of facts vs synthetic for this case."""
        print(f"\n{'='*70}")
        print(f"RECONSTRUCTION SUMMARY: {case_id}")
        print(f"{'='*70}")

        facts = [r for r in self.reconstruction_log if r['type'] == 'DOCUMENTED_FACT']
        synthetics = [r for r in self.reconstruction_log if r['type'] == 'SYNTHETIC_SUPPORT']

        if facts:
            print(f"\n📋 DOCUMENTED HISTORICAL FACTS ({len(facts)}):")
            for f in facts:
                print(f"   [{f['category']}] {f['key']}: {f['value']}")

        if synthetics:
            print(f"\n🔧 SYNTHETIC SUPPORT DATA ({len(synthetics)}):")
            for s in synthetics:
                print(f"   [{s['category']}] {s['key']}: {s['value']}")
                print(f"      └─ Rationale: {s['rationale']}")

        self.reconstruction_log.clear()

    def reconstruct_bug_064(self):
        """BUG-064: Cost Control Failure / Briefing Generation Halt."""

        case_id = 'BUG-064-RECONSTRUCTION'
        print(f"\n🔄 Reconstructing {case_id}...")

        # DOCUMENTED FACTS
        incident_start = datetime(2026, 4, 13, 0, 0, 10)
        incident_end = datetime(2026, 4, 13, 1, 10, 0)
        self.log_fact('Timeline', 'Failure start', str(incident_start) + 'Z')
        self.log_fact('Timeline', 'Failure end (observed)', str(incident_end) + 'Z')
        self.log_fact('Cost Control', 'Soft limit', '$0.25')
        self.log_fact('Cost Control', 'Actual spend at failure', '$0.2954')
        self.log_fact('Operation', 'Blocked operation', 'briefing_generate')
        self.log_fact('Subsystem', 'Root subsystem', 'briefings')
        self.log_fact('Retry pattern', 'Cycles observed', '4 within 70-minute window')

        # Create BugCase
        case_create = BugCaseCreate(
            case_id=case_id,
            root_subsystem='briefings',
            severity=AlertSeverity.HIGH,
            status=CaseStatus.OPEN,
            alert_type='cost_control_soft_limit',
            title='Briefing generation halted — soft limit exceeded',
            summary='Historical reconstruction: BUG-064 cost control failure',
            source_types=['evidence_reconstruction'],
            alert_ids=[],
            first_seen_at=incident_start,
            last_seen_at=incident_end,
            affected_subsystems=['briefings'],
            blast_radius=['briefings'],
            dedupe_key=f'reconstruction-{case_id}-{int(incident_start.timestamp())}',
        )

        case_doc = case_create.model_dump(by_alias=True)
        case_doc['_id'] = ObjectId()
        self.db['bug_cases'].insert_one(case_doc)
        print(f"   ✅ Inserted BugCase: {case_id}")

        # SYNTHETIC SUPPORT: LLM traces
        llm_traces = []
        for i in range(4):
            retry_time = incident_start + timedelta(minutes=i*5)
            cost = 0.0625 + (i * 0.0538)
            llm_traces.append({
                '_id': ObjectId(),
                'operation': 'briefing_generate',
                'timestamp': retry_time,
                'cost': cost,
                'input_tokens': 1200 + (i * 50),
                'output_tokens': 400 + (i * 25),
                'model': 'claude-haiku-4-5-20251001',
                'status': 'failed_soft_limit',
            })
            self.log_synthetic(
                'LLM Traces',
                f'Retry {i+1} cost',
                f'${cost:.4f}',
                f'Realistic cost progression leading to $0.2954 total'
            )

        self.db['llm_traces'].insert_many(llm_traces)

        # SYNTHETIC SUPPORT: Related case
        related_cases = [{
            '_id': ObjectId(),
            'case_id': 'BUG-057-SYNTHETIC',
            'root_subsystem': 'briefings',
            'severity': AlertSeverity.WARNING,
            'status': CaseStatus.CLOSED,
            'alert_type': 'briefing_timeout',
            'title': '[Prior] Briefing generation timeout',
            'summary': 'Related to BUG-064',
            'source_types': ['synthetic'],
            'alert_ids': [],
            'first_seen_at': datetime(2026, 4, 10, 15, 30, 0),
            'last_seen_at': datetime(2026, 4, 10, 16, 45, 0),
            'affected_subsystems': ['briefings'],
            'blast_radius': ['briefings'],
            'dedupe_key': 'bug-057-synthetic',
        }]
        self.db['bug_cases'].insert_many(related_cases)
        self.log_synthetic(
            'Related Cases',
            'BUG-057 (prior briefing issue)',
            'Inserted',
            'Validates related-case collector detects subsystem correlation'
        )

        self.print_reconstruction_summary(case_id)
        return case_id

    def reconstruct_bug_073(self):
        """BUG-073: Articles Missing Fingerprints / Deduplication Broken."""

        case_id = 'BUG-073-RECONSTRUCTION'
        print(f"\n🔄 Reconstructing {case_id}...")

        # DOCUMENTED FACTS
        incident_start = datetime(2026, 4, 14, 2, 0, 0)
        incident_end = datetime(2026, 4, 14, 3, 30, 0)
        self.log_fact('Timeline', 'First observed', str(incident_start) + 'Z')
        self.log_fact('Timeline', 'Detection window end', str(incident_end) + 'Z')
        self.log_fact('Root cause', 'Code path', 'Direct insert_one() bypassed ArticleService')
        self.log_fact('Impact', 'Affected records', '100% of April 14 inserts (fingerprint: null)')
        self.log_fact('Subsystem', 'Root subsystem', 'articles')
        self.log_fact('Related incidents', 'Explicit dependencies', 'BUG-070, BUG-071, BUG-072')

        # Create BugCase
        case_create = BugCaseCreate(
            case_id=case_id,
            root_subsystem='articles',
            severity=AlertSeverity.HIGH,
            status=CaseStatus.OPEN,
            alert_type='code_path_regression',
            title='Articles missing fingerprints — deduplication broken',
            summary='Historical reconstruction: BUG-073 RSS ingestion code path regression',
            source_types=['evidence_reconstruction'],
            alert_ids=[],
            first_seen_at=incident_start,
            last_seen_at=incident_end,
            affected_subsystems=['articles'],
            blast_radius=['articles'],
            dedupe_key=f'reconstruction-{case_id}-{int(incident_start.timestamp())}',
        )

        case_doc = case_create.model_dump(by_alias=True)
        case_doc['_id'] = ObjectId()
        self.db['bug_cases'].insert_one(case_doc)
        print(f"   ✅ Inserted BugCase: {case_id}")

        # SYNTHETIC SUPPORT: Related cases
        related_cases = [
            {
                '_id': ObjectId(),
                'case_id': 'BUG-070-SYNTHETIC',
                'root_subsystem': 'articles',
                'severity': AlertSeverity.WARNING,
                'status': CaseStatus.CLOSED,
                'alert_type': 'filtering_issue',
                'title': '[Prior] Tier-1 filtering regression',
                'summary': 'Related to BUG-073',
                'source_types': ['synthetic'],
                'alert_ids': [],
                'first_seen_at': datetime(2026, 4, 8, 10, 0, 0),
                'last_seen_at': datetime(2026, 4, 8, 11, 15, 0),
                'affected_subsystems': ['articles'],
                'blast_radius': ['articles'],
                'dedupe_key': 'bug-070-synthetic',
            },
            {
                '_id': ObjectId(),
                'case_id': 'BUG-071-SYNTHETIC',
                'root_subsystem': 'narratives',
                'severity': AlertSeverity.WARNING,
                'status': CaseStatus.CLOSED,
                'alert_type': 'narrative_issue',
                'title': '[Prior] Compressed system prompt issue',
                'summary': 'Related to BUG-073',
                'source_types': ['synthetic'],
                'alert_ids': [],
                'first_seen_at': datetime(2026, 4, 9, 14, 0, 0),
                'last_seen_at': datetime(2026, 4, 9, 15, 30, 0),
                'affected_subsystems': ['narratives'],
                'blast_radius': ['narratives'],
                'dedupe_key': 'bug-071-synthetic',
            },
            {
                '_id': ObjectId(),
                'case_id': 'BUG-072-SYNTHETIC',
                'root_subsystem': 'worker',
                'severity': AlertSeverity.WARNING,
                'status': CaseStatus.CLOSED,
                'alert_type': 'cache_issue',
                'title': '[Prior] LLM cache wiring broken',
                'summary': 'Related to BUG-073',
                'source_types': ['synthetic'],
                'alert_ids': [],
                'first_seen_at': datetime(2026, 4, 9, 8, 0, 0),
                'last_seen_at': datetime(2026, 4, 9, 9, 45, 0),
                'affected_subsystems': ['worker'],
                'blast_radius': ['worker'],
                'dedupe_key': 'bug-072-synthetic',
            },
        ]
        self.db['bug_cases'].insert_many(related_cases)
        self.log_synthetic(
            'Related Cases',
            'BUG-070, BUG-071, BUG-072',
            'Inserted',
            'Validates related-case collector detects multi-incident pattern'
        )

        self.print_reconstruction_summary(case_id)
        return case_id

    def reconstruct_bug_084(self):
        """BUG-084: Narrative Summary Fabrication."""

        case_id = 'BUG-084-RECONSTRUCTION'
        print(f"\n🔄 Reconstructing {case_id}...")

        # DOCUMENTED FACTS
        incident_start = datetime(2026, 4, 15, 4, 0, 0)
        incident_end = datetime(2026, 4, 15, 4, 15, 0)
        self.log_fact('Timeline', 'Incident timestamp (approx)', str(incident_start) + 'Z')
        self.log_fact('Subsystem', 'Root subsystem', 'narratives')
        self.log_fact('Root cause 1', 'Prompt instruction', 'Encouraged synthesis → fabrication')
        self.log_fact('Root cause 2', 'Article truncation', '300 characters (insufficient grounding)')
        self.log_fact('Root cause 3', 'Model choice', 'Sonnet instead of standardized Haiku')
        self.log_fact('Manifestation', 'Narrative title', 'Kraken Faces Extortion Over Stolen Internal Data')
        self.log_fact('Source reality', 'Source articles topic', 'Kraken IPO filing (3 articles)')
        self.log_fact('Classification', 'Error type', 'Content fabrication (not infrastructure)')

        # Create BugCase
        case_create = BugCaseCreate(
            case_id=case_id,
            root_subsystem='narratives',
            severity=AlertSeverity.CRITICAL,
            status=CaseStatus.OPEN,
            alert_type='content_fabrication',
            title='Narrative generator fabricates non-existent events',
            summary='Historical reconstruction: BUG-084 LLM prompt/model/grounding issue',
            source_types=['evidence_reconstruction'],
            alert_ids=[],
            first_seen_at=incident_start,
            last_seen_at=incident_end,
            affected_subsystems=['narratives', 'briefings'],
            blast_radius=['narratives', 'briefings'],
            dedupe_key=f'reconstruction-{case_id}-{int(incident_start.timestamp())}',
        )

        case_doc = case_create.model_dump(by_alias=True)
        case_doc['_id'] = ObjectId()
        self.db['bug_cases'].insert_one(case_doc)
        print(f"   ✅ Inserted BugCase: {case_id}")

        # SYNTHETIC SUPPORT: LLM trace
        llm_traces = [{
            '_id': ObjectId(),
            'operation': 'narrative_generate',
            'timestamp': incident_start,
            'cost': 0.0156,
            'input_tokens': 2400,
            'output_tokens': 300,
            'model': 'claude-sonnet-4-5-20250929',
            'status': 'completed_with_fabrication',
        }]
        self.db['llm_traces'].insert_many(llm_traces)
        self.log_synthetic(
            'LLM Trace',
            'Operation cost',
            '$0.0156 (Sonnet)',
            'Realistic cost for narrative operation with Sonnet model'
        )

        self.log_synthetic(
            'Config Evidence',
            'ARTICLE_SUMMARY_TRUNCATE_CHARS',
            '300',
            'Root cause 2: Insufficient grounding context'
        )
        self.log_synthetic(
            'Config Evidence',
            'NARRATIVE_GENERATION_MODEL',
            'claude-sonnet-4-5-20250929',
            'Root cause 3: Wrong model contradicts standardization'
        )

        # CRITICAL: Document the limitation
        print(f"\n⚠️  BUG-084 KNOWN LIMITATION:")
        print(f"   Evidence Pack CANNOT capture: 'LLM output contradicts input'")
        print(f"   No Evidence Pack section compares narrative summary to source articles")
        print(f"   Therefore: Blind diagnosis will likely be PARTIAL or MISS")
        print(f"   This is VALID and USEFUL — it identifies an Evidence Pack coverage gap")

        self.print_reconstruction_summary(case_id)
        return case_id

    def print_database_summary(self):
        """Print what's now in the gate review database."""
        print(f"\n{'='*70}")
        print("DATABASE SUMMARY")
        print(f"{'='*70}")

        cases_count = self.db['bug_cases'].count_documents({})
        traces_count = self.db['llm_traces'].count_documents({})

        print(f"\n✅ Database: bugops_gate_review")
        print(f"   bug_cases: {cases_count}")
        print(f"   llm_traces: {traces_count}")
        print(f"\n📋 Reconstructed cases ready for Evidence Collection:")
        for case_id in ['BUG-064-RECONSTRUCTION', 'BUG-073-RECONSTRUCTION', 'BUG-084-RECONSTRUCTION']:
            case = self.db['bug_cases'].find_one({'case_id': case_id})
            if case:
                print(f"   ✅ {case_id}")
            else:
                print(f"   ❌ {case_id} (not found)")


def main():
    """Run all three reconstructions."""

    print("="*70)
    print("TASK-114C: DOCUMENTED HISTORICAL RECONSTRUCTION")
    print("="*70)
    print("\nPhase 1: Historical Case Reconstruction")
    print("  - Documented facts: timestamps, subsystems, documented root causes")
    print("  - Synthetic support: LLM traces, related cases (realistic but synthetic)")
    print()

    reconstructor = HistoricalReconstructor()

    # Reconstruct all three incidents
    case_ids = [
        reconstructor.reconstruct_bug_064(),
        reconstructor.reconstruct_bug_073(),
        reconstructor.reconstruct_bug_084(),
    ]

    reconstructor.print_database_summary()

    print("\n" + "="*70)
    print("NEXT STEP: Evidence Collection")
    print("="*70)
    print("""
To collect evidence from these reconstructed cases, run this from the main event loop:

    from crypto_news_aggregator.bugops.evidence.collector import EvidenceCollector
    from crypto_news_aggregator.bugops.store import BugOpsStore
    from crypto_news_aggregator.core.config import get_settings

    # In an async function:
    store = BugOpsStore(db=db)
    settings = get_settings()
    collector = EvidenceCollector(store=store, settings=settings, db=db)

    for case_id in case_ids:
        bugcase = await store.get_bugcase(case_id)
        pack = await collector.collect(bugcase)
        print(f"Evidence collected: {pack.pack_id}")

The reconstructed cases are persisted to: mongodb://localhost:27017/bugops_gate_review
""")

    return case_ids


if __name__ == '__main__':
    main()
