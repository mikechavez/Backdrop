import json

files = {
    "entity_extraction": "/Users/mc/entity_extraction_golden.json",
    "sentiment_analysis": "/Users/mc/sentiment_analysis_golden.json",
    "theme_extraction": "/Users/mc/theme_extraction_golden.json",
}

def load(path):
    docs = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                docs.append(json.loads(line))
    return docs

# entity_extraction: 5 typical + 5 edge (short or high entity count)
docs = load(files["entity_extraction"])
typical = [i for i,d in enumerate(docs) if 200 < len(d.get("text","")) < 600 and len(d.get("entities",[])) <= 3][:5]
edge = [i for i,d in enumerate(docs) if len(d.get("text","")) < 200 or len(d.get("entities",[])) > 5][:5]
print(f"\nentity_extraction — validate indices: {sorted(typical + edge)}")

# sentiment_analysis: 5 typical + 5 edge (neutral or short)
docs = load(files["sentiment_analysis"])
typical = [i for i,d in enumerate(docs) if d.get("sentiment",{}).get("label") in ("positive","negative") and len(d.get("text","")) > 200][:5]
edge = [i for i,d in enumerate(docs) if d.get("sentiment",{}).get("label") == "neutral" or len(d.get("text","")) < 200][:5]
print(f"sentiment_analysis — validate indices: {sorted(typical + edge)}")

# theme_extraction: 5 typical + 5 edge (high theme count or short)
docs = load(files["theme_extraction"])
typical = [i for i,d in enumerate(docs) if 200 < len(d.get("text","")) < 600 and len(d.get("themes",[])) <= 5][:5]
edge = [i for i,d in enumerate(docs) if len(d.get("themes",[])) > 6 or len(d.get("text","")) < 200][:5]
print(f"theme_extraction — validate indices: {sorted(typical + edge)}")