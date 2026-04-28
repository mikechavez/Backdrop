#!/usr/bin/env python3
"""
Phase 4: Output Normalization for FEATURE-053 Flash Evaluations

Normalizes all baseline and challenger outputs before scoring.
Applies consistently to both entity and theme extraction arrays, and to sentiment labels.
"""

import json
import re
from pathlib import Path
from html.parser import HTMLParser
from typing import Any


class HTMLStripper(HTMLParser):
    """Strip HTML tags from text."""
    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []

    def handle_data(self, d):
        self.fed.append(d)

    def get_data(self):
        return ''.join(self.fed)


def strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    if not text:
        return text
    stripper = HTMLStripper()
    try:
        stripper.feed(text)
        return stripper.get_data()
    except Exception:
        return text


def normalize_string(s: str) -> str:
    """Normalize a single string: HTML strip, whitespace trim, lowercase, remove punctuation."""
    if not s:
        return ""

    # Strip HTML
    s = strip_html(s)
    # Trim whitespace
    s = s.strip()
    # Lowercase
    s = s.lower()
    # Remove punctuation except hyphens within words
    s = re.sub(r'[^\w\s-]', '', s)
    # Collapse multiple spaces
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def parse_challenger_output(output: Any) -> Any:
    """Parse challenger output which may be a JSON string or markdown code block."""
    if isinstance(output, list):
        return output
    if isinstance(output, dict):
        return output

    if not isinstance(output, str):
        return output

    # Try to extract JSON from markdown code block
    output = output.strip()
    if output.startswith('```json'):
        output = output[7:]  # Remove ```json
    if output.startswith('```'):
        output = output[3:]  # Remove ```
    if output.endswith('```'):
        output = output[:-3]
    output = output.strip()

    try:
        parsed = json.loads(output)
        # If it's wrapped in { "entities": [...] }, extract the entities array
        if isinstance(parsed, dict) and 'entities' in parsed:
            return parsed['entities']
        return parsed
    except json.JSONDecodeError:
        return None


def normalize_entity_extraction(sample: dict) -> dict:
    """
    Normalize entity extraction output.
    Extract 'name' field from entity objects, deduplicate, sort.
    Handles both 'output' (challengers) and 'haiku_output' (baseline) keys.
    """
    normalized = sample.copy()

    # Determine which key to use
    output_key = 'output' if 'output' in normalized else 'haiku_output' if 'haiku_output' in normalized else None
    if not output_key:
        return normalized

    output = normalized[output_key]

    # Parse if it's a challenger output (may be JSON string)
    if output_key == 'output':
        output = parse_challenger_output(output)

    if not isinstance(output, list):
        return normalized

    # Extract names, normalize, deduplicate, sort
    names = set()
    for entity in output:
        if isinstance(entity, dict) and 'name' in entity:
            name = normalize_string(entity['name'])
            if name:
                names.add(name)

    normalized[output_key] = sorted(list(names))
    return normalized


def normalize_sentiment_analysis(sample: dict) -> dict:
    """
    Normalize sentiment analysis output.
    Baseline has {label, score, magnitude}, challenger has numeric score.
    Extract label from baseline, convert score to label for challenger.
    """
    normalized = sample.copy()

    # Baseline: extract label from sentiment object
    if 'haiku_output' in normalized:
        output = normalized['haiku_output']
        if isinstance(output, dict) and 'label' in output:
            normalized['haiku_output'] = normalize_string(output['label'])
        elif isinstance(output, str):
            normalized['haiku_output'] = normalize_string(output)

    # Challenger: convert numeric score to label
    if 'output' in normalized:
        output = normalized['output']
        # Try to parse as number
        try:
            score = float(output) if isinstance(output, str) else output
            # Convert score to label: positive (>0), negative (<0), neutral (=0)
            if score > 0:
                normalized['output'] = 'positive'
            elif score < 0:
                normalized['output'] = 'negative'
            else:
                normalized['output'] = 'neutral'
        except (ValueError, TypeError):
            # If not a number, treat as label
            if isinstance(output, str):
                normalized['output'] = normalize_string(output)

    return normalized


def normalize_theme_extraction(sample: dict) -> dict:
    """
    Normalize theme extraction output.
    Normalize each theme string, deduplicate, sort.
    Handles both 'output' (challengers) and 'haiku_output' (baseline) keys.
    Challenger output may be comma-separated string or JSON list.
    """
    normalized = sample.copy()

    # Determine which key to use
    output_key = 'output' if 'output' in normalized else 'haiku_output' if 'haiku_output' in normalized else None
    if not output_key:
        return normalized

    output = normalized[output_key]

    # Parse if it's a challenger output (may be JSON string or comma-separated)
    if output_key == 'output':
        if isinstance(output, str):
            # Try JSON first
            parsed = parse_challenger_output(output)
            if parsed:
                output = parsed
            else:
                # Fall back to comma-separated parsing
                output = [t.strip() for t in output.split(',')]
        else:
            output = parse_challenger_output(output)

    if not isinstance(output, list):
        return normalized

    # Normalize each theme, deduplicate, sort
    themes = set()
    for theme in output:
        if isinstance(theme, str):
            normalized_theme = normalize_string(theme)
            if normalized_theme:
                themes.add(normalized_theme)

    normalized[output_key] = sorted(list(themes))
    return normalized


def normalize_operation(operation: str, samples: list[dict]) -> list[dict]:
    """Normalize all samples for a given operation."""
    if operation == 'entity_extraction':
        return [normalize_entity_extraction(s) for s in samples]
    elif operation == 'sentiment_analysis':
        return [normalize_sentiment_analysis(s) for s in samples]
    elif operation == 'theme_extraction':
        return [normalize_theme_extraction(s) for s in samples]
    return samples


def normalize_all(run_dir: Path) -> None:
    """
    Normalize all baseline and challenger outputs in a run directory.
    Write normalized outputs to same directory with -normalized suffix.
    """
    operations = ['entity_extraction', 'sentiment_analysis', 'theme_extraction']
    models = ['baseline', 'flash', 'deepseek', 'qwen']

    for operation in operations:
        print(f"\nNormalizing {operation}:")

        for model in models:
            if model == 'baseline':
                filename = f"baseline-{operation}.jsonl"
            else:
                filename = f"challenger-{operation}-{model}.jsonl"

            filepath = run_dir / filename
            if not filepath.exists():
                print(f"  ⚠️  {filename} not found")
                continue

            # Load samples
            samples = []
            with open(filepath) as f:
                for line in f:
                    if line.strip():
                        samples.append(json.loads(line))

            # Normalize
            normalized = normalize_operation(operation, samples)

            # Write normalized output
            normalized_filename = filename.replace('.jsonl', '-normalized.jsonl')
            normalized_filepath = run_dir / normalized_filename

            with open(normalized_filepath, 'w') as f:
                for sample in normalized:
                    f.write(json.dumps(sample) + '\n')

            print(f"  ✅ {model:10} → {normalized_filename}")


if __name__ == '__main__':
    run_dir = Path('/Users/mc/dev-projects/crypto-news-aggregator/docs/decisions/msd-flash/runs/2026-04-28')

    if not run_dir.exists():
        print(f"❌ Run directory not found: {run_dir}")
        exit(1)

    print(f"Starting Phase 4 normalization...")
    print(f"Run dir: {run_dir}")

    normalize_all(run_dir)

    print(f"\n✅ Phase 4 complete. Normalized outputs written to run directory.")
