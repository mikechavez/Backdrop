"""
LLM Gateway — single entry point for all Anthropic API calls.

All LLM calls in the system MUST go through this gateway.
Direct httpx calls to api.anthropic.com are prohibited outside this file.
"""

import uuid
import time
import logging
import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

import httpx

from ..services.cost_tracker import check_llm_budget, refresh_budget_if_stale, CostTracker, get_cost_tracker
from ..db.mongodb import mongo_manager
from .exceptions import LLMError
from ..core.config import get_settings

logger = logging.getLogger(__name__)

_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"


@dataclass
class GatewayResponse:
    """Structured response from the LLM gateway."""
    text: str
    input_tokens: int
    output_tokens: int
    cost: float
    model: str
    operation: str
    trace_id: str


class LLMGateway:
    """
    Single entry point for all Anthropic API calls.

    Enforces:
    - Spend cap (soft + hard limits via check_llm_budget)
    - Cost tracking (via CostTracker.track_call)
    - Tracing (via llm_traces MongoDB collection)

    Two execution modes:
    - call()      — async, for briefing_agent and enrichment pipeline
    - call_sync() — sync, for twitter_service, Celery tasks, and legacy callers
    """

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not configured")
        self._cost_tracker = None  # lazy init (needs async db)

    async def _get_from_cache(self, operation: str, input_hash: str) -> Optional[str]:
        """
        Check if result is cached for this operation and input.

        Args:
            operation: LLM operation name (e.g., "narrative_generate")
            input_hash: SHA1 hash of input messages (for deduplication)

        Returns:
            Cached response text if found, None otherwise
        """
        try:
            db = await mongo_manager.get_async_database()
            result = await db.llm_cache.find_one({
                "operation": operation,
                "input_hash": input_hash
            })

            if result and result.get("cached_response"):
                logger.debug(
                    f"Cache hit for {operation}: {input_hash[:8]}... "
                    f"(cached {result.get('cached_count', 1)} times)"
                )
                # Increment hit counter
                await db.llm_cache.update_one(
                    {"_id": result["_id"]},
                    {"$inc": {"cached_count": 1}}
                )
                return result["cached_response"]

            return None
        except Exception as e:
            logger.debug(f"Cache lookup failed for {operation}: {e}")
            return None

    async def _save_to_cache(
        self,
        operation: str,
        input_hash: str,
        response: str
    ) -> None:
        """
        Save LLM response to cache for future lookups.

        Args:
            operation: LLM operation name
            input_hash: SHA1 hash of input messages
            response: LLM response text
        """
        try:
            db = await mongo_manager.get_async_database()
            await db.llm_cache.update_one(
                {
                    "operation": operation,
                    "input_hash": input_hash
                },
                {
                    "$set": {
                        "operation": operation,
                        "input_hash": input_hash,
                        "cached_response": response,
                        "cached_at": datetime.now(timezone.utc),
                        "cached_count": 1
                    }
                },
                upsert=True  # Create if doesn't exist
            )
            logger.debug(f"Cached response for {operation}: {input_hash[:8]}...")
        except Exception as e:
            logger.debug(f"Cache save failed for {operation}: {e}")

    def _get_from_cache_sync(self, operation: str, input_hash: str) -> Optional[str]:
        """
        Check if result is cached for this operation and input (sync version).

        Args:
            operation: LLM operation name
            input_hash: SHA1 hash of input messages

        Returns:
            Cached response text if found, None otherwise
        """
        try:
            from pymongo import MongoClient
            import os
            db_connection_string = os.getenv('MONGODB_URI')
            if not db_connection_string:
                return None

            client = MongoClient(db_connection_string, serverSelectionTimeoutMS=2000)
            db = client.crypto_news
            result = db.llm_cache.find_one({
                "operation": operation,
                "input_hash": input_hash
            })
            client.close()

            if result and result.get("cached_response"):
                logger.debug(
                    f"Cache hit for {operation}: {input_hash[:8]}... "
                    f"(cached {result.get('cached_count', 1)} times)"
                )
                return result["cached_response"]

            return None
        except Exception as e:
            logger.debug(f"Cache lookup failed for {operation}: {e}")
            return None

    def _save_to_cache_sync(
        self,
        operation: str,
        input_hash: str,
        response: str
    ) -> None:
        """
        Save LLM response to cache for future lookups (sync version).

        Args:
            operation: LLM operation name
            input_hash: SHA1 hash of input messages
            response: LLM response text
        """
        try:
            from pymongo import MongoClient
            import os
            db_connection_string = os.getenv('MONGODB_URI')
            if not db_connection_string:
                logger.debug("MONGODB_URI not set, cannot cache")
                return

            client = MongoClient(db_connection_string, serverSelectionTimeoutMS=2000)
            db = client.crypto_news
            db.llm_cache.update_one(
                {
                    "operation": operation,
                    "input_hash": input_hash
                },
                {
                    "$set": {
                        "operation": operation,
                        "input_hash": input_hash,
                        "cached_response": response,
                        "cached_at": datetime.now(timezone.utc),
                        "cached_count": 1
                    }
                },
                upsert=True
            )
            client.close()
            logger.debug(f"Cached response for {operation}: {input_hash[:8]}...")
        except Exception as e:
            logger.debug(f"Cache save failed for {operation}: {e}")

    def _check_budget(self, operation: str) -> None:
        """Check spend cap. Raises LLMError if blocked."""
        allowed, reason = check_llm_budget(operation)
        if not allowed:
            raise LLMError(
                f"Daily spend limit reached ({reason})",
                error_type="spend_limit",
                model="n/a",
            )

    def _build_headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _build_payload(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        system: Optional[str],
    ) -> dict:
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system:
            payload["system"] = system
        return payload

    def _parse_response(self, data: dict) -> tuple[str, int, int]:
        """Extract text and token counts from API response."""
        text = data.get("content", [{}])[0].get("text", "")
        usage = data.get("usage", {})
        return text, usage.get("input_tokens", 0), usage.get("output_tokens", 0)

    def _write_trace_sync(
        self,
        trace_id: str,
        operation: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        duration_ms: float,
        error: Optional[str] = None,
    ) -> None:
        """Write trace record to llm_traces collection synchronously (blocking). Fire-and-forget."""
        try:
            from pymongo import MongoClient
            import os
            db_connection_string = os.getenv('MONGODB_URI')
            if not db_connection_string:
                logger.error("MONGODB_URI not set, cannot write sync trace")
                return

            client = MongoClient(db_connection_string, serverSelectionTimeoutMS=2000)
            db = client.crypto_news
            db.llm_traces.insert_one({
                "trace_id": trace_id,
                "operation": operation,
                "timestamp": datetime.now(timezone.utc),
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": cost,
                "duration_ms": round(duration_ms, 1),
                "error": error,
                # Placeholder fields for Sprint 14 eval system
                "quality": {
                    "passed": None,
                    "score": None,
                    "checks": [],
                },
            })
            client.close()
        except Exception as e:
            logger.error(f"Failed to write sync trace: {e}")

    async def _write_trace(
        self,
        trace_id: str,
        operation: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        duration_ms: float,
        error: Optional[str] = None,
    ) -> None:
        """Write trace record to llm_traces collection. Fire-and-forget."""
        try:
            db = await mongo_manager.get_async_database()
            await db.llm_traces.insert_one({
                "trace_id": trace_id,
                "operation": operation,
                "timestamp": datetime.now(timezone.utc),
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": cost,
                "duration_ms": round(duration_ms, 1),
                "error": error,
                # Placeholder fields for Sprint 14 eval system
                "quality": {
                    "passed": None,
                    "score": None,
                    "checks": [],
                },
            })
        except Exception as e:
            logger.error(f"Failed to write trace: {e}")

    async def _track_cost(
        self, operation: str, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Track cost via CostTracker. Returns cost."""
        try:
            db = await mongo_manager.get_async_database()
            tracker = get_cost_tracker(db)
            return await tracker.track_call(
                operation=operation,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached=False,
            )
        except Exception as e:
            logger.error(f"Cost tracking failed: {e}")
            return 0.0

    # ── Async entry point ────────────────────────────────────

    async def call(
        self,
        messages: List[Dict[str, str]],
        model: str,
        operation: str,
        max_tokens: int = 2048,
        temperature: float = 0.3,
        system: Optional[str] = None,
    ) -> GatewayResponse:
        """
        Async LLM call with cache support.

        Cache is used for non-critical operations. Critical operations
        (briefing generation) bypass cache to ensure freshness.

        Raises:
            LLMError: On spend cap breach or API failure.
        """
        await refresh_budget_if_stale()
        self._check_budget(operation)

        trace_id = str(uuid.uuid4())
        start = time.monotonic()

        # ═══ CACHE SUPPORT ═══
        # Check cache for non-critical operations
        CACHEABLE_OPERATIONS = [
            "narrative_generate",
            "entity_extraction",
            "narrative_theme_extract"
        ]

        SKIP_CACHE_OPERATIONS = [
            "briefing_generate",  # Always fresh
            "briefing_refine",    # Always fresh
            "briefing_critique",  # Always fresh
        ]

        input_hash = None
        if operation in CACHEABLE_OPERATIONS and operation not in SKIP_CACHE_OPERATIONS:
            # Generate hash of input for deduplication
            input_text = json.dumps(messages, sort_keys=True)
            input_hash = hashlib.sha1(input_text.encode()).hexdigest()

            # Try cache lookup
            cached = await self._get_from_cache(operation, input_hash)
            if cached:
                # Return cached result with zero cost
                duration_ms = (time.monotonic() - start) * 1000
                await self._write_trace(trace_id, operation, model, 0, 0, 0.0, duration_ms)
                return GatewayResponse(
                    text=cached,
                    input_tokens=0,
                    output_tokens=0,
                    cost=0.0,
                    model=model,
                    operation=operation,
                    trace_id=trace_id,
                )

        # ═══ CACHE MISS - CALL API ═══
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    _ANTHROPIC_API_URL,
                    headers=self._build_headers(),
                    json=self._build_payload(messages, model, max_tokens, temperature, system),
                    timeout=120,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            duration_ms = (time.monotonic() - start) * 1000
            error_msg = str(e.response.text[:200])
            await self._write_trace(trace_id, operation, model, 0, 0, 0.0, duration_ms, error=error_msg)
            status = e.response.status_code
            if status == 403:
                error_type = "auth_error"
            elif status == 429:
                error_type = "rate_limit"
            elif status >= 500:
                error_type = "server_error"
            else:
                error_type = "unexpected"
            raise LLMError(error_msg, error_type=error_type, model=model, status_code=status)
        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            await self._write_trace(trace_id, operation, model, 0, 0, 0.0, duration_ms, error=str(e))
            raise LLMError(str(e), error_type="unexpected", model=model)

        duration_ms = (time.monotonic() - start) * 1000
        text, input_tokens, output_tokens = self._parse_response(data)

        cost = await self._track_cost(operation, model, input_tokens, output_tokens)
        await self._write_trace(trace_id, operation, model, input_tokens, output_tokens, cost, duration_ms)

        # ═══ SAVE TO CACHE ═══
        if input_hash and operation in CACHEABLE_OPERATIONS and operation not in SKIP_CACHE_OPERATIONS:
            await self._save_to_cache(operation, input_hash, text)

        return GatewayResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            model=model,
            operation=operation,
            trace_id=trace_id,
        )

    # ── Sync entry point ─────────────────────────────────────

    def call_sync(
        self,
        messages: List[Dict[str, str]],
        model: str,
        operation: str,
        max_tokens: int = 2048,
        temperature: float = 0.3,
        system: Optional[str] = None,
    ) -> GatewayResponse:
        """
        Sync LLM call with cache support.

        Cache is used for non-critical operations. Critical operations
        (briefing generation) bypass cache to ensure freshness.

        Raises:
            LLMError: On spend cap breach or API failure.
        """
        self._check_budget(operation)

        trace_id = str(uuid.uuid4())
        start = time.monotonic()

        # ═══ CACHE SUPPORT ═══
        CACHEABLE_OPERATIONS = [
            "narrative_generate",
            "entity_extraction",
            "narrative_theme_extract"
        ]

        SKIP_CACHE_OPERATIONS = [
            "briefing_generate",  # Always fresh
            "briefing_refine",    # Always fresh
            "briefing_critique",  # Always fresh
        ]

        input_hash = None
        if operation in CACHEABLE_OPERATIONS and operation not in SKIP_CACHE_OPERATIONS:
            # Generate hash of input for deduplication
            input_text = json.dumps(messages, sort_keys=True)
            input_hash = hashlib.sha1(input_text.encode()).hexdigest()

            # Try cache lookup
            cached = self._get_from_cache_sync(operation, input_hash)
            if cached:
                # Return cached result with zero cost
                duration_ms = (time.monotonic() - start) * 1000
                self._write_trace_sync(trace_id, operation, model, 0, 0, 0.0, duration_ms)
                return GatewayResponse(
                    text=cached,
                    input_tokens=0,
                    output_tokens=0,
                    cost=0.0,
                    model=model,
                    operation=operation,
                    trace_id=trace_id,
                )

        # ═══ CACHE MISS - CALL API ═══
        try:
            with httpx.Client() as client:
                response = client.post(
                    _ANTHROPIC_API_URL,
                    headers=self._build_headers(),
                    json=self._build_payload(messages, model, max_tokens, temperature, system),
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            duration_ms = (time.monotonic() - start) * 1000
            status = e.response.status_code
            error_msg = str(e.response.text[:200])
            self._write_trace_sync(trace_id, operation, model, 0, 0, 0.0, duration_ms, error=error_msg)
            if status == 403:
                error_type = "auth_error"
            elif status == 429:
                error_type = "rate_limit"
            elif status >= 500:
                error_type = "server_error"
            else:
                error_type = "unexpected"
            raise LLMError(error_msg, error_type=error_type, model=model, status_code=status)
        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            self._write_trace_sync(trace_id, operation, model, 0, 0, 0.0, duration_ms, error=str(e))
            raise LLMError(str(e), error_type="unexpected", model=model)

        duration_ms = (time.monotonic() - start) * 1000
        text, input_tokens, output_tokens = self._parse_response(data)

        # Sync cost tracking: create tracker inline, write synchronously via pymongo
        cost = 0.0
        try:
            from ..services.cost_tracker import CostTracker as CT
            ct = CT.__new__(CT)
            cost = ct.calculate_cost(model, input_tokens, output_tokens)
        except Exception as e:
            logger.error(f"Sync cost calculation failed: {e}")

        # Write trace synchronously (blocking, but fire-and-forget semantics)
        self._write_trace_sync(trace_id, operation, model, input_tokens, output_tokens, cost, duration_ms)

        # ═══ SAVE TO CACHE ═══
        if input_hash and operation in CACHEABLE_OPERATIONS and operation not in SKIP_CACHE_OPERATIONS:
            self._save_to_cache_sync(operation, input_hash, text)

        return GatewayResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            model=model,
            operation=operation,
            trace_id=trace_id,
        )


# ── Module-level singleton ────────────────────────────────

_gateway: Optional[LLMGateway] = None


def get_gateway() -> LLMGateway:
    """Get or create the global LLMGateway instance."""
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
    return _gateway
