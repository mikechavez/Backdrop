"""Tests for LogRedactor."""

import pytest
from crypto_news_aggregator.bugops.evidence.redaction import LogRedactor


@pytest.fixture
def redactor():
    """Provide a LogRedactor instance."""
    return LogRedactor()


class TestLogRedactorLine:
    """Tests for redact_line() method."""

    def test_redacts_mongodb_uri_standard(self, redactor):
        """Redacts mongodb:// connection strings."""
        line = "Connecting to mongodb://user:pass@localhost:27017/mydb"
        redacted, was_redacted = redactor.redact_line(line)
        assert "[REDACTED:MONGO_URI]" in redacted
        assert was_redacted is True

    def test_redacts_mongodb_uri_srv(self, redactor):
        """Redacts mongodb+srv:// connection strings."""
        line = "Connecting to mongodb+srv://user:pass@cluster.mongodb.net/mydb"
        redacted, was_redacted = redactor.redact_line(line)
        assert "[REDACTED:MONGO_URI]" in redacted
        assert was_redacted is True

    def test_redacts_bearer_token(self, redactor):
        """Redacts Bearer tokens in Authorization headers."""
        line = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWI"
        redacted, was_redacted = redactor.redact_line(line)
        # Bearer token pattern redacts Bearer + token, and Authorization pattern also matches
        assert "[REDACTED]" in redacted
        assert was_redacted is True

    def test_redacts_authorization_header(self, redactor):
        """Redacts Authorization: header values."""
        line = "Authorization: token_secret_value_here"
        redacted, was_redacted = redactor.redact_line(line)
        assert "Authorization: [REDACTED]" in redacted
        assert was_redacted is True

    def test_redacts_api_key_pattern(self, redactor):
        """Redacts api_key=value patterns."""
        line = "request with api_key=sk_live_12345678901234567890"
        redacted, was_redacted = redactor.redact_line(line)
        assert "api_key=[REDACTED:SECRET]" in redacted
        assert was_redacted is True

    def test_redacts_token_pattern(self, redactor):
        """Redacts token=value patterns."""
        line = "auth token=1234567890abcdef"
        redacted, was_redacted = redactor.redact_line(line)
        assert "token=[REDACTED:SECRET]" in redacted
        assert was_redacted is True

    def test_redacts_secret_pattern(self, redactor):
        """Redacts secret=value patterns."""
        line = "secret=my_secret_password_value"
        redacted, was_redacted = redactor.redact_line(line)
        assert "secret=[REDACTED:SECRET]" in redacted
        assert was_redacted is True

    def test_redacts_password_pattern(self, redactor):
        """Redacts password=value patterns."""
        line = "database password=SuperSecretPassword123"
        redacted, was_redacted = redactor.redact_line(line)
        assert "password=[REDACTED:SECRET]" in redacted
        assert was_redacted is True

    def test_redacts_email_addresses(self, redactor):
        """Redacts email addresses."""
        line = "Error reported by user@example.com on 2026-06-20"
        redacted, was_redacted = redactor.redact_line(line)
        assert "[REDACTED:EMAIL]" in redacted
        assert "user@example.com" not in redacted
        assert was_redacted is True

    def test_redacts_long_hex_strings(self, redactor):
        """Redacts 32+ character hex strings (likely tokens)."""
        line = "token=a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a7"
        redacted, was_redacted = redactor.redact_line(line)
        assert "[REDACTED" in redacted
        assert "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a7" not in redacted
        assert was_redacted is True

    def test_does_not_redact_short_hex_strings(self, redactor):
        """Does NOT redact hex strings < 32 chars (not token-like)."""
        line = "Hash value: a1b2c3d4e5f6a1b2"
        redacted, was_redacted = redactor.redact_line(line)
        assert redacted == line
        assert was_redacted is False

    def test_does_not_redact_timestamps(self, redactor):
        """Does NOT redact normal timestamp content."""
        line = "2026-06-20T15:30:45.123456Z - INFO - process started"
        redacted, was_redacted = redactor.redact_line(line)
        assert redacted == line
        assert was_redacted is False

    def test_does_not_redact_log_levels(self, redactor):
        """Does NOT redact log level keywords."""
        line = "ERROR: Connection failed to database"
        redacted, was_redacted = redactor.redact_line(line)
        assert redacted == line
        assert was_redacted is False

    def test_does_not_redact_python_exception(self, redactor):
        """Does NOT redact Python exception messages."""
        line = "ValueError: invalid literal for int() with base 10: 'abc'"
        redacted, was_redacted = redactor.redact_line(line)
        assert redacted == line
        assert was_redacted is False

    def test_does_not_redact_stack_trace(self, redactor):
        """Does NOT redact normal stack trace lines."""
        line = 'File "/app/services/enrichment.py", line 42, in process'
        redacted, was_redacted = redactor.redact_line(line)
        assert redacted == line
        assert was_redacted is False

    def test_handles_empty_string(self, redactor):
        """Handles empty string input gracefully."""
        redacted, was_redacted = redactor.redact_line("")
        assert redacted == ""
        assert was_redacted is False

    def test_multiple_redactions_in_one_line(self, redactor):
        """Handles multiple sensitive patterns in one line."""
        line = "auth token=secret123456 and api_key=key4567890 for user@example.com"
        redacted, was_redacted = redactor.redact_line(line)
        assert "[REDACTED" in redacted
        assert "[REDACTED:EMAIL]" in redacted
        assert was_redacted is True

    def test_case_insensitive_patterns(self, redactor):
        """Redaction patterns are case-insensitive."""
        line = "API_KEY=secret_value_here"
        redacted, was_redacted = redactor.redact_line(line)
        assert "[REDACTED:SECRET]" in redacted
        assert was_redacted is True

    def test_redacts_x_api_key_header(self, redactor):
        """Redacts X-Api-Key header values."""
        line = "X-Api-Key: sk_test_123456789abcdef"
        redacted, was_redacted = redactor.redact_line(line)
        assert "[REDACTED" in redacted
        assert "sk_test_123456789abcdef" not in redacted
        assert was_redacted is True


class TestLogRedactorLines:
    """Tests for redact_lines() method."""

    def test_redacts_multiple_lines(self, redactor):
        """Redacts all lines in a list."""
        lines = [
            "Authorization: Bearer token123456789",
            "Normal log line here",
            "api_key=secret_value_longerthan8",
        ]
        redacted_lines, count = redactor.redact_lines(lines)
        assert len(redacted_lines) == 3
        assert count == 2
        assert "[REDACTED]" in redacted_lines[0]
        assert redacted_lines[1] == "Normal log line here"
        assert "[REDACTED" in redacted_lines[2]

    def test_redaction_count_accuracy(self, redactor):
        """Redaction count matches lines-with-redactions (not total substitutions)."""
        lines = [
            "two secrets: api_key=secret12345 and token=secret67890",
            "Normal line",
            "one secret: password=password123456",
        ]
        redacted_lines, count = redactor.redact_lines(lines)
        assert count == 2  # 2 lines had redactions
        assert "[REDACTED" in redacted_lines[0]
        assert "[REDACTED" in redacted_lines[2]

    def test_empty_list(self, redactor):
        """Handles empty list gracefully."""
        redacted_lines, count = redactor.redact_lines([])
        assert redacted_lines == []
        assert count == 0

    def test_list_with_all_clean_lines(self, redactor):
        """Handles list with no redactions needed."""
        lines = [
            "INFO: Service started successfully",
            "2026-06-20T15:30:45Z - Request processed",
            "DEBUG: Cache hit for entity-bitcoin",
        ]
        redacted_lines, count = redactor.redact_lines(lines)
        assert redacted_lines == lines
        assert count == 0

    def test_list_with_all_redacted_lines(self, redactor):
        """Handles list where all lines need redaction."""
        lines = [
            "user1@example.com failed auth",
            "user2@example.com failed auth",
            "user3@example.com failed auth",
        ]
        redacted_lines, count = redactor.redact_lines(lines)
        assert count == 3
        for line in redacted_lines:
            assert "[REDACTED:EMAIL]" in line
