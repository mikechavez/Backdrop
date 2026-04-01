"""Tests for LLMError exception class."""

import pytest
from crypto_news_aggregator.llm.exceptions import LLMError


class TestLLMError:
    """Test LLMError exception class."""

    def test_llm_error_is_exception(self):
        """LLMError should be a subclass of Exception."""
        error = LLMError("test message", error_type="unexpected")
        assert isinstance(error, Exception)

    def test_llm_error_basic_fields(self):
        """LLMError should store message and error_type."""
        error = LLMError("test message", error_type="auth_error")
        assert str(error) == "test message"
        assert error.error_type == "auth_error"
        assert error.model is None
        assert error.status_code is None

    def test_llm_error_with_model(self):
        """LLMError should store model name."""
        error = LLMError(
            "test message",
            error_type="timeout",
            model="claude-haiku-4-5-20251001",
        )
        assert error.model == "claude-haiku-4-5-20251001"

    def test_llm_error_with_status_code(self):
        """LLMError should store HTTP status code."""
        error = LLMError(
            "test message",
            error_type="rate_limit",
            status_code=429,
        )
        assert error.status_code == 429

    def test_llm_error_all_fields(self):
        """LLMError should store all fields."""
        error = LLMError(
            "test message",
            error_type="server_error",
            model="claude-sonnet-4-5-20250929",
            status_code=500,
        )
        assert str(error) == "test message"
        assert error.error_type == "server_error"
        assert error.model == "claude-sonnet-4-5-20250929"
        assert error.status_code == 500

    def test_llm_error_raise_and_catch(self):
        """LLMError should be raiseable and catchable."""
        with pytest.raises(LLMError) as exc_info:
            raise LLMError("test error", error_type="unexpected")

        assert exc_info.value.error_type == "unexpected"
        assert str(exc_info.value) == "test error"

    def test_llm_error_repr(self):
        """LLMError should have informative repr."""
        error = LLMError(
            "test message",
            error_type="auth_error",
            model="claude-haiku-4-5-20251001",
            status_code=403,
        )
        repr_str = repr(error)
        assert "auth_error" in repr_str
        assert "claude-haiku-4-5-20251001" in repr_str
        assert "403" in repr_str

    def test_llm_error_types(self):
        """LLMError should support all documented error types."""
        error_types = [
            "auth_error",
            "rate_limit",
            "server_error",
            "timeout",
            "all_models_failed",
            "parse_error",
            "unexpected",
        ]
        for error_type in error_types:
            error = LLMError("test", error_type=error_type)
            assert error.error_type == error_type

    def test_llm_error_inheritance(self):
        """LLMError can be caught as Exception."""
        with pytest.raises(Exception):
            raise LLMError("test", error_type="unexpected")

    def test_llm_error_chaining(self):
        """LLMError should support exception chaining."""
        try:
            raise ValueError("original error")
        except ValueError as orig:
            error = LLMError("wrapped", error_type="unexpected")
            with pytest.raises(LLMError):
                raise error from orig
