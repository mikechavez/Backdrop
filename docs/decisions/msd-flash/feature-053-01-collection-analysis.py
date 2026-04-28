import json
from collections import Counter

files = {
    "entity_extraction": "/Users/mc/entity_extraction_golden.json",
    "sentiment_analysis": "/Users/mc/sentiment_analysis_golden.json",
    "theme_extraction": "/Users/mc/theme_extraction_golden.json",
}

for op, path in files.items():
    print(f"\n{'='*50}")
    print(f"OPERATION: {op}")
    print(f"{'='*50}")

    docs = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                docs.append(json.loads(line))

    print(f"Total samples: {len(docs)}")

    # Text length distribution
    lengths = [len(d.get("text", "")) for d in docs]
    print(f"Text length — min: {min(lengths)}, max: {max(lengths)}, avg: {int(sum(lengths)/len(lengths))}")
    print(f"Long articles (>2000 chars): {sum(1 for l in lengths if l > 2000)}")
    print(f"Short articles (<200 chars): {sum(1 for l in lengths if l < 200)}")

    if op == "entity_extraction":
        counts = [len(d.get("entities", [])) for d in docs]
        print(f"Entity count — min: {min(counts)}, max: {max(counts)}, avg: {round(sum(counts)/len(counts),1)}")
        print(f"Multi-entity (>3): {sum(1 for c in counts if c > 3)}")
        print(f"Single entity: {sum(1 for c in counts if c == 1)}")

    if op == "sentiment_analysis":
        labels = [d.get("sentiment", {}).get("label") for d in docs]
        print(f"Sentiment distribution: {dict(Counter(labels))}")

    if op == "theme_extraction":
        counts = [len(d.get("themes", [])) for d in docs]
        print(f"Theme count — min: {min(counts)}, max: {max(counts)}, avg: {round(sum(counts)/len(counts),1)}")

    # Sample doc
    print(f"\nSample doc (first):")
    d = docs[0]
    print(f"  title: {d.get('title','')[:80]}")
    print(f"  text length: {len(d.get('text',''))}")
    if op == "entity_extraction":
        print(f"  entities: {d.get('entities')}")
    if op == "sentiment_analysis":
        print(f"  sentiment: {d.get('sentiment')}")
    if op == "theme_extraction":
        print(f"  themes: {d.get('themes')}")


