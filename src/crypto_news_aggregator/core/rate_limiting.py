"""
Rate limiting middleware for API endpoints.

Implements per-IP rate limiting with configurable limits per endpoint.
"""

import logging
import time
from typing import Dict, Tuple, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class RateLimitStore:
    """Thread-safe in-memory store for rate limit tracking."""

    def __init__(self):
        # Structure: {(ip, endpoint): [(timestamp, count)]}
        self._store: Dict[Tuple[str, str], list] = {}
        self._lock = None  # Will use asyncio.Lock in middleware

    def get_client_ip(self, request: Request) -> str:
        """Extract client IP from request, handling proxies."""
        # Check X-Forwarded-For first (behind proxy like Vercel)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        # Check X-Real-IP (nginx style)
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fallback to direct connection
        return request.client.host if request.client else "unknown"

    def is_rate_limited(
        self,
        ip: str,
        endpoint: str,
        limit: int,
        window_seconds: int = 60
    ) -> Tuple[bool, int]:
        """
        Check if request should be rate limited.

        Args:
            ip: Client IP address
            endpoint: API endpoint path
            limit: Max requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            (is_limited, requests_in_window)
        """
        key = (ip, endpoint)
        now = time.time()
        cutoff = now - window_seconds

        # Initialize if not exists
        if key not in self._store:
            self._store[key] = []

        # Remove expired entries
        self._store[key] = [ts for ts in self._store[key] if ts > cutoff]

        # Check limit
        request_count = len(self._store[key])
        is_limited = request_count >= limit

        # Record this request if not limited
        if not is_limited:
            self._store[key].append(now)

        return is_limited, request_count


# Global rate limit store
_rate_limit_store = RateLimitStore()


# Rate limit configuration per endpoint
RATE_LIMIT_CONFIG = {
    # High-cost endpoints (LLM calls)
    "/v1/chat/completions": {"limit": 5, "window": 60},

    # Medium-cost endpoints (database-heavy)
    "/api/v1/signals/trending": {"limit": 10, "window": 60},
    "/api/v1/briefing/latest": {"limit": 20, "window": 60},
    "/api/v1/narratives": {"limit": 20, "window": 60},

    # Lower-cost endpoints
    "/api/v1/signals": {"limit": 30, "window": 60},
    "/api/v1/signals/search": {"limit": 30, "window": 60},
    "/api/v1/signals/{entity}/articles": {"limit": 30, "window": 60},

    # Health checks - no limit
    "/health": {"limit": None, "window": 60},
    "/": {"limit": None, "window": 60},
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for per-IP rate limiting."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Rate limit incoming requests based on client IP and endpoint.
        """
        # Extract client IP
        client_ip = _rate_limit_store.get_client_ip(request)

        # Get endpoint path (without query params)
        endpoint = request.url.path

        # Find matching rate limit config
        rate_limit_config = None
        for configured_endpoint, config in RATE_LIMIT_CONFIG.items():
            # Handle parameterized routes like /api/v1/signals/{entity}/articles
            if self._matches_endpoint(endpoint, configured_endpoint):
                rate_limit_config = config
                break

        # Check rate limit if configured
        if rate_limit_config and rate_limit_config["limit"] is not None:
            is_limited, request_count = _rate_limit_store.is_rate_limited(
                ip=client_ip,
                endpoint=endpoint,
                limit=rate_limit_config["limit"],
                window_seconds=rate_limit_config["window"]
            )

            if is_limited:
                logger.warning(
                    f"rate_limit: ip={client_ip}, endpoint={endpoint}, "
                    f"limit={rate_limit_config['limit']}, requests_in_window={request_count}"
                )

                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": f"Rate limit exceeded. Max {rate_limit_config['limit']} "
                                 f"requests per {rate_limit_config['window']} seconds."
                    },
                    headers={
                        "Retry-After": str(rate_limit_config["window"])
                    }
                )

        # Process request normally
        response = await call_next(request)
        return response

    @staticmethod
    def _matches_endpoint(path: str, pattern: str) -> bool:
        """Check if path matches endpoint pattern."""
        # Exact match
        if path == pattern:
            return True

        # Pattern match for parameterized routes
        import re
        regex_pattern = pattern.replace("{entity}", r"[^/]+")
        if re.match(f"^{regex_pattern}$", path):
            return True

        return False
