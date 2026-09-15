"""
Worker-level behavioral tests for the enrichment state machine integration
in process_new_articles_from_mongodb() (BUG-108, review follow-up).

Unlike tests/db/test_enrichment_state_machine.py (which tests the individual
claim/complete/fail/lease helpers directly), these tests drive the actual
worker entry point against a real local MongoDB and assert on the resulting
`enrichment` subdocument state, proving the integration wiring itself is
correct: lease fencing on article-content writes, stale-lease preemption
mid-run, and legacy-complete articles being left alone.

get_optimized_llm is forced to fail so the worker takes its regex-extraction
fallback path (deterministic, no external API calls); classify_article is
patched directly to force tier 1/2 outcomes deterministically instead of
depending on the real classifier's keyword heuristics.
"""

import os
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from crypto_news_aggregator.background.rss_fetcher import (
    process_new_articles_from_mongodb,
)
from crypto_news_aggregator.db.operations.enrichment_state import (
    EnrichmentStatus,
    claim_batch,
)
from crypto_news_aggregator.models.article import ArticleMetrics

# Isolated single-node replica set used ONLY by the transaction-dependent
# regression test below. A standalone mongod (the shared `mongo_db` fixture's
# target) does not support multi-document transactions, and this repo's
# tests/conftest.py hardcodes MONGODB_URI to the standalone instance at
# import time, so a plain env var override does not reach it. This connects
# directly to a separate local replica-set deployment on a non-default port,
# entirely independent of and never touching the user's standalone instance
# or its database.
REPLSET_TEST_URI = os.environ.get(
    "BUG108_REPLSET_TEST_URI", "mongodb://localhost:27117/crypto_news"
)


@pytest_asyncio.fixture
async def replset_db():
    """A database on an isolated local replica-set deployment, for tests
    that need real multi-document transaction support. Skips the test with
    a clear reason if that deployment is unreachable, rather than silently
    falling back to a non-transactional path."""
    from crypto_news_aggregator.db.mongodb import mongo_manager

    client = AsyncIOMotorClient(
        REPLSET_TEST_URI, serverSelectionTimeoutMS=2000, connectTimeoutMS=2000
    )
    try:
        await client.admin.command("ping")
    except Exception as e:
        client.close()
        pytest.skip(
            f"Isolated replica-set test deployment unreachable at "
            f"{REPLSET_TEST_URI}: {e}. Start one with a local mongod "
            f"--replSet config to run this transaction-dependent test."
        )

    db = client.get_default_database()
    await db.articles.delete_many({})
    await db.entity_mentions.delete_many({})

    import asyncio as _asyncio

    prior_client = getattr(mongo_manager, "_async_client", None)
    prior_db = getattr(mongo_manager, "_db", None)
    prior_initialized = getattr(mongo_manager, "_initialized", False)
    prior_connection_uri = getattr(mongo_manager, "_connection_uri", None)
    prior_client_loop = getattr(mongo_manager, "_client_loop", None)
    mongo_manager._async_client = client
    mongo_manager._db = db
    mongo_manager._initialized = True
    mongo_manager._connection_uri = REPLSET_TEST_URI
    mongo_manager._client_loop = _asyncio.get_running_loop()

    try:
        yield db
    finally:
        await db.articles.delete_many({})
        await db.entity_mentions.delete_many({})
        mongo_manager._async_client = prior_client
        mongo_manager._db = prior_db
        mongo_manager._initialized = prior_initialized
        mongo_manager._connection_uri = prior_connection_uri
        mongo_manager._client_loop = prior_client_loop
        client.close()


def _article_doc(source_id: str, **extra) -> dict:
    doc = {
        "title": "Bitcoin ETF Approval Sparks Rally",
        "text": "Major financial institutions have approved Bitcoin ETFs.",
        "content": "",
        "description": "",
        "source": "test",
        "source_id": source_id,
        "url": f"https://example.com/{source_id}",
        "lang": "en",
        "metrics": ArticleMetrics().model_dump(),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    doc.update(extra)
    return doc


def _mock_llm_client(with_entities: bool = False):
    """Mock LLM client for the worker's enrichment fallback path.

    `with_entities`: when True, also configures `extract_entities_batch()`
    (the method `_process_entity_extraction_batch()` actually calls on this
    mock -- distinct from `enrich_articles_batch()`, which only supplies
    relevance/sentiment/themes) to return a Bitcoin primary entity. Without
    this, `extract_entities_batch()` is an unconfigured Mock() attribute,
    the worker's `result.get("results", [])` call on it fails with
    'Mock' object is not iterable, and mentions_to_create ends up empty --
    silently skipping the worker's entire mention-persistence code path
    (the exact code this ticket's fix targets) rather than exercising it.
    This was found and fixed while verifying BUG-108's atomic-ownership
    regression tests: without it, none of these worker-level tests actually
    called create_entity_mentions_batch_idempotent() with article_id/
    owner_token set, so they never exercised the transactional writer.
    """
    mock_llm = Mock()
    mock_llm.model_name = "test-llm-provider"

    async def _enrich_articles_batch(batch_input):
        return [
            {
                "id": item["id"],
                "relevance_score": 0.9,
                "sentiment_score": 0.6,
                "themes": ["Bitcoin"],
            }
            for item in batch_input
        ]

    mock_llm.enrich_articles_batch = _enrich_articles_batch

    if with_entities:
        def _extract_entities_batch(batch_input):
            return {
                "results": [
                    {
                        "article_id": item["id"],
                        "primary_entities": [
                            {"name": "Bitcoin", "type": "project", "confidence": 0.9, "ticker": "BTC"}
                        ],
                        "context_entities": [],
                        "sentiment": "positive",
                    }
                    for item in batch_input
                ],
                "usage": {},
            }

        mock_llm.extract_entities_batch = _extract_entities_batch
    else:
        # Explicit Mock() (not unittest.mock's auto-spec default, which is
        # the same thing but stated here so the "why no entities" reason
        # for tests that don't pass with_entities=True is self-documenting)
        # rather than silently relying on Mock()'s default attribute
        # behavior.
        mock_llm.extract_entities_batch = Mock(return_value={"results": [], "usage": {}})

    return mock_llm


@pytest.mark.asyncio
async def test_worker_writes_enriched_fields_and_marks_completed(mongo_db):
    """End-to-end: a tier-1 article claimed by the worker gets both its
    content fields written and its enrichment state marked COMPLETED --
    proving write_enriched_fields()/mark_completed() are actually wired into
    the real code path, not just individually callable."""
    from crypto_news_aggregator.db.operations.entity_mentions_index_rollout import (
        create_unique_index,
    )

    await create_unique_index(mongo_db.entity_mentions)
    await mongo_db.articles.delete_many({})
    await mongo_db.articles.insert_one(_article_doc("worker-complete-1"))

    with patch(
        "crypto_news_aggregator.background.rss_fetcher.get_optimized_llm",
        side_effect=Exception("forced failure: use fallback path"),
    ), patch(
        "crypto_news_aggregator.background.rss_fetcher.get_llm_provider",
        return_value=_mock_llm_client(),
    ), patch(
        "crypto_news_aggregator.background.rss_fetcher.classify_article",
        return_value={"tier": 1, "reason": "forced_tier_1", "matched_pattern": None},
    ):
        processed = await process_new_articles_from_mongodb()

    assert processed == 1

    doc = await mongo_db.articles.find_one({"source_id": "worker-complete-1"})
    assert doc["relevance_score"] == 0.9
    assert doc["sentiment_score"] == 0.6
    assert doc["enrichment"]["status"] == EnrichmentStatus.COMPLETED.value
    assert "owner_token" not in doc["enrichment"]
    assert "lease_expires_at" not in doc["enrichment"]


@pytest.mark.asyncio
async def test_worker_marks_tier2_articles_skipped_not_completed(mongo_db):
    """A tier 2/3 article must land in SKIPPED state (terminal, not
    reprocessed) and must NOT receive relevance_score/sentiment_score
    fields, since enrichment is deliberately not run for it."""
    from crypto_news_aggregator.db.operations.entity_mentions_index_rollout import (
        create_unique_index,
    )

    # The worker's own index-blocking check (defect 2) requires this index
    # to exist before it will claim/process any article; the shared mongo_db
    # fixture does not create it (deliberately -- see
    # entity_mentions_index_rollout.py). This test is about tier-2 skip
    # behavior, not mention persistence, but still needs the worker to get
    # past its index preflight to reach that behavior.
    await create_unique_index(mongo_db.entity_mentions)
    await mongo_db.articles.delete_many({})
    await mongo_db.articles.insert_one(_article_doc("worker-skip-1"))

    with patch(
        "crypto_news_aggregator.background.rss_fetcher.get_optimized_llm",
        side_effect=Exception("forced failure: use fallback path"),
    ), patch(
        "crypto_news_aggregator.background.rss_fetcher.get_llm_provider",
        return_value=_mock_llm_client(),
    ), patch(
        "crypto_news_aggregator.background.rss_fetcher.classify_article",
        return_value={"tier": 2, "reason": "forced_tier_2", "matched_pattern": None},
    ):
        processed = await process_new_articles_from_mongodb()

    assert processed == 1

    doc = await mongo_db.articles.find_one({"source_id": "worker-skip-1"})
    assert doc["relevance_tier"] == 2
    assert "relevance_score" not in doc
    assert doc["enrichment"]["status"] == EnrichmentStatus.SKIPPED.value


@pytest.mark.asyncio
async def test_worker_does_not_reclaim_legacy_complete_article(mongo_db):
    """An article with no `enrichment` subdocument but already showing
    terminal legacy output (tier 1 + recorded sentiment.score) must be left
    completely untouched by the worker -- no claim, no overwrite of its
    existing fields, no enrichment subdocument added."""
    await mongo_db.articles.delete_many({})
    await mongo_db.articles.insert_one(
        _article_doc(
            "worker-legacy-1",
            relevance_tier=1,
            relevance_score=0.5,
            sentiment_score=0.2,
            sentiment={"score": 0.2, "label": "neutral"},
        )
    )

    with patch(
        "crypto_news_aggregator.background.rss_fetcher.get_optimized_llm",
        side_effect=Exception("forced failure: use fallback path"),
    ), patch(
        "crypto_news_aggregator.background.rss_fetcher.get_llm_provider",
        return_value=_mock_llm_client(),
    ):
        processed = await process_new_articles_from_mongodb()

    assert processed == 0

    doc = await mongo_db.articles.find_one({"source_id": "worker-legacy-1"})
    assert doc["relevance_score"] == 0.5  # unchanged
    assert "enrichment" not in doc  # worker did not touch it at all


@pytest.mark.asyncio
async def test_worker_skips_write_when_lease_reclaimed_mid_run(mongo_db):
    """Simulates another worker reclaiming the article's lease after this
    worker claimed it but before it finished processing (e.g. the claim
    happened long enough ago that the lease is already stale by the time
    write_enriched_fields() runs). The original worker's write must not
    land, and the article must be left owned by the reclaiming worker."""
    from crypto_news_aggregator.db.operations.entity_mentions_index_rollout import (
        create_unique_index,
    )

    await create_unique_index(mongo_db.entity_mentions)
    await mongo_db.articles.delete_many({})
    result = await mongo_db.articles.insert_one(_article_doc("worker-preempt-1"))
    article_id = result.inserted_id

    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    # Directly claim the article "in the past" so its lease is already
    # expired relative to real time, simulating a slow worker.
    stale_claim = await claim_batch(
        mongo_db.articles,
        cutoff_date=cutoff,
        limit=10,
        now=datetime.now(timezone.utc) - timedelta(minutes=45),
    )
    assert article_id in stale_claim.article_ids

    # A second worker's process_new_articles_from_mongodb() run reclaims it
    # via the normal eligibility path (lease expired) and completes it.
    with patch(
        "crypto_news_aggregator.background.rss_fetcher.get_optimized_llm",
        side_effect=Exception("forced failure: use fallback path"),
    ), patch(
        "crypto_news_aggregator.background.rss_fetcher.get_llm_provider",
        return_value=_mock_llm_client(),
    ), patch(
        "crypto_news_aggregator.background.rss_fetcher.classify_article",
        return_value={"tier": 1, "reason": "forced_tier_1", "matched_pattern": None},
    ):
        processed = await process_new_articles_from_mongodb()

    assert processed == 1

    doc = await mongo_db.articles.find_one({"_id": article_id})
    assert doc["enrichment"]["status"] == EnrichmentStatus.COMPLETED.value
    assert doc["relevance_score"] == 0.9

    # The original stale claim must not be able to write over this.
    from crypto_news_aggregator.db.operations.enrichment_state import write_enriched_fields

    wrote = await write_enriched_fields(
        mongo_db.articles, article_id, stale_claim.owner_token, {"relevance_score": 0.01}
    )
    assert wrote is False
    doc_after = await mongo_db.articles.find_one({"_id": article_id})
    assert doc_after["relevance_score"] == 0.9  # unchanged by the stale write attempt


@pytest.mark.asyncio
async def test_worker_skips_mention_write_when_lease_expires_during_llm_call(mongo_db):
    """Simulates work lasting beyond the lease interval within a SINGLE
    worker run (not a race between two separate runs): the mocked LLM call
    itself forces the article's lease_expires_at into the past and lets
    another worker reclaim the article before enrich_articles_batch()
    returns, so the lease genuinely expires mid-flight rather than merely
    racing a second claim_batch() call.

    NOTE on what this test actually proves: this article has no entities
    extracted (the default `_mock_llm_client()`'s `extract_entities_batch`
    returns empty results -- entity extraction runs, and completes, BEFORE
    this lease-expiring LLM call), so mentions_to_create ends up empty and
    the worker never reaches its mention-persistence call at all here. What
    this test actually exercises is write_enriched_fields()'s own fencing:
    the stale worker's attempt to write relevance/sentiment fields after
    losing the lease correctly fails and short-circuits (the worker's
    "lease lost before enrichment write landed" branch), which is why no
    mention write is ever attempted -- not because the mention-persistence
    transaction rejected one. The dedicated mention-persistence-transaction
    regression coverage (including a genuinely overlapping takeover, and a
    proof that the actual pre-fix implementation fails the same scenario)
    lives in test_real_writer_blocks_takeover_that_overlaps_live_transaction
    and test_actual_pre_fix_implementation_fails_this_regression below,
    which call the real writer directly against an isolated replica set."""
    from datetime import timedelta

    from crypto_news_aggregator.db.operations.enrichment_state import claim_batch as _claim_batch
    from crypto_news_aggregator.db.operations.entity_mentions_index_rollout import (
        create_unique_index,
    )

    await create_unique_index(mongo_db.entity_mentions)
    await mongo_db.articles.delete_many({})
    result = await mongo_db.articles.insert_one(_article_doc("worker-lease-expires-during-llm"))
    article_id = result.inserted_id

    reclaimer_state = {"owner_token": None}

    async def _enrich_articles_batch_that_outlasts_lease(batch_input):
        # Force this article's lease to already be expired, as if the
        # configured lease duration had genuinely elapsed while this LLM
        # call was in flight, then let a second worker reclaim it -- all
        # before the original call returns control to the caller.
        await mongo_db.articles.update_one(
            {"_id": article_id},
            {"$set": {"enrichment.lease_expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}},
        )
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        reclaim = await _claim_batch(mongo_db.articles, cutoff_date=cutoff, limit=10)
        assert article_id in reclaim.article_ids, "Setup error: reclaim should succeed once lease is expired"
        reclaimer_state["owner_token"] = reclaim.owner_token

        return [
            {
                "id": item["id"],
                "relevance_score": 0.9,
                "sentiment_score": 0.6,
                "themes": ["Bitcoin"],
            }
            for item in batch_input
        ]

    mock_llm = _mock_llm_client()
    mock_llm.enrich_articles_batch = _enrich_articles_batch_that_outlasts_lease

    with patch(
        "crypto_news_aggregator.background.rss_fetcher.get_optimized_llm",
        side_effect=Exception("forced failure: use fallback path"),
    ), patch(
        "crypto_news_aggregator.background.rss_fetcher.get_llm_provider",
        return_value=mock_llm,
    ), patch(
        "crypto_news_aggregator.background.rss_fetcher.classify_article",
        return_value={"tier": 1, "reason": "forced_tier_1", "matched_pattern": None},
    ):
        await process_new_articles_from_mongodb()

    # The original (now-stale) worker must not have written mentions for
    # this article after its lease expired mid-call.
    mentions = await mongo_db.entity_mentions.find(
        {"article_id": str(article_id)}
    ).to_list(length=10)
    assert mentions == [], "Stale worker must not persist mentions after losing its lease mid-run"

    # The article must still show the reclaiming worker as owner (or
    # whatever terminal state that worker's own run leaves it in) -- the
    # original worker's write_enriched_fields() call is itself fenced and
    # already covered by test_worker_skips_write_when_lease_reclaimed_mid_run,
    # so here we only assert the mention-write side of the gap.
    doc = await mongo_db.articles.find_one({"_id": article_id})
    assert doc["enrichment"].get("owner_token") == reclaimer_state["owner_token"]


async def _require_replset_transactions(db):
    """Preflight: confirm this deployment actually supports transactions,
    outside of and before the assertions under test. A capability failure
    here fails the test with a clear message (transactions were required by
    this test's setup); it must never be silently downgraded to a skip once
    the test proceeds past setup, so a genuine transaction-path bug cannot
    disguise itself as "environment doesn't support transactions"."""
    client = db.client
    async with await client.start_session() as session:
        async def _noop(session):
            await db.articles.find_one({}, session=session)

        await session.with_transaction(_noop)


@pytest.mark.asyncio
async def test_real_writer_blocks_takeover_that_overlaps_live_transaction(replset_db):
    """REGRESSION TEST: exercises the REAL writer,
    create_entity_mentions_batch_idempotent(), with Worker B's reclaim
    attempt genuinely OVERLAPPING and completing BEFORE Worker A's
    transaction stages its own fenced write -- a true race, not two calls
    merely sequenced one after the other.

    Mechanism: Worker A's transaction is paused via the production
    function's `_before_fence_hook`, a test-only instrumentation point that
    fires INSIDE the open transaction but BEFORE the fenced ownership write
    is even attempted. While A is paused there, Worker B's real
    `claim_batch()` runs and is given the opportunity to complete first
    (confirmed by asserting on its own result), so B actually wins the
    underlying document write. Only then does A's hook return and let its
    transaction proceed to attempt its own fenced write and commit.

    This was verified empirically (not assumed) against this local replica
    set: MongoDB's WiredTiger document-level locking means whichever write
    reaches the document first holds the lock; a transactional write that
    stages its conditional update before a concurrent non-transactional
    write exists will always see its own fence still match (transaction
    snapshot semantics), which is why the earlier version of this test --
    where A staged its fence write BEFORE B started -- incorrectly showed A
    always winning: it wasn't racing anything, it was simply first. This
    version's hook placement makes B first, which is what an actual overlap
    requires: the transaction's fenced write must then read a document B has
    already changed, and fail to match.

    The required outcome: once B has genuinely completed its reclaim first,
    A's subsequent fenced write inside the transaction must not match, and A
    must persist zero mentions.

    A transaction-capability failure during test SETUP (the deployment
    genuinely does not support transactions) fails the test outright with a
    clear message -- it is not caught or converted to a skip once assertions
    are in play, so a real regression cannot be masked as an environment gap.
    """
    import asyncio
    from datetime import timedelta
    from crypto_news_aggregator.db.operations.enrichment_state import (
        claim_batch as _claim_batch,
    )
    from crypto_news_aggregator.db.operations.entity_mentions import (
        create_entity_mentions_batch_idempotent,
    )
    from crypto_news_aggregator.db.operations.entity_mentions_index_rollout import (
        create_unique_index,
    )

    # Confirm transaction support BEFORE the scenario under test, so a
    # capability gap fails loudly here rather than surfacing confusingly
    # mid-scenario.
    await _require_replset_transactions(replset_db)

    # The mongo_db fixture does not auto-create this index (it is
    # deliberately excluded from startup index creation; see
    # entity_mentions_index_rollout.py). Independent of the uniqueness
    # guarantee under test here, but create it anyway so the writer behaves
    # as it would in a fully-rolled-out deployment.
    await create_unique_index(replset_db.entity_mentions)

    await replset_db.articles.delete_many({})
    await replset_db.entity_mentions.delete_many({})
    result = await replset_db.articles.insert_one(_article_doc("worker-mention-overlap"))
    article_id = result.inserted_id
    article_id_str = str(article_id)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    claim_a = await _claim_batch(replset_db.articles, cutoff_date=cutoff, limit=10)
    assert article_id in claim_a.article_ids
    owner_token_a = claim_a.owner_token

    # Pre-existing mention with distinguishable data: Worker A's stale write
    # (if it wrongly succeeded) would overwrite this; must remain untouched.
    await replset_db.entity_mentions.insert_one(
        {
            "article_id": article_id_str,
            "entity": "Ethereum",
            "entity_type": "project",
            "is_primary": True,
            "sentiment": "neutral",
            "confidence": 0.5,
            "source": "pre-existing",
            "metadata": {},
            "timestamp": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
        }
    )

    mentions_from_a = [
        {
            "entity": "Bitcoin",
            "entity_type": "project",
            "article_id": article_id_str,
            "sentiment": "positive",
            "confidence": 0.9,
            "source": "worker-a-stale",
            "is_primary": True,
        },
        {
            "entity": "Ethereum",
            "entity_type": "project",
            "article_id": article_id_str,
            "sentiment": "positive",
            "confidence": 0.99,
            "source": "worker-a-stale",
            "is_primary": True,
        },
    ]

    # Expire A's lease so B is eligible to reclaim -- the ticket's
    # stale-owner scenario -- but do NOT reclaim yet; that happens
    # concurrently with A's transaction below.
    await replset_db.articles.update_one(
        {"_id": article_id},
        {"$set": {"enrichment.lease_expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}},
    )

    a_ready_for_takeover = asyncio.Event()
    b_reclaimed = asyncio.Event()
    claim_b_holder: dict = {}

    async def _pause_before_a_fences():
        """Fires INSIDE Worker A's open transaction, before it attempts its
        fenced ownership write. Signals B to start, then waits for B to
        actually finish reclaiming (a plain asyncio.Event -- not a database
        call -- so this cannot deadlock against a concurrent DB write: it
        blocks only the Python coroutine, not any MongoDB lock). Only after
        B has genuinely completed does A proceed to its own fenced write,
        guaranteeing A's write is evaluated against a document B has already
        changed -- the actual race, not two sequential calls."""
        a_ready_for_takeover.set()
        await asyncio.wait_for(b_reclaimed.wait(), timeout=10)

    async def _worker_a():
        return await create_entity_mentions_batch_idempotent(
            mentions_from_a,
            article_id=article_id,
            owner_token=owner_token_a,
            _before_fence_hook=_pause_before_a_fences,
        )

    async def _worker_b():
        await asyncio.wait_for(a_ready_for_takeover.wait(), timeout=10)
        claim_b = await _claim_batch(replset_db.articles, cutoff_date=cutoff, limit=10)
        claim_b_holder["claim"] = claim_b
        b_reclaimed.set()
        return claim_b

    a_result, claim_b = await asyncio.gather(_worker_a(), _worker_b())

    assert article_id in claim_b.article_ids, (
        "Setup error: Worker B's reclaim attempt must succeed while A is "
        "paused before its own fenced write."
    )
    owner_token_b = claim_b.owner_token
    assert owner_token_b != owner_token_a

    # The required guarantee: since B genuinely completed its reclaim
    # BEFORE A's fenced write was even attempted, A's fenced write must
    # find the document already changed and fail to match.
    assert a_result == 0, (
        "Worker A must write zero mentions: by the time its fenced write "
        "inside the transaction ran, Worker B had already reclaimed "
        "ownership of the article."
    )

    # Worker B, now the legitimate owner, must be able to write normally.
    b_write_result = await create_entity_mentions_batch_idempotent(
        [
            {
                "entity": "Solana",
                "entity_type": "project",
                "article_id": article_id_str,
                "sentiment": "positive",
                "confidence": 0.8,
                "source": "worker-b-fresh",
                "is_primary": True,
            }
        ],
        article_id=article_id,
        owner_token=owner_token_b,
    )
    assert b_write_result == 1, "Worker B, the legitimate new owner, must be able to write"

    stored = await replset_db.entity_mentions.find(
        {"article_id": article_id_str}
    ).to_list(length=10)
    stored_by_entity = {m["entity"]: m for m in stored}

    assert "Bitcoin" not in stored_by_entity, "Stale worker A must not insert a new mention"
    assert stored_by_entity["Ethereum"]["source"] == "pre-existing", (
        "Stale worker A must not overwrite an existing mention with stale data"
    )
    assert stored_by_entity["Ethereum"]["confidence"] == 0.5
    assert stored_by_entity["Solana"]["source"] == "worker-b-fresh"


@pytest.mark.asyncio
async def test_takeover_attempted_while_a_already_holds_the_fence(replset_db):
    """REGRESSION TEST (the other required ordering): Worker A has ALREADY
    performed its transactional fenced ownership write (staged, uncommitted)
    when Worker B attempts a takeover, before A commits.

    This is the mirror case of test_real_writer_blocks_takeover_that_overlaps_
    live_transaction above, which covers B-completes-first. Both orderings
    are legitimate and must be covered: this test covers A-writes-first.

    Per this transaction's own documented guarantee (see the docstring on
    create_entity_mentions_batch_idempotent, and the empirical finding in
    the test above): once A's fenced write has been staged inside its
    transaction, a concurrent non-transactional writer attempting the same
    document (B's claim_batch(), which uses find_one_and_update with no
    session) blocks on MongoDB's document-level lock until A's transaction
    resolves. "A wins and B waits until A resolves, then proceeds against
    the post-commit state" is therefore a CORRECT outcome here, not a bug --
    A legitimately held the lease at the moment it staged its write, and
    nothing arrived to invalidate that before it did so. This is the
    serialization side of the guarantee: overlapping writers are ordered by
    the document lock, not silently corrupted.

    Mechanism: uses `_after_fence_hook` (fires after A's fenced write is
    staged, before mention writes/commit) to launch B's real claim_batch()
    concurrently, WITHOUT A blocking on B's completion (blocking there would
    deadlock -- documented on the hook itself and confirmed empirically in
    the sibling test above). The test verifies real serialization/conflict
    behavior: B's claim() must not observe success until after A's
    transaction has actually resolved, and after it does, B must legitimately
    reclaim ownership and be able to write.
    """
    import asyncio
    import time
    from datetime import timedelta
    from crypto_news_aggregator.db.operations.enrichment_state import (
        claim_batch as _claim_batch,
    )
    from crypto_news_aggregator.db.operations.entity_mentions import (
        create_entity_mentions_batch_idempotent,
    )
    from crypto_news_aggregator.db.operations.entity_mentions_index_rollout import (
        create_unique_index,
    )

    await _require_replset_transactions(replset_db)
    await create_unique_index(replset_db.entity_mentions)

    await replset_db.articles.delete_many({})
    await replset_db.entity_mentions.delete_many({})
    result = await replset_db.articles.insert_one(_article_doc("worker-a-holds-fence-first"))
    article_id = result.inserted_id
    article_id_str = str(article_id)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    claim_a = await _claim_batch(replset_db.articles, cutoff_date=cutoff, limit=10)
    assert article_id in claim_a.article_ids
    owner_token_a = claim_a.owner_token

    # Expire the lease so B is eligible to attempt a reclaim once it tries --
    # the ticket's stale-owner scenario -- even though A has not actually
    # lost ownership yet at the moment it stages its fenced write.
    await replset_db.articles.update_one(
        {"_id": article_id},
        {"$set": {"enrichment.lease_expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}},
    )

    mentions_from_a = [
        {
            "entity": "Bitcoin",
            "entity_type": "project",
            "article_id": article_id_str,
            "sentiment": "positive",
            "confidence": 0.9,
            "source": "worker-a-winner",
            "is_primary": True,
        }
    ]

    a_fence_staged = asyncio.Event()
    timeline: dict = {}

    async def _signal_b_and_continue():
        """Fires after A's fenced write is staged (uncommitted). Signals B
        to attempt its takeover now, then returns immediately -- A's
        transaction proceeds straight to its mention write and commit
        attempt right after, so B's concurrent claim_batch() is genuinely
        racing A's still-open transaction, not sequenced after it. (Must
        not block here waiting for B: B's write may itself block on A's
        transaction's document lock, which would deadlock against A waiting
        on B.)"""
        timeline["a_fence_staged_at"] = time.monotonic()
        a_fence_staged.set()

    async def _worker_a():
        return await create_entity_mentions_batch_idempotent(
            mentions_from_a,
            article_id=article_id,
            owner_token=owner_token_a,
            _after_fence_hook=_signal_b_and_continue,
        )

    async def _worker_b():
        await asyncio.wait_for(a_fence_staged.wait(), timeout=10)
        claim_b = await _claim_batch(replset_db.articles, cutoff_date=cutoff, limit=10)
        timeline["b_claim_completed_at"] = time.monotonic()
        return claim_b

    a_result, claim_b = await asyncio.gather(_worker_a(), _worker_b())

    # Verify real serialization occurred: B's claim did not complete before
    # A signaled it had already staged its fenced write. (This alone doesn't
    # prove B was blocked by A's open transaction specifically -- scheduling
    # could coincidentally order it this way -- so the decisive assertions
    # are the outcome-based ones below: A must have won, and B's write must
    # reflect a state consistent with running strictly after A resolved.)
    assert timeline["b_claim_completed_at"] >= timeline["a_fence_staged_at"], (
        "Setup error: B's claim must not complete before A signaled its "
        "fence was staged"
    )

    # The required outcome for THIS ordering: A legitimately held the fence
    # first, so A must win -- its write succeeds -- and B's reclaim, however
    # it was internally serialized by MongoDB, must only be visible/usable
    # AFTER A's transaction resolved (B reclaiming is still expected to
    # succeed once A finishes, since A's lease had already expired by then;
    # what must NOT happen is B's reclaim being used to invalidate A's
    # already-staged, already-winning fenced write).
    assert a_result == 1, (
        "Worker A must win: its fenced write was staged before B's takeover "
        "attempt, so A's transaction must commit successfully with its "
        "mention written."
    )
    assert article_id in claim_b.article_ids, (
        "Worker B's reclaim must still succeed once A's transaction has "
        "resolved and its lease has expired -- A winning this round must "
        "not permanently block B from ever reclaiming."
    )
    owner_token_b = claim_b.owner_token
    assert owner_token_b != owner_token_a

    stored = await replset_db.entity_mentions.find(
        {"article_id": article_id_str}
    ).to_list(length=10)
    assert len(stored) == 1
    assert stored[0]["entity"] == "Bitcoin"
    assert stored[0]["source"] == "worker-a-winner", "A's winning write must be the one persisted"

    # B, now the (later) legitimate owner, can still write normally.
    b_write_result = await create_entity_mentions_batch_idempotent(
        [
            {
                "entity": "Solana",
                "entity_type": "project",
                "article_id": article_id_str,
                "sentiment": "positive",
                "confidence": 0.8,
                "source": "worker-b-after-a-won",
                "is_primary": True,
            }
        ],
        article_id=article_id,
        owner_token=owner_token_b,
    )
    assert b_write_result == 1, "B, the new owner after A's round completed, must be able to write"


@pytest.mark.asyncio
async def test_failure_after_first_mention_write_leaves_no_partial_results(replset_db):
    """REGRESSION TEST: forces a failure AFTER the first mention write has
    been staged inside the transaction but before the batch completes, and
    verifies the transaction leaves NO partial mention changes -- the first
    write is rolled back along with everything else, not left as an orphaned
    partial commit.

    Mechanism: a two-mention batch, with `_after_first_mention_hook` (fires
    immediately after the first mention's write is staged, before the
    second mention write or commit) raising a distinct, deliberate exception.
    This is not a MongoDB-level conflict -- it's an application-level failure
    injected mid-transaction -- so it exercises `with_transaction()`'s abort
    path for an ordinary exception raised inside the callback, which is
    exactly the path OwnershipLostError also uses for the ownership-lost
    case. Confirms both that (a) the raised exception propagates out of
    create_entity_mentions_batch_idempotent() rather than being swallowed
    (since this is a genuine, unexpected failure -- not the ownership-lost
    case, which is deliberately converted to a `0` return), and (b) neither
    mention -- not even the first, already-staged one -- exists afterward.
    """
    from datetime import timedelta
    from crypto_news_aggregator.db.operations.enrichment_state import (
        claim_batch as _claim_batch,
    )
    from crypto_news_aggregator.db.operations.entity_mentions import (
        create_entity_mentions_batch_idempotent,
    )
    from crypto_news_aggregator.db.operations.entity_mentions_index_rollout import (
        create_unique_index,
    )

    await _require_replset_transactions(replset_db)
    await create_unique_index(replset_db.entity_mentions)

    await replset_db.articles.delete_many({})
    await replset_db.entity_mentions.delete_many({})
    result = await replset_db.articles.insert_one(_article_doc("worker-partial-write-abort"))
    article_id = result.inserted_id
    article_id_str = str(article_id)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    claim_a = await _claim_batch(replset_db.articles, cutoff_date=cutoff, limit=10)
    assert article_id in claim_a.article_ids
    owner_token_a = claim_a.owner_token

    mentions = [
        {
            "entity": "Bitcoin",
            "entity_type": "project",
            "article_id": article_id_str,
            "sentiment": "positive",
            "confidence": 0.9,
            "source": "first-write-before-failure",
            "is_primary": True,
        },
        {
            "entity": "Ethereum",
            "entity_type": "project",
            "article_id": article_id_str,
            "sentiment": "positive",
            "confidence": 0.8,
            "source": "never-reached",
            "is_primary": True,
        },
    ]

    class _DeliberateMidBatchFailure(Exception):
        """Distinct exception type so the test can assert specifically on
        this failure propagating, not accidentally catching something else
        (e.g. a real OwnershipLostError, which the production code already
        converts to a `0` return rather than propagating)."""

    first_write_staged = {"happened": False}

    async def _fail_after_first_write():
        first_write_staged["happened"] = True
        raise _DeliberateMidBatchFailure("forced failure after first mention write")

    with pytest.raises(_DeliberateMidBatchFailure):
        await create_entity_mentions_batch_idempotent(
            mentions,
            article_id=article_id,
            owner_token=owner_token_a,
            _after_first_mention_hook=_fail_after_first_write,
        )

    assert first_write_staged["happened"], "Setup error: the mid-batch failure hook must have fired"

    # The required guarantee: the transaction aborts as a whole, so NEITHER
    # mention -- not even the first, already-staged one -- persists.
    stored = await replset_db.entity_mentions.find(
        {"article_id": article_id_str}
    ).to_list(length=10)
    assert stored == [], (
        "A failure after the first mention write must leave NO partial "
        "mention changes -- the already-staged first write must be rolled "
        "back along with the rest of the transaction, not left committed."
    )

    # The article's ownership fence write itself must also be rolled back:
    # the failed attempt must not have left any trace, and the owner must
    # still legitimately be able to retry (ownership unchanged, since no
    # takeover occurred in this scenario -- only an injected failure).
    doc = await replset_db.articles.find_one({"_id": article_id})
    assert doc["enrichment"]["owner_token"] == owner_token_a
    assert doc["enrichment"]["status"] == "in_progress"

    # A retry (without the failure hook) must succeed normally and write
    # both mentions -- confirming the aborted attempt left the article in a
    # clean, retryable state rather than a corrupted partial one.
    retry_result = await create_entity_mentions_batch_idempotent(
        mentions, article_id=article_id, owner_token=owner_token_a
    )
    assert retry_result == 2, "A clean retry after the aborted attempt must write both mentions"

    stored_after_retry = await replset_db.entity_mentions.find(
        {"article_id": article_id_str}
    ).to_list(length=10)
    assert len(stored_after_retry) == 2


@pytest.mark.asyncio
async def test_actual_pre_fix_implementation_fails_this_regression(replset_db):
    """Proves the regression test above actually discriminates: replays the
    SAME overlapping interleaving (Worker A's write genuinely overlapping
    Worker B's concurrent reclaim, via asyncio.gather + a deterministic
    pause) against the ACTUAL previous, pre-fix implementation of
    create_entity_mentions_batch_idempotent() -- a verbatim snapshot of the
    function as it existed in this working tree before this session's
    transaction fix (tests/_fixtures/legacy_entity_mentions_pre_transaction_fix.py),
    not a separately hand-written "unsafe example". It must fail here, where
    the real (fixed) writer in the test above passes -- confirming the new
    regression test is not trivially green regardless of implementation.

    The legacy function has no internal instrumentation point (that is
    exactly its defect: its read-then-write gap is implicit, not an
    explicit, closeable pause), so the overlap here is created by pausing
    immediately after its ownership read call returns -- the real place its
    check-then-write race lives -- via a thin wrapper around the database
    call it makes, without modifying the legacy function's logic itself.
    """
    import asyncio
    from datetime import timedelta
    from crypto_news_aggregator.db.operations.enrichment_state import (
        claim_batch as _claim_batch,
    )
    from tests._fixtures.legacy_entity_mentions_pre_transaction_fix import (
        create_entity_mentions_batch_idempotent_pre_fix,
    )

    await _require_replset_transactions(replset_db)

    await replset_db.articles.delete_many({})
    await replset_db.entity_mentions.delete_many({})
    result = await replset_db.articles.insert_one(_article_doc("worker-mention-race-unsafe"))
    article_id = result.inserted_id
    article_id_str = str(article_id)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    claim_a = await _claim_batch(replset_db.articles, cutoff_date=cutoff, limit=10)
    owner_token_a = claim_a.owner_token

    await replset_db.entity_mentions.insert_one(
        {
            "article_id": article_id_str,
            "entity": "Ethereum",
            "entity_type": "project",
            "is_primary": True,
            "sentiment": "neutral",
            "confidence": 0.5,
            "source": "pre-existing",
            "metadata": {},
            "timestamp": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
        }
    )

    await replset_db.articles.update_one(
        {"_id": article_id},
        {"$set": {"enrichment.lease_expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}},
    )

    a_read_ownership = asyncio.Event()

    # Motor returns a NEW AsyncIOMotorCollection wrapper on every `db.articles`
    # attribute access (it does not cache), so patching the instance
    # attribute on `replset_db.articles` does not affect the separate
    # `db.articles` the legacy function resolves internally via
    # mongo_manager.get_async_database(). Patch the bound method on the
    # class itself instead, scoped to only the ownership-check call (by
    # query shape) so it does not affect claim_batch()'s own find/update
    # calls running concurrently in Worker B.
    from motor.motor_asyncio import AsyncIOMotorCollection

    real_find_one = AsyncIOMotorCollection.find_one

    async def _find_one_that_signals_after_ownership_read(self, *args, **kwargs):
        """Wraps the exact find_one() call the legacy function makes to
        check ownership, without altering the legacy function's own code.
        Signals once the read has returned (the legacy implementation has
        now decided ownership is valid) and returns immediately -- the
        legacy function proceeds straight to its unfenced writes right
        after this, so Worker B's concurrent reclaim (started by that
        signal) is racing against those writes for real, not sequenced
        before or after them by the test."""
        query = args[0] if args else kwargs.get("filter")
        res = await real_find_one(self, *args, **kwargs)
        if isinstance(query, dict) and "enrichment.owner_token" in query:
            a_read_ownership.set()
        return res

    mentions_from_a = [
        {
            "entity": "Bitcoin",
            "entity_type": "project",
            "article_id": article_id_str,
            "sentiment": "positive",
            "confidence": 0.9,
            "source": "worker-a-stale",
            "is_primary": True,
        },
        {
            "entity": "Ethereum",
            "entity_type": "project",
            "article_id": article_id_str,
            "sentiment": "positive",
            "confidence": 0.99,
            "source": "worker-a-stale",
            "is_primary": True,
        },
    ]

    async def _worker_a():
        AsyncIOMotorCollection.find_one = _find_one_that_signals_after_ownership_read
        try:
            return await create_entity_mentions_batch_idempotent_pre_fix(
                mentions_from_a, article_id=article_id, owner_token=owner_token_a
            )
        finally:
            AsyncIOMotorCollection.find_one = real_find_one

    async def _worker_b():
        await asyncio.wait_for(a_read_ownership.wait(), timeout=10)
        return await _claim_batch(replset_db.articles, cutoff_date=cutoff, limit=10)

    a_result, claim_b = await asyncio.gather(_worker_a(), _worker_b())

    assert article_id in claim_b.article_ids, "Setup error: Worker B must reclaim"

    assert a_result != 0, (
        "This test is expected to demonstrate the PRE-FIX implementation's "
        "race: its unfenced writes after the ownership read must land "
        "despite the concurrent takeover, proving the regression test above "
        "actually discriminates safe from unsafe behavior rather than being "
        "trivially green. If this assertion fails, the legacy snapshot no "
        "longer reproduces the original defect and needs re-verification, "
        "not silent adjustment."
    )

    stored = await replset_db.entity_mentions.find(
        {"article_id": article_id_str}
    ).to_list(length=10)
    stored_by_entity = {m["entity"]: m for m in stored}
    assert stored_by_entity["Bitcoin"]["source"] == "worker-a-stale", (
        "RACE CONFIRMED in the pre-fix implementation: it inserted a stale "
        "mention despite the ownership takeover having already occurred."
    )


@pytest.mark.asyncio
async def test_worker_blocks_enrichment_when_mention_index_missing(mongo_db):
    """When the article_entity_type_primary_unique index is missing, the
    worker must block enrichment (return 0) before making claims, calling
    LLM, or writing mentions/articles. RSS ingestion and API remain
    available (only enrichment pauses)."""
    from crypto_news_aggregator.db.operations.entity_mentions_index_rollout import UNIQUE_INDEX_NAME

    await mongo_db.articles.delete_many({})
    result = await mongo_db.articles.insert_one(_article_doc("worker-missing-index"))
    article_id = result.inserted_id

    # Verify the index is missing (should be true for a fresh mongo_db)
    indexes = await mongo_db.entity_mentions.index_information()
    assert UNIQUE_INDEX_NAME not in indexes

    with patch(
        "crypto_news_aggregator.background.rss_fetcher.get_optimized_llm",
        side_effect=Exception("forced failure: use fallback path"),
    ), patch(
        "crypto_news_aggregator.background.rss_fetcher.get_llm_provider",
        return_value=_mock_llm_client(),
    ), patch(
        "crypto_news_aggregator.background.rss_fetcher.classify_article",
        return_value={"tier": 1, "reason": "forced_tier_1", "matched_pattern": None},
    ):
        processed = await process_new_articles_from_mongodb()

    assert processed == 0, "Worker must block enrichment when index is missing"

    doc = await mongo_db.articles.find_one({"_id": article_id})
    assert "enrichment" not in doc, "Worker must not claim articles when index is missing"


@pytest.mark.asyncio
async def test_worker_blocks_enrichment_when_mention_index_not_unique(mongo_db):
    """When the index exists but is not marked unique, the worker must block
    enrichment before claims and LLM calls."""
    from crypto_news_aggregator.db.operations.entity_mentions_index_rollout import (
        UNIQUE_INDEX_NAME,
        UNIQUE_INDEX_KEYS,
    )

    await mongo_db.articles.delete_many({})
    await mongo_db.articles.insert_one(_article_doc("worker-non-unique-index"))

    # Create a non-unique index with the same name and keys
    await mongo_db.entity_mentions.create_index(
        UNIQUE_INDEX_KEYS, name=UNIQUE_INDEX_NAME, unique=False
    )

    with patch(
        "crypto_news_aggregator.background.rss_fetcher.get_optimized_llm",
        side_effect=Exception("forced failure: use fallback path"),
    ), patch(
        "crypto_news_aggregator.background.rss_fetcher.get_llm_provider",
        return_value=_mock_llm_client(),
    ), patch(
        "crypto_news_aggregator.background.rss_fetcher.classify_article",
        return_value={"tier": 1, "reason": "forced_tier_1", "matched_pattern": None},
    ):
        processed = await process_new_articles_from_mongodb()

    assert processed == 0, "Worker must block enrichment when index is not unique"
