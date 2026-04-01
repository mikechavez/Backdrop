import json
from typing import Any, Optional, Dict, Union, List
import requests
from .config import get_settings


class RedisRESTClient:
    """
    A Redis client that uses the Upstash REST API for communication.
    This provides a simple key-value interface to Upstash Redis.
    """

    def __init__(self, base_url: str = None, token: str = None):
        """
        Initialize the Redis REST client.

        Args:
            base_url: The base URL of the Upstash Redis REST API
            token: The authentication token for the Upstash Redis instance
        """
        settings = get_settings()
        self.base_url = (base_url or settings.UPSTASH_REDIS_REST_URL).rstrip("/")
        self.token = token or settings.UPSTASH_REDIS_TOKEN

        self.enabled = bool(self.base_url and self.token)

        if self.enabled:
            self.headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
        else:
            self.headers = {}

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make a request to the Upstash Redis REST API."""
        if not self.enabled:
            return {"result": None}  # Return a default response if not enabled

        url = f"{self.base_url}/{endpoint}"
        response = requests.request(method, url, headers=self.headers, **kwargs)
        response.raise_for_status()
        return response.json()

    def get(self, key: str) -> Optional[Any]:
        """Get the value of a key."""
        try:
            response = self._make_request("GET", f"get/{key}")
            return response.get("result")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """Set the value of a key."""
        if not isinstance(value, (str, int, float, bool)):
            value = json.dumps(value)

        endpoint = f"set/{key}/{value}"
        if ex is not None:
            endpoint += f"?ex={ex}"

        response = self._make_request("POST", endpoint)
        return response.get("result") == "OK"

    def delete(self, *keys: str) -> int:
        """Delete one or more keys."""
        key_param = "/".join(keys)
        response = self._make_request("POST", f"del/{key_param}")
        return response.get("result", 0)

    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        response = self._make_request("GET", f"exists/{key}")
        return bool(response.get("result", 0))

    def expire(self, key: str, seconds: int) -> bool:
        """Set a key's time to live in seconds."""
        response = self._make_request("POST", f"expire/{key}/{seconds}")
        return bool(response.get("result", 0))

    def ttl(self, key: str) -> int:
        """Get the time to live for a key in seconds."""
        response = self._make_request("GET", f"ttl/{key}")
        return response.get("result", -2)  # -2 if key doesn't exist, -1 if no TTL

    def incr(self, key: str) -> int:
        """Increment a key's value by 1."""
        response = self._make_request("POST", f"incr/{key}")
        return int(response.get("result", 0))

    def ping(self) -> bool:
        """Ping the Redis server."""
        try:
            response = self._make_request("GET", "ping")
            return response.get("result") == "PONG"
        except requests.exceptions.RequestException:
            return False


# Create a singleton instance
redis_client = RedisRESTClient()
