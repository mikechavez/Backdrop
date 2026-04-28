#!/usr/bin/env python3
"""
Phase 3: Challenger Model Runs
Run Gemini Flash, DeepSeek, and Qwen against the golden sets via OpenRouter.
"""

import json
import sys
import os
import time
import re
from pathlib import Path
from typing import Any
import urllib.request
import urllib.error
from html import unescape
from datetime import datetime


# Production prompts extracted from codebase
PROMPTS = {
    "entity_extraction": """Extract cryptocurrency-related entities from this article.

Title: {title}
Text: {text}

Return a JSON object with this structure:
{{
  "entities": [
    {{
      "name": "Bitcoin",
      "type": "cryptocurrency",
      "confidence": 0.95,
      "is_primary": true
    }}
  ]
}}

Entity types: cryptocurrency, protocol, company, person, event, regulation
Only include entities mentioned in the text. Normalize crypto names (BTC → Bitcoin).""",

    "sentiment_analysis": """Analyze the sentiment of this crypto text. Return ONLY a single number from -1.0 (very bearish) to 1.0 (very bullish). Do not include any explanation or additional text. Just the number:

{text}""",

    "theme_extraction": """Extract the key crypto themes from the following texts. Respond with ONLY a comma-separated list of keywords (e.g., 'Bitcoin, DeFi, Regulation'). Do not include any preamble.

Texts:
{text}"""
}

# Locked model variants from FEATURE-053
MODELS = {
    "baseline": "anthropic/claude-haiku-4-5-20251001",
    "flash": "google/gemini-2.5-flash",
    "deepseek": "deepseek/deepseek-chat",
    "qwen": "qwen/qwen-plus",
}


def strip_html(html: str) -> str:
    """Strip HTML tags from text."""
    text = re.sub(r"<[^>]*>", "", html)
    text = unescape(text)
    text = text.strip()
    return text


def call_openrouter(
    prompt: str,
    model: str,
    max_tokens: int = 1000,
    timeout: int = 30,
) -> dict[str, Any]:
    """
    Call OpenRouter API.

    Returns:
        {
            "content": str,
            "input_tokens": int,
            "output_tokens": int,
            "latency_ms": int,
            "error": str or None
        }
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return {
            "content": None,
            "input_tokens": None,
            "output_tokens": None,
            "latency_ms": None,
            "error": "OPENROUTER_API_KEY not set",
        }

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }

    start = time.time()
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            elapsed_ms = int((time.time() - start) * 1000)
            data = json.loads(response.read().decode("utf-8"))
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            usage = data.get("usage", {})

            return {
                "content": content,
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
                "latency_ms": elapsed_ms,
                "error": None,
            }
    except urllib.error.HTTPError as e:
        elapsed_ms = int((time.time() - start) * 1000)
        error_body = e.read().decode("utf-8")
        return {
            "content": None,
            "input_tokens": None,
            "output_tokens": None,
            "latency_ms": elapsed_ms,
            "error": f"HTTP {e.code}: {error_body[:200]}",
        }
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return {
            "content": None,
            "input_tokens": None,
            "output_tokens": None,
            "latency_ms": elapsed_ms,
            "error": str(e),
        }


def build_prompt(operation: str, sample: dict) -> str:
    """Build prompt for the operation."""
    text = sample["text"]

    if operation == "entity_extraction":
        return PROMPTS["entity_extraction"].format(
            title=sample.get("title", ""),
            text=text,
        )
    elif operation == "sentiment_analysis":
        return PROMPTS["sentiment_analysis"].format(text=text)
    elif operation == "theme_extraction":
        return PROMPTS["theme_extraction"].format(text=text)
    else:
        raise ValueError(f"Unknown operation: {operation}")


def load_baseline_samples(operation: str, input_dir: Path) -> list[dict]:
    """Load baseline samples from Phase 2 output."""
    file_path = input_dir / f"baseline-{operation}.jsonl"

    if not file_path.exists():
        print(f"✗ Not found: {file_path}")
        sys.exit(1)

    samples = []
    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))

    return samples


def process_operation(
    operation: str,
    input_dir: Path,
    output_dir: Path,
    models_to_run: list[str],
) -> None:
    """Process one operation against all challenger models."""
    print(f"\n[Phase 3] Processing {operation}")

    baseline_samples = load_baseline_samples(operation, input_dir)
    print(f"✓ Loaded {len(baseline_samples)} baseline samples")

    # Run each challenger model
    for model_key in models_to_run:
        if model_key == "baseline":
            continue  # Skip baseline, already extracted in Phase 2

        model_string = MODELS[model_key]
        print(f"\n  Running {model_key} ({model_string})...")

        output_file = output_dir / f"challenger-{operation}-{model_key}.jsonl"

        results = []
        errors = 0

        for i, sample in enumerate(baseline_samples):
            prompt = build_prompt(operation, sample)

            # Call OpenRouter
            api_response = call_openrouter(prompt, model_string)

            result = {
                "sample_id": sample["sample_id"],
                "article_id": sample["article_id"],
                "model": model_key,
                "model_string": model_string,
                "output": api_response["content"],
                "input_tokens": api_response["input_tokens"],
                "output_tokens": api_response["output_tokens"],
                "latency_ms": api_response["latency_ms"],
                "error": api_response["error"],
                "timestamp": datetime.now().isoformat(),
            }

            results.append(result)

            if api_response["error"]:
                errors += 1

            # Progress indicator
            if (i + 1) % 10 == 0:
                print(f"    {i + 1}/{len(baseline_samples)}...")

            # Rate limit: small delay between calls
            time.sleep(0.5)

        # Write results
        with open(output_file, "w") as f:
            for result in results:
                f.write(json.dumps(result) + "\n")

        print(f"  ✓ {model_key}: {len(results) - errors}/{len(results)} successful")
        if errors > 0:
            print(f"    ⚠ {errors} errors")


def main():
    """Main entry point."""
    # Check API key
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("\n✗ OPENROUTER_API_KEY not set")
        print("  Load it with: source scripts/load_keys.sh")
        sys.exit(1)

    input_dir = Path(
        "/Users/mc/dev-projects/crypto-news-aggregator/docs/decisions/msd-flash/runs/2026-04-28"
    )
    output_dir = input_dir

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    operations = ["entity_extraction", "sentiment_analysis", "theme_extraction"]
    models_to_run = ["flash", "deepseek", "qwen"]

    print("\n=== FEATURE-053: Phase 3 — Challenger Model Runs ===")
    print(f"Input directory: {input_dir}")
    print(f"Output directory: {output_dir}")
    print(f"Models to run: {', '.join(models_to_run)}")

    for operation in operations:
        process_operation(operation, input_dir, output_dir, models_to_run)

    print("\n=== Phase 3 Complete ===")
    print(f"All challenger outputs written to: {output_dir}")
    print("\nNext: Phase 4 — Output Normalization")


if __name__ == "__main__":
    main()
