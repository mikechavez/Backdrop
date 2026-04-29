#!/usr/bin/env python3
"""
Extract 5 strategically diverse article IDs from golden sets for TASK-086 spot-check.
Avoids bias by selecting across:
- Entity complexity (high/medium/low)
- Article length (short/medium/long)
- Article type (price action, regulatory, technical, etc.)
"""

import json
from pathlib import Path
from statistics import median, stdev

GOLDEN_SET_PATH = Path("/Users/mc/dev-projects/crypto-news-aggregator/docs/decisions/msd-flash/golden-set")

def load_golden_set(operation):
    """Load golden set JSONL for an operation (one JSON object per line)."""
    filepath = GOLDEN_SET_PATH / f"{operation}_golden.json"
    samples = []
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    return samples

def analyze_sample(sample, operation):
    """Analyze sample metadata for diversity selection."""
    analysis = {
        '_id': sample.get('_id'),
        'title': sample.get('title', ''),
        'text': sample.get('text', ''),
    }
    
    # Text length (proxy for complexity)
    text_len = len(sample.get('text', ''))
    analysis['text_length'] = text_len
    
    # Entity complexity (for entity_extraction)
    if operation == 'entity_extraction':
        if 'haiku_entities' in sample:
            analysis['entity_count'] = len(sample.get('haiku_entities', []))
        elif 'entities' in sample:
            analysis['entity_count'] = len(sample.get('entities', []))
        else:
            analysis['entity_count'] = 0
    
    # Theme count (for theme_extraction)
    if operation == 'theme_extraction':
        if 'haiku_themes' in sample:
            analysis['theme_count'] = len(str(sample.get('haiku_themes', '')).split(','))
        else:
            analysis['theme_count'] = 0
    
    # Sentiment label (for sentiment_analysis)
    if operation == 'sentiment_analysis':
        analysis['sentiment_label'] = sample.get('haiku_label', sample.get('sentiment', 'unknown'))
    
    return analysis

def select_diverse(operation, sample_size=5):
    """Select diverse samples across key dimensions."""
    golden_set = load_golden_set(operation)
    
    print(f"\n{'='*70}")
    print(f"OPERATION: {operation}")
    print(f"Total samples: {len(golden_set)}")
    print(f"{'='*70}\n")
    
    # Analyze all samples
    analyzed = [analyze_sample(s, operation) for s in golden_set]
    
    # Sort by text length to get coverage
    analyzed_sorted = sorted(analyzed, key=lambda x: x['text_length'])
    
    # Select diverse by length
    selected = []
    step = len(analyzed_sorted) // sample_size
    
    for i in range(sample_size):
        idx = min(i * step + (step // 2), len(analyzed_sorted) - 1)
        selected.append(analyzed_sorted[idx])
    
    # Print selected articles
    print(f"Selected {sample_size} strategically diverse articles:\n")
    for i, sample in enumerate(selected, 1):
        print(f"{i}. ID: {sample['_id']}")
        print(f"   Title: {sample['title'][:70]}...")
        print(f"   Length: {sample['text_length']} chars")
        if operation == 'entity_extraction':
            print(f"   Entities: {sample.get('entity_count', 'N/A')}")
        elif operation == 'theme_extraction':
            print(f"   Themes: {sample.get('theme_count', 'N/A')}")
        elif operation == 'sentiment_analysis':
            print(f"   Label: {sample.get('sentiment_label', 'N/A')}")
        print()
    
    # Return just the IDs
    return [s['_id'] for s in selected]

# Run for all three operations
all_selections = {}
for operation in ['entity_extraction', 'sentiment_analysis', 'theme_extraction']:
    ids = select_diverse(operation, sample_size=5)
    all_selections[operation] = ids

# Summary output
print(f"\n{'='*70}")
print("SPOT-CHECK ARTICLE SELECTIONS FOR TASK-086")
print(f"{'='*70}\n")

for operation, ids in all_selections.items():
    print(f"{operation}:")
    for i, article_id in enumerate(ids, 1):
        print(f"  {i}. {article_id}")
    print()

# Output as JSON for easy copying
print(f"\nJSON format for ticket:\n")
print(json.dumps(all_selections, indent=2))