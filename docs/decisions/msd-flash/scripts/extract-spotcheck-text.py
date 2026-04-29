#!/usr/bin/env python3
"""
Extract full text of spot-check articles for use in prompt examples.
"""

import json
from pathlib import Path

GOLDEN_SET_PATH = Path("/Users/mc/dev-projects/crypto-news-aggregator/docs/decisions/msd-flash/golden-set")

# Spot-check article IDs (from script output)
SPOTCHECK_IDS = {
    'entity_extraction': [
        '69e124b4cd3cb7bb0f1de49a',
        '69e10224b05c1d4ddc1de4c7',
        '69de1566972adb5ad8c76cb6',
        '69dfb314a634582621effb78',
        '69deb85f2adcac6279c197b5'
    ],
    'sentiment_analysis': [
        '69e124b4cd3cb7bb0f1de49a',
        '69e10224b05c1d4ddc1de4c7',
        '69e0c3100a57f1a2701de53e',
        '69e124b5cd3cb7bb0f1de49b',
        '69de613a972adb5ad8c76df6'
    ],
    'theme_extraction': [
        '69e124b4cd3cb7bb0f1de49a',
        '69e10224b05c1d4ddc1de4c7',
        '69e0c3100a57f1a2701de53e',
        '69e124b5cd3cb7bb0f1de49b',
        '69de613a972adb5ad8c76df6'
    ]
}

def load_golden_set_jsonl(operation):
    """Load JSONL golden set and return dict keyed by _id."""
    filepath = GOLDEN_SET_PATH / f"{operation}_golden.json"
    samples = {}
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                sample = json.loads(line)
                oid = sample.get('_id')
                if isinstance(oid, dict) and '$oid' in oid:
                    samples[oid['$oid']] = sample
                else:
                    samples[oid] = sample
    return samples

def extract_spotcheck_articles():
    """Extract text and metadata for all spot-check articles."""
    
    for operation, ids in SPOTCHECK_IDS.items():
        print(f"\n{'='*80}")
        print(f"OPERATION: {operation.upper()}")
        print(f"{'='*80}\n")
        
        samples = load_golden_set_jsonl(operation)
        
        for i, article_id in enumerate(ids, 1):
            if article_id in samples:
                sample = samples[article_id]
                print(f"\n{i}. ID: {article_id}")
                print(f"   Title: {sample.get('title', 'N/A')}")
                print(f"   Text ({len(sample.get('text', ''))} chars):")
                print(f"   {'-'*76}")
                
                # Print full text
                text = sample.get('text', '')
                if len(text) > 1000:
                    print(f"{text[:1000]}")
                    print(f"   ... [truncated, {len(text) - 1000} more chars]")
                else:
                    print(f"{text}")
                
                print(f"   {'-'*76}")
                
                # Print baseline output for reference
                if operation == 'entity_extraction':
                    if 'haiku_entities' in sample:
                        print(f"   Haiku baseline entities: {sample.get('haiku_entities', [])}")
                    elif 'entities' in sample:
                        print(f"   Haiku baseline entities: {sample.get('entities', [])}")
                
                elif operation == 'sentiment_analysis':
                    label = sample.get('haiku_label', sample.get('sentiment', 'N/A'))
                    if isinstance(label, dict):
                        print(f"   Haiku baseline label: {label.get('label', 'N/A')} (score: {label.get('score', 'N/A')})")
                    else:
                        print(f"   Haiku baseline label: {label}")
                
                elif operation == 'theme_extraction':
                    themes = sample.get('haiku_themes', sample.get('themes', []))
                    print(f"   Haiku baseline themes: {themes}")
            else:
                print(f"\n{i}. ID: {article_id} — NOT FOUND in golden set")

if __name__ == '__main__':
    extract_spotcheck_articles()