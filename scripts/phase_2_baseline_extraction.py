#!/usr/bin/env python3
"""
Phase 2: Baseline Extraction
Load golden sets and extract Haiku baselines (do not re-call API).
"""

import json
import sys
from pathlib import Path
from typing import Any
import re
from html import unescape
from datetime import datetime


def strip_html(html: str) -> str:
    """Strip HTML tags from text."""
    # Remove HTML tags
    text = re.sub(r"<[^>]*>", "", html)
    # Unescape HTML entities
    text = unescape(text)
    # Clean up whitespace
    text = text.strip()
    return text


def process_golden_set(
    operation: str, golden_set_path: Path, output_dir: Path
) -> None:
    """Process a golden set file and extract Haiku baselines."""
    print(f"\n[Phase 2] Processing {operation} from {golden_set_path.name}")

    if not golden_set_path.exists():
        print(f"✗ Not found: {golden_set_path}")
        sys.exit(1)

    samples = []
    samples_with_metadata = 0
    samples_missing_metadata = 0

    # Read JSONL file
    with open(golden_set_path, "r") as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        try:
            doc = json.loads(line)

            # Extract baseline output based on operation
            haiku_output = None
            if operation == "entity_extraction":
                haiku_output = doc.get("entities", [])
            elif operation == "sentiment_analysis":
                haiku_output = doc.get("sentiment")
            elif operation == "theme_extraction":
                haiku_output = doc.get("themes", [])
            else:
                raise ValueError(f"Unknown operation: {operation}")

            # Strip HTML from text
            text = strip_html(doc.get("text", ""))

            sample = {
                "sample_id": f"{operation}_{i + 1}",
                "article_id": doc["_id"]["$oid"],
                "title": doc.get("title", ""),
                "text_original_length": len(doc.get("text", "")),
                "text": text,
                "haiku_output": haiku_output,
                "source": "historical",
                "llm_trace_metadata": None,  # Will be populated if join with llm_traces is possible
                "created_at": doc.get("created_at", {}).get("$date", ""),
            }

            samples.append(sample)

            if sample["llm_trace_metadata"]:
                samples_with_metadata += 1
            else:
                samples_missing_metadata += 1

        except Exception as e:
            print(f"✗ Error parsing line {i + 1}: {e}")
            raise

    # Create phase output
    phase_output = {
        "operation": operation,
        "run_date": datetime.now().isoformat(),
        "golden_set_file": str(golden_set_path),
        "samples": samples,
        "metadata": {
            "total_samples": len(samples),
            "samples_with_trace_metadata": samples_with_metadata,
            "samples_missing_metadata": samples_missing_metadata,
        },
    }

    # Write output JSONL
    output_file = output_dir / f"baseline-{operation}.jsonl"
    with open(output_file, "w") as f:
        for sample in samples:
            f.write(json.dumps(sample) + "\n")

    # Write metadata JSON
    metadata_file = output_dir / f"baseline-{operation}-metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(phase_output, f, indent=2)

    print(f"✓ {operation}: {len(samples)} samples extracted")
    print(f"  - Samples with trace metadata: {samples_with_metadata}")
    print(f"  - Samples missing metadata: {samples_missing_metadata}")
    print(f"  - Output: {output_file}")
    print(f"  - Metadata: {metadata_file}")


def main():
    """Main entry point."""
    golden_set_dir = Path("/Users/mc")
    output_dir = Path(
        "/Users/mc/dev-projects/crypto-news-aggregator/docs/decisions/msd-flash/runs/2026-04-28"
    )

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    operations = [
        ("entity_extraction", "entity_extraction_golden.json"),
        ("sentiment_analysis", "sentiment_analysis_golden.json"),
        ("theme_extraction", "theme_extraction_golden.json"),
    ]

    print("\n=== FEATURE-053: Phase 2 — Baseline Extraction ===")
    print(f"Output directory: {output_dir}")

    for op_name, op_file in operations:
        golden_set_path = golden_set_dir / op_file
        process_golden_set(op_name, golden_set_path, output_dir)

    print("\n=== Phase 2 Complete ===")
    print(f"All baselines extracted to: {output_dir}")
    print("\nNext: Phase 3 — Run challenger models against the same golden sets")


if __name__ == "__main__":
    main()
