"""
Optimized Anthropic LLM Client with Cost Reduction Features:
1. Response caching to avoid duplicate API calls
2. Uses Haiku for simple tasks (entity extraction) - 12x cheaper
3. Model routing handled by LLMGateway via _OPERATION_MODEL_ROUTING
4. Cost tracking handled by LLMGateway (no manual tracking needed)
"""

import asyncio
import json
import logging
import re
from typing import List, Dict, Any, Optional
import httpx
from .cache import LLMResponseCache
from .gateway import get_gateway
from ..services.cost_tracker import check_llm_budget

logger = logging.getLogger(__name__)


class OptimizedAnthropicLLM:
    """
    Optimized LLM client that minimizes API costs through:
    - Response caching
    - Gateway-managed model routing and cost tracking
    """

    # Model constant
    HAIKU_MODEL = "claude-haiku-4-5-20251001"  # 4-5x faster, better quality
    API_URL = "https://api.anthropic.com/v1/messages"
    
    def __init__(self, db, api_key: Optional[str] = None):
        """Initialize the optimized LLM client"""
        if not api_key:
            raise ValueError("Anthropic API key not provided.")
        self.api_key = api_key
        self.db = db
        self.cache = LLMResponseCache(db, ttl_hours=168)  # 1 week cache

    async def initialize(self):
        """Initialize database indexes for cache"""
        await self.cache.initialize_indexes()
    
    def _make_api_call(self, prompt: str, model: str, max_tokens: int = 1000, temperature: float = 0.3, operation: str = "") -> Dict[str, Any]:
        """
        Make synchronous API call to Anthropic via the gateway

        Returns:
            Dict with 'content' (text response), 'input_tokens', and 'output_tokens'
        """
        # --- SPEND CAP CHECK (defense in depth, gateway also checks) ---
        allowed, reason = check_llm_budget(operation)
        if not allowed:
            logger.warning(f"LLM call blocked by spend cap ({reason}) for '{operation}'")
            raise RuntimeError(f"Daily spend limit reached ({reason})")
        # --- END SPEND CAP CHECK ---

        gateway = get_gateway()

        try:
            response = gateway.call_sync(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                operation=operation,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            return {
                "content": response.text,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
            }
        except Exception as e:
            logger.error(f"LLM gateway call failed: {e}")
            raise
    
    async def extract_entities_batch(
        self,
        articles: List[Dict],
        use_cache: bool = True
    ) -> List[Dict]:
        """
        Extract entities from articles using Haiku (cheap & fast)
        
        Args:
            articles: List of article dictionaries
            use_cache: Whether to use cached responses
        
        Returns:
            List of entity extraction results
        """
        results = []
        
        for article in articles:
            # Build prompt
            prompt = self._build_entity_extraction_prompt(article)
            
            # Check cache first
            if use_cache:
                cached_response = await self.cache.get(prompt, self.HAIKU_MODEL)
                if cached_response:
                    results.append(cached_response)
                    continue

            # Make API call with Haiku
            api_response = self._make_api_call(
                prompt=prompt,
                model=self.HAIKU_MODEL,
                max_tokens=1000,
                temperature=0.3,
                operation="entity_extraction"
            )

            # Parse response
            result = self._parse_text_response(api_response["content"])

            # Cache the result
            if use_cache:
                await self.cache.set(prompt, self.HAIKU_MODEL, result)

            results.append(result)
        
        return results
    
    def _build_entity_extraction_prompt(self, article: Dict) -> str:
        """
        Build optimized prompt for entity extraction
        Uses truncated text to save tokens
        """
        # Truncate text to ~500 tokens (2000 chars)
        text = article.get('text', '')[:2000]

        return f"""Extract cryptocurrency-related entities relevant to the article's primary narrative.

Title: {article['title']}
Text: {text}

Return a JSON object with this structure:
{{
  "entities": [
    {{
      "name": "Bitcoin",
      "type": "cryptocurrency",
      "confidence": 0.95,
      "is_primary": true
    }}
  ]
}}

Entity types: cryptocurrency, protocol, company, person, event, regulation

CRITICAL: Extract only entities relevant to the article's core narrative. Ignore:
- Entities mentioned in passing or as background context
- Tangential references (e.g., "Bitcoin fell, and also interest rates rose")
- Infrastructure/supporting entities not central to the story

EXAMPLE:
Article: "Solv Protocol integrated with Utexo to launch bitcoin-native yield with atomic swaps... uses RGB protocol and Lightning Network..."

WRONG (mention-level): [Bitcoin, Solv Protocol, Utexo, USDT, RGB protocol, Lightning Network]
CORRECT (relevance-weighted): [Bitcoin, Solv Protocol, Utexo]
   (RGB protocol and Lightning Network are supporting infrastructure, not primary entities in the narrative about the Solv/Utexo partnership)

Only include entities explicitly mentioned in the text. Normalize crypto names (BTC → Bitcoin).
Include is_primary: true only for entities central to the story."""
    
    def _parse_text_response(self, content: str) -> Dict[str, Any]:
        """Parse text response from Claude into JSON"""
        
        try:
            # Try to parse as JSON
            return json.loads(content)
        except json.JSONDecodeError:
            # Fallback: extract JSON from markdown code blocks
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
                return json.loads(json_str)
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
                return json.loads(json_str)
            else:
                # Return empty result if parsing fails
                return {"entities": []}
    
    async def extract_narrative_elements(
        self,
        article: Dict,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Extract narrative elements (actors, tensions, nucleus entity) using Haiku
        
        Args:
            article: Article dictionary
            use_cache: Whether to use cached responses
        
        Returns:
            Dict with actors, tensions, nucleus_entity, actions
        """
        # Build prompt
        prompt = self._build_narrative_extraction_prompt(article)
        
        # Check cache
        if use_cache:
            cached_response = await self.cache.get(prompt, self.HAIKU_MODEL)
            if cached_response:
                return cached_response

        # Make API call with Haiku
        api_response = self._make_api_call(
            prompt=prompt,
            model=self.HAIKU_MODEL,
            max_tokens=800,
            temperature=0.3,
            operation="narrative_extraction"
        )

        # Parse response
        result = self._parse_text_response(api_response["content"])

        # Cache the result
        if use_cache:
            await self.cache.set(prompt, self.HAIKU_MODEL, result)

        return result
    
    def _build_narrative_extraction_prompt(self, article: Dict) -> str:
        """Build prompt for narrative element extraction"""
        # Truncate text
        text = article.get('text', '')[:2000]
        
        return f"""Analyze this crypto news article and extract narrative elements.

Title: {article['title']}
Text: {text}

Return JSON:
{{
  "nucleus_entity": "Bitcoin",
  "actors": ["Bitcoin", "SEC", "Michael Saylor"],
  "actor_salience": {{"Bitcoin": 5, "SEC": 4, "Michael Saylor": 3}},
  "tensions": ["regulatory uncertainty", "market volatility"],
  "actions": ["filed lawsuit", "price surge"]
}}

Nucleus entity: The primary subject (most important entity)
Actors: Key entities in the story
Actor salience: Importance score 1-5 (5 = most important)
Tensions: Conflicts, themes, or concerns
Actions: Key events or verbs"""
    
    async def generate_narrative_summary(
        self,
        articles: List[Dict],
        use_cache: bool = True
    ) -> str:
        """
        Generate narrative summary using Haiku with strict grounding constraints

        Args:
            articles: List of related articles
            use_cache: Whether to use cached responses

        Returns:
            Summary text
        """
        # Build prompt
        prompt = self._build_summary_prompt(articles)
        
        # Check cache
        if use_cache:
            cached_response = await self.cache.get(prompt, self.HAIKU_MODEL)
            if cached_response:
                return cached_response.get("summary", "")

        # Make API call with Haiku (grounding constraints via prompt)
        api_response = self._make_api_call(
            prompt=prompt,
            model=self.HAIKU_MODEL,
            max_tokens=500,
            temperature=0.5,
            operation="narrative_summary"
        )

        summary = api_response["content"].strip()

        # Flag implausible financial figures for investigation (defense-in-depth)
        for match in re.finditer(r'\$(\d[\d,.]*)\s*(billion|B|trillion|T)\b', summary, re.IGNORECASE):
            try:
                value = float(match.group(1).replace(',', ''))
                unit = match.group(2).lower()
                if unit in ('trillion', 't'):
                    value *= 1000  # normalize to billions
                if value > 50:
                    logger.warning(
                        f"SUSPICIOUS FIGURE in narrative summary: {match.group(0)} "
                        f"(exceeds $50B single-event threshold). "
                        f"Verify source articles. Summary: {summary[:200]}"
                    )
            except ValueError:
                pass

        result = {"summary": summary}

        # Cache the result
        if use_cache:
            await self.cache.set(prompt, self.HAIKU_MODEL, result)

        return summary
    
    def _build_summary_prompt(self, articles: List[Dict]) -> str:
        """Build prompt for narrative summary generation"""
        # Combine article titles and summaries
        articles_text = "\n\n".join([
            f"Article {i+1}:\nTitle: {article['title']}\nText: {article.get('text', '')[:800]}"
            for i, article in enumerate(articles[:10])  # Limit to 10 articles
        ])
        
        return f"""Summarize these related crypto news articles.

{articles_text}

Write a 2-3 sentence summary that:
1. Identifies the main story or theme based ONLY on events explicitly described in the articles above
2. Explains why it matters
3. Notes any conflicting perspectives
4. Verifies financial figures are consistent across articles — if sources disagree on a number, note the discrepancy rather than picking one

CRITICAL: Your summary must describe only events, facts, and claims that are explicitly stated in the provided articles. Do not infer, speculate, or add events not present in the source text. If the articles describe an IPO filing, summarize the IPO filing — do not introduce security breaches, hacks, lawsuits, or other events unless they are explicitly described in the articles.

Be concise and informative."""
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        return await self.cache.get_stats()

    async def clear_old_cache(self) -> int:
        """Clear expired cache entries"""
        return await self.cache.clear_expired()


# Helper function for backward compatibility
async def create_optimized_llm(db, api_key: Optional[str] = None) -> OptimizedAnthropicLLM:
    """
    Factory function to create and initialize OptimizedAnthropicLLM
    
    Args:
        db: MongoDB database instance
        api_key: Optional Anthropic API key
    
    Returns:
        Initialized OptimizedAnthropicLLM instance
    """
    llm = OptimizedAnthropicLLM(db, api_key)
    await llm.initialize()
    return llm
