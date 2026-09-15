"""
Tests for MongoDB client lifecycle and duplicate error handling.

Verifies:
1. _client_loop is assigned atomically with _async_client after ping succeeds
2. Ping failure cleans up both client and loop  
3. DuplicateKeyError handling distinguishes URL from other unique constraints
4. Production code paths are correctly structured
"""

import pytest


def test_mongo_manager_code_assigns_client_and_loop_atomically():
    """Verify that in mongodb.py, _async_client and _client_loop are assigned together.
    
    Check the actual source code to ensure the race condition fix is in place.
    """
    import inspect
    from crypto_news_aggregator.db.mongodb import MongoManager
    
    source = inspect.getsource(MongoManager.get_async_client)
    
    # Key checks:
    # 1. new_client = AsyncIOMotorClient(...) creates variable, not direct assignment
    assert "new_client = AsyncIOMotorClient" in source, \
        "Should assign to local 'new_client' variable first"
    
    # 2. Ping is awaited before assignments
    assert "await new_client.admin.command" in source, \
        "Should ping new_client before assigning to shared state"
    
    # 3. After successful ping, both are assigned
    assert "self._async_client = new_client" in source, \
        "Should assign new_client to _async_client"
    assert "self._client_loop = current_loop" in source, \
        "Should assign current_loop to _client_loop"
    
    # 4. On ping failure, client should be cleaned up before raising
    assert "new_client.close()" in source, \
        "Should close failed client on ping error"


def test_article_service_does_not_close_shared_client():
    """Verify ArticleService.close() does not close mongo_manager client."""
    import inspect
    from crypto_news_aggregator.services.article_service import ArticleService
    
    source = inspect.getsource(ArticleService.close)
    
    # Should NOT call aclose() on the manager
    assert "mongo_manager.aclose()" not in source, \
        "ArticleService must not close the shared mongo_manager client"


def test_duplicate_url_handling_checks_error_details():
    """Verify articles.py checks for URL duplicates using error details."""
    import inspect
    from crypto_news_aggregator.db.operations.articles import create_or_update_articles
    
    source = inspect.getsource(create_or_update_articles)
    
    # Should check error details structure
    assert "e.details" in source, "Should check error.details for structured info"
    
    # Should look for 'url' in the index/key information
    assert "url" in source, "Should specifically handle URL index violations"


def test_enrichment_query_structure_from_production_code():
    """Verify the production enrichment eligibility query uses an age cutoff.

    Exercises the actual query builder (db/operations/enrichment_state.build_eligible_query)
    used by process_new_articles_from_mongodb() via claim_batch(), rather than
    inspecting source text for a variable that no longer exists post-BUG-108
    (candidate selection now goes through the durable claim/lease state machine).
    See tests/background/test_enrichment_query_bounds.py and
    tests/db/test_enrichment_state_machine.py for full behavioral coverage.
    """
    from datetime import datetime, timedelta, timezone

    from crypto_news_aggregator.db.operations.enrichment_state import build_eligible_query

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    query = build_eligible_query(cutoff)

    assert query["created_at"] == {"$gte": cutoff}
    assert "$or" in query and len(query["$or"]) > 0
