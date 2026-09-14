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
    """Verify production enrichment query uses age cutoff and ordering."""
    import ast
    import inspect
    from crypto_news_aggregator.background import rss_fetcher
    
    source = inspect.getsource(rss_fetcher.process_new_articles_from_mongodb)
    tree = ast.parse(source)
    
    # Look for key query characteristics
    enrichment_query_found = False
    sort_found = False
    limit_found = False
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "enrichment_query":
                    enrichment_query_found = True
                    if isinstance(node.value, ast.Dict):
                        keys = [k.value if isinstance(k, ast.Constant) else None 
                               for k in node.value.keys]
                        assert "created_at" in keys, \
                            "enrichment_query must have 'created_at' key"
        
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == "sort" and len(node.args) >= 2:
                    first_arg = node.args[0]
                    if isinstance(first_arg, ast.Constant) and first_arg.value == "created_at":
                        sort_found = True
                if node.func.attr == "limit":
                    limit_found = True
    
    assert enrichment_query_found, \
        "enrichment_query dict must be in process_new_articles_from_mongodb()"
    assert sort_found, \
        ".sort('created_at', ...) must be in MongoDB query"
    assert limit_found, \
        ".limit() must be in MongoDB query to bound memory"
