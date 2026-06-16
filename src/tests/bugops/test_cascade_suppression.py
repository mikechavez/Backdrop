"""Integration tests for cascade suppression processing order (TASK-108)."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from crypto_news_aggregator.bugops.monitor import BugOpsMonitor
from crypto_news_aggregator.bugops.models import BugCase, BugCaseCreate, AlertSeverity
from crypto_news_aggregator.bugops.dependency_graph import DependencyGraph


@pytest.fixture
def mock_settings():
    """Mock BugOps settings."""
    settings = MagicMock()
    settings.BUGOPS_ENABLED = True
    settings.BUGOPS_SLACK_ENABLED = False
    settings.BUGOPS_POLL_INTERVAL_SECONDS = 60
    return settings


@pytest.fixture
def mock_detectors():
    """Create mock freshness detectors."""
    detectors = []

    # Map subsystems to source_type names (note: "articles" → "article_freshness" not "articles_freshness")
    config = [
        ("articles", "article_freshness"),
        ("signals", "signal_freshness"),
        ("narratives", "narrative_freshness"),
        ("briefings", "briefing_freshness"),
    ]
    for subsystem, source_type in config:
        detector = MagicMock()
        detector.source_type = source_type
        detector.root_subsystem = subsystem
        detector.severity = AlertSeverity.HIGH
        detector.dedupe_key = f"{source_type}:{subsystem}"
        detector.suggested_manual_check = f"Check {subsystem} health"
        detector.check_failure = AsyncMock(return_value=False)  # Default: no failure
        detectors.append(detector)

    return detectors


@pytest.fixture
def monitor_with_mocks(mock_settings, mock_detectors):
    """Create a monitor with mocked dependencies."""
    with patch.object(BugOpsMonitor, '__init__', lambda x: None):
        monitor = BugOpsMonitor()
        monitor.settings = mock_settings
        monitor.store = AsyncMock()
        monitor.signal_sources = []
        monitor.running = False
        monitor.dependency_graph = DependencyGraph()
        monitor.freshness_detectors = mock_detectors
        monitor.detector_by_subsystem = {d.root_subsystem: d for d in mock_detectors}
        monitor.is_first_poll = True
    return monitor


class TestCascadeSuppressionOrder:
    """Test cascade suppression processing order: upstream → dedupe → create."""

    @pytest.mark.asyncio
    async def test_upstream_case_exists_suppresses_new_case(self, monitor_with_mocks):
        """Step 2: If upstream BugCase exists, attach observation and stop."""
        # Setup: articles detector fails, ingestion case exists upstream
        monitor_with_mocks.freshness_detectors[0].check_failure = AsyncMock(
            return_value=True
        )

        upstream_case = BugCase(
            case_id="bc_ingestion_123",
            status="open",
            root_subsystem="ingestion",
            affected_subsystems=[],
            **{
                "severity": AlertSeverity.HIGH,
                "alert_type": "ingestion_failure",
                "title": "Ingestion Failure",
                "summary": "Ingestion failed",
                "dedupe_key": "test",
                "source_types": ["test"],
                "first_seen_at": datetime.utcnow(),
                "last_seen_at": datetime.utcnow(),
            }
        )
        monitor_with_mocks.store.find_open_case_by_root_subsystem = AsyncMock(
            return_value=upstream_case
        )
        monitor_with_mocks.store.attach_observation_to_case = AsyncMock()
        monitor_with_mocks.store.create_case_direct = AsyncMock()

        # Act
        await monitor_with_mocks._poll_freshness_detectors()

        # Assert
        # Should check upstream
        monitor_with_mocks.store.find_open_case_by_root_subsystem.assert_called()
        # Should attach to upstream case
        monitor_with_mocks.store.attach_observation_to_case.assert_called_once()
        call_args = monitor_with_mocks.store.attach_observation_to_case.call_args
        assert call_args[0][0] == upstream_case.case_id
        assert "articles" in call_args[1]["affected_subsystems"]
        # Should NOT create new case
        monitor_with_mocks.store.create_case_direct.assert_not_called()

    @pytest.mark.asyncio
    async def test_dedupe_key_suppresses_new_case(self, monitor_with_mocks):
        """Step 3: If open case with same dedupe_key exists, attach and stop."""
        # Setup: articles detector fails, no upstream case, but existing case with same dedupe_key
        monitor_with_mocks.freshness_detectors[0].check_failure = AsyncMock(
            return_value=True
        )
        monitor_with_mocks.store.find_open_case_by_root_subsystem = AsyncMock(
            return_value=None
        )

        existing_case = BugCase(
            case_id="bc_articles_123",
            status="open",
            root_subsystem="articles",
            dedupe_key="article_freshness:articles",
            affected_subsystems=[],
            **{
                "severity": AlertSeverity.HIGH,
                "alert_type": "article_freshness",
                "title": "Article Freshness",
                "summary": "Articles stalled",
                "source_types": ["article_freshness"],
                "first_seen_at": datetime.utcnow(),
                "last_seen_at": datetime.utcnow(),
            }
        )
        monitor_with_mocks.store.find_open_case_by_dedupe_key = AsyncMock(
            return_value=existing_case
        )
        monitor_with_mocks.store.attach_observation_to_case = AsyncMock()
        monitor_with_mocks.store.create_case_direct = AsyncMock()

        # Act
        await monitor_with_mocks._poll_freshness_detectors()

        # Assert
        # Should check dedupe_key
        monitor_with_mocks.store.find_open_case_by_dedupe_key.assert_called_with(
            "article_freshness:articles"
        )
        # Should attach to existing case
        monitor_with_mocks.store.attach_observation_to_case.assert_called_once()
        call_args = monitor_with_mocks.store.attach_observation_to_case.call_args
        assert call_args[0][0] == existing_case.case_id
        # Should NOT create new case
        monitor_with_mocks.store.create_case_direct.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_upstream_or_dedupe_creates_new_case(self, monitor_with_mocks):
        """Step 4: If no upstream or dedupe match, create new BugCase."""
        # Setup: articles detector fails, no upstream, no dedupe match
        monitor_with_mocks.freshness_detectors[0].check_failure = AsyncMock(
            return_value=True
        )
        monitor_with_mocks.store.find_open_case_by_root_subsystem = AsyncMock(
            return_value=None
        )
        monitor_with_mocks.store.find_open_case_by_dedupe_key = AsyncMock(
            return_value=None
        )

        new_case = BugCase(
            case_id="bc_articles_new",
            status="open",
            root_subsystem="articles",
            affected_subsystems=[],
            **{
                "severity": AlertSeverity.HIGH,
                "alert_type": "article_freshness",
                "title": "Article Freshness Failure",
                "summary": "No articles output within expected window.",
                "dedupe_key": "article_freshness:articles",
                "source_types": ["article_freshness"],
                "first_seen_at": datetime.utcnow(),
                "last_seen_at": datetime.utcnow(),
                "detection_type": "startup",
            }
        )
        monitor_with_mocks.store.create_case_direct = AsyncMock(return_value=new_case)

        # Act
        await monitor_with_mocks._poll_freshness_detectors()

        # Assert
        monitor_with_mocks.store.create_case_direct.assert_called_once()
        call_args = monitor_with_mocks.store.create_case_direct.call_args
        case_create = call_args[0][0]
        assert case_create.root_subsystem == "articles"
        assert case_create.dedupe_key == "article_freshness:articles"
        assert case_create.severity == AlertSeverity.HIGH


class TestDetectionTypeAssignment:
    """Test detection_type assignment: startup on first poll, runtime thereafter."""

    @pytest.mark.asyncio
    async def test_detection_type_startup_on_first_poll(self, monitor_with_mocks):
        """detection_type should be 'startup' when is_first_poll=True."""
        monitor_with_mocks.freshness_detectors[0].check_failure = AsyncMock(
            return_value=True
        )
        monitor_with_mocks.store.find_open_case_by_root_subsystem = AsyncMock(
            return_value=None
        )
        monitor_with_mocks.store.find_open_case_by_dedupe_key = AsyncMock(
            return_value=None
        )
        monitor_with_mocks.store.create_case_direct = AsyncMock()
        monitor_with_mocks.is_first_poll = True

        # Act
        await monitor_with_mocks._poll_freshness_detectors()

        # Assert
        call_args = monitor_with_mocks.store.create_case_direct.call_args
        case_create = call_args[0][0]
        assert case_create.detection_type == "startup"

    @pytest.mark.asyncio
    async def test_detection_type_runtime_on_subsequent_polls(self, monitor_with_mocks):
        """detection_type should be 'runtime' when is_first_poll=False."""
        monitor_with_mocks.freshness_detectors[0].check_failure = AsyncMock(
            return_value=True
        )
        monitor_with_mocks.store.find_open_case_by_root_subsystem = AsyncMock(
            return_value=None
        )
        monitor_with_mocks.store.find_open_case_by_dedupe_key = AsyncMock(
            return_value=None
        )
        monitor_with_mocks.store.create_case_direct = AsyncMock()
        monitor_with_mocks.is_first_poll = False

        # Act
        await monitor_with_mocks._poll_freshness_detectors()

        # Assert
        call_args = monitor_with_mocks.store.create_case_direct.call_args
        case_create = call_args[0][0]
        assert case_create.detection_type == "runtime"

    @pytest.mark.asyncio
    async def test_is_first_poll_flips_after_detector_cycle(self, monitor_with_mocks):
        """is_first_poll should be False after first complete detector cycle."""
        # No detectors fail - just test the flip
        for detector in monitor_with_mocks.freshness_detectors:
            detector.check_failure = AsyncMock(return_value=False)

        monitor_with_mocks.is_first_poll = True

        # Act
        await monitor_with_mocks._poll_freshness_detectors()

        # Assert
        assert monitor_with_mocks.is_first_poll is False


class TestBlastRadiusPopulation:
    """Test blast_radius is populated from DependencyGraph.get_downstream_nodes()."""

    @pytest.mark.asyncio
    async def test_blast_radius_populated_on_new_case(self, monitor_with_mocks):
        """blast_radius should be populated from DependencyGraph."""
        # Setup: articles detector fails, no upstream/dedupe match
        monitor_with_mocks.freshness_detectors[0].check_failure = AsyncMock(
            return_value=True
        )
        monitor_with_mocks.store.find_open_case_by_root_subsystem = AsyncMock(
            return_value=None
        )
        monitor_with_mocks.store.find_open_case_by_dedupe_key = AsyncMock(
            return_value=None
        )
        monitor_with_mocks.store.create_case_direct = AsyncMock()

        # Act
        await monitor_with_mocks._poll_freshness_detectors()

        # Assert
        call_args = monitor_with_mocks.store.create_case_direct.call_args
        case_create = call_args[0][0]
        # Articles downstream: signals, narratives, briefings
        expected_downstream = ["signals", "narratives", "briefings"]
        assert case_create.blast_radius == expected_downstream


class TestAffectedSubsystemsOnUpstreamAttachment:
    """Test affected_subsystems are populated when attaching to upstream case."""

    @pytest.mark.asyncio
    async def test_affected_subsystems_added_on_upstream_attach(self, monitor_with_mocks):
        """When attaching to upstream case, affected_subsystems should include detector's root_subsystem."""
        # Setup: articles fails, ingestion case exists upstream
        monitor_with_mocks.freshness_detectors[0].check_failure = AsyncMock(
            return_value=True
        )

        upstream_case = BugCase(
            case_id="bc_ingestion_123",
            status="open",
            root_subsystem="ingestion",
            affected_subsystems=[],
            **{
                "severity": AlertSeverity.HIGH,
                "alert_type": "ingestion_failure",
                "title": "Ingestion Failure",
                "summary": "Ingestion failed",
                "dedupe_key": "test",
                "source_types": ["test"],
                "first_seen_at": datetime.utcnow(),
                "last_seen_at": datetime.utcnow(),
            }
        )
        monitor_with_mocks.store.find_open_case_by_root_subsystem = AsyncMock(
            return_value=upstream_case
        )
        monitor_with_mocks.store.attach_observation_to_case = AsyncMock()

        # Act
        await monitor_with_mocks._poll_freshness_detectors()

        # Assert
        call_args = monitor_with_mocks.store.attach_observation_to_case.call_args
        assert call_args[1]["affected_subsystems"] == ["articles"]


class TestDetectorExceptionIsolation:
    """Test detector failures do not halt the loop or prevent other detectors from running."""

    @pytest.mark.asyncio
    async def test_detector_exception_does_not_halt_loop(self, monitor_with_mocks):
        """If one detector throws, other detectors should still run."""
        # Setup: first detector throws, second detector fails normally
        monitor_with_mocks.freshness_detectors[0].check_failure = AsyncMock(
            side_effect=RuntimeError("Detector crashed")
        )
        monitor_with_mocks.freshness_detectors[1].check_failure = AsyncMock(
            return_value=True
        )

        monitor_with_mocks.store.find_open_case_by_root_subsystem = AsyncMock(
            return_value=None
        )
        monitor_with_mocks.store.find_open_case_by_dedupe_key = AsyncMock(
            return_value=None
        )
        monitor_with_mocks.store.create_case_direct = AsyncMock()

        # Act - should not raise
        await monitor_with_mocks._poll_freshness_detectors()

        # Assert - second detector still processed
        assert monitor_with_mocks.store.create_case_direct.call_count >= 1


class TestProcessingOrderEnforcement:
    """Test that processing order is deterministic: upstream always before dedupe."""

    @pytest.mark.asyncio
    async def test_upstream_check_before_dedupe_check(self, monitor_with_mocks):
        """Upstream check must happen before dedupe check."""
        # Setup: both upstream and dedupe matches exist (shouldn't happen, but test the order)
        monitor_with_mocks.freshness_detectors[0].check_failure = AsyncMock(
            return_value=True
        )

        upstream_case = BugCase(
            case_id="bc_ingestion_123",
            status="open",
            root_subsystem="ingestion",
            affected_subsystems=[],
            **{
                "severity": AlertSeverity.HIGH,
                "alert_type": "test",
                "title": "Test",
                "summary": "Test",
                "dedupe_key": "test",
                "source_types": ["test"],
                "first_seen_at": datetime.utcnow(),
                "last_seen_at": datetime.utcnow(),
            }
        )
        dedupe_case = BugCase(
            case_id="bc_articles_123",
            status="open",
            root_subsystem="articles",
            affected_subsystems=[],
            **{
                "severity": AlertSeverity.HIGH,
                "alert_type": "test",
                "title": "Test",
                "summary": "Test",
                "dedupe_key": "article_freshness:articles",
                "source_types": ["test"],
                "first_seen_at": datetime.utcnow(),
                "last_seen_at": datetime.utcnow(),
            }
        )

        monitor_with_mocks.store.find_open_case_by_root_subsystem = AsyncMock(
            return_value=upstream_case
        )
        monitor_with_mocks.store.find_open_case_by_dedupe_key = AsyncMock(
            return_value=dedupe_case
        )
        monitor_with_mocks.store.attach_observation_to_case = AsyncMock()

        # Act
        await monitor_with_mocks._poll_freshness_detectors()

        # Assert: should use upstream case, not dedupe case
        call_args = monitor_with_mocks.store.attach_observation_to_case.call_args
        assert call_args[0][0] == upstream_case.case_id
        # dedupe check should not be called because upstream was found
        monitor_with_mocks.store.find_open_case_by_dedupe_key.assert_not_called()
