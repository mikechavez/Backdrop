"""Tests for DependencyGraph v1."""

import pytest

from crypto_news_aggregator.bugops.dependency_graph import DependencyGraph
from crypto_news_aggregator.bugops.models import BugOpsSubsystem


class TestDependencyGraphInstantiation:
    """Test graph instantiation and version."""

    def test_instantiate_no_args(self):
        """DependencyGraph is instantiatable with no arguments."""
        graph = DependencyGraph()
        assert graph is not None

    def test_version_is_1_0(self):
        """VERSION class attribute is 1.0."""
        assert DependencyGraph.VERSION == "1.0"


class TestUpstreamTraversal:
    """Test get_upstream_nodes() for all graph nodes."""

    @pytest.fixture
    def graph(self):
        return DependencyGraph()

    def test_upstream_scheduler_is_empty(self, graph):
        """Root node scheduler has no upstream."""
        assert graph.get_upstream_nodes("scheduler") == []

    def test_upstream_ingestion(self, graph):
        """Upstream of ingestion is [scheduler]."""
        assert graph.get_upstream_nodes("ingestion") == ["scheduler"]

    def test_upstream_articles(self, graph):
        """Upstream of articles is [ingestion, scheduler]."""
        assert graph.get_upstream_nodes("articles") == ["ingestion", "scheduler"]

    def test_upstream_signals(self, graph):
        """Upstream of signals is [articles, ingestion, scheduler]."""
        assert graph.get_upstream_nodes("signals") == [
            "articles",
            "ingestion",
            "scheduler",
        ]

    def test_upstream_narratives(self, graph):
        """Upstream of narratives is [signals, articles, ingestion, scheduler]."""
        assert graph.get_upstream_nodes("narratives") == [
            "signals",
            "articles",
            "ingestion",
            "scheduler",
        ]

    def test_upstream_briefings(self, graph):
        """Upstream of briefings is [narratives, signals, articles, ingestion, scheduler]."""
        assert graph.get_upstream_nodes("briefings") == [
            "narratives",
            "signals",
            "articles",
            "ingestion",
            "scheduler",
        ]


class TestDownstreamTraversal:
    """Test get_downstream_nodes() for all graph nodes."""

    @pytest.fixture
    def graph(self):
        return DependencyGraph()

    def test_downstream_scheduler(self, graph):
        """Downstream of scheduler is [ingestion, articles, signals, narratives, briefings]."""
        assert graph.get_downstream_nodes("scheduler") == [
            "ingestion",
            "articles",
            "signals",
            "narratives",
            "briefings",
        ]

    def test_downstream_ingestion(self, graph):
        """Downstream of ingestion is [articles, signals, narratives, briefings]."""
        assert graph.get_downstream_nodes("ingestion") == [
            "articles",
            "signals",
            "narratives",
            "briefings",
        ]

    def test_downstream_articles(self, graph):
        """Downstream of articles is [signals, narratives, briefings]."""
        assert graph.get_downstream_nodes("articles") == [
            "signals",
            "narratives",
            "briefings",
        ]

    def test_downstream_signals(self, graph):
        """Downstream of signals is [narratives, briefings]."""
        assert graph.get_downstream_nodes("signals") == ["narratives", "briefings"]

    def test_downstream_narratives(self, graph):
        """Downstream of narratives is [briefings]."""
        assert graph.get_downstream_nodes("narratives") == ["briefings"]

    def test_downstream_briefings_is_empty(self, graph):
        """Leaf node briefings has no downstream."""
        assert graph.get_downstream_nodes("briefings") == []


class TestReservedSubsystems:
    """Test reserved subsystems not in v1 graph (worker, database)."""

    @pytest.fixture
    def graph(self):
        return DependencyGraph()

    def test_upstream_worker_is_empty(self, graph):
        """worker is reserved but not in graph; upstream returns []."""
        assert graph.get_upstream_nodes("worker") == []

    def test_downstream_database_is_empty(self, graph):
        """database is reserved but not in graph; downstream returns []."""
        assert graph.get_downstream_nodes("database") == []

    def test_upstream_database_is_empty(self, graph):
        """database is reserved but not in graph; upstream returns []."""
        assert graph.get_upstream_nodes("database") == []

    def test_downstream_worker_is_empty(self, graph):
        """worker is reserved but not in graph; downstream returns []."""
        assert graph.get_downstream_nodes("worker") == []


class TestUnknownSubsystems:
    """Test unknown/invalid subsystems."""

    @pytest.fixture
    def graph(self):
        return DependencyGraph()

    def test_upstream_unknown_subsystem(self, graph):
        """Unknown subsystem returns [] for upstream."""
        assert graph.get_upstream_nodes("unknown_subsystem") == []

    def test_downstream_unknown_subsystem(self, graph):
        """Unknown subsystem returns [] for downstream."""
        assert graph.get_downstream_nodes("unknown_subsystem") == []

    def test_upstream_empty_string(self, graph):
        """Empty string returns [] for upstream."""
        assert graph.get_upstream_nodes("") == []

    def test_downstream_empty_string(self, graph):
        """Empty string returns [] for downstream."""
        assert graph.get_downstream_nodes("") == []

    def test_upstream_typo_subsystem(self, graph):
        """Typo in subsystem name returns [] for upstream."""
        assert graph.get_upstream_nodes("article") == []

    def test_downstream_typo_subsystem(self, graph):
        """Typo in subsystem name returns [] for downstream."""
        assert graph.get_downstream_nodes("signalss") == []


class TestEnumInputs:
    """Test that both string and BugOpsSubsystem enum inputs work correctly."""

    @pytest.fixture
    def graph(self):
        return DependencyGraph()

    def test_upstream_with_enum_signals(self, graph):
        """get_upstream_nodes() accepts BugOpsSubsystem.SIGNALS enum."""
        result = graph.get_upstream_nodes(BugOpsSubsystem.SIGNALS)
        assert result == ["articles", "ingestion", "scheduler"]

    def test_upstream_with_enum_articles(self, graph):
        """get_upstream_nodes() accepts BugOpsSubsystem.ARTICLES enum."""
        result = graph.get_upstream_nodes(BugOpsSubsystem.ARTICLES)
        assert result == ["ingestion", "scheduler"]

    def test_upstream_with_enum_briefings(self, graph):
        """get_upstream_nodes() accepts BugOpsSubsystem.BRIEFINGS enum."""
        result = graph.get_upstream_nodes(BugOpsSubsystem.BRIEFINGS)
        assert result == [
            "narratives",
            "signals",
            "articles",
            "ingestion",
            "scheduler",
        ]

    def test_upstream_with_enum_scheduler(self, graph):
        """get_upstream_nodes() accepts BugOpsSubsystem.SCHEDULER (root, no upstream)."""
        result = graph.get_upstream_nodes(BugOpsSubsystem.SCHEDULER)
        assert result == []

    def test_downstream_with_enum_articles(self, graph):
        """get_downstream_nodes() accepts BugOpsSubsystem.ARTICLES enum."""
        result = graph.get_downstream_nodes(BugOpsSubsystem.ARTICLES)
        assert result == ["signals", "narratives", "briefings"]

    def test_downstream_with_enum_scheduler(self, graph):
        """get_downstream_nodes() accepts BugOpsSubsystem.SCHEDULER enum."""
        result = graph.get_downstream_nodes(BugOpsSubsystem.SCHEDULER)
        assert result == [
            "ingestion",
            "articles",
            "signals",
            "narratives",
            "briefings",
        ]

    def test_downstream_with_enum_briefings(self, graph):
        """get_downstream_nodes() accepts BugOpsSubsystem.BRIEFINGS enum (leaf, no downstream)."""
        result = graph.get_downstream_nodes(BugOpsSubsystem.BRIEFINGS)
        assert result == []

    def test_upstream_with_enum_worker_reserved(self, graph):
        """get_upstream_nodes() accepts BugOpsSubsystem.WORKER (reserved, not in graph)."""
        result = graph.get_upstream_nodes(BugOpsSubsystem.WORKER)
        assert result == []

    def test_downstream_with_enum_database_reserved(self, graph):
        """get_downstream_nodes() accepts BugOpsSubsystem.DATABASE (reserved, not in graph)."""
        result = graph.get_downstream_nodes(BugOpsSubsystem.DATABASE)
        assert result == []

    def test_string_and_enum_equivalence_signals(self, graph):
        """String and enum inputs produce identical results for signals."""
        string_result = graph.get_upstream_nodes("signals")
        enum_result = graph.get_upstream_nodes(BugOpsSubsystem.SIGNALS)
        assert string_result == enum_result

    def test_string_and_enum_equivalence_articles_downstream(self, graph):
        """String and enum inputs produce identical downstream results for articles."""
        string_result = graph.get_downstream_nodes("articles")
        enum_result = graph.get_downstream_nodes(BugOpsSubsystem.ARTICLES)
        assert string_result == enum_result
