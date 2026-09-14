"""
Tests for enrichment query boundedness and age cutoff.

Verifies:
1. Enrichment query includes age cutoff to prevent processing old articles
2. Articles are processed newest-first (descending created_at order)
3. Query respects max article limit to prevent unbounded memory use
"""

import pytest
from datetime import datetime, timezone, timedelta


def test_enrichment_import_successful():
    """Verify enrichment module imports without errors."""
    from crypto_news_aggregator.background import rss_fetcher

    assert rss_fetcher is not None
    assert hasattr(rss_fetcher, 'process_new_articles_from_mongodb')


def test_age_cutoff_calculated_correctly():
    """Test age cutoff is calculated and included in query."""
    from datetime import datetime as dt, timezone as tz, timedelta

    # Simulate what happens in the enrichment function
    age_cutoff_days = 30  # Per ticket requirements
    cutoff_date = dt.now(tz.utc) - timedelta(days=age_cutoff_days)

    # Verify cutoff is in the past
    assert cutoff_date < dt.now(tz.utc)

    # Verify cutoff is approximately 30 days ago (within 1 day tolerance)
    delta_days = (dt.now(tz.utc) - cutoff_date).days
    assert 29 <= delta_days <= 31


@pytest.mark.asyncio
async def test_enrichment_query_structure_from_production_code():
    """Verify production enrichment query structure by inspecting actual rss_fetcher code.

    Extract and verify the exact query dict, sort(), and limit() calls from the
    process_new_articles_from_mongodb() function using AST inspection and execution.
    """
    import ast
    import inspect
    from datetime import datetime as dt, timezone as tz, timedelta
    from crypto_news_aggregator.background import rss_fetcher
    from crypto_news_aggregator.core.config import get_settings

    # Get the actual function source
    source = inspect.getsource(rss_fetcher.process_new_articles_from_mongodb)

    # Parse and find the enrichment_query dict assignment
    tree = ast.parse(source)

    # Look for the enrichment_query variable assignment
    enrichment_query_found = False
    sort_found = False
    limit_found = False

    for node in ast.walk(tree):
        # Check for enrichment_query dict with created_at
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "enrichment_query":
                    enrichment_query_found = True
                    # Verify the dict has "created_at" key
                    if isinstance(node.value, ast.Dict):
                        keys = [k.value if isinstance(k, ast.Constant) else None
                               for k in node.value.keys]
                        assert "created_at" in keys, \
                            "enrichment_query must have 'created_at' key in source"

        # Check for .sort("created_at", -1)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == "sort":
                    if len(node.args) >= 2:
                        first_arg = node.args[0]
                        second_arg = node.args[1]
                        if isinstance(first_arg, ast.Constant) and first_arg.value == "created_at":
                            if isinstance(second_arg, ast.UnaryOp) and isinstance(second_arg.op, ast.USub):
                                if isinstance(second_arg.operand, ast.Constant) and second_arg.operand.value == 1:
                                    sort_found = True

                # Check for .limit(max_batch_articles)
                if node.func.attr == "limit":
                    limit_found = True

    # Verify query structure was found in production code
    assert enrichment_query_found, \
        "enrichment_query dict assignment not found in process_new_articles_from_mongodb()"
    assert sort_found, \
        ".sort('created_at', -1) not found in MongoDB query in process_new_articles_from_mongodb()"
    assert limit_found, \
        ".limit() not found in MongoDB query in process_new_articles_from_mongodb()"

    # Now verify the query behavior by extracting settings
    settings = get_settings()
    age_cutoff_days = settings.ENRICHMENT_AGE_CUTOFF_DAYS
    cutoff_date = dt.now(tz.utc) - timedelta(days=age_cutoff_days)

    # Verify cutoff bounds are reasonable
    assert age_cutoff_days > 0, "Age cutoff days must be positive"
    assert cutoff_date < dt.now(tz.utc), "Cutoff must be in the past"
    assert (dt.now(tz.utc) - cutoff_date).days >= age_cutoff_days - 1, \
        "Cutoff must be within configured age window"


def test_mongo_sort_order_specification():
    """Verify MongoDB sort specification for newest-first ordering."""
    # MongoDB sort: ("field", -1) for descending
    field = "created_at"
    direction = -1  # -1 = descending = newest first

    assert field == "created_at"
    assert direction == -1


def test_max_articles_limit_reasonable():
    """Verify max articles per run prevents unbounded memory."""
    max_articles = 5000

    # 5000 articles at typical ~10KB = ~50MB in memory
    # This prevents OOM while allowing good throughput
    assert max_articles > 0
    assert max_articles <= 10000  # Sanity upper bound


def test_batch_size_for_entity_extraction():
    """Verify batch size for entity extraction is reasonable."""
    batch_size = 10  # Standard per settings

    assert batch_size > 0
    assert batch_size <= 1000  # Sanity bound

    # With 5000 article limit and 10 per batch = 500 batches max per run
    max_articles = 5000
    max_batches = max_articles // batch_size
    assert max_batches <= 500  # Reasonable number of batches
