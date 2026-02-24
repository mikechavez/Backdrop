import os
import json
import logging
from typing import List, Dict, Any
import httpx
from .base import LLMProvider
from .tracking import track_usage
from ..services.entity_normalization import normalize_entity_name

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
        return {"results": [], "usage": {}}
