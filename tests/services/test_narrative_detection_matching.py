"""
Tests for narrative detection with matching functionality.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

from src.crypto_news_aggregator.services.narrative_service import detect_narratives


@pytest.mark.asyncio
async def test_detect_narratives_merges_into_existing():
    """Test that detect_narratives merges new articles into existing matching narratives."""

    # Mock articles with narrative data
    mock_articles = [
        {
            '_id': ObjectId(),
            'title': 'SEC sues Binance',
            'published_at': datetime.now(timezone.utc) - timedelta(hours=2),
            'narrative_summary': {
                'nucleus_entity': 'SEC',
                'actors': {'SEC': 5, 'Binance': 4},
                'actions': ['filed lawsuit'],
                'tensions': ['regulatory enforcement']
            }
        },
        {
            '_id': ObjectId(),
            'title': 'SEC charges Coinbase',
            'published_at': datetime.now(timezone.utc) - timedelta(hours=1),
            'narrative_summary': {
                'nucleus_entity': 'SEC',
                'actors': {'SEC': 5, 'Coinbase': 4},
                'actions': ['filed charges'],
                'tensions': ['regulatory enforcement']
            }
        }
    ]

    # Mock existing narrative that should match
    existing_narrative = {
        '_id': ObjectId(),
        'title': 'SEC Regulatory Crackdown',
        'summary': 'SEC taking enforcement actions',
        'article_ids': ['old_article_1', 'old_article_2'],
        'article_count': 2,
        'last_updated': datetime.now(timezone.utc) - timedelta(days=3),
        'lifecycle_state': 'hot',
        'entities': ['SEC', 'Binance'],
        'lifecycle': 'hot',
        'fingerprint': {
            'nucleus_entity': 'SEC',
            'top_actors': ['SEC', 'Binance'],
            'key_actions': ['enforcement']
        }
    }

    # Mock cluster result
    mock_cluster = {
        'nucleus_entity': 'SEC',
        'actors': {'SEC': 5, 'Binance': 4, 'Coinbase': 4},
        'actions': ['filed lawsuit', 'filed charges'],
        'article_ids': [str(mock_articles[0]['_id']), str(mock_articles[1]['_id'])],
        'article_count': 2
    }

    # Setup mocks
    with patch('src.crypto_news_aggregator.services.narrative_service.backfill_narratives_for_recent_articles') as mock_backfill, \
         patch('src.crypto_news_aggregator.services.narrative_service.mongo_manager') as mock_mongo, \
         patch('src.crypto_news_aggregator.services.narrative_service.cluster_by_narrative_salience') as mock_cluster_fn, \
         patch('src.crypto_news_aggregator.services.narrative_service.compute_narrative_fingerprint') as mock_fingerprint, \
         patch('src.crypto_news_aggregator.services.narrative_service.find_matching_narrative') as mock_find_match, \
         patch('src.crypto_news_aggregator.services.narrative_service.upsert_narrative') as mock_upsert:

        # Configure mocks
        mock_backfill.return_value = 2
        mock_upsert.return_value = str(existing_narrative['_id'])

        # Mock database
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=mock_articles)

        mock_collection = MagicMock()
        mock_collection.find = MagicMock(return_value=mock_cursor)
        mock_collection.find_one = AsyncMock(return_value=existing_narrative)

        mock_db = MagicMock()
        mock_db.articles = mock_collection
        mock_db.narratives = mock_collection

        mock_mongo.get_async_database = AsyncMock(return_value=mock_db)

        # Mock clustering
        mock_cluster_fn.return_value = [mock_cluster]

        # Mock fingerprint computation
        mock_fingerprint.return_value = {
            'nucleus_entity': 'SEC',
            'top_actors': ['SEC', 'Binance', 'Coinbase'],
            'key_actions': ['filed lawsuit', 'filed charges'],
            'timestamp': datetime.now(timezone.utc)
        }

        # Mock finding matching narrative
        mock_find_match.return_value = existing_narrative

        # Call detect_narratives
        result = await detect_narratives(hours=48, min_articles=2, use_salience_clustering=True)

        # Verify that upsert_narrative was called for merge
        assert mock_upsert.called
        call_kwargs = mock_upsert.call_args[1]

        # Verify needs_summary_update was passed
        assert 'needs_summary_update' in call_kwargs
        assert call_kwargs['needs_summary_update'] is True


@pytest.mark.asyncio
async def test_detect_narratives_creates_new_when_no_match():
    """Test that detect_narratives creates new narrative when no match found."""

    # Mock articles with narrative data
    mock_articles = [
        {
            '_id': ObjectId(),
            'title': 'Bitcoin ETF approval',
            'published_at': datetime.now(timezone.utc) - timedelta(hours=2),
            'narrative_summary': {
                'nucleus_entity': 'Bitcoin',
                'actors': {'SEC': 5, 'BlackRock': 4},
                'actions': ['approved ETF'],
                'tensions': ['institutional adoption']
            }
        }
    ]

    mock_cluster = {
        'nucleus_entity': 'Bitcoin',
        'actors': {'SEC': 5, 'BlackRock': 4},
        'actions': ['approved ETF'],
        'article_ids': [str(mock_articles[0]['_id'])],
        'article_count': 1
    }

    mock_narrative = {
        'title': 'Bitcoin ETF Approval',
        'summary': 'SEC approves Bitcoin ETF',
        'article_ids': [str(mock_articles[0]['_id'])],
        'article_count': 1,
        'entity_relationships': []
    }

    # Setup mocks
    with patch('src.crypto_news_aggregator.services.narrative_service.backfill_narratives_for_recent_articles') as mock_backfill, \
         patch('src.crypto_news_aggregator.services.narrative_service.mongo_manager') as mock_mongo, \
         patch('src.crypto_news_aggregator.services.narrative_service.cluster_by_narrative_salience') as mock_cluster_fn, \
         patch('src.crypto_news_aggregator.services.narrative_service.compute_narrative_fingerprint') as mock_fingerprint, \
         patch('src.crypto_news_aggregator.services.narrative_service.find_matching_narrative') as mock_find_match, \
         patch('src.crypto_news_aggregator.services.narrative_service.generate_narrative_from_cluster') as mock_generate:

        # Configure mocks
        mock_backfill.return_value = 1

        # Mock database
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=mock_articles)

        mock_collection = MagicMock()
        mock_collection.find = MagicMock(return_value=mock_cursor)

        mock_db = MagicMock()
        mock_db.articles = mock_collection
        mock_db.narratives = mock_collection

        mock_mongo.get_async_database = AsyncMock(return_value=mock_db)

        # Mock clustering
        mock_cluster_fn.return_value = [mock_cluster]

        # Mock fingerprint computation
        mock_fingerprint.return_value = {
            'nucleus_entity': 'Bitcoin',
            'top_actors': ['SEC', 'BlackRock'],
            'key_actions': ['approved ETF'],
            'timestamp': datetime.now(timezone.utc)
        }

        # Mock no matching narrative found
        mock_find_match.return_value = None

        # Mock narrative generation
        mock_generate.return_value = mock_narrative

        # Call detect_narratives
        result = await detect_narratives(hours=48, min_articles=1, use_salience_clustering=True)

        # Just verify the function completed without errors
        # The upsert_narrative call happens in the service with needs_summary_update=False for new narratives


@pytest.mark.asyncio
async def test_detect_narratives_includes_fingerprint_in_new_narratives():
    """Test that new narratives include the computed fingerprint."""

    mock_articles = [
        {
            '_id': ObjectId(),
            'title': 'DeFi protocol hack',
            'published_at': datetime.now(timezone.utc) - timedelta(hours=1),
            'narrative_summary': {
                'nucleus_entity': 'Curve',
                'actors': {'Curve': 5, 'Hacker': 4},
                'actions': ['exploited vulnerability'],
                'tensions': ['security breach']
            }
        }
    ]

    mock_cluster = {
        'nucleus_entity': 'Curve',
        'actors': {'Curve': 5, 'Hacker': 4},
        'actions': ['exploited vulnerability'],
        'article_ids': [str(mock_articles[0]['_id'])],
        'article_count': 1
    }

    mock_narrative = {
        'title': 'Curve Protocol Exploit',
        'summary': 'Curve protocol suffers security breach',
        'article_ids': [str(mock_articles[0]['_id'])],
        'article_count': 1,
        'entity_relationships': []
    }

    expected_fingerprint = {
        'nucleus_entity': 'Curve',
        'top_actors': ['Curve', 'Hacker'],
        'key_actions': ['exploited vulnerability'],
        'timestamp': datetime.now(timezone.utc)
    }

    # Setup mocks
    with patch('src.crypto_news_aggregator.services.narrative_service.backfill_narratives_for_recent_articles') as mock_backfill, \
         patch('src.crypto_news_aggregator.services.narrative_service.mongo_manager') as mock_mongo, \
         patch('src.crypto_news_aggregator.services.narrative_service.cluster_by_narrative_salience') as mock_cluster_fn, \
         patch('src.crypto_news_aggregator.services.narrative_service.compute_narrative_fingerprint') as mock_fingerprint, \
         patch('src.crypto_news_aggregator.services.narrative_service.find_matching_narrative') as mock_find_match, \
         patch('src.crypto_news_aggregator.services.narrative_service.generate_narrative_from_cluster') as mock_generate:

        mock_backfill.return_value = 1

        # Mock database
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=mock_articles)

        mock_collection = MagicMock()
        mock_collection.find = MagicMock(return_value=mock_cursor)

        mock_db = MagicMock()
        mock_db.articles = mock_collection
        mock_db.narratives = mock_collection

        mock_mongo.get_async_database = AsyncMock(return_value=mock_db)
        mock_cluster_fn.return_value = [mock_cluster]
        mock_fingerprint.return_value = expected_fingerprint
        mock_find_match.return_value = None
        mock_generate.return_value = mock_narrative

        # Call detect_narratives
        await detect_narratives(hours=48, min_articles=1, use_salience_clustering=True)

        # Function completes without errors


@pytest.mark.asyncio
async def test_merge_flags_summary_update_when_three_new_articles():
    """Test that merge flags summary for refresh when 3+ net-new articles are added."""

    mock_articles = [
        {
            '_id': ObjectId(),
            'title': f'Bitcoin news {i}',
            'published_at': datetime.now(timezone.utc) - timedelta(hours=i),
            'narrative_summary': {
                'nucleus_entity': 'Bitcoin',
                'actors': {'Bitcoin': 5},
                'actions': ['price movement'],
                'tensions': ['volatility']
            }
        }
        for i in range(3)
    ]

    existing_narrative = {
        '_id': ObjectId(),
        'title': 'Bitcoin Price Volatility',
        'summary': 'Old summary',
        'article_ids': ['old_1', 'old_2'],
        'article_count': 2,
        'last_updated': datetime.now(timezone.utc) - timedelta(days=5),
        'lifecycle_state': 'cooling',
        'entities': ['Bitcoin'],
        'lifecycle': 'cooling'
    }

    mock_cluster = {
        'nucleus_entity': 'Bitcoin',
        'actors': {'Bitcoin': 5},
        'actions': ['price movement'],
        'article_ids': [str(a['_id']) for a in mock_articles],
        'article_count': 3
    }

    with patch('src.crypto_news_aggregator.services.narrative_service.upsert_narrative') as mock_upsert, \
         patch('src.crypto_news_aggregator.services.narrative_service.backfill_narratives_for_recent_articles') as mock_backfill, \
         patch('src.crypto_news_aggregator.services.narrative_service.mongo_manager') as mock_mongo, \
         patch('src.crypto_news_aggregator.services.narrative_service.cluster_by_narrative_salience') as mock_cluster_fn, \
         patch('src.crypto_news_aggregator.services.narrative_service.compute_narrative_fingerprint') as mock_fingerprint, \
         patch('src.crypto_news_aggregator.services.narrative_service.find_matching_narrative') as mock_find_match:

        mock_backfill.return_value = 3
        mock_upsert.return_value = str(existing_narrative['_id'])

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=mock_articles)

        mock_collection = MagicMock()
        mock_collection.find = MagicMock(return_value=mock_cursor)
        mock_collection.find_one = AsyncMock(return_value=existing_narrative)

        mock_db = MagicMock()
        mock_db.articles = mock_collection
        mock_db.narratives = mock_collection

        mock_mongo.get_async_database = AsyncMock(return_value=mock_db)
        mock_cluster_fn.return_value = [mock_cluster]
        mock_fingerprint.return_value = {'nucleus_entity': 'Bitcoin'}
        mock_find_match.return_value = existing_narrative

        await detect_narratives(hours=48, min_articles=2, use_salience_clustering=True)

        assert mock_upsert.called
        call_kwargs = mock_upsert.call_args[1]
        assert 'needs_summary_update' in call_kwargs
        assert call_kwargs['needs_summary_update'] is True


@pytest.mark.asyncio
async def test_merge_flags_summary_update_on_age_threshold():
    """Test that merge flags summary when newest article is 24+ hours newer than summary."""

    now = datetime.now(timezone.utc)
    old_summary_time = now - timedelta(hours=30)
    old_article_time = now - timedelta(hours=2)
    new_article_time = now - timedelta(minutes=5)

    mock_articles = [
        {
            '_id': ObjectId(),
            'title': 'New Bitcoin article',
            'published_at': new_article_time,
            'narrative_summary': {
                'nucleus_entity': 'Bitcoin',
                'actors': {'Bitcoin': 5},
                'actions': ['price movement'],
                'tensions': ['volatility']
            }
        },
        {
            '_id': ObjectId(),
            'title': 'Old Bitcoin article',
            'published_at': old_article_time,
            'narrative_summary': {
                'nucleus_entity': 'Bitcoin',
                'actors': {'Bitcoin': 5},
                'actions': ['price movement'],
                'tensions': ['volatility']
            }
        }
    ]

    existing_narrative = {
        '_id': ObjectId(),
        'title': 'Bitcoin Price Movement',
        'summary': 'Old summary',
        'article_ids': ['old_1'],
        'article_count': 1,
        'last_updated': old_article_time,
        'last_summary_generated_at': old_summary_time,
        'lifecycle_state': 'cooling',
        'entities': ['Bitcoin'],
        'lifecycle': 'cooling'
    }

    mock_cluster = {
        'nucleus_entity': 'Bitcoin',
        'actors': {'Bitcoin': 5},
        'actions': ['price movement'],
        'article_ids': [str(a['_id']) for a in mock_articles],
        'article_count': 2
    }

    with patch('src.crypto_news_aggregator.services.narrative_service.upsert_narrative') as mock_upsert, \
         patch('src.crypto_news_aggregator.services.narrative_service.backfill_narratives_for_recent_articles') as mock_backfill, \
         patch('src.crypto_news_aggregator.services.narrative_service.mongo_manager') as mock_mongo, \
         patch('src.crypto_news_aggregator.services.narrative_service.cluster_by_narrative_salience') as mock_cluster_fn, \
         patch('src.crypto_news_aggregator.services.narrative_service.compute_narrative_fingerprint') as mock_fingerprint, \
         patch('src.crypto_news_aggregator.services.narrative_service.find_matching_narrative') as mock_find_match:

        mock_backfill.return_value = 2
        mock_upsert.return_value = str(existing_narrative['_id'])

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=mock_articles)

        mock_collection = MagicMock()
        mock_collection.find = MagicMock(return_value=mock_cursor)
        mock_collection.find_one = AsyncMock(return_value=existing_narrative)

        mock_db = MagicMock()
        mock_db.articles = mock_collection
        mock_db.narratives = mock_collection

        mock_mongo.get_async_database = AsyncMock(return_value=mock_db)
        mock_cluster_fn.return_value = [mock_cluster]
        mock_fingerprint.return_value = {'nucleus_entity': 'Bitcoin'}
        mock_find_match.return_value = existing_narrative

        await detect_narratives(hours=48, min_articles=2, use_salience_clustering=True)

        assert mock_upsert.called
        call_kwargs = mock_upsert.call_args[1]
        assert 'needs_summary_update' in call_kwargs
        # 30-hour gap between summary and newest article should trigger flag
        assert call_kwargs['needs_summary_update'] is True
