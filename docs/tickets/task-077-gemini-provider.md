---
ticket_id: TASK-077
title: GeminiProvider Implementation — Stub + Factory Integration
priority: critical
severity: high
status: OPEN
date_created: 2026-04-27
updated: 2026-04-27
effort_estimate: 3-4 hours
---

# TASK-077: GeminiProvider Implementation — Stub + Factory Integration

## Problem Statement

factory.py has PROVIDER_MAP with only Sentient and Anthropic providers. For Flash evaluations (FEATURE-053) to work, we need GeminiProvider available in the provider factory. Additionally, GeminiProvider.call() must return the same response shape as AnthropicProvider.call() to avoid breaking the gateway's response wrapping logic.

---

## Task

### 1. Create GeminiProvider Class (gemini.py)

Create new file: `src/crypto_news_aggregator/llm/gemini.py`

```python
from abc import ABC
from typing import Optional, Dict, Any, List
import logging

# Assume this exists; if not, check AnthropicProvider for interface
from src.crypto_news_aggregator.llm.base import LLMProvider

logger = logging.getLogger(__name__)

class GeminiProvider(LLMProvider):
    """
    Google Gemini API provider.
    
    Sprint 16: Stub implementation with structure in place.
    Sprint 17: Full call() implementation with Gemini API integration.
    
    CRITICAL: call() must return the same response shape as AnthropicProvider.call()
    for gateway consistency. Do not invent new response formats.
    """
    
    def __init__(self, api_key: str):
        """
        Args:
            api_key: Gemini API key (from GEMINI_API_KEY env var)
        
        Raises:
            ValueError: if api_key is None or empty
        """
        if not api_key:
            raise ValueError("GEMINI_API_KEY must be set and non-empty")
        self.api_key = api_key
        self.provider_name = "gemini"
    
    def call(
        self,
        model: str,  # e.g., "gemini-2.5-flash"
        prompt: str,
        messages: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Call Gemini API.
        
        Args:
            model: Model name (e.g., "gemini-2.5-flash")
            prompt: System prompt or instruction
            messages: Message history (if any)
            **kwargs: Additional arguments (temperature, max_tokens, etc.)
        
        Returns:
            Response dict with same structure as AnthropicProvider.call()
            
            **CRITICAL CONTRACT:**
            Must include:
            - "text": str (generated content)
            - "input_tokens": int
            - "output_tokens": int
            - "model": str (actual model used)
            - "cost": float (USD cost of this call)
            - "latency_ms": float (milliseconds)
            
            Example:
            {
                "text": "Generated response...",
                "input_tokens": 150,
                "output_tokens": 80,
                "model": "gemini-2.5-flash",
                "cost": 0.00035,
                "latency_ms": 245.5
            }
        
        Sprint 16 Behavior:
        - If GEMINI_API_KEY is set: make real API calls
        - If key not available: return deterministic mock with consistent structure
        
        Sprint 17:
        - Implement full Gemini API integration
        - Use google.generativeai library or direct REST API
        """
        raise NotImplementedError(
            "Gemini provider implementation deferred to Sprint 17. "
            "Structure is in place for factory integration and gateway consistency. "
            "Return contract: must match AnthropicProvider.call() response shape."
        )
```

### 2. Update factory.py — Add to PROVIDER_MAP

Modify `src/crypto_news_aggregator/llm/factory.py`:

**Line ~9 (imports):**
```python
from src.crypto_news_aggregator.llm.gemini import GeminiProvider  # NEW import
```

**Line ~12 (PROVIDER_MAP dict):**
```python
PROVIDER_MAP = {
    "sentient": SentientProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,  # NEW
}
```

### 3. Update factory.py — Add Gemini API Key Handling

Modify `get_llm_provider()` function (~line 32-39):

```python
def get_llm_provider(name: str) -> LLMProvider:
    """
    Instantiate and return the requested LLM provider.
    
    Args:
        name: Provider name ("sentient", "anthropic", or "gemini")
    
    Returns:
        LLMProvider instance
    
    Raises:
        ValueError: if provider not found or API key not configured
    """
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
    
    elif name == "gemini":  # NEW
        api_key = getattr(settings, "GEMINI_API_KEY", None)
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY not set. "
                "Gemini provider requires configuration for Flash evaluations."
            )
        return PROVIDER_MAP[name](api_key)
    
    else:
        raise ValueError(f"Unknown provider: {name}")
```

### 4. Update config.py — Add GEMINI_API_KEY

Modify `src/crypto_news_aggregator/core/config.py`:

```python
class Settings(BaseSettings):
    # ... existing config ...
    
    GEMINI_API_KEY: Optional[str] = Field(
        default=None,
        env="GEMINI_API_KEY",
        description="Google Gemini API key (required for Flash evaluations in FEATURE-053)"
    )
```

### 5. Testing

#### Unit Tests

```python
def test_gemini_provider_instantiation():
    """GeminiProvider instantiates with valid API key"""
    provider = GeminiProvider(api_key="test_key_12345")
    assert provider.api_key == "test_key_12345"
    assert provider.provider_name == "gemini"

def test_gemini_provider_rejects_empty_key():
    """GeminiProvider raises ValueError if API key is empty"""
    with pytest.raises(ValueError, match="GEMINI_API_KEY must be set"):
        GeminiProvider(api_key="")

def test_gemini_provider_call_not_implemented():
    """GeminiProvider.call() raises NotImplementedError with clear message"""
    provider = GeminiProvider(api_key="test_key")
    with pytest.raises(NotImplementedError, match="deferred to Sprint 17"):
        provider.call(
            model="gemini-2.5-flash",
            prompt="test",
            messages=[]
        )

def test_factory_gemini_provider_instantiation():
    """factory.get_llm_provider("gemini") returns GeminiProvider instance"""
    # Mock settings with GEMINI_API_KEY set
    with mock.patch("factory.settings.GEMINI_API_KEY", "test_key"):
        provider = get_llm_provider("gemini")
        assert isinstance(provider, GeminiProvider)
        assert provider.api_key == "test_key"

def test_factory_gemini_provider_no_key():
    """factory.get_llm_provider("gemini") raises if GEMINI_API_KEY not set"""
    with mock.patch("factory.settings.GEMINI_API_KEY", None):
        with pytest.raises(ValueError, match="GEMINI_API_KEY not set"):
            get_llm_provider("gemini")

def test_config_gemini_api_key_loaded():
    """config.Settings loads GEMINI_API_KEY from env"""
    with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "env_key_abc"}):
        settings = Settings()
        assert settings.GEMINI_API_KEY == "env_key_abc"

def test_provider_map_includes_gemini():
    """PROVIDER_MAP includes "gemini" key"""
    assert "gemini" in PROVIDER_MAP
    assert PROVIDER_MAP["gemini"] == GeminiProvider
```

#### Integration Tests

- [ ] `get_llm_provider("gemini")` returns `GeminiProvider` instance
- [ ] `GeminiProvider` instantiates without error (with valid key)
- [ ] `GeminiProvider` raises on empty key
- [ ] All existing tests pass (no regression to sentient/anthropic providers)
- [ ] PROVIDER_MAP includes "gemini" key

---

## Verification

- [ ] `gemini.py` created with `GeminiProvider` class
- [ ] `GeminiProvider` inherits from `LLMProvider` base class (or compatible interface)
- [ ] `factory.py` imports `GeminiProvider` without import errors
- [ ] `PROVIDER_MAP` includes `"gemini": GeminiProvider`
- [ ] `config.py` loads `GEMINI_API_KEY` correctly
- [ ] `get_llm_provider("gemini")` returns `GeminiProvider` instance (with key set)
- [ ] `GeminiProvider.call()` raises `NotImplementedError` with clear message
- [ ] All existing provider tests pass (no regression)

---

## Acceptance Criteria

- [ ] `GeminiProvider` class exists and is importable
- [ ] `GeminiProvider` in `PROVIDER_MAP`
- [ ] `GEMINI_API_KEY` in `config.py` (optional, default None)
- [ ] `factory.get_llm_provider("gemini")` returns `GeminiProvider` instance (if key set)
- [ ] `factory.get_llm_provider("gemini")` raises `ValueError` if key not set
- [ ] `GeminiProvider.call()` raises `NotImplementedError` with reference to Sprint 17
- [ ] **CRITICAL: `GeminiProvider.call()` docstring documents return contract matching `AnthropicProvider.call()`**
- [ ] All existing tests pass (no regression)
- [ ] Code is ready for Sprint 17 implementation (no structural changes needed)

---

## Return Contract Documentation

**CRITICAL FOR GATEWAY CONSISTENCY:**

`GeminiProvider.call()` MUST return the same response shape as `AnthropicProvider.call()`:

```python
{
    "text": str,           # Generated content
    "input_tokens": int,   # Input token count
    "output_tokens": int,  # Output token count
    "model": str,          # Model name used
    "cost": float,         # USD cost
    "latency_ms": float    # Milliseconds
}
```

Do NOT invent new fields or change this structure. Gateway.call() wraps this response and expects this exact schema.

---

## Impact

- Enables FEATURE-053 (Flash evals) to reference "gemini:gemini-2.5-flash" model strings
- Foundation for full Gemini API integration in Sprint 17
- Supports A/B testing infrastructure (RoutingStrategy can now route to Gemini)
- Makes provider factory extensible for future models

---

## Related Tickets

- TASK-076 (RoutingStrategy must be able to route to Gemini)
- FEATURE-053 (blocks: Flash evals need provider available)
- Sprint 17: Full implementation ticket (deferred)