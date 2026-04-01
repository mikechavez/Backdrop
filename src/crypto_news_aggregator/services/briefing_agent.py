"""
Briefing Agent Service for generating daily crypto briefings.

This is the main orchestration service that:
- Loads memory context (feedback, history, patterns)
- Gathers current signals and narratives
- Detects patterns in market data
- Uses LLM to generate narrative briefings
- Implements the self-refine pattern for quality

Architecture: Memory-Augmented ReAct + Self-Refine (single agent)
"""

import asyncio
import json
import logging
import httpx
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from crypto_news_aggregator.core.config import get_settings
from crypto_news_aggregator.llm.exceptions import LLMError
from crypto_news_aggregator.db.mongodb import mongo_manager
from crypto_news_aggregator.db.operations.briefing import (
    insert_briefing,
    insert_pattern,
    check_briefing_exists_for_slot,
    get_latest_briefing,
)
from crypto_news_aggregator.services.memory_manager import (
    get_memory_manager,
    MemoryContext,
)
from crypto_news_aggregator.services.pattern_detector import (
    get_pattern_detector,
    PatternSummary,
)
from crypto_news_aggregator.services.market_event_detector import (
    get_market_event_detector,
)

logger = logging.getLogger(__name__)

# LLM Configuration
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-5-20250929"  # Sonnet 4.5 - best instruction following
FALLBACK_MODELS = [
    "claude-haiku-4-5-20251001",  # Haiku 4.5 as fallback
]


@dataclass
class BriefingInput:
    """Input data for briefing generation."""

    briefing_type: str  # "morning" or "evening"
    signals: List[Dict[str, Any]]
    narratives: List[Dict[str, Any]]
    patterns: PatternSummary
    memory: MemoryContext
    generated_at: datetime


@dataclass
class GeneratedBriefing:
    """Output from briefing generation."""

    narrative: str
    key_insights: List[str]
    entities_mentioned: List[str]
    detected_patterns: List[str]
    recommendations: List[Dict[str, str]]
    confidence_score: float


class BriefingAgent:
    """
    AI-powered briefing agent that generates daily crypto briefings.

    Uses a single-agent architecture with:
    - Memory augmentation from feedback and history
    - Pattern detection for market insights
    - Self-refine loop for quality assurance
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the briefing agent.

        Args:
            api_key: Anthropic API key (defaults to settings)
        """
        settings = get_settings()
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not configured")

        self.memory_manager = get_memory_manager()
        self.pattern_detector = get_pattern_detector()
        self.cost_tracker = None  # Lazy initialization

    async def _get_cost_tracker(self):
        """Get or initialize cost tracker."""
        if self.cost_tracker is None:
            from crypto_news_aggregator.services.cost_tracker import CostTracker
            db = await mongo_manager.get_async_database()
            self.cost_tracker = CostTracker(db)
        return self.cost_tracker

    async def generate_briefing(
        self,
        briefing_type: str = "morning",
        force: bool = False,
        is_smoke: bool = False,
        task_id: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a new briefing.

        Args:
            briefing_type: "morning" or "evening"
            force: If True, generate even if one already exists for this slot
            is_smoke: If True, mark as smoke test (don't publish to production)
            task_id: Celery task ID for correlation (passed from bound task)

        Returns:
            Generated briefing document or None if skipped/failed
        """
        now = datetime.now(timezone.utc)

        # Check if briefing already exists for this slot
        if not force:
            exists = await check_briefing_exists_for_slot(briefing_type, now)
            if exists:
                logger.info(f"{briefing_type.title()} briefing already exists for today")
                return None

        logger.info(f"Starting {briefing_type} briefing generation")

        try:
            # Step 1: Gather inputs
            briefing_input = await self._gather_inputs(briefing_type, now)

            # Step 2: Generate initial briefing
            generated = await self._generate_with_llm(briefing_input)

            # Step 3: Self-refine (quality check with multi-pass refinement)
            refined = await self._self_refine(generated, briefing_input, max_iterations=2)

            # Step 4: Save briefing to database
            briefing_doc = await self._save_briefing(
                briefing_type, briefing_input, refined, is_smoke=is_smoke, task_id=task_id
            )

            # Step 5: Save detected patterns
            await self._save_patterns(briefing_doc["_id"], briefing_input.patterns)

            logger.info(f"Successfully generated {briefing_type} briefing")
            return briefing_doc

        except LLMError:
            raise
        except Exception as e:
            logger.exception(f"Failed to generate {briefing_type} briefing: {e}")
            return None

    async def _gather_inputs(
        self, briefing_type: str, now: datetime
    ) -> BriefingInput:
        """Gather all inputs needed for briefing generation."""
        # Load memory context
        memory = await self.memory_manager.load_memory(history_days=7)
        logger.info(
            f"Loaded memory: {len(memory.history)} history items, "
            f"{len(memory.patterns)} patterns, {len(memory.manual_inputs)} manual inputs"
        )

        # Get current signals
        signals = await self._get_trending_signals()
        logger.info(f"Retrieved {len(signals)} trending signals")

        # Get current narratives
        narratives = await self._get_active_narratives()
        logger.info(f"Retrieved {len(narratives)} active narratives")

        # Detect and include market shock events
        detector = get_market_event_detector()
        market_events = await detector.detect_market_events()

        if market_events:
            logger.info(f"Detected {len(market_events)} market shock events")

            # Create/update narratives for each market event
            for event in market_events:
                await detector.create_or_update_market_event_narrative(event)

            # Refresh narratives to include newly created market event narratives
            narratives = await self._get_active_narratives()

            # Boost market events in the narrative ranking
            narratives = await detector.boost_market_event_in_briefing(narratives)
            logger.info(f"Market events prioritized in narrative ranking")

        # Detect patterns
        patterns = await self.pattern_detector.detect_all_patterns(
            current_signals=signals,
            current_narratives=narratives,
            history=memory.history,
        )
        logger.info(
            f"Detected patterns: {len(patterns.entity_surges)} surges, "
            f"{len(patterns.sentiment_shifts)} sentiment shifts, "
            f"{len(patterns.expected_events)} expected events, "
            f"{len(patterns.narrative_emergences)} emergences"
        )

        return BriefingInput(
            briefing_type=briefing_type,
            signals=signals,
            narratives=narratives,
            patterns=patterns,
            memory=memory,
            generated_at=now,
        )

    async def _get_trending_signals(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get top trending signals from the database."""
        db = await mongo_manager.get_async_database()
        collection = db.trending_signals

        # Get signals from last 24 hours, sorted by score
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        cursor = collection.find(
            {"updated_at": {"$gte": cutoff}},
            sort=[("metrics.score_24h", -1)],
        ).limit(limit)

        signals = await cursor.to_list(length=limit)
        return signals

    async def _get_active_narratives(self, limit: int = 15, max_age_days: int = 7) -> List[Dict[str, Any]]:
        """Get active narratives from the database with fresh recency calculation.

        Args:
            limit: Maximum number of narratives to return
            max_age_days: Only include narratives with articles in the last N days
        """
        from math import exp
        from bson import ObjectId

        db = await mongo_manager.get_async_database()
        narratives_collection = db.narratives
        articles_collection = db.articles

        # Get narratives that are not dormant
        active_states = ["emerging", "rising", "hot", "cooling", "echo", "reactivated"]

        cursor = narratives_collection.find(
            {"lifecycle_state": {"$in": active_states}},
        ).limit(limit * 3)  # Get more to filter after recency check

        narratives = await cursor.to_list(length=limit * 3)

        # Calculate fresh recency for each narrative based on newest article
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=max_age_days)
        fresh_narratives = []

        for narrative in narratives:
            article_ids = narrative.get("article_ids", [])
            if not article_ids:
                continue

            # Get newest article date
            object_ids = [ObjectId(aid) if isinstance(aid, str) else aid for aid in article_ids[:10]]
            article_cursor = articles_collection.find(
                {"_id": {"$in": object_ids}},
                {"published_at": 1}
            )
            articles = await article_cursor.to_list(length=10)

            if not articles:
                continue

            dates = [a.get("published_at") for a in articles if a.get("published_at")]
            if not dates:
                continue

            newest_article = max(dates)

            # Ensure timezone aware
            if newest_article.tzinfo is None:
                newest_article = newest_article.replace(tzinfo=timezone.utc)

            # Skip narratives older than cutoff
            if newest_article < cutoff:
                logger.debug(f"Skipping stale narrative: {narrative.get('title', 'Unknown')[:40]} (newest: {newest_article})")
                continue

            # Calculate fresh recency score (24h half-life)
            hours_since = (now - newest_article).total_seconds() / 3600
            fresh_recency = exp(-hours_since / 24)

            narrative["_fresh_recency"] = fresh_recency
            narrative["_newest_article"] = newest_article
            fresh_narratives.append(narrative)

        # Sort by fresh recency and return top N
        fresh_narratives.sort(key=lambda x: x.get("_fresh_recency", 0), reverse=True)

        logger.info(f"Filtered to {len(fresh_narratives)} fresh narratives (max {max_age_days} days old)")

        return fresh_narratives[:limit]

    async def _generate_with_llm(
        self, briefing_input: BriefingInput
    ) -> GeneratedBriefing:
        """Generate briefing content using LLM."""
        prompt = self._build_generation_prompt(briefing_input)

        response_text = await self._call_llm(
            prompt,
            system_prompt=self._get_system_prompt(briefing_input.briefing_type),
            max_tokens=4096,
        )

        return self._parse_briefing_response(response_text)

    async def _self_refine(
        self,
        generated: GeneratedBriefing,
        briefing_input: BriefingInput,
        max_iterations: int = 2,
    ) -> GeneratedBriefing:
        """
        Self-refine the generated briefing for quality with iterative refinement.

        This implements the multi-pass self-refine pattern:
        1. Evaluate the initial output
        2. Identify issues
        3. Refine if needed
        4. Repeat up to max_iterations times
        5. Return best attempt

        Args:
            generated: Initial briefing output
            briefing_input: Input data used for generation
            max_iterations: Maximum refinement passes (default: 2)

        Returns:
            Refined briefing (may still have issues if max iterations hit)
        """
        current = generated

        for iteration in range(max_iterations):
            # Build critique prompt
            critique_prompt = self._build_critique_prompt(current, briefing_input)

            critique_response = await self._call_llm(
                critique_prompt,
                system_prompt="You are a crypto market analyst reviewing a briefing for quality.",
                max_tokens=1024,
            )

            # Check if refinement is needed
            needs_refinement = self._check_needs_refinement(critique_response)

            if not needs_refinement:
                logger.info(f"Briefing passed quality check on iteration {iteration + 1}")
                # Add iteration metadata
                current.detected_patterns.append(f"Quality passed on iteration {iteration + 1}")
                return current

            logger.info(f"Briefing needs refinement (iteration {iteration + 1}/{max_iterations})")
            logger.debug(f"Critique: {critique_response[:200]}...")

            # Build refinement prompt
            refinement_prompt = self._build_refinement_prompt(
                current, critique_response, briefing_input
            )

            refined_response = await self._call_llm(
                refinement_prompt,
                system_prompt=self._get_system_prompt(briefing_input.briefing_type),
                max_tokens=4096,
            )

            current = self._parse_briefing_response(refined_response)

        # Max iterations reached without passing quality check
        logger.warning(f"Briefing refinement stopped at max iterations ({max_iterations})")

        # Reduce confidence score if we hit max iterations
        if current.confidence_score > 0.6:
            current.confidence_score = 0.6

        # Add metadata about refinement attempts
        current.detected_patterns.append(f"Max refinement iterations ({max_iterations}) reached")

        return current

    def _get_system_prompt(self, briefing_type: str) -> str:
        """Get the enhanced system prompt for briefing generation."""
        time_context = "morning" if briefing_type == "morning" else "evening"

        return f"""You are a senior crypto market analyst writing a {time_context} briefing memo.

Your role is to synthesize ONLY the narratives listed below into an insightful briefing.

═══════════════════════════════════════════════════════════════════════════════
CRITICAL: ZERO TOLERANCE FOR HALLUCINATION
═══════════════════════════════════════════════════════════════════════════════

You will be given a list of narratives below. Your briefing MUST:
✓ ONLY discuss narratives explicitly listed in the data below
✓ ONLY use facts, names, and details that appear in those narratives
✗ NEVER add companies, people, events, or facts from your training knowledge
✗ NEVER mention entities unless they appear in the narratives below
✗ NEVER invent acquisitions, partnerships, or regulatory events

If you mention something not in the provided narratives, the briefing is INVALID.

═══════════════════════════════════════════════════════════════════════════════

WRITING RULES:

1. SPECIFIC ENTITY REFERENCES (NEW - CRITICAL)
   - ALWAYS use full entity names: "Binance", "BlackRock", "Cardano"
   - NEVER use vague references: "the platform", "the exchange", "the network"
   - If an entity is mentioned multiple times, use its name each time
   - Example GOOD: "Binance has expanded its stablecoin offerings..."
   - Example BAD: "The exchange is expanding..." (which exchange?)

2. EXPLAIN "WHY IT MATTERS" (MANDATORY)
   - Every significant development MUST include its implications
   - Use phrases like:
     * "The significance lies in..."
     * "This matters because..."
     * "The immediate impact is..."
     * "This represents..."
   - Connect events to broader market trends or investor decisions
   - Example GOOD: "BlackRock's Bitcoin ETF positioning represents material institutional endorsement that could drive Q1 capital flows despite regulatory uncertainty."
   - Example BAD: "BlackRock designated Bitcoin ETF as key theme." (so what?)

3. ONLY COVER NARRATIVES FROM THE DATA
   - Read the "Active Narratives" section carefully
   - Each narrative you discuss MUST match one of the titles listed
   - Do not add stories that aren't in the list

4. USE EXACT DETAILS FROM SUMMARIES
   - The narrative summaries contain the facts you should use
   - Copy specific details (names, amounts, events) from the summaries
   - If a summary lacks details, say so rather than inventing them

5. NO GENERIC FILLER
   - BANNED: "The crypto markets continue to...", "In a mix of developments..."
   - BANNED: "Looking ahead, the industry will be shaped by..."
   - BANNED: "Navigating challenges", "Amid uncertainty", "In the evolving landscape"
   - Start directly with your most important story
   - End with specific actionable focus areas

6. PROFESSIONAL ANALYST TONE
   - Write as flowing memo, not bullet points
   - Connect related developments with causal reasoning
   - Be direct about uncertainty when data is limited
   - Use informed opinion with clear reasoning

7. STRUCTURE
   - Each paragraph = one narrative or connected set of narratives
   - Open with most significant development
   - End with specific "immediate focus" areas

8. RECOMMENDATIONS (CRITICAL)
   - Include 2-3 recommendations for further reading
   - ONLY recommend narratives from the "ALLOWED NARRATIVES" list above
   - Use the EXACT narrative title as the recommendation title (matching case)
   - For theme, use the topic/category the narrative falls under (e.g., "Regulation", "Trading", "Infrastructure")
   - Example: {{"title": "Binance Expands in South Korea", "theme": "Regulatory Expansion"}}
   - NEVER create recommendation titles that aren't in the allowed list
   - NEVER suggest topics or narratives that weren't provided

GOOD EXAMPLE:
"Binance has expanded its stablecoin offerings with the listing of a Kyrgyzstan som-pegged stablecoin, marking a strategic move into Central Asian markets. The exchange is simultaneously addressing security concerns through its anti-scam initiatives, though the specific technical measures remain undisclosed in available reporting. This parallel focus on market expansion and security infrastructure reflects the operational priorities of centralized exchanges navigating growth and trust simultaneously."

BAD EXAMPLE:
"The exchange continues to navigate the evolving landscape with new offerings. They are also working on security. This shows how platforms are adapting."
(Why bad? Vague "the exchange", generic filler "evolving landscape", no specific names, no "why it matters")

Output Format:
Return valid JSON:
{{
    "narrative": "The briefing text...",
    "key_insights": ["insight1", "insight2", "insight3"],
    "entities_mentioned": ["Entity1", "Entity2"],  // Full names only
    "detected_patterns": ["pattern1", "pattern2"],
    "recommendations": [{{"title": "...", "theme": "..."}}],
    "confidence_score": 0.85
}}"""

    def _build_generation_prompt(self, briefing_input: BriefingInput) -> str:
        """Build the main generation prompt."""
        parts = []

        # Time context
        time_str = briefing_input.generated_at.strftime("%A, %B %d, %Y")
        parts.append(f"Generate the {briefing_input.briefing_type} crypto briefing for {time_str}.\n")

        # Memory context (feedback and guidelines)
        memory_context = briefing_input.memory.to_prompt_context()
        if memory_context:
            parts.append(memory_context)

        # Current signals
        if briefing_input.signals:
            parts.append("\n## Current Trending Signals\n")
            for signal in briefing_input.signals[:10]:
                entity = signal.get("entity", "Unknown")
                score = signal.get("metrics", {}).get("score_24h", 0)
                velocity = signal.get("metrics", {}).get("velocity_24h", 0)
                parts.append(f"- {entity}: score={score:.1f}, velocity={velocity:.0f}%\n")

        # Current narratives - include summaries for detail
        if briefing_input.narratives:
            # Build explicit list of allowed narratives
            narrative_titles = [n.get("title", "Untitled") for n in briefing_input.narratives[:8]]

            parts.append("\n═══════════════════════════════════════════════════════════════════════════════\n")
            parts.append("ALLOWED NARRATIVES - You may ONLY discuss these stories:\n")
            for i, title in enumerate(narrative_titles, 1):
                parts.append(f"  {i}. {title}\n")
            parts.append("\nAny other company, person, or event NOT listed above is FORBIDDEN.\n")
            parts.append("═══════════════════════════════════════════════════════════════════════════════\n\n")

            parts.append("## Narrative Details (use these facts):\n\n")
            for narrative in briefing_input.narratives[:8]:
                title = narrative.get("title", "Untitled")
                summary = narrative.get("summary", "")
                article_count = narrative.get("article_count", 0)

                parts.append(f"### {title}\n")
                parts.append(f"Sources: {article_count} articles\n")
                if summary:
                    parts.append(f"Facts: {summary}\n")
                parts.append("\n")

        # Detected patterns
        patterns_context = briefing_input.patterns.to_prompt_context()
        if patterns_context:
            parts.append("\n")
            parts.append(patterns_context)

        # Manual inputs
        if briefing_input.memory.manual_inputs:
            parts.append("\n## External Inputs to Consider\n")
            for inp in briefing_input.memory.manual_inputs[:3]:
                title = inp.get("title", "Untitled")
                content = inp.get("content", "")[:200]
                parts.append(f"### {title}\n{content}...\n\n")

        parts.append("\n---\n")
        parts.append("Generate the briefing now. REMEMBER:\n")
        parts.append("- ONLY use facts from the narratives and signals above\n")
        parts.append("- Include specific details from the narrative summaries\n")
        parts.append("- If a narrative lacks details, either skip it or acknowledge the limitation\n")
        parts.append("- No generic openings or closings\n")
        parts.append("- RECOMMENDATIONS: Include 2-3 recommendations ONLY from the ALLOWED NARRATIVES list (matching exact titles)\n")
        parts.append("\nReturn ONLY valid JSON.")

        return "".join(parts)

    def _build_critique_prompt(
        self, generated: GeneratedBriefing, briefing_input: BriefingInput
    ) -> str:
        """Build enhanced prompt for self-critique."""
        # Build list of narrative titles for grounding check
        narrative_titles = [n.get("title", "") for n in briefing_input.narratives[:8]]

        # Extract entity names from narratives
        narrative_entities = set()
        for narrative in briefing_input.narratives[:8]:
            entities = narrative.get("entities", [])
            if entities:
                narrative_entities.update(entities[:5])  # Top 5 entities per narrative

        return f"""Review this crypto briefing for quality issues:

BRIEFING NARRATIVE:
{generated.narrative}

KEY INSIGHTS:
{json.dumps(generated.key_insights, indent=2)}

AVAILABLE NARRATIVES (the only valid sources):
{json.dumps(narrative_titles, indent=2)}

AVAILABLE ENTITIES (the only entities that can be mentioned):
{json.dumps(list(narrative_entities), indent=2)}

Check for these issues:

1. HALLUCINATION: Does the briefing mention facts, companies, events, or numbers that are NOT from the provided narratives? This is the most critical issue.

2. VAGUE ENTITY REFERENCES (NEW - CRITICAL): Does the briefing use vague references like "the platform", "the exchange", "the network", "the protocol" instead of specific entity names? Every entity must be named explicitly.

3. MISSING "WHY IT MATTERS": Are events mentioned without explaining their significance or implications? Each development needs clear reasoning for its importance.

4. VAGUE CLAIMS: Are there statements like "X is navigating challenges" without specific details? Each claim needs specifics.

5. MISSING CONTEXT: Are numbers mentioned without baselines or comparisons?

6. GENERIC FILLER: Does it start with "The crypto markets continue to..." or end with generic forward-looking statements? Check for banned phrases like "amid uncertainty", "navigating challenges", "evolving landscape".

7. ABRUPT TRANSITIONS: Does it switch topics mid-paragraph without logical connection?

Respond with:
{{
    "needs_refinement": true/false,
    "issues": ["issue1", "issue2"],
    "suggestions": ["suggestion1", "suggestion2"]
}}"""

    def _check_needs_refinement(self, critique_response: str) -> bool:
        """Check if the critique indicates refinement is needed."""
        try:
            # Try to parse JSON response
            import re
            json_match = re.search(r"\{.*\}", critique_response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                return data.get("needs_refinement", False)
        except (json.JSONDecodeError, AttributeError):
            pass

        # Fallback: check for keywords
        lower_response = critique_response.lower()
        refinement_keywords = ["needs refinement", "should be improved", "issues found", "missing"]
        return any(kw in lower_response for kw in refinement_keywords)

    def _build_refinement_prompt(
        self,
        generated: GeneratedBriefing,
        critique: str,
        briefing_input: BriefingInput,
    ) -> str:
        """Build prompt for refinement pass."""
        return f"""Refine this crypto briefing based on the critique feedback:

ORIGINAL BRIEFING:
{generated.narrative}

CRITIQUE FEEDBACK:
{critique}

AVAILABLE DATA:
- Signals: {len(briefing_input.signals)} trending entities
- Narratives: {len(briefing_input.narratives)} active narratives
- Patterns: {len(briefing_input.patterns.all_patterns())} detected patterns

Address the issues identified in the critique and generate an improved briefing.
Return ONLY valid JSON in the same format as before."""

    def _match_recommendations_to_narratives(
        self,
        recommendations: List[Dict[str, str]],
        narratives: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Match recommendation titles to narrative IDs.

        Args:
            recommendations: List of recommendations from LLM with {title, theme}
            narratives: List of available narratives with {_id, title, ...}

        Returns:
            List of recommendations with narrative_id added where possible
        """
        # Build a map of narrative titles to their IDs (case-insensitive)
        title_to_id = {}
        for narrative in narratives:
            narrative_title = narrative.get("title", "").strip().lower()
            if narrative_title:
                narrative_id = str(narrative.get("_id", ""))
                if narrative_id and narrative_id != "":
                    title_to_id[narrative_title] = narrative_id

        # Match each recommendation to a narrative by title
        matched_recommendations = []
        for rec in recommendations:
            rec_title = rec.get("title", "").strip().lower()
            matched_rec = dict(rec)  # Copy recommendation

            # Try to find matching narrative ID
            if rec_title and rec_title in title_to_id:
                matched_rec["narrative_id"] = title_to_id[rec_title]
                logger.debug(f"Matched recommendation '{rec.get('title')}' to narrative {title_to_id[rec_title]}")
            else:
                # Log when we can't match (for debugging)
                if rec_title:
                    logger.debug(f"Could not match recommendation '{rec.get('title')}' to any narrative")

            matched_recommendations.append(matched_rec)

        return matched_recommendations

    def _parse_briefing_response(self, response_text: str) -> GeneratedBriefing:
        """Parse LLM response into GeneratedBriefing."""
        try:
            # Try to extract JSON from response
            import re
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = response_text

            # Clean up the JSON string - replace literal newlines in string values
            # This handles cases where the LLM outputs multi-line strings
            # Replace actual newlines with escaped newlines for valid JSON
            cleaned_json = ""
            in_string = False
            escape_next = False
            for char in json_str:
                if escape_next:
                    cleaned_json += char
                    escape_next = False
                elif char == '\\':
                    cleaned_json += char
                    escape_next = True
                elif char == '"':
                    cleaned_json += char
                    in_string = not in_string
                elif in_string and char == '\n':
                    cleaned_json += '\\n'
                elif in_string and char == '\r':
                    cleaned_json += '\\r'
                elif in_string and char == '\t':
                    cleaned_json += '\\t'
                else:
                    cleaned_json += char

            data = json.loads(cleaned_json)

            return GeneratedBriefing(
                narrative=data.get("narrative", ""),
                key_insights=data.get("key_insights", []),
                entities_mentioned=data.get("entities_mentioned", []),
                detected_patterns=data.get("detected_patterns", []),
                recommendations=data.get("recommendations", []),
                confidence_score=data.get("confidence_score", 0.7),
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.debug(f"Raw response: {response_text[:500]}")

            # Return minimal briefing
            return GeneratedBriefing(
                narrative=response_text[:2000] if response_text else "Failed to generate briefing.",
                key_insights=[],
                entities_mentioned=[],
                detected_patterns=[],
                recommendations=[],
                confidence_score=0.3,
            )

    async def _call_llm(
        self,
        prompt: str,
        system_prompt: str,
        max_tokens: int = 2048,
    ) -> str:
        """Call the LLM API with fallback models."""
        models_to_try = [DEFAULT_MODEL] + FALLBACK_MODELS

        for model in models_to_try:
            try:
                logger.info(f"Trying LLM model: {model}")
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        ANTHROPIC_API_URL,
                        headers={
                            "x-api-key": self.api_key,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json",
                        },
                        json={
                            "model": model,
                            "max_tokens": max_tokens,
                            "system": system_prompt,
                            "messages": [{"role": "user", "content": prompt}],
                        },
                        timeout=120,
                    )
                    logger.info(f"LLM response status: {response.status_code}")
                    if response.status_code != 200:
                        try:
                            error_data = response.json()
                            logger.error(f"API error response: {error_data}")
                        except Exception:
                            logger.error(f"API error body: {response.text[:500]}")
                    response.raise_for_status()
                    data = response.json()

                    if model != DEFAULT_MODEL:
                        logger.info(f"Using fallback model: {model}")

                    # Extract response text
                    text = data.get("content", [{}])[0].get("text", "")

                    # Track cost (async, non-blocking)
                    try:
                        usage = data.get("usage", {})
                        input_tokens = usage.get("input_tokens", 0)
                        output_tokens = usage.get("output_tokens", 0)

                        if input_tokens > 0 or output_tokens > 0:
                            tracker = await self._get_cost_tracker()
                            asyncio.create_task(
                                tracker.track_call(
                                    operation="briefing_generation",
                                    model=model,
                                    input_tokens=input_tokens,
                                    output_tokens=output_tokens,
                                    cached=False
                                )
                            )
                    except Exception as e:
                        logger.error(f"Cost tracking failed: {e}")

                    return text

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 403:
                    logger.warning(f"403 Forbidden for model {model}, trying fallback...")
                    continue
                logger.error(f"LLM API error: {e.response.status_code}", exc_info=True)
                raise
            except Exception as e:
                logger.error(f"LLM call failed: {e}", exc_info=True)
                raise

        raise RuntimeError("All LLM models failed")

    async def _save_briefing(
        self,
        briefing_type: str,
        briefing_input: BriefingInput,
        generated: GeneratedBriefing,
        is_smoke: bool = False,
        task_id: str | None = None,
    ) -> Dict[str, Any]:
        """Save the generated briefing to the database."""
        from bson import ObjectId
        import re

        # Extract iteration count from detected_patterns if present
        iteration_count = 1
        for pattern in generated.detected_patterns:
            if "iteration" in pattern.lower():
                # Extract number from patterns like "Quality passed on iteration 2"
                match = re.search(r'iteration (\d+)', pattern.lower())
                if match:
                    iteration_count = int(match.group(1))
                    break

        # Match recommendations to narrative IDs
        matched_recommendations = self._match_recommendations_to_narratives(
            generated.recommendations,
            briefing_input.narratives,
        )

        briefing_doc = {
            "type": briefing_type,
            "title": f"🔬 SMOKE TEST - {briefing_type.title()} Briefing" if is_smoke else None,
            "generated_at": briefing_input.generated_at,
            "version": "2.0",  # Agent-generated briefings
            "content": {
                "narrative": generated.narrative,
                "key_insights": generated.key_insights,
                "entities_mentioned": generated.entities_mentioned,
                "detected_patterns": generated.detected_patterns,
                "recommendations": matched_recommendations,
            },
            "metadata": {
                "confidence_score": generated.confidence_score,
                "signal_count": len(briefing_input.signals),
                "narrative_count": len(briefing_input.narratives),
                "pattern_count": len(briefing_input.patterns.all_patterns()),
                "manual_input_count": len(briefing_input.memory.manual_inputs),
                "model": DEFAULT_MODEL,
                "refinement_iterations": iteration_count,  # NEW: Track iterations
            },
            "is_smoke": is_smoke,
            "published": not is_smoke,  # Don't publish smoke tests
            "task_id": task_id,  # For correlation: Beat → Worker → DB (None if called outside Celery)
        }

        briefing_id = await insert_briefing(briefing_doc)
        briefing_doc["_id"] = ObjectId(briefing_id)

        logger.info(f"Saved briefing {briefing_id} (iterations: {iteration_count})")
        return briefing_doc

    async def _save_patterns(
        self, briefing_id: str, patterns: PatternSummary
    ) -> None:
        """Save detected patterns to the database."""
        for pattern in patterns.all_patterns():
            pattern_doc = {
                "briefing_id": briefing_id,
                "pattern_type": pattern.pattern_type,
                "description": pattern.description,
                "entities": pattern.entities,
                "confidence": pattern.confidence,
                "details": pattern.details,
            }
            await insert_pattern(pattern_doc)

        logger.info(f"Saved {len(patterns.all_patterns())} patterns for briefing {briefing_id}")


# Singleton instance
_briefing_agent: Optional[BriefingAgent] = None


def get_briefing_agent() -> BriefingAgent:
    """Get or create the singleton BriefingAgent instance."""
    global _briefing_agent
    if _briefing_agent is None:
        _briefing_agent = BriefingAgent()
    return _briefing_agent


async def generate_morning_briefing(force: bool = False, is_smoke: bool = False, task_id: str | None = None) -> Optional[Dict[str, Any]]:
    """Convenience function to generate morning briefing."""
    agent = get_briefing_agent()
    return await agent.generate_briefing("morning", force=force, is_smoke=is_smoke, task_id=task_id)


async def generate_afternoon_briefing(force: bool = False, is_smoke: bool = False, task_id: str | None = None) -> Optional[Dict[str, Any]]:
    """Convenience function to generate afternoon briefing (manual trigger only)."""
    agent = get_briefing_agent()
    return await agent.generate_briefing("afternoon", force=force, is_smoke=is_smoke, task_id=task_id)


async def generate_evening_briefing(force: bool = False, is_smoke: bool = False, task_id: str | None = None) -> Optional[Dict[str, Any]]:
    """Convenience function to generate evening briefing."""
    agent = get_briefing_agent()
    return await agent.generate_briefing("evening", force=force, is_smoke=is_smoke, task_id=task_id)
