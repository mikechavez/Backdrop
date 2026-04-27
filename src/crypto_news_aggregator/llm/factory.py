from typing import List, Optional

from .base import LLMProvider
from .sentient import SentientProvider
from .anthropic import AnthropicProvider
from .gemini import GeminiProvider
from .optimized_anthropic import OptimizedAnthropicLLM, create_optimized_llm
from ..core.config import get_settings

PROVIDER_MAP = {
    "sentient": SentientProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
}


def get_llm_provider(name: str = None) -> LLMProvider:
    """
    Instantiate and return the requested LLM provider.

    Args:
        name: Provider name ("sentient", "anthropic", or "gemini").
              If not provided, uses LLM_PROVIDER environment variable.

    Returns:
        LLMProvider instance

    Raises:
        ValueError: if provider not found or API key not configured
    """
    settings = get_settings()

    # Use provided name or fall back to LLM_PROVIDER env var
    if name is None:
        name = getattr(settings, "LLM_PROVIDER", "anthropic").lower()
    else:
        name = name.lower()

    if name not in PROVIDER_MAP:
        raise ValueError(
            f"Unknown provider: {name}. Available: {list(PROVIDER_MAP.keys())}"
        )

    if name == "sentient":
        api_key = getattr(settings, "SENTIENT_API_KEY", None)
        if not api_key:
            raise ValueError("SENTIENT_API_KEY not set")
        return PROVIDER_MAP[name](api_key)

    elif name == "anthropic":
        api_key = getattr(settings, "ANTHROPIC_API_KEY", None)
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        return PROVIDER_MAP[name](api_key)

    elif name == "gemini":
        api_key = getattr(settings, "GEMINI_API_KEY", None)
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY not set. "
                "Gemini provider requires configuration for Flash evaluations."
            )
        return PROVIDER_MAP[name](api_key)

    else:
        raise ValueError(f"Unknown provider: {name}")


async def get_optimized_llm(db) -> OptimizedAnthropicLLM:
    """
    Factory function to get an optimized LLM provider with caching and cost tracking.
    
    This is the preferred method for entity extraction as it:
    - Uses Haiku model (12x cheaper than Sonnet)
    - Caches responses to avoid duplicate API calls
    - Tracks costs for monitoring
    
    Args:
        db: MongoDB database instance
    
    Returns:
        Initialized OptimizedAnthropicLLM instance
    """
    settings = get_settings()
    api_key = settings.ANTHROPIC_API_KEY
    
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")
    
    return await create_optimized_llm(db, api_key)
