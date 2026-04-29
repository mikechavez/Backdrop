#!/usr/bin/env python3
"""
FEATURE-054 Phase 1: Corrected Baselines
Run Haiku with corrected prompts against Tier 1 golden sets (100 samples per operation)
Uses OpenRouter for all API calls (consistent with FEATURE-053 Phase 3)
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
HAIKU_MODEL = "anthropic/claude-haiku-4-5-20251001"
OPENROUTER_URL = "https://openrouter.ai/api/v1/messages"
OUTPUT_DIR = Path("/Users/mc/dev-projects/crypto-news-aggregator/docs/sprints/sprint-017-tier1-cost-optimization/decisions/phase-1-baselines")
GOLDEN_SETS = {
    "entity_extraction": "/Users/mc/dev-projects/crypto-news-aggregator/docs/decisions/msd-flash/golden-set/entity_extraction_golden.json",
    "sentiment_analysis": "/Users/mc/dev-projects/crypto-news-aggregator/docs/decisions/msd-flash/golden-set/sentiment_analysis_golden.json",
    "theme_extraction": "/Users/mc/dev-projects/crypto-news-aggregator/docs/decisions/msd-flash/golden-set/theme_extraction_golden.json",
}

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

def call_openrouter(prompt: str, api_key: str, operation: str) -> Dict[str, Any]:
    """Make API call to Haiku via OpenRouter"""
    payload = {
        "model": HAIKU_MODEL,
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

            # OpenRouter returns content as array, not choices
            if "content" in data and isinstance(data["content"], list):
                content_text = data["content"][0].get("text", "")
            else:
                return {
                    "status": "error",
                    "error": f"Unexpected response format: {str(data)[:200]}",
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
            "error": f"HTTP {e.code}: {error_body}",
            "latency_ms": int((time.time() - start_time) * 1000),
        }
    except KeyError as e:
        return {
            "status": "error",
            "error": f"KeyError: {str(e)} in response",
            "latency_ms": int((time.time() - start_time) * 1000),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "latency_ms": int((time.time() - start_time) * 1000),
        }

def build_entity_extraction_prompt(article: Dict) -> str:
    """Build entity extraction prompt (corrected: relevance-weighted)"""
    text = article.get('text', '')[:2000]
    title = article.get('title', '')

    return f"""Extract cryptocurrency-related entities relevant to the article's primary narrative.

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

Only extract entities that are relevant to the article's primary narrative. Focus on primary entities, not every mention."""

def build_sentiment_analysis_prompt(text: str) -> str:
    """Build sentiment analysis prompt (corrected: explicit neutral definition)"""
    return f"""Analyze the sentiment of this crypto text. Return ONLY a single number from -1.0 (very bearish) to 1.0 (very bullish). Do not include any explanation or additional text. Just the number.

Sentiment Scale:
- Bullish (0.3 to 1.0): Article emphasizes gains, positive developments, bullish signals, or constructive news
- Bearish (-1.0 to -0.3): Article emphasizes losses, negative events, regulatory concerns, or destructive developments
- Neutral (-0.3 to 0.3): Factual reporting without strong directional bias. Includes crime/legal/regulatory articles where the event is negative but the framing is factual (e.g., "CFTC filed lawsuit" without inflammatory language or speculation)

EXAMPLE:
Text: "Jean-Didier Berger said at Paris Blockchain Week that France is preparing new steps to protect crypto holders as wrench attacks and kidnappings keep mounting."

WRONG (misclassified as negative): -0.4
CORRECT (neutral): -0.1
   (Reports negative event [kidnappings] factually without inflammatory language or speculation. Focus is on preparedness/protection, not loss/harm.)

Return ONLY the number, no explanation:

{text}"""

def build_theme_extraction_prompt(texts: List[str]) -> str:
    """Build theme extraction prompt (corrected: exclude proper nouns)"""
    combined_texts = "\n".join(texts)

    return f"""Extract the key conceptual themes from the following texts. Respond with ONLY a comma-separated list of themes (e.g., 'regulatory pressure, market volatility, institutional adoption'). Do not include any preamble.

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

Texts:
{combined_texts}"""

def run_phase_1(api_key: str):
    """Execute Phase 1: Corrected Baselines"""

    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    start_time = time.time()
    results = {
        "phase": 1,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "model": HAIKU_MODEL,
        "operations": {}
    }

    total_calls = 0
    total_success = 0

    # ENTITY EXTRACTION
    print("\n=== Phase 1: Entity Extraction ===")
    docs = load_golden_set(GOLDEN_SETS["entity_extraction"])
    entity_outputs = []
    entity_stats = {"success": 0, "error": 0, "total_input_tokens": 0, "total_output_tokens": 0, "total_latency_ms": 0}

    for i, doc in enumerate(docs):
        text = strip_html(doc.get('text', ''))
        prompt = build_entity_extraction_prompt({"title": doc.get('title', ''), "text": text})

        result = call_openrouter(prompt, api_key, "entity_extraction")
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
            entity_stats["success"] += 1
            entity_stats["total_input_tokens"] += result.get("input_tokens", 0)
            entity_stats["total_output_tokens"] += result.get("output_tokens", 0)
            entity_stats["total_latency_ms"] += result.get("latency_ms", 0)
            total_success += 1
        else:
            entity_stats["error"] += 1
            output_record["error"] = result.get("error", "Unknown error")

        entity_outputs.append(output_record)

        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/100 samples processed")

        time.sleep(0.5)

    with open(OUTPUT_DIR / "baseline-entity_extraction.jsonl", 'w') as f:
        for record in entity_outputs:
            f.write(json.dumps(record) + '\n')

    entity_stats["samples"] = len(entity_outputs)
    entity_stats["success_rate"] = entity_stats["success"] / len(entity_outputs) * 100
    results["operations"]["entity_extraction"] = entity_stats
    print(f"✓ Entity extraction: {entity_stats['success']}/{entity_stats['samples']} successful")

    # SENTIMENT ANALYSIS
    print("\n=== Phase 1: Sentiment Analysis ===")
    docs = load_golden_set(GOLDEN_SETS["sentiment_analysis"])
    sentiment_outputs = []
    sentiment_stats = {"success": 0, "error": 0, "total_input_tokens": 0, "total_output_tokens": 0, "total_latency_ms": 0}

    for i, doc in enumerate(docs):
        text = strip_html(doc.get('text', ''))
        prompt = build_sentiment_analysis_prompt(text)

        result = call_openrouter(prompt, api_key, "sentiment_analysis")
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
            sentiment_stats["success"] += 1
            sentiment_stats["total_input_tokens"] += result.get("input_tokens", 0)
            sentiment_stats["total_output_tokens"] += result.get("output_tokens", 0)
            sentiment_stats["total_latency_ms"] += result.get("latency_ms", 0)
            total_success += 1
        else:
            sentiment_stats["error"] += 1
            output_record["error"] = result.get("error", "Unknown error")

        sentiment_outputs.append(output_record)

        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/100 samples processed")

        time.sleep(0.5)

    with open(OUTPUT_DIR / "baseline-sentiment_analysis.jsonl", 'w') as f:
        for record in sentiment_outputs:
            f.write(json.dumps(record) + '\n')

    sentiment_stats["samples"] = len(sentiment_outputs)
    sentiment_stats["success_rate"] = sentiment_stats["success"] / len(sentiment_outputs) * 100
    results["operations"]["sentiment_analysis"] = sentiment_stats
    print(f"✓ Sentiment analysis: {sentiment_stats['success']}/{sentiment_stats['samples']} successful")

    # THEME EXTRACTION
    print("\n=== Phase 1: Theme Extraction ===")
    docs = load_golden_set(GOLDEN_SETS["theme_extraction"])
    theme_outputs = []
    theme_stats = {"success": 0, "error": 0, "total_input_tokens": 0, "total_output_tokens": 0, "total_latency_ms": 0}

    for i, doc in enumerate(docs):
        text = strip_html(doc.get('text', ''))
        prompt = build_theme_extraction_prompt([text])

        result = call_openrouter(prompt, api_key, "theme_extraction")
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
            theme_stats["success"] += 1
            theme_stats["total_input_tokens"] += result.get("input_tokens", 0)
            theme_stats["total_output_tokens"] += result.get("output_tokens", 0)
            theme_stats["total_latency_ms"] += result.get("latency_ms", 0)
            total_success += 1
        else:
            theme_stats["error"] += 1
            output_record["error"] = result.get("error", "Unknown error")

        theme_outputs.append(output_record)

        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/100 samples processed")

        time.sleep(0.5)

    with open(OUTPUT_DIR / "baseline-theme_extraction.jsonl", 'w') as f:
        for record in theme_outputs:
            f.write(json.dumps(record) + '\n')

    theme_stats["samples"] = len(theme_outputs)
    theme_stats["success_rate"] = theme_stats["success"] / len(theme_outputs) * 100
    results["operations"]["theme_extraction"] = theme_stats
    print(f"✓ Theme extraction: {theme_stats['success']}/{theme_stats['samples']} successful")

    # Summary
    elapsed = time.time() - start_time
    results["summary"] = {
        "total_calls": total_calls,
        "total_success": total_success,
        "success_rate": total_success / total_calls * 100,
        "elapsed_seconds": elapsed,
    }

    with open(OUTPUT_DIR / "phase-1-metadata.json", 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n=== Phase 1 Complete ===")
    print(f"Total API calls: {total_calls}")
    print(f"Successful: {total_success}/{total_calls} ({total_success/total_calls*100:.1f}%)")
    print(f"Elapsed: {elapsed:.1f}s")
    print(f"Output dir: {OUTPUT_DIR}")

if __name__ == "__main__":
    api_key = os.getenv("OPENROUTER_API_KEY")
    run_phase_1(api_key)
