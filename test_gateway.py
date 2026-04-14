#!/usr/bin/env python3
"""Quick test of the LLM gateway."""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from crypto_news_aggregator.llm.gateway import get_gateway

async def main():
    gateway = get_gateway()

    # Test message
    messages = [
        {
            "role": "user",
            "content": "Generate a narrative for these articles: [Bitcoin ETF launched, Goldman Sachs files Bitcoin ETF]"
        }
    ]

    print("Testing gateway.call() with narrative_generate operation...")
    print(f"Messages: {messages}")
    print()

    try:
        result = await gateway.call(
            messages=messages,
            model="claude-haiku-4-5-20251001",
            operation="narrative_generate",
            max_tokens=512,
            temperature=0.3,
        )

        print("✅ Success!")
        print()
        print(f"Response type: {type(result)}")
        print(f"Response.text: {result.text[:200]}...")
        print()
        print(f"Full response:")
        print(f"  text: {result.text}")
        print(f"  input_tokens: {result.input_tokens}")
        print(f"  output_tokens: {result.output_tokens}")
        print(f"  cost: ${result.cost:.6f}")
        print(f"  model: {result.model}")
        print(f"  operation: {result.operation}")
        print(f"  trace_id: {result.trace_id}")

    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
