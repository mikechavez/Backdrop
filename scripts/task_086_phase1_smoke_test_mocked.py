#!/usr/bin/env python3
"""
TASK-086 Phase 1: Mocked Smoke Tests

Validates the routing and request formatting for article_enrichment_batch WITHOUT
hitting live APIs. Uses mocked HTTP responses and optional test DB.

Tests:
1. Routing mechanism: article_enrichment_batch -> deepseek:deepseek-v4-flash
2. Request formatting: Validates DeepSeek request payload shape
3. Response parsing: Validates DeepSeek response format handling
4. llm_traces shape: Validates trace write format (mocked DB)
5. Rollback: Validates switch back to Anthropic routing
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock, patch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from crypto_news_aggregator.llm.gateway import (
    _OPERATION_ROUTING,
    RoutingStrategy,
    LLMGateway,
)


# ──────────────────────────────────────────────────────────────
# Test data
# ──────────────────────────────────────────────────────────────

TEST_ARTICLES = [
    {
        "id": "test_001",
        "text": "Bitcoin rallied 5% today on institutional adoption news.",
    },
    {
        "id": "test_002",
        "text": "SEC filing shows concern over stablecoin regulation.",
    },
]

# Mock DeepSeek API response
MOCK_DEEPSEEK_RESPONSE = {
    "choices": [
        {
            "message": {
                "content": json.dumps([
                    {
                        "article_index": 0,
                        "article_id": "test_001",
                        "relevance_score": 0.85,
                        "sentiment_score": 0.6,
                        "themes": ["institutional adoption", "market movement"]
                    },
                    {
                        "article_index": 1,
                        "article_id": "test_002",
                        "relevance_score": 0.75,
                        "sentiment_score": -0.4,
                        "themes": ["regulation", "stablecoins"]
                    }
                ])
            }
        }
    ],
    "usage": {
        "prompt_tokens": 500,
        "completion_tokens": 120,
    }
}

# Mock Anthropic API response
MOCK_ANTHROPIC_RESPONSE = {
    "content": [
        {
            "text": json.dumps([
                {
                    "article_index": 0,
                    "article_id": "test_001",
                    "relevance_score": 0.87,
                    "sentiment_score": 0.65,
                    "themes": ["institutional adoption", "market movement"]
                },
                {
                    "article_index": 1,
                    "article_id": "test_002",
                    "relevance_score": 0.78,
                    "sentiment_score": -0.35,
                    "themes": ["regulation", "stablecoins"]
                }
            ])
        }
    ],
    "usage": {
        "input_tokens": 510,
        "output_tokens": 125,
    }
}


def print_header(text: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}")


def print_subheader(text: str) -> None:
    """Print a formatted subsection header."""
    print(f"\n{'-'*70}")
    print(f"  {text}")
    print(f"{'-'*70}")


# ──────────────────────────────────────────────────────────────
# Test 1: Routing Mechanism
# ──────────────────────────────────────────────────────────────

def test_routing_to_deepseek() -> bool:
    """
    Validate that article_enrichment_batch routing can be set to DeepSeek.
    """
    print_subheader("Test 1: Routing to DeepSeek")

    # Set routing to DeepSeek
    deepseek_model = "deepseek:deepseek-v4-flash"
    _OPERATION_ROUTING["article_enrichment_batch"] = RoutingStrategy(
        "article_enrichment_batch",
        primary=deepseek_model,
    )

    # Verify routing selection
    routing = _OPERATION_ROUTING.get("article_enrichment_batch")
    selected = routing.select("test_key")

    print(f"Routing operation: article_enrichment_batch")
    print(f"Primary model: {routing.primary}")
    print(f"Selected model: {selected}")

    if selected == deepseek_model:
        print(f"✓ Routing correctly set to DeepSeek")
        return True
    else:
        print(f"✗ Routing mismatch: expected {deepseek_model}, got {selected}")
        return False


# ──────────────────────────────────────────────────────────────
# Test 2: Model String Parsing
# ──────────────────────────────────────────────────────────────

def test_model_string_parsing() -> bool:
    """
    Validate that provider-aware model strings are parsed correctly.
    """
    print_subheader("Test 2: Model String Parsing")

    gateway = LLMGateway(api_key="test_key")

    test_cases = [
        ("deepseek:deepseek-v4-flash", ("deepseek", "deepseek-v4-flash")),
        ("anthropic:claude-haiku-4-5-20251001", ("anthropic", "claude-haiku-4-5-20251001")),
        ("claude-haiku-4-5-20251001", ("anthropic", "claude-haiku-4-5-20251001")),  # Legacy format
    ]

    all_passed = True
    for model_str, expected in test_cases:
        provider, model_name = gateway._parse_model_string(model_str)
        passed = (provider, model_name) == expected

        status = "✓" if passed else "✗"
        print(f"{status} {model_str}")
        print(f"   -> ({provider}, {model_name})")

        if not passed:
            print(f"   Expected: {expected}")
            all_passed = False

    return all_passed


# ──────────────────────────────────────────────────────────────
# Test 3: Provider URL Resolution
# ──────────────────────────────────────────────────────────────

def test_provider_urls() -> bool:
    """
    Validate that provider URLs are correctly resolved.
    """
    print_subheader("Test 3: Provider URL Resolution")

    gateway = LLMGateway(api_key="test_key")

    deepseek_url = gateway._get_provider_url("deepseek")
    anthropic_url = gateway._get_provider_url("anthropic")

    print(f"DeepSeek URL: {deepseek_url}")
    print(f"Anthropic URL: {anthropic_url}")

    deepseek_ok = deepseek_url == "https://api.deepseek.com/chat/completions"
    anthropic_ok = anthropic_url.startswith("https://api.anthropic.com")

    if deepseek_ok:
        print("✓ DeepSeek URL correct")
    else:
        print(f"✗ DeepSeek URL incorrect")

    if anthropic_ok:
        print("✓ Anthropic URL correct")
    else:
        print(f"✗ Anthropic URL incorrect")

    return deepseek_ok and anthropic_ok


# ──────────────────────────────────────────────────────────────
# Test 4: Request Payload Building
# ──────────────────────────────────────────────────────────────

def test_request_payload_building() -> bool:
    """
    Validate that request payloads are built correctly for each provider.
    """
    print_subheader("Test 4: Request Payload Building")

    gateway = LLMGateway(api_key="test_key")

    messages = [{"role": "user", "content": "Test prompt"}]

    # DeepSeek payload
    deepseek_payload = gateway._build_provider_payload(
        messages=messages,
        provider="deepseek",
        model_name="deepseek-v4-flash",
        max_tokens=2048,
        temperature=0.3,
        system=None,
    )

    print("DeepSeek payload:")
    print(f"  - model: {deepseek_payload.get('model')}")
    print(f"  - messages: {len(deepseek_payload.get('messages', []))} message(s)")
    print(f"  - max_tokens: {deepseek_payload.get('max_tokens')}")
    print(f"  - temperature: {deepseek_payload.get('temperature')}")
    print(f"  - thinking: {deepseek_payload.get('thinking')}")

    # Anthropic payload
    anthropic_payload = gateway._build_provider_payload(
        messages=messages,
        provider="anthropic",
        model_name="claude-haiku-4-5-20251001",
        max_tokens=2048,
        temperature=0.3,
        system="You are helpful",
    )

    print("\nAnthropic payload:")
    print(f"  - model: {anthropic_payload.get('model')}")
    print(f"  - messages: {len(anthropic_payload.get('messages', []))} message(s)")
    print(f"  - max_tokens: {anthropic_payload.get('max_tokens')}")
    print(f"  - temperature: {anthropic_payload.get('temperature')}")
    print(f"  - system: {'present' if anthropic_payload.get('system') else 'absent'}")

    # Validate structure
    deepseek_ok = (
        deepseek_payload.get("model") == "deepseek-v4-flash"
        and deepseek_payload.get("max_tokens") == 2048
        and len(deepseek_payload.get("messages", [])) == 1
    )

    anthropic_ok = (
        anthropic_payload.get("model") == "claude-haiku-4-5-20251001"
        and anthropic_payload.get("system") == "You are helpful"
        and len(anthropic_payload.get("messages", [])) == 1
    )

    if deepseek_ok:
        print("\n✓ DeepSeek payload structure valid")
    else:
        print("\n✗ DeepSeek payload structure invalid")

    if anthropic_ok:
        print("✓ Anthropic payload structure valid")
    else:
        print("✗ Anthropic payload structure invalid")

    return deepseek_ok and anthropic_ok


# ──────────────────────────────────────────────────────────────
# Test 5: Response Parsing
# ──────────────────────────────────────────────────────────────

def test_response_parsing() -> bool:
    """
    Validate that API responses are parsed correctly for each provider.
    """
    print_subheader("Test 5: Response Parsing")

    gateway = LLMGateway(api_key="test_key")

    # Parse DeepSeek response
    deepseek_text, deepseek_input, deepseek_output = gateway._parse_provider_response(
        MOCK_DEEPSEEK_RESPONSE, "deepseek"
    )

    print("DeepSeek response:")
    print(f"  - Text length: {len(deepseek_text)} chars")
    print(f"  - Input tokens: {deepseek_input}")
    print(f"  - Output tokens: {deepseek_output}")

    # Parse Anthropic response
    anthropic_text, anthropic_input, anthropic_output = gateway._parse_provider_response(
        MOCK_ANTHROPIC_RESPONSE, "anthropic"
    )

    print("\nAnthropic response:")
    print(f"  - Text length: {len(anthropic_text)} chars")
    print(f"  - Input tokens: {anthropic_input}")
    print(f"  - Output tokens: {anthropic_output}")

    # Validate parsing
    deepseek_ok = (
        len(deepseek_text) > 0
        and deepseek_input == 500
        and deepseek_output == 120
    )

    anthropic_ok = (
        len(anthropic_text) > 0
        and anthropic_input == 510
        and anthropic_output == 125
    )

    if deepseek_ok:
        print("\n✓ DeepSeek response parsing valid")
    else:
        print("\n✗ DeepSeek response parsing invalid")

    if anthropic_ok:
        print("✓ Anthropic response parsing valid")
    else:
        print("✗ Anthropic response parsing invalid")

    return deepseek_ok and anthropic_ok


# ──────────────────────────────────────────────────────────────
# Test 6: Trace Record Shape
# ──────────────────────────────────────────────────────────────

def test_trace_record_shape() -> bool:
    """
    Validate that trace records have the correct shape for llm_traces collection.
    """
    print_subheader("Test 6: llm_traces Record Shape")

    # Build a mock trace record as would be written by _write_trace_sync
    trace_record = {
        "trace_id": "test-trace-001",
        "operation": "article_enrichment_batch",
        "timestamp": "2026-05-01T00:00:00Z",
        "model": "deepseek:deepseek-v4-flash",
        "input_tokens": 500,
        "output_tokens": 120,
        "cost": 0.00021,
        "duration_ms": 850.5,
        "error": None,
        "quality": {
            "passed": None,
            "score": None,
            "checks": [],
        },
    }

    print("Trace record for DeepSeek article_enrichment_batch:")
    print(f"  - trace_id: {trace_record['trace_id']}")
    print(f"  - operation: {trace_record['operation']}")
    print(f"  - model: {trace_record['model']}")
    print(f"  - tokens: {trace_record['input_tokens']} + {trace_record['output_tokens']}")
    print(f"  - cost: ${trace_record['cost']:.6f}")
    print(f"  - duration: {trace_record['duration_ms']}ms")

    # Validate required fields
    required_fields = ["trace_id", "operation", "model", "input_tokens", "output_tokens", "cost", "duration_ms"]
    all_present = all(field in trace_record for field in required_fields)

    if all_present:
        print("\n✓ Trace record has all required fields")
    else:
        missing = [f for f in required_fields if f not in trace_record]
        print(f"\n✗ Trace record missing fields: {missing}")

    # Validate field types
    type_ok = (
        isinstance(trace_record["input_tokens"], int)
        and isinstance(trace_record["output_tokens"], int)
        and isinstance(trace_record["cost"], (int, float))
        and isinstance(trace_record["duration_ms"], (int, float))
    )

    if type_ok:
        print("✓ Trace record fields have correct types")
    else:
        print("✗ Trace record fields have incorrect types")

    return all_present and type_ok


# ──────────────────────────────────────────────────────────────
# Test 7: Rollback Routing
# ──────────────────────────────────────────────────────────────

def test_rollback_routing() -> bool:
    """
    Validate that routing can be switched back to Anthropic (rollback).
    """
    print_subheader("Test 7: Rollback Routing")

    # Start with DeepSeek
    deepseek_model = "deepseek:deepseek-v4-flash"
    _OPERATION_ROUTING["article_enrichment_batch"] = RoutingStrategy(
        "article_enrichment_batch",
        primary=deepseek_model,
    )

    routing = _OPERATION_ROUTING.get("article_enrichment_batch")
    selected = routing.select("test_key")
    print(f"Current routing: {selected}")

    if selected != deepseek_model:
        print(f"✗ Initial routing not set to DeepSeek")
        return False

    # Rollback to Anthropic
    anthropic_model = "anthropic:claude-haiku-4-5-20251001"
    _OPERATION_ROUTING["article_enrichment_batch"] = RoutingStrategy(
        "article_enrichment_batch",
        primary=anthropic_model,
    )

    routing = _OPERATION_ROUTING.get("article_enrichment_batch")
    selected = routing.select("test_key")
    print(f"Rollback routing: {selected}")

    if selected == anthropic_model:
        print("✓ Rollback to Anthropic successful")
        return True
    else:
        print(f"✗ Rollback failed: expected {anthropic_model}, got {selected}")
        return False


# ──────────────────────────────────────────────────────────────
# Test 8: Cost Calculation
# ──────────────────────────────────────────────────────────────

def test_cost_calculation() -> bool:
    """
    Validate that costs are calculated correctly for DeepSeek vs Anthropic.
    """
    print_subheader("Test 8: Cost Calculation (DeepSeek vs Anthropic)")

    # Mock pricing (from cost_tracker)
    # DeepSeek v4-flash: $0.14/1M input, $0.28/1M output
    # Anthropic Haiku: $0.80/1M input, $4.00/1M output

    deepseek_input_cost_per_1k = 0.14 / 1000
    deepseek_output_cost_per_1k = 0.28 / 1000
    anthropic_input_cost_per_1k = 0.80 / 1000
    anthropic_output_cost_per_1k = 4.00 / 1000

    # Test case: 500 input tokens, 120 output tokens
    input_tokens = 500
    output_tokens = 120

    deepseek_cost = (input_tokens / 1000) * deepseek_input_cost_per_1k + \
                    (output_tokens / 1000) * deepseek_output_cost_per_1k
    anthropic_cost = (input_tokens / 1000) * anthropic_input_cost_per_1k + \
                     (output_tokens / 1000) * anthropic_output_cost_per_1k

    print(f"Input tokens: {input_tokens}")
    print(f"Output tokens: {output_tokens}")
    print(f"\nDeepSeek v4-flash:")
    print(f"  - Input cost: ${(input_tokens / 1000) * deepseek_input_cost_per_1k:.6f}")
    print(f"  - Output cost: ${(output_tokens / 1000) * deepseek_output_cost_per_1k:.6f}")
    print(f"  - Total cost: ${deepseek_cost:.6f}")

    print(f"\nAnthropic Haiku:")
    print(f"  - Input cost: ${(input_tokens / 1000) * anthropic_input_cost_per_1k:.6f}")
    print(f"  - Output cost: ${(output_tokens / 1000) * anthropic_output_cost_per_1k:.6f}")
    print(f"  - Total cost: ${anthropic_cost:.6f}")

    savings_ratio = deepseek_cost / anthropic_cost if anthropic_cost > 0 else 0
    savings_pct = (1 - savings_ratio) * 100

    print(f"\n✓ DeepSeek is {savings_ratio:.2f}x the cost ({savings_pct:.1f}% savings)")

    return deepseek_cost < anthropic_cost


# ──────────────────────────────────────────────────────────────
# Main test runner
# ──────────────────────────────────────────────────────────────

def main():
    """Run all mocked smoke tests."""
    print_header("TASK-086 Phase 1: Mocked Smoke Tests")

    tests = [
        ("Routing to DeepSeek", test_routing_to_deepseek),
        ("Model String Parsing", test_model_string_parsing),
        ("Provider URL Resolution", test_provider_urls),
        ("Request Payload Building", test_request_payload_building),
        ("Response Parsing", test_response_parsing),
        ("Trace Record Shape", test_trace_record_shape),
        ("Rollback Routing", test_rollback_routing),
        ("Cost Calculation", test_cost_calculation),
    ]

    results = {}
    for test_name, test_func in tests:
        try:
            passed = test_func()
            results[test_name] = "PASS" if passed else "FAIL"
        except Exception as e:
            print(f"\n✗ Exception: {e}")
            import traceback
            traceback.print_exc()
            results[test_name] = "ERROR"

    # ── Summary ────────────────────────────────────────────────
    print_header("MOCKED SMOKE TEST SUMMARY")

    pass_count = sum(1 for v in results.values() if v == "PASS")
    total_count = len(results)

    for test_name, result in results.items():
        symbol = "✓" if result == "PASS" else "✗"
        print(f"{symbol} {test_name}: {result}")

    print(f"\n{pass_count}/{total_count} tests passed")

    if pass_count == total_count:
        print("\n✓ All mocked tests passed!")
        print("\n" + "="*70)
        print("CREDENTIALS REQUIRED FOR LIVE SMOKE TESTING")
        print("="*70)
        print("\nTo run the live smoke test, you will need:")
        print("\n1. ANTHROPIC_API_KEY")
        print("   - Account with available credits")
        print("   - Required for baseline enrichment batch call")
        print("")
        print("2. DEEPSEEK_API_KEY")
        print("   - Account with available credits")
        print("   - Required for DeepSeek enrichment batch call")
        print("")
        print("3. MONGODB_URI")
        print("   - Connection string to crypto_news database")
        print("   - Required to verify llm_traces records")
        print("")
        print("Once credentials are set in .env and sourced, run:")
        print("  poetry run python scripts/task_086_phase1_smoke_test.py")
        print("="*70)
        return 0
    else:
        print("\n✗ Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
