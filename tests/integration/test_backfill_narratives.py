"""
Integration tests for narrative backfill script with rate limiting.
"""
import pytest
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def mock_articles():
    """Create mock articles for testing."""
    articles = []
    for i in range(30):  # 30 test articles
        articles.append({
            "_id": f"article_{i}",
            "title": f"Test Article {i}",
            "content": f"Content for article {i}",
            "published_at": datetime.now(timezone.utc) - timedelta(hours=i),
        })
    return articles


@pytest.fixture
def mock_narrative_data():
    """Create mock narrative data."""
    return {
        "actors": ["Bitcoin", "Ethereum"],
        "actor_salience": {"Bitcoin": 0.8, "Ethereum": 0.6},
        "nucleus_entity": "Bitcoin",
        "actions": ["price increase", "market rally"],
        "tensions": ["volatility", "regulation"],
        "implications": "Bullish sentiment in crypto markets",
        "narrative_summary": "Bitcoin leads market rally",
        "narrative_hash": "test_hash_123",
    }


def setup_mongo_mocks(articles_list):
    """Helper to setup MongoDB mocks properly."""
    mock_db = AsyncMock()
    mock_collection = AsyncMock()
    mock_cursor = AsyncMock()
    mock_cursor.limit = Mock(return_value=mock_cursor)  # limit() returns cursor itself
    mock_cursor.to_list = AsyncMock(return_value=articles_list)

    mock_collection.find.return_value = mock_cursor
    mock_collection.update_one = AsyncMock()
    mock_db.articles = mock_collection

    return mock_db, mock_collection, mock_cursor


@pytest.mark.asyncio
class TestBackfillRateLimiting:
    """Integration tests for backfill with rate limiting."""
    
    async def test_throughput_calculation_at_startup(self, mock_articles, mock_narrative_data, caplog):
        """Test that throughput is calculated and logged at startup."""
        from scripts.backfill_narratives import backfill_with_rate_limiting
        
        with patch('scripts.backfill_narratives.mongo_manager') as mock_mongo:
            # Setup mocks
            mock_db, mock_collection, mock_cursor = setup_mongo_mocks([])
            mock_mongo.get_async_database = AsyncMock(return_value=mock_db)
            
            # Run backfill
            await backfill_with_rate_limiting(hours=24, limit=10, batch_size=15, batch_delay=30, article_delay=1.0)
            
            # Verify throughput calculation was logged
            assert "Rate limiting configuration:" in caplog.text
            assert "Batch size: 15 articles" in caplog.text
            assert "Expected throughput:" in caplog.text
    
    async def test_actual_throughput_monitoring(self, mock_articles, mock_narrative_data, caplog):
        """Test that actual throughput is calculated and logged per batch."""
        from scripts.backfill_narratives import backfill_with_rate_limiting

        with patch('scripts.backfill_narratives.mongo_manager') as mock_mongo, \
             patch('scripts.backfill_narratives.discover_narrative_from_article') as mock_discover:

            # Setup mocks using helper
            mock_db, mock_collection, mock_cursor = setup_mongo_mocks(mock_articles[:15])
            mock_mongo.get_async_database = AsyncMock(return_value=mock_db)

            # Mock narrative discovery
            mock_discover.return_value = mock_narrative_data
            
            # Run backfill with minimal delays for testing
            await backfill_with_rate_limiting(
                hours=24, 
                limit=15, 
                batch_size=15, 
                batch_delay=0,  # No delay for testing
                article_delay=0.01  # Minimal delay
            )
            
            # Verify throughput was logged
            assert "Throughput:" in caplog.text
            assert "articles/min" in caplog.text
    
    async def test_batch_processing_with_delays(self, mock_articles, mock_narrative_data):
        """Test that delays are applied correctly between articles and batches."""
        from scripts.backfill_narratives import backfill_with_rate_limiting

        with patch('scripts.backfill_narratives.mongo_manager') as mock_mongo, \
             patch('scripts.backfill_narratives.discover_narrative_from_article') as mock_discover, \
             patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:

            # Setup mocks using helper
            mock_db, mock_collection, mock_cursor = setup_mongo_mocks(mock_articles[:30])
            mock_mongo.get_async_database = AsyncMock(return_value=mock_db)
            mock_discover.return_value = mock_narrative_data
            
            # Run backfill
            await backfill_with_rate_limiting(
                hours=24,
                limit=30,
                batch_size=15,
                batch_delay=5,
                article_delay=0.5
            )
            
            # Verify sleep was called
            assert mock_sleep.called
            
            # Count article delays and batch delays
            article_delay_calls = [call for call in mock_sleep.call_args_list if call[0][0] == 0.5]
            batch_delay_calls = [call for call in mock_sleep.call_args_list if call[0][0] == 5]
            
            # Should have 14 article delays in first batch + 14 in second batch = 28
            assert len(article_delay_calls) == 28
            
            # Should have 1 batch delay between the 2 batches
            assert len(batch_delay_calls) == 1
    
    async def test_rate_limit_warning_triggers(self, mock_articles, mock_narrative_data, caplog):
        """Test that warnings trigger when throughput exceeds threshold."""
        from scripts.backfill_narratives import backfill_with_rate_limiting

        with patch('scripts.backfill_narratives.mongo_manager') as mock_mongo, \
             patch('scripts.backfill_narratives.discover_narrative_from_article') as mock_discover:

            # Setup mocks using helper
            mock_db, mock_collection, mock_cursor = setup_mongo_mocks(mock_articles[:20])
            mock_mongo.get_async_database = AsyncMock(return_value=mock_db)
            mock_discover.return_value = mock_narrative_data
            
            # Run with aggressive settings that should trigger warning
            await backfill_with_rate_limiting(
                hours=24,
                limit=20,
                batch_size=20,
                batch_delay=10,
                article_delay=0.1  # Very fast = high throughput
            )
            
            # Check if warning was logged (throughput will be very high with 0.1s delays)
            # With 20 articles, 19 * 0.1s = 1.9s + 10s = 11.9s per batch
            # 20 / 11.9 * 60 = ~100 articles/min (way over limit)
            assert "WARNING" in caplog.text or "exceeds safe limit" in caplog.text
    
    async def test_conservative_defaults_stay_under_limit(self, mock_articles, mock_narrative_data):
        """Test that default conservative settings stay under rate limits."""
        from scripts.backfill_narratives import backfill_with_rate_limiting

        with patch('scripts.backfill_narratives.mongo_manager') as mock_mongo, \
             patch('scripts.backfill_narratives.discover_narrative_from_article') as mock_discover:

            # Setup mocks using helper
            mock_db, mock_collection, mock_cursor = setup_mongo_mocks(mock_articles[:15])
            mock_mongo.get_async_database = AsyncMock(return_value=mock_db)
            mock_discover.return_value = mock_narrative_data
            
            start_time = time.time()
            
            # Run with default conservative settings
            await backfill_with_rate_limiting(
                hours=24,
                limit=15,
                batch_size=15,
                batch_delay=30,
                article_delay=1.0
            )
            
            elapsed_time = time.time() - start_time
            
            # Should take at least 44 seconds for one batch
            # (14 article delays * 1.0s + 30s batch delay, but no batch delay for last batch)
            # So just 14 seconds of article delays
            assert elapsed_time >= 14.0
    
    async def test_empty_articles_returns_zero(self):
        """Test that backfill returns 0 when no articles need processing."""
        from scripts.backfill_narratives import backfill_with_rate_limiting

        with patch('scripts.backfill_narratives.mongo_manager') as mock_mongo:
            # Setup mocks using helper
            mock_db, mock_collection, mock_cursor = setup_mongo_mocks([])
            mock_mongo.get_async_database = AsyncMock(return_value=mock_db)
            
            result = await backfill_with_rate_limiting(hours=24, limit=10)
            
            assert result == 0
    
    async def test_failed_narrative_extraction_counted(self, mock_articles):
        """Test that failed narrative extractions are counted."""
        from scripts.backfill_narratives import backfill_with_rate_limiting

        with patch('scripts.backfill_narratives.mongo_manager') as mock_mongo, \
             patch('scripts.backfill_narratives.discover_narrative_from_article') as mock_discover, \
             patch('asyncio.sleep', new_callable=AsyncMock):

            # Setup mocks using helper
            mock_db, mock_collection, mock_cursor = setup_mongo_mocks(mock_articles[:5])
            mock_mongo.get_async_database = AsyncMock(return_value=mock_db)
            
            # Mock narrative discovery to return None (failure)
            mock_discover.return_value = None
            
            result = await backfill_with_rate_limiting(
                hours=24,
                limit=5,
                batch_size=5,
                batch_delay=0,
                article_delay=0.01
            )
            
            # Should return 0 successful updates
            assert result == 0
    
    async def test_successful_narrative_extraction_counted(self, mock_articles, mock_narrative_data):
        """Test that successful narrative extractions are counted."""
        from scripts.backfill_narratives import backfill_with_rate_limiting

        with patch('scripts.backfill_narratives.mongo_manager') as mock_mongo, \
             patch('scripts.backfill_narratives.discover_narrative_from_article') as mock_discover, \
             patch('asyncio.sleep', new_callable=AsyncMock):

            # Setup mocks using helper
            mock_db, mock_collection, mock_cursor = setup_mongo_mocks(mock_articles[:5])
            mock_mongo.get_async_database = AsyncMock(return_value=mock_db)

            # Mock narrative discovery to return data
            mock_discover.return_value = mock_narrative_data
            
            result = await backfill_with_rate_limiting(
                hours=24,
                limit=5,
                batch_size=5,
                batch_delay=0,
                article_delay=0.01
            )
            
            # Should return 5 successful updates
            assert result == 5


@pytest.mark.asyncio
class TestBatchProcessingLogic:
    """Test batch processing logic."""
    
    async def test_correct_number_of_batches(self, mock_articles, mock_narrative_data):
        """Test that correct number of batches are processed."""
        from scripts.backfill_narratives import backfill_with_rate_limiting
        
        with patch('scripts.backfill_narratives.mongo_manager') as mock_mongo, \
             patch('scripts.backfill_narratives.discover_narrative_from_article') as mock_discover, \
             patch('asyncio.sleep', new_callable=AsyncMock):
            
            # Setup mocks
            mock_db = AsyncMock()
            mock_collection = Mock()
            mock_cursor = Mock()
            
            mock_mongo.get_async_database = AsyncMock(return_value=mock_db)
            mock_db.articles = mock_collection
            mock_collection.find.return_value = mock_cursor
            mock_cursor.to_list = AsyncMock(return_value=mock_articles[:30])  # 30 articles
            mock_collection.update_one = AsyncMock()
            mock_discover.return_value = mock_narrative_data
            
            await backfill_with_rate_limiting(
                hours=24,
                limit=30,
                batch_size=15,
                batch_delay=0,
                article_delay=0.01
            )
            
            # Should have called update_one 30 times (once per article)
            assert mock_collection.update_one.call_count == 30
    
    async def test_partial_last_batch(self, mock_articles, mock_narrative_data):
        """Test that partial last batch is handled correctly."""
        from scripts.backfill_narratives import backfill_with_rate_limiting
        
        with patch('scripts.backfill_narratives.mongo_manager') as mock_mongo, \
             patch('scripts.backfill_narratives.discover_narrative_from_article') as mock_discover, \
             patch('asyncio.sleep', new_callable=AsyncMock):
            
            # Setup mocks
            mock_db = AsyncMock()
            mock_collection = Mock()
            mock_cursor = Mock()
            
            mock_mongo.get_async_database = AsyncMock(return_value=mock_db)
            mock_db.articles = mock_collection
            mock_collection.find.return_value = mock_cursor
            mock_cursor.to_list = AsyncMock(return_value=mock_articles[:17])  # 17 articles (15 + 2)
            mock_collection.update_one = AsyncMock()
            mock_discover.return_value = mock_narrative_data
            
            result = await backfill_with_rate_limiting(
                hours=24,
                limit=17,
                batch_size=15,
                batch_delay=0,
                article_delay=0.01
            )
            
            # Should process all 17 articles
            assert result == 17
            assert mock_collection.update_one.call_count == 17


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
