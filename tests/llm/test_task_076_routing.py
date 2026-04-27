"""
Tests for TASK-076: RoutingStrategy Implementation — Complete + Wire Routing Into Gateway
"""

import pytest
from src.crypto_news_aggregator.llm.gateway import (
    RoutingStrategy,
    _get_routing_strategy,
    _OPERATION_ROUTING,
)


class TestRoutingStrategySelect:
    """Test RoutingStrategy.select() method."""

    def test_select_no_variant_returns_primary(self):
        """If variant is None, select() always returns primary."""
        strategy = RoutingStrategy(
            "test_op",
            primary="anthropic:haiku",
            variant=None,
            variant_ratio=0.5
        )
        assert strategy.select("key_1") == "anthropic:haiku"
        assert strategy.select("key_2") == "anthropic:haiku"
        assert strategy.select("key_3") == "anthropic:haiku"

    def test_select_zero_ratio_returns_primary(self):
        """If variant_ratio is 0, select() always returns primary."""
        strategy = RoutingStrategy(
            "test_op",
            primary="anthropic:haiku",
            variant="gemini:flash",
            variant_ratio=0.0
        )
        assert strategy.select("key_1") == "anthropic:haiku"
        assert strategy.select("key_2") == "anthropic:haiku"
        assert strategy.select("key_3") == "anthropic:haiku"

    def test_select_deterministic(self):
        """Same key → same output (determinism)."""
        strategy = RoutingStrategy(
            "test_op",
            primary="anthropic:haiku",
            variant="gemini:flash",
            variant_ratio=0.5
        )
        key = "entity_extraction:trace_abc123"
        result1 = strategy.select(key)
        result2 = strategy.select(key)
        assert result1 == result2

    def test_select_50_50_split(self):
        """With variant_ratio=0.5, roughly 50% go to each model."""
        strategy = RoutingStrategy(
            "test_op",
            primary="anthropic:haiku",
            variant="gemini:flash",
            variant_ratio=0.5
        )

        variant_count = 0
        for i in range(100):
            key = f"test_op:trace_{i}"
            if strategy.select(key) == "gemini:flash":
                variant_count += 1

        assert 40 <= variant_count <= 60, f"Expected 40-60 variants, got {variant_count}"

    def test_select_75_25_split(self):
        """With variant_ratio=0.25, roughly 25% go to variant."""
        strategy = RoutingStrategy(
            "test_op",
            primary="anthropic:haiku",
            variant="gemini:flash",
            variant_ratio=0.25
        )

        variant_count = 0
        for i in range(100):
            key = f"test_op:trace_{i}"
            if strategy.select(key) == "gemini:flash":
                variant_count += 1

        assert 15 <= variant_count <= 35, f"Expected 15-35 variants, got {variant_count}"

    def test_select_ratio_clamped(self):
        """variant_ratio is clamped to [0, 1] in __init__."""
        strategy_too_high = RoutingStrategy(
            "test_op",
            primary="anthropic:haiku",
            variant="gemini:flash",
            variant_ratio=1.5
        )
        assert strategy_too_high.variant_ratio == 1.0

        strategy_negative = RoutingStrategy(
            "test_op",
            primary="anthropic:haiku",
            variant="gemini:flash",
            variant_ratio=-0.5
        )
        assert strategy_negative.variant_ratio == 0.0

    def test_select_returns_variant_or_primary(self):
        """select() always returns one of primary or variant."""
        strategy = RoutingStrategy(
            "test_op",
            primary="anthropic:haiku",
            variant="gemini:flash",
            variant_ratio=0.5
        )

        for i in range(100):
            key = f"test_op:trace_{i}"
            result = strategy.select(key)
            assert result in ["anthropic:haiku", "gemini:flash"]


class TestRoutingStrategyResolveModel:
    """Test RoutingStrategy.resolve_model() method."""

    def test_resolve_model_no_override(self):
        """If requested == selected, no override."""
        strategy = RoutingStrategy(
            "test_op",
            primary="anthropic:haiku",
        )
        actual, overridden = strategy.resolve_model("anthropic:haiku", "anthropic:haiku")
        assert actual == "anthropic:haiku"
        assert overridden is False

    def test_resolve_model_with_override(self):
        """If requested != selected, override is True."""
        strategy = RoutingStrategy(
            "test_op",
            primary="anthropic:haiku",
        )
        actual, overridden = strategy.resolve_model("anthropic:haiku", "anthropic:sonnet")
        assert actual == "anthropic:haiku"
        assert overridden is True

    def test_resolve_model_no_request(self):
        """If no requested model, no override."""
        strategy = RoutingStrategy(
            "test_op",
            primary="anthropic:haiku",
        )
        actual, overridden = strategy.resolve_model("anthropic:haiku", None)
        assert actual == "anthropic:haiku"
        assert overridden is False


class TestGetRoutingStrategy:
    """Test _get_routing_strategy() helper."""

    def test_all_operations_have_strategies(self):
        """All 14 required operations have strategies."""
        operations = [
            "narrative_generate",
            "entity_extraction",
            "narrative_theme_extract",
            "actor_tension_extract",
            "cluster_narrative_gen",
            "narrative_polish",
            "briefing_generate",
            "briefing_refine",
            "briefing_critique",
            "provider_fallback",
            "sentiment_analysis",
            "theme_extraction",
            "relevance_scoring",
            "insight_generation",
        ]
        for op in operations:
            strategy = _get_routing_strategy(op)
            assert strategy is not None
            assert strategy.primary == "anthropic:claude-haiku-4-5-20251001"

    def test_all_strategies_primary_is_haiku(self):
        """All strategies default to Haiku."""
        for op, strategy in _OPERATION_ROUTING.items():
            if op not in ["test_operation", "sync_operation"]:  # Skip test operations
                assert strategy.primary == "anthropic:claude-haiku-4-5-20251001"

    def test_unknown_operation_raises_error(self):
        """Unknown operation raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            _get_routing_strategy("unknown_operation")

        assert "unknown_operation" in str(exc_info.value)
        assert "has no routing strategy" in str(exc_info.value)

    def test_operation_routing_dict_count(self):
        """_OPERATION_ROUTING dict has at least 14 operations."""
        operations = {
            "narrative_generate",
            "entity_extraction",
            "narrative_theme_extract",
            "actor_tension_extract",
            "cluster_narrative_gen",
            "narrative_polish",
            "briefing_generate",
            "briefing_refine",
            "briefing_critique",
            "provider_fallback",
            "sentiment_analysis",
            "theme_extraction",
            "relevance_scoring",
            "insight_generation",
        }
        for op in operations:
            assert op in _OPERATION_ROUTING


class TestRoutingStrategyGuardClause:
    """Test critical guard clause: if variant is None or ratio is 0, always return primary."""

    def test_guard_clause_none_variant(self):
        """Guard: None variant always returns primary (regardless of ratio)."""
        strategy = RoutingStrategy(
            "test_op",
            primary="anthropic:haiku",
            variant=None,
            variant_ratio=0.99  # High ratio, but variant is None
        )
        for i in range(20):
            assert strategy.select(f"key_{i}") == "anthropic:haiku"

    def test_guard_clause_zero_ratio(self):
        """Guard: zero ratio always returns primary (regardless of variant)."""
        strategy = RoutingStrategy(
            "test_op",
            primary="anthropic:haiku",
            variant="gemini:flash",
            variant_ratio=0.0  # Zero ratio
        )
        for i in range(20):
            assert strategy.select(f"key_{i}") == "anthropic:haiku"

    def test_no_guard_clause_both_present(self):
        """No guard: variant present and ratio > 0 allows bucketing."""
        strategy = RoutingStrategy(
            "test_op",
            primary="anthropic:haiku",
            variant="gemini:flash",
            variant_ratio=0.5
        )
        results = set()
        for i in range(100):
            results.add(strategy.select(f"key_{i}"))

        # Should have both primary and variant in results
        assert "anthropic:haiku" in results
        assert "gemini:flash" in results
