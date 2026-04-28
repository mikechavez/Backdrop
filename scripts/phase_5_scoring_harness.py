#!/usr/bin/env python3
"""
Phase 5: Scoring Harness for FEATURE-053 Flash Evaluations

Implements the exact scoring logic from EVAL-001-evaluation-contract.md:
- entity_extraction: F1 with alias normalization
- sentiment_analysis: binary label match
- theme_extraction: adjusted F1 with token overlap pass
"""

import json
import re
from pathlib import Path
from typing import Any
from collections import defaultdict


# Build alias table from golden set scan
ENTITY_ALIASES = {
    'fed': 'federal reserve',
    'federal reserve board': 'federal reserve',
    'the fed': 'federal reserve',
    'u.s.': 'united states',
    'usa': 'united states',
    'us': 'united states',
    'sec': 'securities and exchange commission',
    'sec chair': 'securities and exchange commission',
    'sec chairman': 'securities and exchange commission',
    'fed chair': 'federal reserve',
    'fed chairman': 'federal reserve',
    'btc': 'bitcoin',
    'eth': 'ethereum',
    'usdc': 'usd coin',
    'usdt': 'tether',
    'ceo': 'chief executive officer',
    'cto': 'chief technology officer',
}


def normalize_for_match(s: str) -> str:
    """Normalize string for matching: lowercase, strip punctuation/whitespace."""
    s = s.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def apply_alias(s: str, aliases: dict) -> str:
    """Apply alias table to normalize entity names."""
    normalized = normalize_for_match(s)
    return aliases.get(normalized, normalized)


def tokenize(s: str) -> set[str]:
    """Simple word tokenization."""
    s = s.lower().strip()
    words = re.findall(r'\w+', s)
    return set(words)


def token_overlap(s1: str, s2: str) -> float:
    """Calculate token overlap ratio (intersection / min length)."""
    tokens1 = tokenize(s1)
    tokens2 = tokenize(s2)

    if not tokens1 or not tokens2:
        return 0.0

    intersection = len(tokens1 & tokens2)
    min_len = min(len(tokens1), len(tokens2))
    return intersection / min_len if min_len > 0 else 0.0


def score_entity_extraction(haiku_names: list[str], flash_names: list[str], aliases: dict) -> dict:
    """
    Score entity extraction using F1.
    haiku_names and flash_names are already normalized (lowercase, deduplicated, sorted).
    """
    # Apply aliases
    haiku_normalized = set(apply_alias(n, aliases) for n in haiku_names)
    flash_normalized = set(apply_alias(n, aliases) for n in flash_names)

    # Precision: what fraction of Flash's entities are in Haiku's set
    if flash_normalized:
        precision = len(haiku_normalized & flash_normalized) / len(flash_normalized)
    else:
        precision = 1.0 if not haiku_normalized else 0.0

    # Recall: what fraction of Haiku's entities Flash caught
    if haiku_normalized:
        recall = len(haiku_normalized & flash_normalized) / len(haiku_normalized)
    else:
        recall = 1.0 if not flash_normalized else 0.0

    # F1
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * (precision * recall) / (precision + recall)

    return {
        'f1': f1,
        'precision': precision,
        'recall': recall,
        'haiku_count': len(haiku_normalized),
        'flash_count': len(flash_normalized),
        'matched': len(haiku_normalized & flash_normalized),
    }


def score_sentiment_analysis(haiku_label: str, flash_label: str) -> dict:
    """
    Score sentiment analysis using binary label match.
    Labels are already normalized (lowercase).
    """
    match = haiku_label == flash_label
    score = 100.0 if match else 0.0

    return {
        'score': score,
        'match': match,
        'haiku_label': haiku_label,
        'flash_label': flash_label,
    }


def score_theme_extraction(haiku_themes: list[str], flash_themes: list[str]) -> dict:
    """
    Score theme extraction using adjusted F1 with token overlap.
    Pass 1: exact string match (already normalized).
    Pass 2: if no exact match, check 50% token overlap.
    """
    haiku_set = set(haiku_themes)
    flash_set = set(flash_themes)

    # Pass 1: exact matches
    exact_matches = haiku_set & flash_set

    # Pass 2: token overlap for unmatched themes
    additional_matches = set()
    for flash_theme in flash_set - exact_matches:
        for haiku_theme in haiku_set - exact_matches:
            if token_overlap(flash_theme, haiku_theme) >= 0.5:
                additional_matches.add((flash_theme, haiku_theme))

    # Calculate adjusted F1
    total_matches = len(exact_matches) + len(additional_matches)

    if flash_set:
        precision = total_matches / len(flash_set)
    else:
        precision = 1.0 if not haiku_set else 0.0

    if haiku_set:
        recall = total_matches / len(haiku_set)
    else:
        recall = 1.0 if not flash_set else 0.0

    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * (precision * recall) / (precision + recall)

    return {
        'f1': f1,
        'precision': precision,
        'recall': recall,
        'haiku_count': len(haiku_set),
        'flash_count': len(flash_set),
        'exact_matches': len(exact_matches),
        'token_overlap_matches': len(additional_matches),
    }


def score_operation(operation: str, baseline_samples: list[dict], challenger_samples: list[dict], model: str) -> tuple[list[dict], dict]:
    """
    Score all samples for an operation against baseline.
    Returns list of scored samples and operation-level stats.
    """
    scored_samples = []
    scores = []
    flagged_count = 0

    for haiku_sample, flash_sample in zip(baseline_samples, challenger_samples):
        sample_id = haiku_sample.get('sample_id', haiku_sample.get('_id', '?'))
        # Baseline uses 'haiku_output', challenger uses 'output'
        haiku_output = haiku_sample.get('haiku_output')
        flash_output = flash_sample.get('output')

        if operation == 'entity_extraction':
            score_result = score_entity_extraction(
                haiku_output if isinstance(haiku_output, list) else [],
                flash_output if isinstance(flash_output, list) else [],
                ENTITY_ALIASES
            )
            f1 = score_result['f1']
            flagged = f1 < 0.85
        elif operation == 'sentiment_analysis':
            score_result = score_sentiment_analysis(
                haiku_output if isinstance(haiku_output, str) else '',
                flash_output if isinstance(flash_output, str) else ''
            )
            flagged = not score_result['match']
        elif operation == 'theme_extraction':
            score_result = score_theme_extraction(
                haiku_output if isinstance(haiku_output, list) else [],
                flash_output if isinstance(flash_output, list) else []
            )
            f1 = score_result['f1']
            flagged = f1 < 0.80
        else:
            continue

        scores.append(score_result.get('f1', score_result.get('score', 0)))
        if flagged:
            flagged_count += 1

        scored_sample = {
            '_id': sample_id,
            'score': score_result,
            'flagged': flagged,
        }
        scored_samples.append(scored_sample)

    # Operation-level stats
    mean_score = sum(scores) / len(scores) if scores else 0
    flagged_pct = (flagged_count / len(scored_samples) * 100) if scored_samples else 0
    operation_flagged = flagged_pct > 5.0

    stats = {
        'operation': operation,
        'model': model,
        'samples_total': len(scored_samples),
        'samples_flagged': flagged_count,
        'flagged_pct': flagged_pct,
        'operation_flagged': operation_flagged,
        'mean_score': mean_score,
    }

    return scored_samples, stats


def score_all(run_dir: Path) -> None:
    """
    Score all operations for all models.
    Write scored samples and operation stats to dated output directory.
    """
    operations = ['entity_extraction', 'sentiment_analysis', 'theme_extraction']
    models = ['flash', 'deepseek', 'qwen']

    all_stats = []

    for operation in operations:
        print(f"\nScoring {operation}:")

        # Load baseline (normalized)
        baseline_file = run_dir / f"baseline-{operation}-normalized.jsonl"
        baseline_samples = []
        if baseline_file.exists():
            with open(baseline_file) as f:
                for line in f:
                    if line.strip():
                        baseline_samples.append(json.loads(line))
        else:
            print(f"  ⚠️  Baseline not found: {baseline_file}")
            continue

        for model in models:
            challenger_file = run_dir / f"challenger-{operation}-{model}-normalized.jsonl"

            challenger_samples = []
            if challenger_file.exists():
                with open(challenger_file) as f:
                    for line in f:
                        if line.strip():
                            challenger_samples.append(json.loads(line))
            else:
                print(f"  ⚠️  {model} not found")
                continue

            # Score
            scored, stats = score_operation(operation, baseline_samples, challenger_samples, model)

            # Write scored samples
            scored_file = run_dir / f"scored-{operation}-{model}.jsonl"
            with open(scored_file, 'w') as f:
                for sample in scored:
                    f.write(json.dumps(sample) + '\n')

            all_stats.append(stats)
            print(f"  ✅ {model:10} → mean={stats['mean_score']:.1f}, flagged={stats['flagged_pct']:.1f}%")

    # Write operation stats summary
    stats_file = run_dir / 'scoring-stats.json'
    with open(stats_file, 'w') as f:
        json.dump(all_stats, f, indent=2)

    print(f"\n✅ Phase 5 complete. Scored outputs and stats written to run directory.")


if __name__ == '__main__':
    run_dir = Path('/Users/mc/dev-projects/crypto-news-aggregator/docs/decisions/msd-flash/runs/2026-04-28')

    if not run_dir.exists():
        print(f"❌ Run directory not found: {run_dir}")
        exit(1)

    print(f"Starting Phase 5 scoring...")
    print(f"Run dir: {run_dir}")

    score_all(run_dir)
