"""
Service for handling cryptocurrency price data and monitoring with alerting capabilities.
"""

import logging
import aiohttp
import asyncio
from collections import Counter
from typing import Dict, Optional, List, Any, Tuple
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from aiocache import caches, cached
from ..core.config import get_settings
from ..services.article_service import article_service
import random
import numpy as np

# Configure a simple in-memory cache
# In a production environment, you might want to use RedisCache or MemcachedCache
caches.set_config(
    {
        "default": {
            "cache": "aiocache.SimpleMemoryCache",
            "serializer": {"class": "aiocache.serializers.StringSerializer"},
        }
    }
)


# --- MOCK DATA --- #
def _generate_mock_market_data(coin_id: str) -> Dict[str, Any]:
    """Generates detailed mock market data for a given coin ID."""
    base_prices = {"bitcoin": 60000, "ethereum": 2000}
    base_price = base_prices.get(coin_id, 100)

    return {
        "id": coin_id,
        "name": coin_id.capitalize(),
        "current_price": base_price * (1 + random.uniform(-0.05, 0.05)),
        "market_cap_rank": (
            1 if coin_id == "bitcoin" else 2 if coin_id == "ethereum" else 100
        ),
        "price_change_percentage_1h_in_currency": random.uniform(-1, 1),
        "price_change_percentage_24h_in_currency": random.uniform(-5, 5),
        "price_change_percentage_7d_in_currency": random.uniform(-10, 10),
        "total_volume": random.uniform(1e9, 5e10),
        "market_cap": (
            base_price * 21000000 if coin_id == "bitcoin" else base_price * 120000000
        ),
    }


def _generate_mock_price(coin_id: str) -> Dict[str, Any]:
    """Generates mock price data for a given coin ID."""
    base_price = {
        "bitcoin": 60000,
        "ethereum": 2000,
    }.get(coin_id.lower(), 100)

    price = base_price * (1 + random.uniform(-0.05, 0.05))
    change_24h = random.uniform(-5, 5)

    return {
        "price": price,
        "change_24h": change_24h,
        "timestamp": datetime.now(timezone.utc),
    }


# --- API Usage Counter ---
API_CALL_COUNTER = {"count": 0, "last_reset": datetime.now(timezone.utc)}
MONTHLY_API_LIMIT = 10000
WARNING_THRESHOLD = 0.8  # 80% of the limit


def increment_api_call_counter():
    """Increments the API call counter and logs a warning if the usage is high."""
    now = datetime.now(timezone.utc)
    # Reset counter monthly
    if (now - API_CALL_COUNTER["last_reset"]).days > 30:
        API_CALL_COUNTER["count"] = 0
        API_CALL_COUNTER["last_reset"] = now

    API_CALL_COUNTER["count"] += 1
    usage_percent = (API_CALL_COUNTER["count"] / MONTHLY_API_LIMIT) * 100

    if usage_percent >= WARNING_THRESHOLD * 100:
        logger.warning(
            f"CoinGecko API usage is at {usage_percent:.2f}% of the monthly limit. "
            f"({API_CALL_COUNTER['count']}/{MONTHLY_API_LIMIT})"
        )
    logger.debug(f"CoinGecko API calls: {API_CALL_COUNTER['count']}")


logger = logging.getLogger(__name__)

COIN_ID_TO_SYMBOL = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "dogecoin": "DOGE",
    "cardano": "ADA",
    "ripple": "XRP",
    "polkadot": "DOT",
    "chainlink": "LINK",
    "litecoin": "LTC",
}

DEFAULT_NEWS_LOOKBACK_HOURS = 48
DEFAULT_NEWS_LIMIT = 8


class CoinGeckoPriceService:
    """Service for handling cryptocurrency price data and monitoring using CoinGecko API."""

    def __init__(self):
        self.settings = get_settings()
        self._configure_endpoints()
        self.session = None
        self.price_history: Dict[str, List[Dict]] = {}
        self.market_data: Dict[str, Any] = {}

    def _configure_endpoints(self):
        """Sets the base URL based on the presence of an API key."""
        # Forcing public endpoint as the key is a demo key.
        self.BASE_URL = "https://api.coingecko.com/api/v3"
        if self.settings.coingecko_api_key:
            logger.info("CoinGecko API key found. Using Public endpoint for Demo key.")
        else:
            logger.info("No CoinGecko API key found. Using Public endpoint.")

    def reinitialize(self):
        """Re-initializes the service with the latest settings."""
        logger.info("Re-initializing CoinGeckoPriceService with latest settings.")
        get_settings.cache_clear()  # Clear the cache for the settings function
        self.settings = get_settings()
        self._configure_endpoints()
        # The session will be recreated automatically on the next API call

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp client session."""
        if self.session is None or self.session.closed:
            # Demo API key does not require a header. The key is identified by the account.
            # For a real Pro plan, the header logic would need to be restored.
            self.session = aiohttp.ClientSession()
        return self.session

    def _get_url_with_api_key(self, url: str) -> str:
        """Appends the CoinGecko API key as a query parameter if it exists."""
        if self.settings.coingecko_api_key:
            # For Demo plan, key is sent as a query param to the public endpoint
            separator = "&" if "?" in url else "?"
            return (
                f"{url}{separator}x_cg_demo_api_key={self.settings.coingecko_api_key}"
            )
        return url

    async def close(self):
        """Close the aiohttp client session."""
        if self.session and not self.session.closed:
            await self.session.close()

    @cached(ttl=300)  # Cache for 5 minutes
    async def get_bitcoin_price(self) -> Dict[str, float]:
        """
        Get current Bitcoin price and 24h change from CoinGecko.

        Returns:
            Dict containing 'price' (float), 'change_24h' (float), and 'timestamp' (datetime)
        """
        if self.settings.TESTING_MODE or self.settings.COINGECKO_API_DISABLED:
            logger.info("TESTING_MODE or COINGECKO_API_DISABLED enabled. Returning mock Bitcoin price.")
            return _generate_mock_price("bitcoin")

        increment_api_call_counter()
        session = await self.get_session()
        base_url = f"{self.BASE_URL}/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"
        url = self._get_url_with_api_key(base_url)

        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()

                price_data = data.get("bitcoin", {})
                price = price_data.get("usd")
                change_24h = price_data.get("usd_24h_change", 0)

                return {
                    "price": float(price) if price is not None else None,
                    "change_24h": float(change_24h) if change_24h is not None else 0.0,
                    "timestamp": datetime.now(timezone.utc),
                }

        except aiohttp.ClientError as e:
            logger.error(f"Error fetching Bitcoin price from CoinGecko: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in get_bitcoin_price: {e}")
            raise

    @cached(ttl=300)  # Cache for 5 minutes
    async def get_prices(self, coin_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get current prices and 24h change for a list of cryptocurrencies.

        Args:
            coin_ids: A list of CoinGecko coin IDs (e.g., ['bitcoin', 'ethereum']).

        Returns:
            A dictionary mapping each coin ID to its price data.
        """
        if not coin_ids:
            return {}

        if self.settings.TESTING_MODE or self.settings.COINGECKO_API_DISABLED:
            logger.info(f"TESTING_MODE or COINGECKO_API_DISABLED enabled. Returning mock prices for: {coin_ids}")
            return {coin_id: _generate_mock_price(coin_id) for coin_id in coin_ids}

        increment_api_call_counter()
        session = await self.get_session()
        ids_str = ",".join(coin_ids)
        base_url = f"{self.BASE_URL}/simple/price?ids={ids_str}&vs_currencies=usd&include_24hr_change=true"
        url = self._get_url_with_api_key(base_url)

        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()

                result = {}
                for coin_id, price_data in data.items():
                    price = price_data.get("usd")
                    change_24h = price_data.get("usd_24h_change", 0)
                    result[coin_id] = {
                        "price": float(price) if price is not None else None,
                        "change_24h": (
                            float(change_24h) if change_24h is not None else 0.0
                        ),
                        "timestamp": datetime.now(timezone.utc),
                    }
                return result

        except aiohttp.ClientError as e:
            logger.error(f"Error fetching prices from CoinGecko: {e}")
            return {
                coin_id: {} for coin_id in coin_ids
            }  # Return empty dicts for failed coins
        except Exception as e:
            logger.error(f"Unexpected error in get_prices: {e}")
            return {coin_id: {} for coin_id in coin_ids}

    @cached(ttl=300)  # Cache for 5 minutes
    async def get_markets_data(self, coin_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get detailed market data for a list of cryptocurrencies.

        Args:
            coin_ids: A list of CoinGecko coin IDs (e.g., ['bitcoin', 'ethereum']).

        Returns:
            A dictionary mapping each coin ID to its market data.
        """
        if not coin_ids:
            return {}

        if self.settings.TESTING_MODE or self.settings.COINGECKO_API_DISABLED:
            logger.info(
                f"TESTING_MODE or COINGECKO_API_DISABLED enabled. Returning mock market data for: {coin_ids}"
            )
            return {
                coin_id: _generate_mock_market_data(coin_id) for coin_id in coin_ids
            }

        increment_api_call_counter()
        session = await self.get_session()
        ids_str = ",".join(coin_ids)
        price_change_params = "1h,24h,7d"
        base_url = f"{self.BASE_URL}/coins/markets?vs_currency=usd&ids={ids_str}&price_change_percentage={price_change_params}"
        url = self._get_url_with_api_key(base_url)

        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()

                result = {item["id"]: item for item in data}
                return result

        except aiohttp.ClientError as e:
            logger.error(f"Error fetching market data from CoinGecko: {e}")
            return {coin_id: {} for coin_id in coin_ids}
        except Exception as e:
            logger.error(f"Unexpected error in get_markets_data: {e}")
            return {coin_id: {} for coin_id in coin_ids}

    @cached(ttl=300)  # Cache for 5 minutes
    async def get_historical_prices(
        self, coin_id: str, days: int
    ) -> Optional[Dict[str, List[Tuple[datetime, float]]]]:
        """
        Get historical price and volume data for a specific coin.

        Args:
            coin_id: The CoinGecko ID of the coin (e.g., 'bitcoin').
            days: The number of days to fetch historical data for.

        Returns:
            A dictionary with 'prices' and 'volumes', each a list of (timestamp, value) tuples, or None if an error occurs.
        """
        if self.settings.TESTING_MODE or self.settings.COINGECKO_API_DISABLED:
            logger.info(
                f"TESTING_MODE or COINGECKO_API_DISABLED enabled. Returning mock historical prices for: {coin_id}"
            )
            mock_prices = []
            for i in range(days):
                date = datetime.now(timezone.utc) - timedelta(days=i)
                mock_data = _generate_mock_price(coin_id)
                mock_prices.append((date, mock_data["price"]))
            # Mock volume data as well
            mock_volumes = [(p[0], random.uniform(1e9, 5e10)) for p in mock_prices]
            return {
                "prices": list(reversed(mock_prices)),
                "volumes": list(reversed(mock_volumes)),
            }

        increment_api_call_counter()
        session = await self.get_session()
        base_url = f"{self.BASE_URL}/coins/{coin_id}/market_chart?vs_currency=usd&days={days}&interval=daily"
        url = self._get_url_with_api_key(base_url)

        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()

                prices = data.get("prices", [])
                volumes = data.get("total_volumes", [])

                # Convert timestamp from ms to datetime object
                price_data = [
                    (datetime.fromtimestamp(p[0] / 1000, tz=timezone.utc), p[1])
                    for p in prices
                ]
                volume_data = [
                    (datetime.fromtimestamp(v[0] / 1000, tz=timezone.utc), v[1])
                    for v in volumes
                ]

                return {"prices": price_data, "volumes": volume_data}

        except aiohttp.ClientError as e:
            logger.error(f"Error fetching historical data for {coin_id}: {e}")
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error in get_historical_prices for {coin_id}: {e}"
            )
            return None

    async def calculate_price_change_percent(
        self, current_price: float, previous_price: float
    ) -> float:
        """
        Calculate percentage change between two prices.

        Args:
            current_price: Current price
            previous_price: Previous price to compare against

        Returns:
            float: Percentage change (can be positive or negative)
        """
        if previous_price == 0:
            return 0.0
        return ((current_price - previous_price) / previous_price) * 100

    async def should_trigger_alert(
        self, current_price: float, last_alert_price: float, threshold: float
    ) -> Tuple[bool, float]:
        """
        Check if price change exceeds the specified threshold.

        Args:
            current_price: Current price
            last_alert_price: Price at last alert
            threshold: Percentage threshold for alert

        Returns:
            Tuple of (should_alert, change_percent)
        """
        if last_alert_price is None:
            return False, 0.0

        change_percent = await self.calculate_price_change_percent(
            current_price, last_alert_price
        )

        return abs(change_percent) >= threshold, change_percent

    @cached(ttl=300)  # Cache for 5 minutes
    async def get_market_data(self) -> Dict[str, Any]:
        """
        Get current market data for Bitcoin.

        Returns:
            Dict containing market data including price, market cap, volume, etc.
        """
        if self.settings.TESTING_MODE:
            logger.info("TESTING_MODE enabled. Returning mock market data.")
            mock_price_data = _generate_mock_price("bitcoin")
            return {
                "current_price": mock_price_data["price"],
                "price_change_percentage_24h": mock_price_data["change_24h"],
                "market_cap": 1.2e12,  # Mock value
                "total_volume": 5e10,  # Mock value
                "high_24h": mock_price_data["price"] * 1.05,
                "low_24h": mock_price_data["price"] * 0.95,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

        increment_api_call_counter()
        session = await self.get_session()
        base_url = f"{self.BASE_URL}/coins/bitcoin?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false&sparkline=false"
        url = self._get_url_with_api_key(base_url)

        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()

            if not data or "market_data" not in data:
                logger.warning("No market data available in API response")
                return {}

            market_data = data["market_data"]
            self.market_data = {
                "current_price": market_data.get("current_price", {}).get("usd"),
                "price_change_percentage_24h": market_data.get(
                    "price_change_percentage_24h", 0
                ),
                "market_cap": market_data.get("market_cap", {}).get("usd", 0),
                "total_volume": market_data.get("total_volume", {}).get("usd", 0),
                "high_24h": market_data.get("high_24h", {}).get("usd"),
                "low_24h": market_data.get("low_24h", {}).get("usd"),
                "last_updated": market_data.get("last_updated"),
            }

            # Update price history with the latest data
            if "current_price" in self.market_data:
                await self._update_price_history(
                    self.market_data["current_price"],
                    self.market_data["price_change_percentage_24h"],
                )

            return self.market_data

        except Exception as e:
            logger.error(f"Error fetching market data: {e}")
            return {}

    async def _update_price_history(self, price: float, change_24h: float) -> None:
        """Update the price history with the latest price data."""
        timestamp = datetime.utcnow()
        price_entry = {
            "price": price,
            "timestamp": timestamp,
            "price_change_percentage_24h": change_24h,
        }

        if "bitcoin" not in self.price_history:
            self.price_history["bitcoin"] = []

        self.price_history["bitcoin"].append(price_entry)

        # Keep only the last 1000 price points to prevent memory issues
        if len(self.price_history["bitcoin"]) > 1000:
            self.price_history["bitcoin"] = self.price_history["bitcoin"][-1000:]

    def get_recent_price_history(self, hours: int = 24) -> List[Dict]:
        """
        Get recent price history for Bitcoin.

        Args:
            hours: Number of hours of history to return (max 168 hours/7 days)

        Returns:
            List of price points with timestamp and price
        """
        if "bitcoin" not in self.price_history or not self.price_history["bitcoin"]:
            return []

        # Cap at 7 days of history for performance
        hours = min(int(hours), 168)
        cutoff = datetime.utcnow() - timedelta(hours=hours)

        return [p for p in self.price_history["bitcoin"] if p["timestamp"] > cutoff]

    @cached(ttl=600)  # Cache for 10 minutes
    async def get_global_market_data(self) -> Dict[str, Any]:
        """
        Get global cryptocurrency market data, including market cap, volume, and BTC dominance.

        Returns:
            Dict containing global market data.
        """
        if self.settings.TESTING_MODE:
            logger.info("TESTING_MODE enabled. Returning mock global market data.")
            return {
                "total_market_cap": {"usd": 2.5e12},
                "total_volume": {"usd": 1.5e11},
                "market_cap_percentage": {"btc": 45.0, "eth": 18.0},
            }

        increment_api_call_counter()
        session = await self.get_session()
        base_url = f"{self.BASE_URL}/global"
        url = self._get_url_with_api_key(base_url)

        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                return data.get("data", {})
        except aiohttp.ClientError as e:
            logger.error(f"Error fetching global market data from CoinGecko: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error in get_global_market_data: {e}")
            return {}

    def _get_trend_momentum_commentary(
        self, price_1h: float, price_24h: float, price_7d: float
    ) -> Tuple[str, str]:
        """Analyzes multi-timeframe data to identify trend and momentum."""
        # Trend Analysis
        if price_1h > 0 and price_24h > 0 and price_7d > 0:
            trend = "strong bullish momentum"
        elif price_1h < 0 and price_24h < 0 and price_7d < 0:
            trend = "strong bearish momentum"
        elif price_1h > 0 and price_24h > 0 and price_7d < 0:
            trend = "a potential bullish reversal"
        elif price_1h < 0 and price_24h < 0 and price_7d > 0:
            trend = "a potential bearish reversal"
        elif abs(price_24h) < 1:
            trend = "a consolidation phase"
        else:
            trend = "mixed signals"

        # Momentum Indicator
        if abs(price_24h) > 5:
            momentum = "high"
        elif abs(price_24h) > 2:
            momentum = "moderate"
        else:
            momentum = "low"

        return trend, momentum

    def _format_percent(self, value: Optional[float], decimals: int = 2) -> str:
        """Utility for formatting percentage changes with sign."""
        if value is None:
            return "N/A"
        try:
            return f"{value:+.{decimals}f}%"
        except (TypeError, ValueError):
            return "N/A"

    async def _fetch_related_news(
        self,
        search_terms: List[str],
        *,
        hours: int = DEFAULT_NEWS_LOOKBACK_HOURS,
        limit: int = DEFAULT_NEWS_LIMIT,
    ) -> List[Dict[str, Any]]:
        """Fetch high-signal articles associated with the provided search terms."""
        unique_terms = [
            term
            for term in {t.strip() for t in search_terms if t and isinstance(t, str)}
            if term
        ]
        if not unique_terms:
            return []

        try:
            return await article_service.get_top_articles_for_symbols(
                unique_terms,
                hours=hours,
                limit=limit,
            )
        except Exception as exc:
            logger.warning(
                "Failed to retrieve related news articles: %s", exc, exc_info=True
            )
            return []

    @cached(ttl=600)  # Cache for 10 minutes - longer cache for analysis
    async def generate_market_analysis_commentary(
        self, coin_id: str = "bitcoin"
    ) -> str:
        """Generate enriched market commentary for a cryptocurrency with comprehensive narrative analysis.

        This function provides sophisticated crash analysis by correlating price movements
        with news drivers, mentioning key factors like ETF outflows, whale liquidations,
        and Fed policy uncertainty.
        """
        try:
            # Fetch related news articles for narrative analysis
            search_terms = [coin_id.lower(), coin_id.upper()]
            if coin_id.lower() == "bitcoin":
                search_terms.extend(["BTC", "Bitcoin"])
            elif coin_id.lower() == "ethereum":
                search_terms.extend(["ETH", "Ethereum"])

            related_news = await self._fetch_related_news(
                search_terms,
                hours=24,  # Focus on recent 24 hours for crash analysis
                limit=10,
            )

            # Use sophisticated narrative analysis
            narratives_section = await self._analyze_developing_narratives(
                related_news, coin_id, historical_hours=48  # 2 days for crash context
            )

            # Get market data for context
            market_data = await self.get_global_market_data()
            coin_data = market_data.get(coin_id.lower(), {})

            if not coin_data:
                return f"Market data unavailable for {coin_id}. {narratives_section}"

            # Extract key metrics
            current_price = coin_data.get("current_price")
            price_1h = coin_data.get("price_change_percentage_1h_in_currency", 0)
            price_24h = coin_data.get("price_change_percentage_24h_in_currency", 0)
            price_7d = coin_data.get("price_change_percentage_7d_in_currency", 0)
            market_cap_rank = coin_data.get("market_cap_rank", "N/A")
            total_volume = coin_data.get("total_volume", 0)
            market_cap = coin_data.get("market_cap", 0)

            # Get competitor data for context
            competitor_data = {}
            if coin_id.lower() == "bitcoin":
                competitor_data = market_data.get("ethereum", {})
            elif coin_id.lower() == "ethereum":
                competitor_data = market_data.get("bitcoin", {})

            # Generate trend and momentum commentary
            trend, momentum = self._get_trend_momentum_commentary(
                price_1h, price_24h, price_7d
            )

            # Format market context
            market_context = f"Market showing {trend} with {momentum} momentum."

            # Format volume summary
            if total_volume > 1000000000:  # > $1B
                volume_summary = (
                    f"High trading volume at ${(total_volume / 1000000000):.1f}B."
                )
            else:
                volume_summary = f"Trading volume at ${(total_volume / 1000000):.0f}M."

            # Format volatility summary (based on price movements)
            volatility = (
                "extreme"
                if abs(price_24h) > 5
                else "high" if abs(price_24h) > 2 else "moderate"
            )
            volatility_summary = f"Market volatility is {volatility}."

            # Format momentum summary
            momentum_summary = f"Price momentum indicates {trend.lower()}."

            # Competitor context
            competitor_context = ""
            if competitor_data:
                competitor_name = competitor_data.get("name", coin_id.capitalize())
                competitor_change = competitor_data.get(
                    "price_change_percentage_24h_in_currency"
                )
                if competitor_change is not None:
                    competitor_context = f"Key peer check: {competitor_name} 24h move {self._format_percent(competitor_change)}."

            # Bitcoin dominance (only for Bitcoin analysis)
            btc_dominance_section = ""
            if coin_id.lower() == "bitcoin":
                # Calculate approximate BTC dominance from market cap
                total_market_cap = sum(
                    coin.get("market_cap", 0)
                    for coin in market_data.values()
                    if coin.get("market_cap")
                )
                if total_market_cap > 0:
                    btc_dominance = (market_cap / total_market_cap) * 100
                    btc_dominance_section = (
                        f"Bitcoin's market dominance stands at {btc_dominance:.2f}%."
                    )

            # Build comprehensive response
            coin_name = coin_id.capitalize()
            headline_price = (
                f"{coin_name} (Rank #{market_cap_rank}) is trading at "
                f"{f'${current_price:,.2f}' if current_price is not None else 'price unavailable'}."
            )

            move_summary = (
                f"Timeframe performance — 1h {self._format_percent(price_1h)}, "
                f"24h {self._format_percent(price_24h)}, 7d {self._format_percent(price_7d)}."
            )

            commentary_parts = [headline_price, move_summary]
            if market_context:
                commentary_parts.append(market_context)
            commentary_parts.extend(
                [volume_summary, volatility_summary, momentum_summary]
            )
            if competitor_context:
                commentary_parts.append(competitor_context)
            commentary_parts.append(narratives_section)
            if btc_dominance_section:
                commentary_parts.append(btc_dominance_section)

            return " ".join(part for part in commentary_parts if part).strip()

        except Exception as e:
            logger.error(
                f"Error generating market analysis for {coin_id}: {e}", exc_info=True
            )
            return f"Market analysis temporarily unavailable for {coin_id}. Please try again later."

    async def _analyze_developing_narratives(
        self,
        current_articles: List[Dict[str, Any]],
        coin_id: str,
        historical_hours: int = 168,  # 7 days
    ) -> str:
        """Analyze developing narratives from current and historical news articles.

        Args:
            current_articles: Current news articles to analyze
            coin_id: The cryptocurrency being analyzed
            historical_hours: How far back to look for historical context

        Returns:
            Detailed narrative analysis string
        """
        if not current_articles:
            return "Developing narratives: No high-signal news to analyze yet."

        # Get historical articles for context
        historical_search_terms = [coin_id.lower(), coin_id.upper()]
        if coin_id.lower() == "bitcoin":
            historical_search_terms.extend(["BTC", "Bitcoin"])
        elif coin_id.lower() == "ethereum":
            historical_search_terms.extend(["ETH", "Ethereum"])

        try:
            historical_articles = await self._fetch_related_news(
                historical_search_terms, hours=historical_hours, limit=20
            )
        except Exception:
            historical_articles = []

        # Analyze current narratives
        current_themes = self._extract_themes_from_articles(current_articles)
        current_sentiment_trend = self._analyze_sentiment_trend(current_articles)

        # Analyze historical context
        historical_themes = self._extract_themes_from_articles(historical_articles)
        narrative_evolution = self._analyze_narrative_evolution(
            current_themes, historical_themes
        )

        # Generate narrative description
        narrative_description = self._generate_narrative_description(
            current_themes, current_sentiment_trend, narrative_evolution, coin_id
        )

        return narrative_description

    def _extract_themes_from_articles(
        self, articles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Extract meaningful themes and narratives from articles.

        Args:
            articles: List of news articles

        Returns:
            Dictionary containing themes, sentiment patterns, and narrative elements
        """
        if not articles:
            return {"themes": [], "sentiment_patterns": {}, "narrative_elements": []}

        themes = []
        sentiment_scores = []
        narrative_elements = []

        # Theme extraction from titles and content
        for article in articles:
            title = article.get("title", "").lower()
            keywords = article.get("keywords", [])

            # Extract narrative themes from titles - Enhanced for crash analysis
            if any(
                word in title
                for word in ["surge", "surges", "rally", "rallies", "soar", "soars"]
            ):
                themes.append("price_surge")
            if any(
                word in title
                for word in [
                    "fall",
                    "falls",
                    "drop",
                    "drops",
                    "decline",
                    "declines",
                    "crash",
                    "crashing",
                    "dump",
                    "dumping",
                ]
            ):
                themes.append("price_decline")
            if any(
                word in title
                for word in ["adoption", "adopts", "integration", "mainstream"]
            ):
                themes.append("institutional_adoption")
            if any(
                word in title
                for word in ["regulation", "regulatory", "rules", "compliance"]
            ):
                themes.append("regulatory_development")
            if any(word in title for word in ["etf", "fund", "investment", "treasury"]):
                themes.append("institutional_investment")
            if any(
                word in title for word in ["technical", "upgrade", "update", "fork"]
            ):
                themes.append("technical_development")
            if any(
                word in title
                for word in ["million", "billion", "funding", "raise", "investment"]
            ):
                themes.append("funding_activity")

            # Enhanced crash-specific theme detection
            if any(word in title for word in ["etf", "outflows", "outflow"]):
                themes.append("etf_outflows")
            if any(
                word in title
                for word in ["whale", "liquidation", "liquidations", "cascade"]
            ):
                themes.append("whale_liquidations")
            if any(
                word in title
                for word in ["fed", "federal", "policy", "hawkish", "dovish"]
            ):
                themes.append("monetary_policy")
            if any(
                word in title
                for word in ["volatility", "volatile", "turbulence", "turmoil"]
            ):
                themes.append("market_volatility")

            # Extract sentiment
            sentiment_score = article.get("sentiment_score", 0.0)
            sentiment_scores.append(sentiment_score)

            # Extract narrative elements
            if "bull" in title or "bullish" in title:
                narrative_elements.append("bullish_sentiment")
            if "bear" in title or "bearish" in title:
                narrative_elements.append("bearish_sentiment")
            if any(
                word in title for word in ["future", "outlook", "prospect", "potential"]
            ):
                narrative_elements.append("future_outlook")

        # Count theme frequencies
        theme_counts = {}
        for theme in themes:
            theme_counts[theme] = theme_counts.get(theme, 0) + 1

        # Sort themes by frequency
        sorted_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)

        return {
            "themes": sorted_themes,
            "sentiment_scores": sentiment_scores,
            "narrative_elements": list(set(narrative_elements)),
            "avg_sentiment": (
                sum(sentiment_scores) / len(sentiment_scores)
                if sentiment_scores
                else 0.0
            ),
        }

    def _analyze_sentiment_trend(
        self, articles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze sentiment trends in the articles with user-friendly explanations.

        Args:
            articles: List of news articles

        Returns:
            Dictionary with sentiment trend analysis and clear explanations
        """
        if not articles:
            return {
                "trend": "neutral",
                "confidence": 0.0,
                "user_friendly": "Limited news coverage available",
            }

        sentiment_scores = [article.get("sentiment_score", 0.0) for article in articles]
        avg_sentiment = (
            sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.0
        )

        # Determine trend strength with user-friendly descriptions
        if avg_sentiment >= 0.3:
            trend = "bullish"
            confidence = min(avg_sentiment * 2, 1.0)  # Scale to 0-1
            user_friendly = "Strong positive sentiment suggesting upward price pressure"
        elif avg_sentiment >= 0.1:
            trend = "bullish"
            confidence = min(avg_sentiment * 3, 1.0)
            user_friendly = "Positive sentiment indicating potential buying interest"
        elif avg_sentiment <= -0.3:
            trend = "bearish"
            confidence = min(abs(avg_sentiment) * 2, 1.0)
            user_friendly = (
                "Strong negative sentiment suggesting continued downward pressure"
            )
        elif avg_sentiment <= -0.1:
            trend = "bearish"
            confidence = min(abs(avg_sentiment) * 3, 1.0)
            user_friendly = "Negative sentiment indicating selling pressure"
        else:
            trend = "neutral"
            confidence = 1.0 - min(abs(avg_sentiment) * 4, 1.0)
            user_friendly = "Mixed sentiment with no clear directional bias"

        return {
            "trend": trend,
            "confidence": confidence,
            "avg_score": avg_sentiment,
            "user_friendly": user_friendly,
        }

    def _analyze_narrative_evolution(
        self, current_themes: Dict, historical_themes: Dict
    ) -> Dict[str, Any]:
        """Analyze how narratives have evolved over time.

        Args:
            current_themes: Current themes analysis
            historical_themes: Historical themes analysis

        Returns:
            Dictionary with narrative evolution analysis
        """
        current_top_themes = [
            theme for theme, count in current_themes.get("themes", [])[:3]
        ]
        historical_top_themes = [
            theme for theme, count in historical_themes.get("themes", [])[:5]
        ]

        # Find emerging themes (in current but not historical)
        emerging_themes = [
            theme for theme in current_top_themes if theme not in historical_top_themes
        ]

        # Find continuing themes (in both)
        continuing_themes = [
            theme for theme in current_top_themes if theme in historical_top_themes
        ]

        # Calculate theme evolution
        current_sentiment = current_themes.get("avg_sentiment", 0.0)
        historical_sentiment = historical_themes.get("avg_sentiment", 0.0)
        sentiment_change = current_sentiment - historical_sentiment

        return {
            "emerging_themes": emerging_themes,
            "continuing_themes": continuing_themes,
            "sentiment_change": sentiment_change,
            "narrative_maturity": len(continuing_themes)
            / max(len(current_top_themes), 1),
        }

    def _generate_narrative_description(
        self, current_themes: Dict, sentiment_trend: Dict, evolution: Dict, coin_id: str
    ) -> str:
        """Generate a compelling narrative description with clear market direction guidance.

        Args:
            current_themes: Current themes analysis
            sentiment_trend: Sentiment trend analysis
            evolution: Narrative evolution analysis
            coin_id: The cryptocurrency being analyzed

        Returns:
            Formatted narrative description string with clear market direction
        """
        top_themes = current_themes.get("themes", [])

        if not top_themes:
            return f"Market analysis shows {sentiment_trend['user_friendly']}. Overall sentiment {current_themes.get('avg_sentiment', 0):+.2f}."

        # Create meaningful theme descriptions - Enhanced for crash analysis with clear explanations
        theme_descriptions = []
        for theme, count in top_themes[:3]:
            if theme == "price_surge":
                theme_descriptions.append("strong buying momentum")
            elif theme == "price_decline":
                theme_descriptions.append("significant selling pressure")
            elif theme == "institutional_adoption":
                theme_descriptions.append("growing mainstream acceptance")
            elif theme == "regulatory_development":
                theme_descriptions.append("regulatory uncertainty affecting prices")
            elif theme == "institutional_investment":
                theme_descriptions.append("large investor activity driving prices")
            elif theme == "technical_development":
                theme_descriptions.append("positive technical developments")
            elif theme == "funding_activity":
                theme_descriptions.append("increased funding and development")
            # Enhanced crash-specific theme descriptions with clear market impact
            elif theme == "etf_outflows":
                theme_descriptions.append(
                    "ETF outflows creating significant selling pressure"
                )
            elif theme == "whale_liquidations":
                theme_descriptions.append(
                    "large holder sales triggering market decline"
                )
            elif theme == "monetary_policy":
                theme_descriptions.append(
                    "central bank policy creating market uncertainty"
                )
            elif theme == "market_volatility":
                theme_descriptions.append("extreme price swings and uncertainty")
            else:
                theme_descriptions.append(f"{theme.replace('_', ' ')} trends")

        # Build narrative description with clear market direction
        narrative_parts = []

        # Main themes with market impact explanation
        if theme_descriptions:
            narrative_parts.append(f"Key drivers: {', '.join(theme_descriptions)}")

        # Narrative evolution with clear market direction implications
        emerging = evolution.get("emerging_themes", [])
        continuing = evolution.get("continuing_themes", [])

        if emerging:
            emerging_desc = [theme.replace("_", " ") for theme in emerging]
            narrative_parts.append(f"New factors emerging: {', '.join(emerging_desc)}")

        if continuing:
            continuing_desc = [theme.replace("_", " ") for theme in continuing]
            narrative_parts.append(f"Ongoing pressures: {', '.join(continuing_desc)}")

        # Clear sentiment explanation with market direction guidance
        sentiment_trend_desc = sentiment_trend["trend"]
        confidence = sentiment_trend["confidence"]
        user_friendly_sentiment = sentiment_trend["user_friendly"]

        narrative_parts.append(user_friendly_sentiment)

        # Narrative maturity with clear implications for market direction
        maturity = evolution.get("narrative_maturity", 0)
        if maturity > 0.6:
            narrative_parts.append(
                "Multiple consistent factors pointing to continued downward movement"
            )
        elif maturity > 0.3:
            narrative_parts.append(
                "Several factors suggesting potential further decline"
            )
        else:
            narrative_parts.append("Early signs of market stress that could develop")

        # Add overall sentiment score in context
        avg_sentiment = current_themes.get("avg_sentiment", 0)
        if avg_sentiment <= -0.2:
            narrative_parts.append(
                "Strong negative news flow suggests continued downside risk"
            )
        elif avg_sentiment <= -0.1:
            narrative_parts.append(
                "Negative news environment indicates caution warranted"
            )
        elif avg_sentiment >= 0.2:
            narrative_parts.append(
                "Positive news flow suggests potential recovery ahead"
            )
        elif avg_sentiment >= 0.1:
            narrative_parts.append(
                "Moderately positive news could support price stabilization"
            )

        return f"Market analysis: {'; '.join(narrative_parts)}. Overall sentiment {avg_sentiment:+.2f}."

        # Factory function for dependency injection (v2)
        @lru_cache()
        def get_price_service() -> CoinGeckoPriceService:
            """Factory function to get a singleton instance of the price service."""


# Factory function for dependency injection (v2)
@lru_cache()
def get_price_service() -> CoinGeckoPriceService:
    """Factory function to get a singleton instance of the price service."""
    return CoinGeckoPriceService()


price_service = get_price_service()
