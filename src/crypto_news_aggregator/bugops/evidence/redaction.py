"""Log redaction for Evidence Packs."""

import re

REDACTION_PATTERNS = [
    # MongoDB connection strings
    (r'mongodb(\+srv)?://[^\s\'"<>]+', '[REDACTED:MONGO_URI]'),
    # Bearer tokens
    (r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', 'Bearer [REDACTED]'),
    # Authorization headers
    (r'(Authorization|X-Api-Key)\s*:\s*\S+', r'\1: [REDACTED]'),
    # Generic secret key=value patterns
    (r'(api[_-]?key|token|secret|password|passwd|pwd)\s*[=:]\s*[^\s\'"<>{},]{8,}',
     r'\1=[REDACTED:SECRET]'),
    # Email addresses
    (r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[REDACTED:EMAIL]'),
    # Long hex strings (likely tokens/keys — 32+ hex chars)
    (r'\b[0-9a-fA-F]{32,}\b', '[REDACTED:TOKEN]'),
]


class LogRedactor:
    """Redacts sensitive information from log lines."""

    def __init__(self):
        self._patterns = [
            (re.compile(pattern, re.IGNORECASE), replacement)
            for pattern, replacement in REDACTION_PATTERNS
        ]

    def redact_line(self, line: str) -> tuple[str, bool]:
        """
        Apply all redaction patterns to a single log line.
        Returns (redacted_line, was_redacted).
        was_redacted is True if any pattern matched.
        """
        redacted = line
        was_redacted = False
        for pattern, replacement in self._patterns:
            new_line = pattern.sub(replacement, redacted)
            if new_line != redacted:
                was_redacted = True
                redacted = new_line
        return redacted, was_redacted

    def redact_lines(self, lines: list[str]) -> tuple[list[str], int]:
        """
        Redact all lines in a list.
        Returns (redacted_lines, total_lines_with_redactions).
        """
        redacted_lines = []
        redaction_count = 0
        for line in lines:
            redacted, was_redacted = self.redact_line(line)
            redacted_lines.append(redacted)
            if was_redacted:
                redaction_count += 1
        return redacted_lines, redaction_count
