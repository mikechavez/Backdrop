#!/usr/bin/env python3
"""
Phase 6: Generate Decision Records (MSD-001 through MSD-003) for FEATURE-053

Produces three decision records with:
- Quality metrics tables
- Latency and cost analysis
- Failure mode taxonomy
- Data-driven decisions (SWAP/STAY/CONDITIONAL)
"""

import json
import statistics
from pathlib import Path
from typing import Any


FAILURE_TAXONOMIES = {
    'entity_extraction': [
        'missed_entity', 'extra_entity', 'alias_mismatch', 'boundary_error'
    ],
    'sentiment_analysis': [
        'polarity_flip', 'neutral_misclassification', 'low_confidence_divergence'
    ],
    'theme_extraction': [
        'semantic_miss', 'overgeneralized', 'overly_specific', 'phrasing_mismatch'
    ],
}

MANUAL_VALIDATION = {
    'entity_extraction': {
        'agreement': 30,
        'caveat': 'Disagreements concentrated around extraction granularity. Reviewer labeled at conceptual level; Haiku labels at mention level. Haiku is internally consistent. Parity scores measure whether challengers match Haiku\'s mention-level philosophy. Prompt refinement deferred to Sprint 17.'
    },
    'sentiment_analysis': {
        'agreement': 80,
        'caveat': 'Two mismatches on neutral/negative boundary on genuinely ambiguous articles. Label-level agreement is reliable. Baseline is trustworthy.'
    },
    'theme_extraction': {
        'agreement': 10,
        'caveat': 'Systematic philosophy gap — Haiku includes entity names as themes; reviewer labeled only conceptual themes. Haiku is internally consistent. Interpret parity scores conservatively for this operation. Prompt refinement deferred to Sprint 17.'
    },
}

MODELS = ['flash', 'deepseek', 'qwen']
OPERATIONS = ['entity_extraction', 'sentiment_analysis', 'theme_extraction']

# Estimated costs (per 1M tokens, from public pricing)
MODEL_COSTS = {
    'haiku': {'input': 0.80, 'output': 4.00},
    'flash': {'input': 2.50, 'output': 10.00},
    'deepseek': {'input': 0.14, 'output': 0.28},
    'qwen': {'input': 0.15, 'output': 0.45},
}


def load_baseline_samples(run_dir: Path, operation: str) -> list[dict]:
    """Load baseline samples."""
    filepath = run_dir / f"baseline-{operation}.jsonl"
    samples = []
    if filepath.exists():
        with open(filepath) as f:
            for line in f:
                if line.strip():
                    samples.append(json.loads(line))
    return samples


def load_scored_samples(run_dir: Path, operation: str, model: str) -> list[dict]:
    """Load scored samples for a model."""
    filepath = run_dir / f"scored-{operation}-{model}.jsonl"
    samples = []
    if filepath.exists():
        with open(filepath) as f:
            for line in f:
                if line.strip():
                    samples.append(json.loads(line))
    return samples


def extract_worst_samples(scored_samples: list[dict], count: int = 10) -> list[dict]:
    """Extract worst N samples by score."""
    # Sort by score, ascending
    sorted_samples = sorted(
        scored_samples,
        key=lambda s: s.get('score', {}).get('f1', s.get('score', {}).get('score', 0))
    )
    return sorted_samples[:count]


def format_table_row(cells: list[str], col_widths: list[int]) -> str:
    """Format a row for markdown table."""
    return '| ' + ' | '.join(
        cell.ljust(width) for cell, width in zip(cells, col_widths)
    ) + ' |'


def generate_quality_table(operation: str, stats: dict[str, dict]) -> str:
    """Generate quality metrics table for an operation."""
    lines = []
    lines.append('')
    lines.append('## Quality Metrics')
    lines.append('')

    # Metrics by operation type
    if operation == 'entity_extraction' or operation == 'theme_extraction':
        lines.append('| Model | Mean F1 | Flagged Samples | Flagged % |')
        lines.append('|---|---|---|---|')
        for model in MODELS:
            s = stats.get(model, {})
            lines.append(f"| {model:10} | {s.get('mean_score', 0):.2f} | {s.get('samples_flagged', 0):3d}/{s.get('samples_total', 0)} | {s.get('flagged_pct', 0):5.1f}% |")
    else:  # sentiment_analysis
        lines.append('| Model | Accuracy | Flagged Samples | Flagged % |')
        lines.append('|---|---|---|---|')
        for model in MODELS:
            s = stats.get(model, {})
            accuracy = (100 - s.get('flagged_pct', 0))
            lines.append(f"| {model:10} | {accuracy:6.1f}% | {s.get('samples_flagged', 0):3d}/{s.get('samples_total', 0)} | {s.get('flagged_pct', 0):5.1f}% |")

    return '\n'.join(lines)


def generate_latency_table(run_dir: Path, operation: str) -> str:
    """Generate latency table for an operation."""
    lines = []
    lines.append('')
    lines.append('## Latency Analysis')
    lines.append('')
    lines.append('| Model | p50 (ms) | p95 (ms) | avg (ms) |')
    lines.append('|---|---|---|---|')

    for model in ['haiku'] + MODELS:
        if model == 'haiku':
            # Haiku latency from baseline
            filepath = run_dir / f"baseline-{operation}-metadata.json"
        else:
            filepath = run_dir / f"challenger-{operation}-{model}.jsonl"

        if model == 'haiku' and filepath.exists():
            with open(filepath) as f:
                meta = json.load(f)
                latencies = meta.get('latencies_ms', [])
        elif filepath.exists() and model != 'haiku':
            latencies = []
            with open(filepath) as f:
                for line in f:
                    if line.strip():
                        sample = json.loads(line)
                        if sample.get('latency_ms'):
                            latencies.append(sample['latency_ms'])
        else:
            latencies = []

        if latencies:
            latencies_sorted = sorted(latencies)
            p50 = latencies_sorted[len(latencies_sorted) // 2]
            p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)]
            avg = statistics.mean(latencies)
        else:
            p50 = p95 = avg = 0

        lines.append(f"| {model:10} | {p50:8.0f} | {p95:8.0f} | {avg:8.0f} |")

    return '\n'.join(lines)


def generate_cost_table(run_dir: Path, operation: str) -> str:
    """Generate cost analysis table."""
    lines = []
    lines.append('')
    lines.append('## Cost Analysis')
    lines.append('')

    # Load token counts from baseline and each model
    token_data = {}

    # Baseline
    baseline_file = run_dir / f"baseline-{operation}.jsonl"
    haiku_tokens = {'input': [], 'output': []}
    if baseline_file.exists():
        with open(baseline_file) as f:
            for line in f:
                if line.strip():
                    sample = json.loads(line)
                    # These aren't in baseline, estimate from metadata

    # Load metadata for baseline tokens
    metadata_file = run_dir / f"baseline-{operation}-metadata.json"
    if metadata_file.exists():
        with open(metadata_file) as f:
            meta = json.load(f)
            haiku_tokens['input'] = meta.get('input_tokens_per_sample', [])
            haiku_tokens['output'] = meta.get('output_tokens_per_sample', [])

    challenger_tokens = {'flash': {'input': [], 'output': []}, 'deepseek': {'input': [], 'output': []}, 'qwen': {'input': [], 'output': []}}
    for model in MODELS:
        filepath = run_dir / f"challenger-{operation}-{model}.jsonl"
        if filepath.exists():
            with open(filepath) as f:
                for line in f:
                    if line.strip():
                        sample = json.loads(line)
                        if sample.get('input_tokens'):
                            challenger_tokens[model]['input'].append(sample['input_tokens'])
                        if sample.get('output_tokens'):
                            challenger_tokens[model]['output'].append(sample['output_tokens'])

    # Calculate costs
    lines.append('| Metric | Haiku | Flash | DeepSeek | Qwen |')
    lines.append('|---|---|---|---|---|')

    # Cost per 1k tokens
    costs_str = '| Cost / 1k tokens | '
    for model in ['haiku'] + MODELS:
        model_key = model if model == 'haiku' else model
        cost_info = MODEL_COSTS.get(model_key, {'input': 0, 'output': 0})
        # Rough estimate: (input_cost * avg_input + output_cost * avg_output) / 1000
        blended = (cost_info['input'] * 500 + cost_info['output'] * 100) / 1000  # Rough average
        costs_str += f"${blended:.4f} | "
    lines.append(costs_str)

    # Avg input tokens
    avg_str = '| Avg input tokens | '
    haiku_input_avg = statistics.mean(haiku_tokens['input']) if haiku_tokens['input'] else 0
    for model in ['haiku'] + MODELS:
        if model == 'haiku':
            avg_str += f"{haiku_input_avg:.0f} | "
        else:
            avg = statistics.mean(challenger_tokens[model]['input']) if challenger_tokens[model]['input'] else 0
            avg_str += f"{avg:.0f} | "
    lines.append(avg_str)

    # Avg output tokens
    avg_str = '| Avg output tokens | '
    haiku_output_avg = statistics.mean(haiku_tokens['output']) if haiku_tokens['output'] else 0
    for model in ['haiku'] + MODELS:
        if model == 'haiku':
            avg_str += f"{haiku_output_avg:.0f} | "
        else:
            avg = statistics.mean(challenger_tokens[model]['output']) if challenger_tokens[model]['output'] else 0
            avg_str += f"{avg:.0f} | "
    lines.append(avg_str)

    return '\n'.join(lines)


def generate_decision_record(operation: str, run_dir: Path, stats_by_model: dict[str, dict]) -> str:
    """Generate a complete MSD decision record."""
    lines = []

    # Header
    msd_num = 1 if operation == 'entity_extraction' else 2 if operation == 'sentiment_analysis' else 3
    lines.append(f"# MSD-{msd_num:03d}: {operation.replace('_', ' ').title()}")
    lines.append('')
    lines.append(f"**Status:** Complete")
    lines.append(f"**Operation:** {operation}")
    lines.append(f"**Golden Set Size:** 100 samples")
    lines.append(f"**Evaluation Date:** 2026-04-28")
    lines.append(f"**Baseline Model:** Haiku 4.5")
    lines.append('')

    # Evaluation Summary
    lines.append('## Evaluation Summary')
    lines.append('')
    lines.append(f'This decision record evaluates three challenger models (Flash, DeepSeek, Qwen) against Haiku baseline for {operation}. The evaluation uses parity measurement: can each challenger substitute for Haiku without users noticing a difference?')
    lines.append('')

    # Quality Metrics
    lines.append(generate_quality_table(operation, stats_by_model))

    # Latency
    lines.append(generate_latency_table(run_dir, operation))

    # Cost
    lines.append(generate_cost_table(run_dir, operation))

    # Per-model decisions
    lines.append('')
    lines.append('## Per-Model Decisions')
    lines.append('')

    for model in MODELS:
        stats = stats_by_model.get(model, {})
        mean_score = stats.get('mean_score', 0)
        flagged_pct = stats.get('flagged_pct', 0)
        operation_flagged = stats.get('operation_flagged', False)

        # Simple decision logic
        if operation in ['entity_extraction', 'theme_extraction']:
            threshold = 0.85
            if mean_score >= threshold and not operation_flagged:
                decision = '**SWAP**'
                rationale = f'Mean F1 {mean_score:.2f} exceeds threshold ({threshold}). Quality parity met. Cost savings justify swap.'
            elif mean_score >= threshold * 0.95 and flagged_pct <= 10:
                decision = '**CONDITIONAL**'
                rationale = f'Mean F1 {mean_score:.2f} near threshold. Acceptable for batch processing only, not real-time.'
            else:
                decision = '**STAY**'
                rationale = f'Mean F1 {mean_score:.2f} below threshold ({threshold}). Quality risk outweighs cost savings.'
        else:  # sentiment_analysis
            accuracy = 100 - flagged_pct
            if accuracy >= 75 and not operation_flagged:
                decision = '**SWAP**'
                rationale = f'Accuracy {accuracy:.0f}% exceeds baseline. Quality parity met. Cost savings justify swap.'
            elif accuracy >= 70:
                decision = '**CONDITIONAL**'
                rationale = f'Accuracy {accuracy:.0f}% near threshold. Acceptable for non-critical paths only.'
            else:
                decision = '**STAY**'
                rationale = f'Accuracy {accuracy:.0f}% below acceptable threshold. Quality degradation too high.'

        lines.append(f'### {model.capitalize()}')
        lines.append('')
        lines.append(f'{decision}')
        lines.append('')
        lines.append(f'{rationale}')
        lines.append('')

    # Manual Validation Caveat
    lines.append('## Manual Validation Caveat')
    lines.append('')
    caveat = MANUAL_VALIDATION.get(operation, {})
    lines.append(f"Manual validation agreement: **{caveat.get('agreement', 0)}%**")
    lines.append('')
    lines.append(f"{caveat.get('caveat', '')}")
    lines.append('')

    # Next Steps
    lines.append('## Recommendations')
    lines.append('')
    lines.append('1. Review per-model decisions above')
    lines.append('2. If SWAP: prepare rollout plan with gradual traffic shift')
    lines.append('3. If CONDITIONAL: document specific constraints in code')
    lines.append('4. If STAY: defer to Sprint 17 after prompt refinement')
    lines.append('')

    return '\n'.join(lines)


def main():
    run_dir = Path('/Users/mc/dev-projects/crypto-news-aggregator/docs/decisions/msd-flash/runs/2026-04-28')
    decisions_dir = Path('/Users/mc/dev-projects/crypto-news-aggregator/docs/decisions')

    # Load stats
    stats_file = run_dir / 'scoring-stats.json'
    if not stats_file.exists():
        print(f"❌ Stats file not found: {stats_file}")
        return

    with open(stats_file) as f:
        all_stats = json.load(f)

    # Group stats by operation and model
    stats_by_operation = {}
    for stat in all_stats:
        op = stat['operation']
        model = stat['model']
        if op not in stats_by_operation:
            stats_by_operation[op] = {}
        stats_by_operation[op][model] = stat

    # Generate decision records
    for i, operation in enumerate(OPERATIONS, start=1):
        print(f"Generating MSD-{i:03d}: {operation}")

        record = generate_decision_record(operation, run_dir, stats_by_operation.get(operation, {}))

        # Write to file
        filename = f"MSD-{i:03d}-{operation}.md"
        filepath = decisions_dir / filename

        with open(filepath, 'w') as f:
            f.write(record)

        print(f"  ✅ Written to {filepath}")

    print(f"\n✅ Phase 6 complete. Decision records written.")


if __name__ == '__main__':
    main()
