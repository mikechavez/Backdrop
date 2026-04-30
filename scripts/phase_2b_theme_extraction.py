#!/usr/bin/env python3
"""
FEATURE-054 Phase 2b: Theme Extraction Only (Minimal)
Run Flash, DeepSeek, Qwen on theme_extraction golden set
Uses OpenRouter for API calls
"""

import json
import os
import sys
import time
import re
import html
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

# Constants
CHALLENGER_MODELS = {
    "flash": "google/gemini-2.5-flash",
    "deepseek": "deepseek/deepseek-chat",
    "qwen": "qwen/qwen-plus",
}
OPENROUTER_URL = "https://openrouter.ai/api/v1/messages"
OUTPUT_DIR = Path("/Users/mc/dev-projects/crypto-news-aggregator/docs/sprints/sprint-017-tier1-cost-optimization/decisions/phase-2-challenger-runs")
GOLDEN_SET_PATH = "/Users/mc/dev-projects/crypto-news-aggregator/docs/decisions/msd-flash/golden-set/theme_extraction_golden.json"

def strip_html(text: str) -> str:
    """Strip HTML tags from text"""
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    return text.strip()

def load_golden_set(filepath: str) -> List[Dict]:
    """Load JSONL golden set file"""
    docs = []
    with open(filepath, 'r') as f:
        for line in f:
            if line.strip():
                docs.append(json.loads(line))
    return docs

def call_openrouter(prompt: str, api_key: str, model: str) -> Dict[str, Any]:
    """Make API call to OpenRouter"""
    payload = {
        "model": model,
        "max_tokens": 1024,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}]
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    start_time = time.time()
    try:
        req = urllib.request.Request(
            OPENROUTER_URL,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=30.0) as response:
            data = json.loads(response.read().decode('utf-8'))
            latency_ms = int((time.time() - start_time) * 1000)

            if "error" in data:
                return {
                    "status": "error",
                    "error": str(data.get("error", "Unknown error")),
                    "latency_ms": latency_ms,
                }

            if "content" in data and isinstance(data["content"], list):
                content_text = data["content"][0].get("text", "")
            else:
                return {
                    "status": "error",
                    "error": f"Unexpected response format",
                    "latency_ms": latency_ms,
                }

            return {
                "status": "success",
                "content": content_text,
                "input_tokens": data["usage"]["input_tokens"],
                "output_tokens": data["usage"]["output_tokens"],
                "latency_ms": latency_ms,
            }
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        return {
            "status": "error",
            "error": f"HTTP {e.code}: {error_body[:200]}",
            "latency_ms": int((time.time() - start_time) * 1000),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)[:200],
            "latency_ms": int((time.time() - start_time) * 1000),
        }

def build_theme_extraction_prompt(text: str) -> str:
    """Build theme extraction prompt (corrected: exclude proper nouns)"""
    return f"""Extract the key conceptual themes from the following text. Respond with ONLY a comma-separated list of themes (e.g., 'regulatory pressure, market volatility, institutional adoption'). Do not include any preamble.

Themes should be:
- Conceptual (not entity names): "regulation" not "SEC", "market volatility" not "Bitcoin"
- Exclude proper nouns: No company names, person names, coin names, or protocol names
- Focus on narrative concepts: regulatory, technical, market, adoption, security, legal, etc.

EXAMPLE:
Text: "Goldman Sachs filed for a Bitcoin Premium Income ETF..."

WRONG (includes entity names): Bitcoin, ETF, Goldman Sachs, Institutional Adoption, Covered Call Strategy
CORRECT (conceptual only): ETF, Institutional Adoption
   (Exclude: Bitcoin [cryptocurrency], Goldman Sachs [company], Covered Call Strategy [implementation detail]. Keep: conceptual themes.)

Return ONLY the comma-separated list, no explanation:

{text}"""

def run_phase_2b(api_key: str):
    """Execute Phase 2b: Theme Extraction Only"""

    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=== Phase 2b: Theme Extraction ===")
    docs = load_golden_set(GOLDEN_SET_PATH)
    print(f"Loaded {len(docs)} articles from golden set")

    start_time = time.time()
    results = {
        "phase": "2b",
        "operation": "theme_extraction",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "models": CHALLENGER_MODELS,
        "operation_results": {}
    }

    total_calls = 0
    total_success = 0

    # For each challenger model
    for model_name, model_string in CHALLENGER_MODELS.items():
        print(f"\nRunning {model_name.upper()}...")
        outputs = []
        stats = {"success": 0, "error": 0, "total_input_tokens": 0, "total_output_tokens": 0, "total_latency_ms": 0}

        for i, doc in enumerate(docs):
            text = strip_html(doc.get('text', ''))
            prompt = build_theme_extraction_prompt(text)

            result = call_openrouter(prompt, api_key, model_string)
            total_calls += 1

            output_record = {
                "sample_id": str(doc["_id"]),
                "input_text": text[:500],
                "raw_output": result.get("content", ""),
                "latency_ms": result.get("latency_ms", 0),
                "input_tokens": result.get("input_tokens", 0),
                "output_tokens": result.get("output_tokens", 0),
                "status": result["status"],
            }

            if result["status"] == "success":
                stats["success"] += 1
                stats["total_input_tokens"] += result.get("input_tokens", 0)
                stats["total_output_tokens"] += result.get("output_tokens", 0)
                stats["total_latency_ms"] += result.get("latency_ms", 0)
                total_success += 1
            else:
                stats["error"] += 1
                output_record["error"] = result.get("error", "Unknown error")

            outputs.append(output_record)

            if (i + 1) % 20 == 0:
                print(f"  {i + 1}/100 samples processed")

            time.sleep(0.5)

        # Write outputs
        output_file = OUTPUT_DIR / f"challenger-theme_extraction-{model_name}.jsonl"
        with open(output_file, 'w') as f:
            for record in outputs:
                f.write(json.dumps(record) + '\n')

        stats["samples"] = len(outputs)
        stats["success_rate"] = stats["success"] / len(outputs) * 100
        results["operation_results"][model_name] = stats

        print(f"  ✓ {model_name}: {stats['success']}/{stats['samples']} successful")

    # Summary
    elapsed = time.time() - start_time
    results["summary"] = {
        "total_calls": total_calls,
        "total_success": total_success,
        "success_rate": total_success / total_calls * 100 if total_calls > 0 else 0,
        "elapsed_seconds": elapsed,
    }

    with open(OUTPUT_DIR / "phase-2b-metadata.json", 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n=== Phase 2b Complete ===")
    print(f"Total API calls: {total_calls}")
    print(f"Successful: {total_success}/{total_calls} ({total_success/total_calls*100:.1f}%)")
    print(f"Elapsed: {elapsed:.1f}s ({elapsed/60:.1f}m)")
    print(f"Output dir: {OUTPUT_DIR}")

if __name__ == "__main__":
    api_key = os.getenv("OPENROUTER_API_KEY")
    run_phase_2b(api_key)
