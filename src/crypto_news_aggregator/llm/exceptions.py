"""
LLM error handling with structured error types.

This module provides exception classes for LLM API failures, enabling
downstream callers to distinguish between different failure modes
(auth, rate limit, server error, timeout, etc.) and respond appropriately.
"""


class LLMError(Exception):
    """
    Structured exception for LLM API failures with error_type classification.

    Attributes:
        error_type: One of:
            - "auth_error": Authentication/authorization failure (403)
            - "rate_limit": Rate limit exceeded (429)
            - "server_error": LLM API server error (5xx)
            - "timeout": Request timeout
            - "all_models_failed": All fallback models exhausted
            - "parse_error": Response parsing failure
            - "unexpected": Other unexpected errors
        model: Name of the LLM model that failed (if applicable)
        status_code: HTTP status code from API (if applicable)
    """

    def __init__(
        self,
        message: str,
        *,
        error_type: str,
        model: str | None = None,
        status_code: int | None = None,
    ):
        """
        Initialize LLMError with structured context.

        Args:
            message: Human-readable error message
            error_type: Classification of the error (required, keyword-only)
            model: Name of the LLM model (optional)
            status_code: HTTP status code (optional)
        """
        super().__init__(message)
        self.error_type = error_type
        self.model = model
        self.status_code = status_code

    def __repr__(self) -> str:
        """Return detailed string representation."""
        parts = [f"error_type={self.error_type!r}"]
        if self.model:
            parts.append(f"model={self.model!r}")
        if self.status_code:
            parts.append(f"status_code={self.status_code}")
        return f"LLMError({super().__str__()!r}, {', '.join(parts)})"
