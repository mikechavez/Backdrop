import json
import os

files = {
    "entity_extraction": "/Users/mc/entity_extraction_golden.json",
    "sentiment_analysis": "/Users/mc/sentiment_analysis_golden.json",
    "theme_extraction": "/Users/mc/theme_extraction_golden.json",
}

indices = {
    "entity_extraction": [0, 2, 4, 6, 7, 9, 10, 11, 12, 22],
    "sentiment_analysis": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    "theme_extraction": [0, 1, 2, 4, 6, 7, 9, 23, 26, 30],
}

def load(path):
    docs = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                docs.append(json.loads(line))
    return docs

lines = []

for op, path in files.items():
    docs = load(path)
    target = indices[op]
    lines.append(f"\n# OPERATION: {op}\n")
    for i in target:
        d = docs[i]
        lines.append(f"\n## Sample {i}")
        lines.append(f"**TITLE:** {d.get('title','')}")
        lines.append(f"\n**TEXT:** {d.get('text','')}")
        if op == "entity_extraction":
            entities = [e['name'] for e in d.get('entities', [])]
            lines.append(f"\n**HAIKU OUTPUT:** {entities}")
        elif op == "sentiment_analysis":
            s = d.get('sentiment', {})
            lines.append(f"\n**HAIKU OUTPUT:** {s.get('label')} (score: {s.get('score')})")
        elif op == "theme_extraction":
            lines.append(f"\n**HAIKU OUTPUT:** {d.get('themes', [])}")
        lines.append(f"\n**YOUR LABEL:** ___")
        lines.append(f"\n**MATCH:** ___")
        lines.append("\n---")

output_path = os.path.join(os.getcwd(), "f053-validation-worksheet.md")
with open(output_path, "w") as f:
    f.write("\n".join(lines))

print(f"Saved to {output_path}")