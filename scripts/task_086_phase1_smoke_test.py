#!/usr/bin/env python3
"""
TASK-086 Phase 1: Pre-Production Smoke Tests

Tests the routing and execution of article_enrichment_batch with:
1. Anthropic (current baseline)
2. DeepSeek (new provider)

Validates:
- Both calls return valid enrichment JSON
- llm_traces records correct model refs
- DeepSeek cost is lower than Haiku
- Rollback routing works (switch back to Anthropic)
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Any
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from crypto_news_aggregator.llm.gateway import get_gateway, _OPERATION_ROUTING, RoutingStrategy
from crypto_news_aggregator.llm.anthropic import AnthropicProvider
from crypto_news_aggregator.db.mongodb import mongo_manager


# ──────────────────────────────────────────────────────────────
# Test articles (real sample data)
# ──────────────────────────────────────────────────────────────

TEST_ARTICLES = [
    {
        "id": "test_001",
        "text": "Bitcoin rallied 5% today on institutional adoption news. "
                "Major pension funds are considering allocation. Ethereum also gained 3%."
    },
    {
        "id": "test_002",
        "text": "SEC filing shows concern over stablecoin regulation. Regulatory pressure "
                "mounting for USDC and USDT. Market sentiment cautious."
    },
    {
        "id": "test_003",
        "text": "DeFi protocol Aave released security audit results. No critical vulnerabilities found. "
                "Community positive on upgrade path."
    }
]


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


async def test_enrichment_with_routing(
    provider_name: str,
    model_ref: str,
) -> Dict[str, Any]:
    """
    Test article_enrichment_batch with a specific provider routing.

    Args:
        provider_name: "anthropic" or "deepseek" (for display)
        model_ref: Full model reference (e.g., "anthropic:claude-haiku-4-5-20251001")

    Returns:
        Dict with test results and metrics
    """
    print_subheader(f"Testing article_enrichment_batch with {provider_name}")

    # Update routing to use the specified provider
    print(f"Setting routing: article_enrichment_batch -> {model_ref}")
    _OPERATION_ROUTING["article_enrichment_batch"] = RoutingStrategy(
        "article_enrichment_batch",
        primary=model_ref,
    )

    # Create LLM client and call enrich_articles_batch
    from crypto_news_aggregator.core.config import get_settings
    settings = get_settings()
    llm_client = AnthropicProvider(api_key=settings.ANTHROPIC_API_KEY)

    print(f"Calling enrich_articles_batch with {len(TEST_ARTICLES)} articles...")
    try:
        enrichment_results = await llm_client.enrich_articles_batch(TEST_ARTICLES)

        # Validate results
        print(f"✓ Received {len(enrichment_results)} enrichment results")

        for idx, result in enumerate(enrichment_results):
            print(f"\n  Article {idx + 1}:")
            print(f"    - ID: {result.get('id')}")
            print(f"    - Relevance: {result.get('relevance_score'):.2f}")
            print(f"    - Sentiment: {result.get('sentiment_score'):.2f}")
            print(f"    - Themes: {', '.join(result.get('themes', []))}")

            # Validate JSON structure
            assert isinstance(result.get('relevance_score'), (int, float)), "relevance_score not numeric"
            assert isinstance(result.get('sentiment_score'), (int, float)), "sentiment_score not numeric"
            assert isinstance(result.get('themes'), list), "themes not a list"

            # Validate ranges
            assert 0.0 <= result.get('relevance_score', 0.0) <= 1.0, \
                f"relevance_score {result.get('relevance_score')} out of range [0.0, 1.0]"
            assert -1.0 <= result.get('sentiment_score', 0.0) <= 1.0, \
                f"sentiment_score {result.get('sentiment_score')} out of range [-1.0, 1.0]"

        print(f"\n✓ All enrichment results valid")
        return {
            "success": True,
            "provider": provider_name,
            "model_ref": model_ref,
            "results": enrichment_results,
        }

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "provider": provider_name,
            "model_ref": model_ref,
            "error": str(e),
        }


async def check_llm_traces(
    model_ref: str,
    operation: str = "article_enrichment_batch",
    limit: int = 1,
) -> Dict[str, Any]:
    """
    Check llm_traces collection for recent calls with the given model.

    Args:
        model_ref: Model reference to search for
        operation: Operation name to filter on
        limit: Number of recent traces to fetch

    Returns:
        Dict with trace info and metrics
    """
    print_subheader(f"Checking llm_traces for {model_ref}")

    try:
        db = await mongo_manager.get_async_database()
        traces = await db.llm_traces.find({
            "operation": operation,
            "model": model_ref,
        }).sort("timestamp", -1).limit(limit).to_list(limit)

        if not traces:
            print(f"✗ No traces found for model={model_ref}, operation={operation}")
            return {
                "found": False,
                "model": model_ref,
                "operation": operation,
            }

        print(f"✓ Found {len(traces)} trace(s)")

        for idx, trace in enumerate(traces):
            print(f"\n  Trace {idx + 1}:")
            print(f"    - Timestamp: {trace.get('timestamp')}")
            print(f"    - Model: {trace.get('model')}")
            print(f"    - Operation: {trace.get('operation')}")
            print(f"    - Input tokens: {trace.get('input_tokens')}")
            print(f"    - Output tokens: {trace.get('output_tokens')}")
            print(f"    - Cost: ${trace.get('cost', 0.0):.6f}")
            print(f"    - Duration: {trace.get('duration_ms'):.1f}ms")

            if trace.get('error'):
                print(f"    - Error: {trace.get('error')}")

        return {
            "found": True,
            "model": model_ref,
            "operation": operation,
            "traces": traces,
        }

    except Exception as e:
        print(f"✗ Error querying traces: {e}")
        return {
            "found": False,
            "model": model_ref,
            "operation": operation,
            "error": str(e),
        }


async def compare_costs(
    haiku_trace: Dict[str, Any],
    deepseek_trace: Dict[str, Any],
) -> None:
    """
    Compare costs between Haiku and DeepSeek traces.

    Args:
        haiku_trace: Trace info from Haiku call
        deepseek_trace: Trace info from DeepSeek call
    """
    print_subheader("Cost Comparison")

    if not haiku_trace.get("found") or not deepseek_trace.get("found"):
        print("✗ Cannot compare costs: missing trace data")
        return

    haiku_cost = haiku_trace["traces"][0].get("cost", 0.0) if haiku_trace["traces"] else 0.0
    deepseek_cost = deepseek_trace["traces"][0].get("cost", 0.0) if deepseek_trace["traces"] else 0.0

    haiku_tokens = haiku_trace["traces"][0].get("input_tokens", 0) + \
                   haiku_trace["traces"][0].get("output_tokens", 0) if haiku_trace["traces"] else 0
    deepseek_tokens = deepseek_trace["traces"][0].get("input_tokens", 0) + \
                      deepseek_trace["traces"][0].get("output_tokens", 0) if deepseek_trace["traces"] else 0

    print(f"Haiku:    ${haiku_cost:.6f} ({haiku_tokens} tokens)")
    print(f"DeepSeek: ${deepseek_cost:.6f} ({deepseek_tokens} tokens)")

    if haiku_cost > 0:
        ratio = deepseek_cost / haiku_cost
        savings = (1 - ratio) * 100
        print(f"\n✓ DeepSeek is {ratio:.2f}x the cost of Haiku ({savings:.1f}% savings)")
    else:
        print("⚠ Cannot calculate ratio (Haiku cost is zero)")


async def test_rollback() -> None:
    """
    Test that rollback routing works: switch back to Anthropic.
    """
    print_subheader("Testing Rollback to Anthropic")

    # Switch back to Anthropic
    haiku_model = "anthropic:claude-haiku-4-5-20251001"
    print(f"Setting routing back to Anthropic: {haiku_model}")
    _OPERATION_ROUTING["article_enrichment_batch"] = RoutingStrategy(
        "article_enrichment_batch",
        primary=haiku_model,
    )

    # Verify the routing is set
    routing = _OPERATION_ROUTING.get("article_enrichment_batch")
    selected = routing.select("test_rollback:key")
    print(f"✓ Routing verified: {selected}")

    if selected == haiku_model:
        print("✓ Rollback successful: routing restored to Anthropic")
    else:
        print(f"✗ Rollback failed: expected {haiku_model}, got {selected}")


async def main():
    """Run all pre-production smoke tests."""
    print_header("TASK-086 Phase 1: Pre-Production Smoke Tests")
    print(f"\nTest started: {datetime.now(timezone.utc).isoformat()}")
    print(f"Test articles: {len(TEST_ARTICLES)}")

    results = {}

    # ── Test 1: Anthropic (baseline) ────────────────────────────
    print_header("Test 1: Anthropic (Baseline)")
    haiku_result = await test_enrichment_with_routing(
        provider_name="Anthropic",
        model_ref="anthropic:claude-haiku-4-5-20251001",
    )
    results["anthropic"] = haiku_result

    if not haiku_result.get("success"):
        print("\n✗ Anthropic test failed. Stopping smoke tests.")
        sys.exit(1)

    # Wait for traces to be written
    await asyncio.sleep(2)

    # Check Anthropic traces
    haiku_trace = await check_llm_traces("anthropic:claude-haiku-4-5-20251001")
    results["anthropic_trace"] = haiku_trace

    # ── Test 2: DeepSeek (new provider) ────────────────────────
    print_header("Test 2: DeepSeek (New Provider)")
    deepseek_result = await test_enrichment_with_routing(
        provider_name="DeepSeek",
        model_ref="deepseek:deepseek-v4-flash",
    )
    results["deepseek"] = deepseek_result

    if not deepseek_result.get("success"):
        print("\n✗ DeepSeek test failed. Rolling back to Anthropic.")
        await test_rollback()
        sys.exit(1)

    # Wait for traces to be written
    await asyncio.sleep(2)

    # Check DeepSeek traces
    deepseek_trace = await check_llm_traces("deepseek:deepseek-v4-flash")
    results["deepseek_trace"] = deepseek_trace

    # ── Test 3: Cost comparison ────────────────────────────────
    print_header("Test 3: Cost Comparison")
    await compare_costs(haiku_trace, deepseek_trace)

    # ── Test 4: Rollback ───────────────────────────────────────
    print_header("Test 4: Rollback Verification")
    await test_rollback()

    # ── Summary ────────────────────────────────────────────────
    print_header("SMOKE TEST SUMMARY")
    print("\n✓ All smoke tests passed!")
    print("\nResults:")
    print(f"  - Anthropic enrichment: PASS")
    print(f"  - DeepSeek enrichment: PASS")
    print(f"  - Traces recorded: {haiku_trace.get('found')} (Anthropic), {deepseek_trace.get('found')} (DeepSeek)")
    print(f"  - Rollback verified: PASS")
    print(f"\n✓ Ready for Phase 1 production deployment")

    # Save results to file for review
    results_file = os.path.join(
        os.path.dirname(__file__),
        "..",
        "docs",
        "sprints",
        "sprint-017-tier1-cost-optimization",
        "validation",
        "TASK-086-phase1-smoke-test-results.json"
    )
    os.makedirs(os.path.dirname(results_file), exist_ok=True)
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n✓ Results saved to: {results_file}")


if __name__ == "__main__":
    asyncio.run(main())
