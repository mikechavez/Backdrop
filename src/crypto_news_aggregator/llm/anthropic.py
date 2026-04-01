import os
import json
import logging
from typing import List, Dict, Any
import httpx
from .base import LLMProvider
from .tracking import track_usage
from ..services.entity_normalization import normalize_entity_name
from ..services.rate_limiter import get_rate_limiter
from ..services.circuit_breaker import get_circuit_breaker

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    """
    LLM provider for Anthropic's Claude models, using direct httpx calls to bypass client issues.
    """

    API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(
        self, api_key: str, model_name: str = "claude-haiku-4-5-20251001"
    ):
        if not api_key:
            raise ValueError("Anthropic API key not provided.")
        self.api_key = api_key
        self.model_name = model_name

    def _get_completion(self, prompt: str) -> str:
        """
        Get completion from Claude. Does NOT fall back to Sonnet.

        NOTE: This method is used by all narrative processing (narrative_themes.py),
        not just briefings. Sonnet fallback causes unnecessary 5x cost escalation.
        Sonnet is only used in briefing_agent.py which has its own separate model fallback chain.
        See BUG-039 for context.
        """
        # Use primary model only (Haiku) - no expensive fallback
        model = self.model_name

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 2048,  # Increased for narrative JSON responses
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            with httpx.Client() as client:
                response = client.post(
                    self.API_URL, headers=headers, json=payload, timeout=30
                )
                response.raise_for_status()
                data = response.json()
                return data.get("content", [{}])[0].get("text", "")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.warning(
                    f"403 Forbidden for model {model}. "
                    f"NOT falling back to Sonnet (BUG-039). "
                    f"Will retry or fail gracefully."
                )
                try:
                    error_json = e.response.json()
                    error_msg = error_json.get("error", {}).get("message", "")
                    logger.debug(f"Error details: {error_msg}")
                except:
                    pass
            else:
                # For non-403 errors, log and return empty
                logger.error(
                    f"Anthropic API request failed with status {e.response.status_code}: {e.response.text}"
                )
            return ""
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            return ""

    def _get_completion_with_usage(self, prompt: str) -> tuple[str, dict]:
        """
        Get completion from Claude and return both response text and usage metrics.
        Used internally for cost tracking.

        Returns:
            Tuple of (response_text, usage_dict) where usage_dict has input_tokens and output_tokens
        """
        model = self.model_name

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            with httpx.Client() as client:
                response = client.post(
                    self.API_URL, headers=headers, json=payload, timeout=30
                )
                response.raise_for_status()
                data = response.json()
                text = data.get("content", [{}])[0].get("text", "")
                usage = data.get("usage", {})
                return text, usage
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 403:
                logger.error(
                    f"Anthropic API request failed with status {e.response.status_code}: {e.response.text}"
                )
            return "", {}
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            return "", {}

    @track_usage
    def analyze_sentiment(self, text: str) -> float:
        prompt = f"Analyze the sentiment of this crypto text. Return ONLY a single number from -1.0 (very bearish) to 1.0 (very bullish). Do not include any explanation or additional text. Just the number:\n\n{text}"
        response = self._get_completion(prompt)
        try:
            # Extract the first number from the response (in case there's extra text)
            import re

            numbers = re.findall(r"[-+]?\d*\.\d+|\d+", response.strip())
            if numbers:
                return float(numbers[0])
            return float(response.strip())
        except (ValueError, TypeError):
            return 0.0

    @track_usage
    def extract_themes(self, texts: List[str]) -> List[str]:
        combined_texts = "\n".join(texts)
        prompt = f"Extract the key crypto themes from the following texts. Respond with ONLY a comma-separated list of keywords (e.g., 'Bitcoin, DeFi, Regulation'). Do not include any preamble.\n\nTexts:\n{combined_texts}"
        response = self._get_completion(prompt)
        if response:
            return [theme.strip() for theme in response.split(",")]
        return []

    @track_usage
    def generate_insight(self, data: Dict[str, Any]) -> str:
        sentiment_score = data.get("sentiment_score", 0.0)
        themes = data.get("themes", [])
        prompt = f"Given a sentiment score of {sentiment_score} and the themes {', '.join(themes)}, generate a concise market insight for cryptocurrency traders. The response must be a maximum of 2-3 sentences."
        return self._get_completion(prompt)

    @track_usage
    def score_relevance(self, text: str) -> float:
        prompt = f"On a scale from 0.0 to 1.0, how relevant is this text to cryptocurrency market movements? Return ONLY a single floating-point number with no explanation:\n\n{text}"
        response = self._get_completion(prompt)
        try:
            # Extract the first number from the response (in case there's extra text)
            import re

            numbers = re.findall(r"[-+]?\d*\.\d+|\d+", response.strip())
            if numbers:
                return float(numbers[0])
            return float(response.strip())
        except (ValueError, TypeError):
            return 0.0

    def extract_entities_batch(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extracts entities from a batch of articles using Claude Haiku only.
        Returns structured data with entities for each article and usage metrics.
        No fallback to Sonnet (see BUG-039).
        """
        from ..core.config import settings
        import asyncio

        # Circuit breaker check: entity_extraction
        try:
            circuit_breaker = get_circuit_breaker()
            state = circuit_breaker._get_state("entity_extraction")
            if state.value == "open":
                message = (
                    f"Circuit breaker OPEN for 'entity_extraction' due to repeated failures. "
                    f"Service unavailable, retrying in {circuit_breaker.config['cooldown_seconds']}s."
                )
                logger.warning(message)
                return {"results": [], "usage": {}}
        except Exception as e:
            logger.warning(f"Failed to check circuit breaker for entity_extraction: {e}")

        # Rate limit check: entity_extraction
        try:
            rate_limiter = get_rate_limiter()
            # Use sync-style check since this method is synchronous
            key = rate_limiter._get_daily_key("entity_extraction")
            count = rate_limiter.redis.get(key)
            current_count = int(count) if count else 0
            limit = rate_limiter.limits.get("entity_extraction", 5000)

            if current_count >= limit:
                logger.warning(
                    f"Daily limit for 'entity_extraction' hit ({limit} calls). "
                    f"Resets tomorrow at midnight UTC."
                )
                return {"results": [], "usage": {}}
        except Exception as e:
            logger.warning(f"Failed to check rate limit for entity_extraction: {e}")

        # Build the batch prompt
        articles_text = []
        for idx, article in enumerate(articles):
            article_id = article.get("id", f"article_{idx}")
            title = article.get("title", "")
            text = article.get("text", "")
            articles_text.append(
                f"Article {idx} (ID: {article_id}):\nTitle: {title}\nText: {text}\n"
            )

        combined_articles = "\n---\n".join(articles_text)

        prompt = f"""Extract entities from these {len(articles)} crypto news articles. Return ONLY valid JSON with no markdown.

PRIMARY entities (trackable/investable):
- cryptocurrency: Bitcoin, Ethereum, Litecoin, Solana (include ticker like $BTC if mentioned)
- blockchain: Ethereum, Solana, Avalanche (as platforms)
- protocol: Uniswap, Aave, Lido (DeFi protocols)
- company: Circle, Coinbase, MicroStrategy, BlackRock (crypto-related companies)
- organization: SEC, Federal Reserve, IMF, World Bank, CFTC (government/regulatory/NGO)

CONTEXT entities (for enrichment):
- event: launch, hack, upgrade, halving, rally, approval
- concept: DeFi, regulation, staking, altcoin, ETF, NFT
- person: Vitalik Buterin, Michael Saylor, Donald Trump, Gary Gensler
- location: New York, Abu Dhabi, Dubai, El Salvador

Rules:
- Confidence must be > 0.80
- Tickers must be $SYMBOL format (2-5 uppercase letters)
- Generic phrases like 'Pilot Program' are concepts
- Return valid JSON only, no markdown formatting

Return ONLY a JSON array with one object per article:
{{
  "article_index": 0,
  "article_id": "the_id_from_input",
  "primary_entities": [
    {{"name": "Bitcoin", "type": "cryptocurrency", "ticker": "$BTC", "confidence": 0.95}},
    {{"name": "Circle", "type": "company", "confidence": 0.90}}
  ],
  "context_entities": [
    {{"name": "regulation", "type": "concept", "confidence": 0.85}},
    {{"name": "Michael Saylor", "type": "person", "confidence": 0.88}}
  ],
  "sentiment": "positive"
}}

Articles:
{combined_articles}

Return ONLY the JSON array, no other text."""

        # Use Haiku only - no Sonnet fallback
        # NOTE: Entity extraction should fail rather than silently use 5x more expensive model.
        # See BUG-039 for context.
        models_to_try = [
            (settings.ANTHROPIC_ENTITY_MODEL, "Haiku 4.5"),
        ]

        last_error = None

        for entity_model, model_label in models_to_try:
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": entity_model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            }

            try:
                logger.info(
                    f"Attempting entity extraction with {model_label} ({entity_model})"
                )
                with httpx.Client() as client:
                    response = client.post(
                        self.API_URL, headers=headers, json=payload, timeout=60
                    )
                    response.raise_for_status()
                    data = response.json()

                    # Extract response text
                    response_text = data.get("content", [{}])[0].get("text", "")
                    
                    # Log raw response for debugging
                    logger.info(f"Raw Anthropic response (first 500 chars): {response_text[:500]}")

                    # Extract usage metrics
                    usage = data.get("usage", {})
                    input_tokens = usage.get("input_tokens", 0)
                    output_tokens = usage.get("output_tokens", 0)

                    # Calculate costs (use Haiku pricing as baseline)
                    input_cost = (
                        input_tokens / 1000
                    ) * settings.ANTHROPIC_ENTITY_INPUT_COST_PER_1K_TOKENS
                    output_cost = (
                        output_tokens / 1000
                    ) * settings.ANTHROPIC_ENTITY_OUTPUT_COST_PER_1K_TOKENS
                    total_cost = input_cost + output_cost

                    # Parse JSON response
                    import re

                    # Try to extract JSON array from response
                    json_match = re.search(r"\[.*\]", response_text, re.DOTALL)
                    if json_match:
                        results = json.loads(json_match.group(0))
                    else:
                        results = json.loads(response_text)
                    
                    # Apply entity normalization to all extracted entities
                    for article_result in results:
                        # Normalize primary entities
                        for entity in article_result.get("primary_entities", []):
                            original_name = entity.get("name")
                            if original_name:
                                normalized_name = normalize_entity_name(original_name)
                                entity["name"] = normalized_name
                                # Also normalize ticker if present
                                ticker = entity.get("ticker")
                                if ticker:
                                    entity["ticker"] = normalize_entity_name(ticker)
                        
                        # Normalize context entities (only if they're cryptocurrency-related)
                        for entity in article_result.get("context_entities", []):
                            original_name = entity.get("name")
                            if original_name and entity.get("type") in ["cryptocurrency", "blockchain"]:
                                normalized_name = normalize_entity_name(original_name)
                                entity["name"] = normalized_name
                    
                    # Log parsed results for debugging
                    logger.info(f"Parsed {len(results)} article results from LLM")
                    if results:
                        # Log first result structure
                        first_result = results[0]
                        primary_count = len(first_result.get("primary_entities", []))
                        context_count = len(first_result.get("context_entities", []))
                        logger.info(f"Sample result structure - primary_entities: {primary_count}, context_entities: {context_count}")
                        if primary_count > 0:
                            logger.info(f"Sample primary entities (normalized): {first_result.get('primary_entities', [])[:3]}")
                        if context_count > 0:
                            logger.info(f"Sample context entities: {first_result.get('context_entities', [])[:3]}")

                    logger.info(f"Successfully extracted entities using {model_label}")

                    # Record circuit breaker success
                    try:
                        circuit_breaker = get_circuit_breaker()
                        circuit_breaker.record_success("entity_extraction")
                    except Exception as e:
                        logger.warning(f"Failed to record circuit breaker success for entity_extraction: {e}")

                    # Increment rate limiter counter after successful extraction
                    try:
                        rate_limiter = get_rate_limiter()
                        rate_limiter.redis.incr(rate_limiter._get_daily_key("entity_extraction"))
                        rate_limiter.redis.expire(rate_limiter._get_daily_key("entity_extraction"), 24 * 60 * 60)
                    except Exception as e:
                        logger.warning(f"Failed to increment rate limiter for entity_extraction: {e}")

                    # Track cost (async, non-blocking)
                    try:
                        from crypto_news_aggregator.services.cost_tracker import CostTracker
                        from crypto_news_aggregator.db.mongo_manager import mongo_manager
                        import asyncio

                        async def _track_entity_cost():
                            db = await mongo_manager.get_async_database()
                            tracker = CostTracker(db)
                            await tracker.track_call(
                                operation="entity_extraction",
                                model=entity_model,
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                            )

                        # Schedule as background task if we have event loop
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                asyncio.create_task(_track_entity_cost())
                            else:
                                # If no running loop, try to run synchronously via thread
                                import threading
                                threading.Thread(target=lambda: asyncio.run(_track_entity_cost()), daemon=True).start()
                        except RuntimeError:
                            # No event loop in current thread, schedule in thread
                            import threading
                            threading.Thread(target=lambda: asyncio.run(_track_entity_cost()), daemon=True).start()
                    except Exception as e:
                        logger.warning(f"Failed to track entity extraction cost: {e}")

                    return {
                        "results": results,
                        "usage": {
                            "model": entity_model,
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "total_tokens": input_tokens + output_tokens,
                            "input_cost": input_cost,
                            "output_cost": output_cost,
                            "total_cost": total_cost,
                        },
                    }
            except httpx.HTTPStatusError as e:
                error_detail = {
                    "status_code": e.response.status_code,
                    "response_text": e.response.text,
                    "model": entity_model,
                    "model_label": model_label,
                }

                # Log detailed error information
                logger.error(
                    f"Anthropic API request failed for {model_label} ({entity_model}): "
                    f"Status {e.response.status_code}, Response: {e.response.text}"
                )

                # Parse error response for more details
                try:
                    error_json = e.response.json()
                    error_type = error_json.get("error", {}).get("type", "unknown")
                    error_message = error_json.get("error", {}).get(
                        "message", "unknown"
                    )
                    logger.error(f"Error type: {error_type}, Message: {error_message}")
                except:
                    pass

                last_error = error_detail

                # If 403, try next model in fallback list
                if e.response.status_code == 403:
                    logger.warning(
                        f"403 Forbidden for {model_label}, trying fallback model..."
                    )
                    continue
                else:
                    # For other HTTP errors, don't try fallback
                    break

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response from {model_label}: {e}")
                last_error = {
                    "error": "json_decode",
                    "message": str(e),
                    "model": entity_model,
                }
                break
            except Exception as e:
                logger.error(f"Entity extraction failed for {model_label}: {e}")
                last_error = {
                    "error": "exception",
                    "message": str(e),
                    "model": entity_model,
                }
                break

        # All models failed
        logger.error(f"All entity extraction models failed. Last error: {last_error}")

        # Record circuit breaker failure
        try:
            circuit_breaker = get_circuit_breaker()
            circuit_breaker.record_failure("entity_extraction")
        except Exception as e:
            logger.warning(f"Failed to record circuit breaker failure for entity_extraction: {e}")

        return {"results": [], "usage": {}}

    async def enrich_articles_batch(self, articles: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Batch enrich multiple articles with relevance, sentiment, and themes in a single prompt.
        TASK-025 Priority 3: 50% cost reduction by batching 10 articles per call.

        Args:
            articles: List of dicts with "id" and "text" keys (max 10 articles per call)

        Returns:
            List of dicts with enrichment results: {
                "id": article_id,
                "relevance_score": float 0-1,
                "sentiment_score": float -1-1,
                "themes": [str]
            }
        """
        if not articles or len(articles) == 0:
            return []

        # Circuit breaker checks: enrich_articles_batch uses both sentiment_analysis and theme_extraction
        circuit_breaker = get_circuit_breaker()
        allowed, message = await circuit_breaker.check_circuit("sentiment_analysis")
        if not allowed:
            logger.warning(f"Circuit breaker OPEN for sentiment_analysis: {message}")
            return []

        allowed, message = await circuit_breaker.check_circuit("theme_extraction")
        if not allowed:
            logger.warning(f"Circuit breaker OPEN for theme_extraction: {message}")
            return []

        # Rate limit check: enrich_articles_batch uses both sentiment_analysis and theme_extraction
        rate_limiter = get_rate_limiter()
        allowed, message = await rate_limiter.check_limit("sentiment_analysis")
        if not allowed:
            logger.warning(f"Rate limit hit for sentiment_analysis: {message}")
            return []

        allowed, message = await rate_limiter.check_limit("theme_extraction")
        if not allowed:
            logger.warning(f"Rate limit hit for theme_extraction: {message}")
            return []

        # Limit to 10 articles per batch (tunable)
        batch_articles = articles[:10]

        # Build combined prompt for batch scoring
        articles_text = []
        for idx, article in enumerate(batch_articles):
            article_id = article.get("id", f"article_{idx}")
            text = article.get("text", "")[:2000]  # Limit text length
            articles_text.append(f"Article {idx} (ID: {article_id}):\n{text}")

        combined_articles = "\n---\n".join(articles_text)

        prompt = f"""Analyze these {len(batch_articles)} cryptocurrency news articles and return ONLY valid JSON.

For each article, provide:
1. relevance_score: 0.0-1.0 (how relevant to crypto market movements)
2. sentiment_score: -1.0-1.0 (bearish to bullish)
3. themes: comma-separated keywords

Return ONLY a JSON array with this structure:
[
  {{
    "article_index": 0,
    "article_id": "the_id_from_input",
    "relevance_score": 0.8,
    "sentiment_score": 0.3,
    "themes": ["Bitcoin", "DeFi", "Regulation"]
  }}
]

Articles:
{combined_articles}

Return ONLY the JSON array, no other text."""

        try:
            response_text, usage = self._get_completion_with_usage(prompt)

            # Record success immediately (before any processing)
            circuit_breaker.record_success("sentiment_analysis")
            circuit_breaker.record_success("theme_extraction")

            # Increment rate limiter counters after successful API call
            rate_limiter = get_rate_limiter()
            await rate_limiter.increment("sentiment_analysis")
            await rate_limiter.increment("theme_extraction")

            # Track cost
            try:
                from crypto_news_aggregator.services.cost_tracker import CostTracker
                from crypto_news_aggregator.db.mongo_manager import mongo_manager

                if usage and (usage.get("input_tokens", 0) > 0 or usage.get("output_tokens", 0) > 0):
                    db = await mongo_manager.get_async_database()
                    tracker = CostTracker(db)
                    import asyncio
                    asyncio.create_task(
                        tracker.track_call(
                            operation="article_enrichment_batch",
                            model=self.model_name,
                            input_tokens=usage.get("input_tokens", 0),
                            output_tokens=usage.get("output_tokens", 0),
                        )
                    )
                    logger.info(
                        f"Batch enriched {len(batch_articles)} articles: "
                        f"{usage.get('input_tokens', 0)}+{usage.get('output_tokens', 0)} tokens"
                    )
            except Exception as e:
                logger.warning(f"Failed to track batch enrichment cost: {e}")

            # Parse response
            try:
                import re
                json_match = re.search(r"\[.*\]", response_text, re.DOTALL)
                if json_match:
                    results = json.loads(json_match.group(0))
                else:
                    results = json.loads(response_text)

                # Validate and return
                enriched = []
                for result in results:
                    enriched.append({
                        "id": result.get("article_id", ""),
                        "relevance_score": float(result.get("relevance_score", 0.0)),
                        "sentiment_score": float(result.get("sentiment_score", 0.0)),
                        "themes": result.get("themes", []) if isinstance(result.get("themes", []), list) else [],
                    })
                return enriched
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                logger.error(f"Failed to parse batch enrichment response: {e}")
                return []
        except Exception as e:
            # Record failure on exception
            circuit_breaker.record_failure("sentiment_analysis")
            circuit_breaker.record_failure("theme_extraction")
            logger.error(f"API error in enrich_articles_batch: {e}")
            return []

    async def score_relevance_tracked(self, text: str, operation: str = "relevance_scoring") -> float:
        """
        Score relevance with cost tracking (async version for RSS enrichment).

        Args:
            text: Text to score
            operation: Operation name for tracking (default: "relevance_scoring")

        Returns:
            Relevance score 0.0-1.0
        """
        # Circuit breaker check
        circuit_breaker = get_circuit_breaker()
        allowed, message = await circuit_breaker.check_circuit(operation)
        if not allowed:
            logger.warning(f"Circuit breaker OPEN for {operation}: {message}")
            return 0.0

        # Rate limit check
        rate_limiter = get_rate_limiter()
        allowed, message = await rate_limiter.check_limit(operation)
        if not allowed:
            logger.warning(f"Rate limit hit for {operation}: {message}")
            return 0.0

        prompt = f"On a scale from 0.0 to 1.0, how relevant is this text to cryptocurrency market movements? Return ONLY a single floating-point number with no explanation:\n\n{text}"

        try:
            response_text, usage = self._get_completion_with_usage(prompt)

            # Record success immediately (before any processing)
            circuit_breaker.record_success(operation)

            # Increment rate limiter counter after successful API call
            await rate_limiter.increment(operation)

            # Track cost asynchronously if tracking is available
            try:
                from crypto_news_aggregator.services.cost_tracker import CostTracker
                from crypto_news_aggregator.db.mongo_manager import mongo_manager

                if usage and (usage.get("input_tokens", 0) > 0 or usage.get("output_tokens", 0) > 0):
                    db = await mongo_manager.get_async_database()
                    tracker = CostTracker(db)
                    import asyncio
                    asyncio.create_task(
                        tracker.track_call(
                            operation=operation,
                            model=self.model_name,
                            input_tokens=usage.get("input_tokens", 0),
                            output_tokens=usage.get("output_tokens", 0),
                        )
                    )
            except Exception as e:
                logger.warning(f"Failed to track cost for {operation}: {e}")

            # Parse response
            try:
                import re
                numbers = re.findall(r"[-+]?\d*\.\d+|\d+", response_text.strip())
                if numbers:
                    return float(numbers[0])
                return float(response_text.strip())
            except (ValueError, TypeError):
                return 0.0
        except Exception as e:
            # Record failure on exception
            circuit_breaker.record_failure(operation)
            logger.error(f"API error in score_relevance_tracked for {operation}: {e}")
            return 0.0

    async def analyze_sentiment_tracked(self, text: str, operation: str = "sentiment_analysis") -> float:
        """
        Analyze sentiment with cost tracking (async version for RSS enrichment).

        Args:
            text: Text to analyze
            operation: Operation name for tracking (default: "sentiment_analysis")

        Returns:
            Sentiment score -1.0 to 1.0
        """
        # Circuit breaker check
        circuit_breaker = get_circuit_breaker()
        allowed, message = await circuit_breaker.check_circuit(operation)
        if not allowed:
            logger.warning(f"Circuit breaker OPEN for {operation}: {message}")
            return 0.0

        # Rate limit check
        rate_limiter = get_rate_limiter()
        allowed, message = await rate_limiter.check_limit(operation)
        if not allowed:
            logger.warning(f"Rate limit hit for {operation}: {message}")
            return 0.0

        prompt = f"Analyze the sentiment of this crypto text. Return ONLY a single number from -1.0 (very bearish) to 1.0 (very bullish). Do not include any explanation or additional text. Just the number:\n\n{text}"

        try:
            response_text, usage = self._get_completion_with_usage(prompt)

            # Record success immediately (before any processing)
            circuit_breaker.record_success(operation)

            # Increment rate limiter counter after successful API call
            await rate_limiter.increment(operation)

            # Track cost asynchronously if tracking is available
            try:
                from crypto_news_aggregator.services.cost_tracker import CostTracker
                from crypto_news_aggregator.db.mongo_manager import mongo_manager

                if usage and (usage.get("input_tokens", 0) > 0 or usage.get("output_tokens", 0) > 0):
                    db = await mongo_manager.get_async_database()
                    tracker = CostTracker(db)
                    import asyncio
                    asyncio.create_task(
                        tracker.track_call(
                            operation=operation,
                            model=self.model_name,
                            input_tokens=usage.get("input_tokens", 0),
                            output_tokens=usage.get("output_tokens", 0),
                        )
                    )
            except Exception as e:
                logger.warning(f"Failed to track cost for {operation}: {e}")

            # Parse response
            try:
                import re
                numbers = re.findall(r"[-+]?\d*\.\d+|\d+", response_text.strip())
                if numbers:
                    return float(numbers[0])
                return float(response_text.strip())
            except (ValueError, TypeError):
                return 0.0
        except Exception as e:
            # Record failure on exception
            circuit_breaker.record_failure(operation)
            logger.error(f"API error in analyze_sentiment_tracked for {operation}: {e}")
            return 0.0

    async def extract_themes_tracked(self, texts: List[str], operation: str = "theme_extraction") -> List[str]:
        """
        Extract themes with cost tracking (async version for RSS enrichment).

        Args:
            texts: List of texts to extract themes from
            operation: Operation name for tracking (default: "theme_extraction")

        Returns:
            List of extracted themes
        """
        # Circuit breaker check
        circuit_breaker = get_circuit_breaker()
        allowed, message = await circuit_breaker.check_circuit(operation)
        if not allowed:
            logger.warning(f"Circuit breaker OPEN for {operation}: {message}")
            return []

        # Rate limit check
        rate_limiter = get_rate_limiter()
        allowed, message = await rate_limiter.check_limit(operation)
        if not allowed:
            logger.warning(f"Rate limit hit for {operation}: {message}")
            return []

        combined_texts = "\n".join(texts)
        prompt = f"Extract the key crypto themes from the following texts. Respond with ONLY a comma-separated list of keywords (e.g., 'Bitcoin, DeFi, Regulation'). Do not include any preamble.\n\nTexts:\n{combined_texts}"

        try:
            response_text, usage = self._get_completion_with_usage(prompt)

            # Record success immediately (before any processing)
            circuit_breaker.record_success(operation)

            # Increment rate limiter counter after successful API call
            await rate_limiter.increment(operation)

            # Track cost asynchronously if tracking is available
            try:
                from crypto_news_aggregator.services.cost_tracker import CostTracker
                from crypto_news_aggregator.db.mongo_manager import mongo_manager

                if usage and (usage.get("input_tokens", 0) > 0 or usage.get("output_tokens", 0) > 0):
                    db = await mongo_manager.get_async_database()
                    tracker = CostTracker(db)
                    import asyncio
                    asyncio.create_task(
                        tracker.track_call(
                            operation=operation,
                            model=self.model_name,
                            input_tokens=usage.get("input_tokens", 0),
                            output_tokens=usage.get("output_tokens", 0),
                        )
                    )
            except Exception as e:
                logger.warning(f"Failed to track cost for {operation}: {e}")

            # Parse response
            if response_text:
                return [theme.strip() for theme in response_text.split(",")]
            return []
        except Exception as e:
            # Record failure on exception
            circuit_breaker.record_failure(operation)
            logger.error(f"API error in extract_themes_tracked for {operation}: {e}")
            return []
