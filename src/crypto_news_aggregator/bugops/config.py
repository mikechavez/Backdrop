"""BugOps configuration."""

from ..core.config import get_settings


def get_bugops_settings():
    """Get BugOps settings from core config."""
    return get_settings()
