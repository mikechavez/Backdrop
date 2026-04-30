#!/usr/bin/env python3
"""
Phase 3: Threshold-based Scoring Harness

Scores Phase 2 challenger outputs against reference answers (ground truth).
Calculates F1 (entity/theme) and Accuracy (sentiment) per model per operation.
Outputs:
1. scoring_results.csv: Pass/fail per model per operation
2. cost_metrics.csv: Token count, cost, latency per model per operation (if available)
"""

import json
import csv
import os
import sys
from collections import defaultdict
from statistics import mean, stdev, quantiles
from pathlib import Path

# Thresholds from TASK-082
THRESHOLDS = {
    "entity_extraction": 0.82,      # F1 >= 0.82
    "sentiment_analysis": 0.77,     # Accuracy >= 77%
    "theme_extraction": 0.78,       # Adjusted F1 >= 0.78
}

# OpenRouter pricing (input/output tokens per 1M)
PRICING = {
    "flash": {"input": 0.075, "output": 0.30},        # Google Gemini 2.5 Flash
    "deepseek": {"input": 0.14, "output": 0.28},      # DeepSeek Chat
    "qwen": {"input": 0.08, "output": 0.24},          # Qwen Plus
    "haiku": {"input": 0.80, "output": 4.00},         # Claude Haiku (for comparison)
}

def load_reference_answers(ref_path):
    """Load ground truth from reference_answers.json"""
    with open(ref_path) as f:
        return json.load(f)

def load_phase2_jsonl(jsonl_path):
    """Load Phase 2 JSONL output. Parse article _id from sample_id."""
    outputs = {}
    with open(jsonl_path) as f:
        for line in f:
            try:
                item = json.loads(line)
                # Extract ObjectId from sample_id: "{'$oid': '69ddd19a972adb5ad8c76bbf'}"
                sample_id = item.get("sample_id", "")
                try:
                    # Parse string representation of ObjectId
                    article_id = sample_id.split("'")[3]
                except (IndexError, ValueError):
                    continue

                outputs[article_id] = item
            except json.JSONDecodeError:
                continue
    return outputs

def calculate_entity_f1(reference_entities, predicted_entities):
    """Calculate F1 score for entity extraction.
    reference_entities: list of strings (ground truth)
    predicted_entities: list of strings (model output)
    Matching: case-insensitive, order-independent
    """
    if not reference_entities and not predicted_entities:
        return 1.0  # Both empty = perfect match

    ref_set = {e.lower() for e in reference_entities}
    pred_set = {e.lower() for e in predicted_entities}

    if not pred_set:
        return 0.0 if ref_set else 1.0
    if not ref_set:
        return 0.0

    correct = len(ref_set & pred_set)
    precision = correct / len(pred_set) if pred_set else 0
    recall = correct / len(ref_set) if ref_set else 0

    if precision + recall == 0:
        return 0.0

    f1 = 2 * (precision * recall) / (precision + recall)
    return f1

def calculate_sentiment_accuracy(reference_label, predicted_label):
    """Calculate accuracy for sentiment analysis.
    reference_label: string (positive/neutral/negative)
    predicted_label: string (model output label)
    Returns: 1.0 if match, 0.0 otherwise
    """
    return 1.0 if reference_label.lower() == predicted_label.lower() else 0.0

def calculate_theme_f1(reference_themes, predicted_themes):
    """Calculate adjusted F1 for theme extraction with partial credit for substring matches.
    reference_themes: list of strings (ground truth)
    predicted_themes: list of strings (model output)
    """
    if not reference_themes and not predicted_themes:
        return 1.0

    ref_lower = [t.lower() for t in reference_themes]
    pred_lower = [t.lower() for t in predicted_themes]

    if not pred_lower:
        return 0.0 if ref_lower else 1.0
    if not ref_lower:
        return 0.0

    # Exact matches
    exact_matches = sum(1 for p in pred_lower if p in ref_lower)

    # Partial matches (substring)
    partial_matches = 0
    for p in pred_lower:
        if p not in ref_lower:  # Skip already exact-matched
            for r in ref_lower:
                if p in r or r in p:  # Bidirectional substring match
                    partial_matches += 1
                    break

    correct = exact_matches + (0.5 * partial_matches)  # Half credit for partials
    precision = correct / len(pred_lower)
    recall = correct / len(ref_lower)

    if precision + recall == 0:
        return 0.0

    f1 = 2 * (precision * recall) / (precision + recall)
    return f1

def parse_entity_output(raw_output):
    """Parse entity output from model (JSON string or raw list).
    Handles markdown-wrapped JSON: ```json {...}```
    """
    try:
        if not isinstance(raw_output, str):
            return []

        # Remove markdown code fences if present
        text = raw_output.strip()
        if text.startswith("```"):
            # Find closing ```
            end_idx = text.rfind("```")
            if end_idx > 3:
                text = text[3:end_idx].strip()
                # Remove 'json' language specifier if present
                if text.startswith("json"):
                    text = text[4:].strip()

        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        elif isinstance(parsed, dict) and "entities" in parsed:
            # Extract just the names from entity objects
            entities = parsed["entities"]
            if isinstance(entities, list) and entities and isinstance(entities[0], dict):
                return [e.get("name", "") for e in entities if e.get("name")]
            return entities
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return []

def parse_sentiment_output(raw_output):
    """Parse sentiment score from model output.
    Output is typically a score (float). Convert to label for comparison.
    Label mapping: score > 0.2 → positive, score < -0.2 → negative, else neutral
    """
    try:
        if isinstance(raw_output, str):
            # Try parsing as JSON first (in case of wrapped output)
            try:
                parsed = json.loads(raw_output.strip())
                if isinstance(parsed, dict):
                    score = float(parsed.get("score", 0))
                elif isinstance(parsed, (int, float)):
                    score = float(parsed)
                else:
                    score = 0.0
            except (json.JSONDecodeError, ValueError):
                # If not JSON, try direct float conversion
                score = float(raw_output.strip())
        elif isinstance(raw_output, (int, float)):
            score = float(raw_output)
        else:
            score = 0.0

        # Map score to label
        if score > 0.2:
            label = "positive"
        elif score < -0.2:
            label = "negative"
        else:
            label = "neutral"

        return label, score
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return "neutral", 0.0

def parse_theme_output(raw_output):
    """Parse themes from model output.
    Handles: comma-separated strings, markdown-wrapped JSON, or direct JSON.
    """
    try:
        if not isinstance(raw_output, str):
            return []

        text = raw_output.strip()

        # Try JSON first (markdown-wrapped or direct)
        if text.startswith("```") or text.startswith("{") or text.startswith("["):
            if text.startswith("```"):
                # Remove markdown code fences
                end_idx = text.rfind("```")
                if end_idx > 3:
                    text = text[3:end_idx].strip()
                    if text.startswith("json"):
                        text = text[4:].strip()

            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(t).strip() for t in parsed]
                elif isinstance(parsed, dict) and "themes" in parsed:
                    themes = parsed["themes"]
                    if isinstance(themes, list):
                        return [str(t).strip() for t in themes]
            except (json.JSONDecodeError, ValueError):
                pass

        # Fall back to comma-separated parsing
        themes = [t.strip() for t in text.split(",") if t.strip()]
        if themes:
            return themes
    except (TypeError, ValueError):
        pass
    return []

def score_operation(operation, reference_answers, phase2_outputs, cost_data):
    """Score all articles for a single operation.
    Returns: (scores_list, matched_count, cost_metrics_dict)
    """
    scores = []
    matched = 0

    # Collect cost/latency metrics
    tokens_list = []
    latencies = []

    for article_id, reference_output in reference_answers.items():
        if article_id not in phase2_outputs:
            continue

        matched += 1
        phase2_item = phase2_outputs[article_id]
        raw_output = phase2_item.get("raw_output")

        # Collect cost metrics
        input_tokens = phase2_item.get("input_tokens", 0)
        output_tokens = phase2_item.get("output_tokens", 0)
        latency_ms = phase2_item.get("latency_ms", 0)

        total_tokens = input_tokens + output_tokens
        tokens_list.append(total_tokens)
        if latency_ms:
            latencies.append(latency_ms)

        cost_data["input_tokens"].append(input_tokens)
        cost_data["output_tokens"].append(output_tokens)
        cost_data["latencies"].append(latency_ms)

        # Calculate score based on operation
        if operation == "entity_extraction":
            predicted = parse_entity_output(raw_output)
            score = calculate_entity_f1(reference_output, predicted)
        elif operation == "sentiment_analysis":
            predicted_label, _ = parse_sentiment_output(raw_output)
            score = calculate_sentiment_accuracy(reference_output["label"], predicted_label)
        elif operation == "theme_extraction":
            predicted = parse_theme_output(raw_output)
            score = calculate_theme_f1(reference_output, predicted)
        else:
            score = 0.0

        scores.append(score)

    # Calculate cost metrics
    cost_metrics = {
        "avg_input_tokens": mean(cost_data["input_tokens"]) if cost_data["input_tokens"] else 0,
        "avg_output_tokens": mean(cost_data["output_tokens"]) if cost_data["output_tokens"] else 0,
    }

    if latencies:
        sorted_lat = sorted(latencies)
        cost_metrics["p50_latency_ms"] = sorted_lat[len(sorted_lat) // 2]
        if len(sorted_lat) >= 20:
            cost_metrics["p95_latency_ms"] = sorted_lat[int(len(sorted_lat) * 0.95)]
        else:
            cost_metrics["p95_latency_ms"] = sorted_lat[-1]  # Use max if < 20 samples
    else:
        cost_metrics["p50_latency_ms"] = 0
        cost_metrics["p95_latency_ms"] = 0

    return scores, matched, cost_metrics

def main():
    base_dir = Path("/Users/mc/dev-projects/crypto-news-aggregator/docs/sprints/sprint-017-tier1-cost-optimization/decisions")
    phase2_dir = base_dir / "phase-2-challenger-runs"
    ref_path = base_dir / "reference_answers.json"
    output_dir = base_dir / "phase-3-scoring"

    # Create output directory
    output_dir.mkdir(exist_ok=True)

    # Load reference answers
    print("Loading reference answers...")
    reference_answers = load_reference_answers(ref_path)

    # Scoring results
    scoring_results = []
    cost_results = []

    models = ["flash", "deepseek", "qwen"]
    operations = ["entity_extraction", "sentiment_analysis", "theme_extraction"]

    print(f"Scoring {len(operations)} operations × {len(models)} models = {len(operations) * len(models)} model-operation pairs\n")

    for operation in operations:
        print(f"\n{'='*60}")
        print(f"Operation: {operation}")
        print(f"{'='*60}")
        threshold = THRESHOLDS[operation]

        for model in models:
            # Load Phase 2 output
            jsonl_file = phase2_dir / f"challenger-{operation}-{model}.jsonl"

            if not jsonl_file.exists():
                print(f"  {model}: FILE NOT FOUND ({jsonl_file})")
                continue

            print(f"  Loading {jsonl_file.name}...")
            phase2_outputs = load_phase2_jsonl(jsonl_file)

            # Get reference answers for this operation
            ref_answers = reference_answers.get(operation, {})

            # Score
            cost_data = {"input_tokens": [], "output_tokens": [], "latencies": []}
            scores, matched, cost_metrics = score_operation(operation, ref_answers, phase2_outputs, cost_data)

            if not scores:
                print(f"    ⚠️  No matching articles found")
                continue

            mean_score = mean(scores)
            status = "PASS" if mean_score >= threshold else "FAIL"
            stdev_score = stdev(scores) if len(scores) > 1 else 0.0

            # Format score based on operation
            if operation == "sentiment_analysis":
                score_display = f"{mean_score*100:.1f}%"
                threshold_display = f"{threshold*100:.0f}%"
            else:
                score_display = f"{mean_score:.4f}"
                threshold_display = f"{threshold:.2f}"

            notes = f"Mean {score_display} (σ={stdev_score:.4f}), {matched} articles"

            print(f"    {model.upper()}: {score_display} vs. {threshold_display} → {status}")
            print(f"      {notes}")

            if cost_metrics["p50_latency_ms"]:
                print(f"      Latency: p50={cost_metrics['p50_latency_ms']:.0f}ms, p95={cost_metrics['p95_latency_ms']:.0f}ms")

            # Calculate cost (in cents per 1M tokens)
            avg_input = cost_metrics.get("avg_input_tokens", 0)
            avg_output = cost_metrics.get("avg_output_tokens", 0)
            pricing = PRICING.get(model, {})
            cost_per_1m = pricing.get("input", 0) * avg_input + pricing.get("output", 0) * avg_output

            # Scoring results row
            scoring_results.append({
                "operation": operation,
                "model": model,
                "samples": matched,
                "score": mean_score,
                "threshold": threshold,
                "status": status,
                "notes": notes,
            })

            # Cost metrics row
            cost_results.append({
                "operation": operation,
                "model": model,
                "avg_tokens": avg_input + avg_output,
                "avg_cost_usd": cost_per_1m / 1_000_000,
                "p50_latency_ms": cost_metrics["p50_latency_ms"],
                "p95_latency_ms": cost_metrics["p95_latency_ms"],
            })

    # Write scoring results CSV
    scoring_csv = output_dir / "scoring_results.csv"
    print(f"\n\nWriting scoring results to {scoring_csv}...")
    with open(scoring_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["operation", "model", "samples", "score", "threshold", "status", "notes"])
        writer.writeheader()
        writer.writerows(scoring_results)
    print(f"✓ {len(scoring_results)} rows written")

    # Write cost metrics CSV
    if cost_results:
        cost_csv = output_dir / "cost_metrics.csv"
        print(f"\nWriting cost metrics to {cost_csv}...")
        with open(cost_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["operation", "model", "avg_tokens", "avg_cost_usd", "p50_latency_ms", "p95_latency_ms"])
            writer.writeheader()
            writer.writerows(cost_results)
        print(f"✓ {len(cost_results)} rows written")

    print(f"\n{'='*60}")
    print("Phase 3 Scoring Complete")
    print(f"{'='*60}")
    print(f"Scoring results: {scoring_csv}")
    print(f"Cost metrics: {cost_csv}")

    # Summary
    pass_count = sum(1 for r in scoring_results if r["status"] == "PASS")
    fail_count = sum(1 for r in scoring_results if r["status"] == "FAIL")
    print(f"\nSummary: {pass_count} PASS, {fail_count} FAIL (of {len(scoring_results)} total)")

if __name__ == "__main__":
    main()
