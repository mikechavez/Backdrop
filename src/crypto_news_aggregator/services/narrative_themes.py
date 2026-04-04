"""
Theme extraction service for narrative detection.

This service uses Claude Sonnet to extract thematic categories from articles,
enabling theme-based narrative clustering instead of entity co-occurrence.
"""

import asyncio
import hashlib
import json
import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from itertools import combinations
from collections import defaultdict, Counter

from ..db.mongodb import mongo_manager
from ..llm.factory import get_llm_provider

logger = logging.getLogger(__name__)

# Maximum relevance tier to include in narrative detection/backfill
# Tier 1 = high signal, Tier 2 = medium, Tier 3 = low (excluded)
MAX_RELEVANCE_TIER = 2


def validate_entity_in_text(nucleus_entity: str, article_title: str, article_text: str) -> bool:
    """
    Validate that the extracted nucleus entity actually appears in the article text.

    This prevents LLM hallucinations where the model extracts entities not present
    in the source material (e.g., "Netflix" extracted from "Coinbase earnings" article).

    Args:
        nucleus_entity: Entity extracted by LLM (e.g., "Netflix", "Coinbase")
        article_title: Article headline
        article_text: Full article text

    Returns:
        True if entity found in title or text, False otherwise

    Example:
        >>> validate_entity_in_text("Netflix", "Netflix Stock Surges", "Netflix reported...")
        True
        >>> validate_entity_in_text("Netflix", "Coinbase Earnings", "Coinbase reported...")
        False
    """
    if not nucleus_entity:
        return False

    # Normalize for case-insensitive matching
    entity_lower = nucleus_entity.lower()
    title_lower = (article_title or "").lower()
    text_lower = (article_text or "").lower()

    # Check if entity appears in title or text
    # For simple entities (alphanumeric + spaces), use word boundaries to avoid false positives
    # For entities with special characters, match the exact string as-is

    # Determine if entity has special characters (anything that's not alphanumeric, space, or hyphen)
    has_special_chars = bool(re.search(r'[^\w\s\-]', entity_lower))

    if has_special_chars:
        # For entities like "OpenAI (ChatGPT)" or "U.S. Securities", match the exact string
        found_in_title = entity_lower in title_lower
        found_in_text = entity_lower in text_lower
    else:
        # For simple entities, use word boundaries to avoid substring matches
        # e.g., prevent "Bit" from matching in "Bitcoin"
        pattern = r'\b' + re.escape(entity_lower) + r'\b'
        found_in_title = bool(re.search(pattern, title_lower))
        found_in_text = bool(re.search(pattern, text_lower))

    return found_in_title or found_in_text


def validate_narrative_json(data: Dict) -> Tuple[bool, Optional[str]]:
    """
    Validate LLM-extracted narrative data.

    Returns: (is_valid, error_message)
    """
    # Check required fields
    required_fields = ['actors', 'actor_salience', 'nucleus_entity',
                       'narrative_focus', 'actions', 'tensions', 'narrative_summary']

    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"

    # Validate actors is a list
    if not isinstance(data['actors'], list):
        return False, "actors must be a list"

    # Tier 3 auto-fix: backfill empty actors from nucleus_entity if available
    if len(data['actors']) == 0:
        nucleus = data.get('nucleus_entity', '')
        if nucleus:
            logger.debug(f"Auto-fixing: backfilling empty actors with nucleus_entity '{nucleus}'")
            data['actors'] = [nucleus]
        else:
            return False, "actors empty and no nucleus_entity to backfill"

    # Cap actors at 20 (prevent bloat)
    if len(data['actors']) > 20:
        logger.debug(f"Capping actors list from {len(data['actors'])} to 20")
        data['actors'] = data['actors'][:20]

    # Validate nucleus_entity exists and is a string
    if not isinstance(data['nucleus_entity'], str) or not data['nucleus_entity']:
        return False, "nucleus_entity must be non-empty string"

    # Validate narrative_focus exists and is a reasonable phrase (2-10 words)
    focus = data.get('narrative_focus', '')
    if not isinstance(focus, str) or not focus.strip():
        return False, "narrative_focus must be non-empty string"

    # Count words in focus (allow 1-10 words for flexibility)
    word_count = len(focus.strip().split())
    if word_count < 1 or word_count > 10:
        return False, f"narrative_focus should be 2-5 words, got {word_count} words: '{focus}'"

    # Auto-fix: Normalize focus to lowercase for consistency
    data['narrative_focus'] = focus.strip().lower()

    # Auto-fix: Ensure nucleus_entity is in actors list
    if data['nucleus_entity'] not in data['actors']:
        logger.debug(f"Adding nucleus_entity {data['nucleus_entity']} to actors list")
        data['actors'].insert(0, data['nucleus_entity'])
    
    # Validate salience scores
    if not isinstance(data.get('actor_salience'), dict):
        return False, "actor_salience must be a dictionary"
    
    for entity, score in data['actor_salience'].items():
        if not isinstance(score, (int, float)):
            return False, f"Invalid salience type for {entity}: {type(score)}"
        if not (1 <= score <= 5):
            return False, f"Invalid salience {score} for {entity} (must be 1-5)"
    
    # Tier 2 auto-fix: Ensure nucleus has salience score (default to 5 if missing)
    if data['nucleus_entity'] not in data.get('actor_salience', {}):
        logger.debug(
            f"Auto-fixing: adding salience 5 for nucleus_entity '{data['nucleus_entity']}'"
        )
        data['actor_salience'][data['nucleus_entity']] = 5
    
    # Validate narrative_summary is non-empty
    if not isinstance(data.get('narrative_summary'), str) or len(data['narrative_summary']) < 10:
        return False, "narrative_summary must be string with at least 10 characters"
    
    return True, None


def compute_narrative_fingerprint(cluster: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute a composite fingerprint for a narrative cluster to enable intelligent matching.

    The fingerprint captures the structural components of a narrative:
    - Nucleus entity (the central protagonist)
    - Narrative focus (what is happening - the key differentiator for parallel stories)
    - Top actors by salience (key participants)
    - Key actions (main events)
    - Timestamp (when fingerprint was computed)

    Args:
        cluster: Dict containing:
            - nucleus_entity: str, the primary entity the narrative is about
            - narrative_focus: str, 2-5 word phrase describing what's happening
            - actors: dict with entity names as keys and salience scores as values
            - actions: list of action/event strings

    Returns:
        Dict with fingerprint components:
            - nucleus_entity: str
            - narrative_focus: str (normalized to lowercase)
            - top_actors: list of top 5 actors sorted by salience (descending)
            - key_actions: list of top 3 actions
            - timestamp: datetime when fingerprint was computed
    """
    # Extract nucleus entity
    nucleus_entity = cluster.get('nucleus_entity', '')

    # Extract narrative focus (normalize to lowercase)
    narrative_focus = cluster.get('narrative_focus', '')
    if narrative_focus:
        narrative_focus = narrative_focus.strip().lower()

    # Extract and sort actors by salience
    actors_dict = cluster.get('actors', {})
    if isinstance(actors_dict, dict):
        # Sort actors by salience score (descending) and take top 5
        sorted_actors = sorted(
            actors_dict.items(),
            key=lambda x: x[1],
            reverse=True
        )
        top_actors = [actor for actor, _ in sorted_actors[:5]]
    else:
        # Handle case where actors might be a list instead of dict
        top_actors = list(actors_dict)[:5] if actors_dict else []

    # Extract key actions (top 3)
    actions = cluster.get('actions', [])
    key_actions = actions[:3] if actions else []

    # Create fingerprint
    fingerprint = {
        'nucleus_entity': nucleus_entity,
        'narrative_focus': narrative_focus,
        'top_actors': top_actors,
        'key_actions': key_actions,
        'timestamp': datetime.now(timezone.utc)
    }

    return fingerprint


def _compute_focus_similarity(focus1: str, focus2: str) -> float:
    """
    Token-based similarity for narrative focus phrases.

    Compares focus phrases by word overlap, with graduated scoring:
    - 1.0: Exact match (identical focus phrases)
    - 0.9: High similarity (>80% word overlap)
    - 0.7: Partial similarity (>50% word overlap)
    - 0.0: Different focus phrases
    - 0.5: Neutral (at least one focus is missing - legacy data compatibility)

    Args:
        focus1: First narrative focus phrase (or empty string)
        focus2: Second narrative focus phrase (or empty string)

    Returns:
        Similarity score between 0.0 and 1.0

    Example:
        >>> _compute_focus_similarity("price surge", "price surge")
        1.0
        >>> _compute_focus_similarity("price surge", "price rally")
        0.7
        >>> _compute_focus_similarity("price surge", "governance")
        0.0
    """
    # Handle missing focus (legacy data compatibility)
    if not focus1 or not focus2:
        return 0.5  # Neutral for missing focus

    # Normalize to lowercase and handle exact match
    focus1_lower = focus1.lower().strip()
    focus2_lower = focus2.lower().strip()

    if focus1_lower == focus2_lower:
        return 1.0

    # Tokenize into words
    tokens1 = set(focus1_lower.split())
    tokens2 = set(focus2_lower.split())

    # Calculate Jaccard similarity (intersection / union)
    overlap = len(tokens1 & tokens2)
    total = len(tokens1 | tokens2)

    if total == 0:
        return 0.0

    ratio = overlap / total

    # Graduated scoring based on overlap ratio
    if ratio > 0.8:
        return 0.9
    elif ratio > 0.5:
        return 0.7
    else:
        return 0.0


def calculate_fingerprint_similarity(
    fingerprint1: Dict[str, Any],
    fingerprint2: Dict[str, Any]
) -> float:
    """
    Calculate similarity between two narrative fingerprints.

    Uses weighted scoring to determine if two narratives should be merged:
    - Focus match (narrative_focus token overlap): weight 0.5 (primary discriminator)
    - Nucleus match (exact match of nucleus_entity): weight 0.3
    - Actor overlap (Jaccard similarity of top_actors): weight 0.1
    - Action overlap (Jaccard similarity of key_actions): weight 0.1

    IMPORTANT: Uses hard gate logic to prevent unrelated narratives from merging.
    Two fingerprints must have EITHER a focus match OR nucleus match to proceed
    with weighted scoring. If neither matches, returns 0.0 immediately.

    The narrative_focus is the PRIMARY differentiator for parallel stories about
    the same entity. E.g., "Dogecoin price surge" vs "Dogecoin governance dispute"
    should NOT merge even though they share the same nucleus_entity.

    Args:
        fingerprint1: First fingerprint dict with nucleus_entity, narrative_focus, top_actors, key_actions
        fingerprint2: Second fingerprint dict with nucleus_entity, narrative_focus, top_actors, key_actions

    Returns:
        Similarity score between 0.0 and 1.0, where 1.0 is identical

    Example:
        >>> fp1 = {
        ...     'nucleus_entity': 'SEC',
        ...     'narrative_focus': 'regulatory enforcement action',
        ...     'top_actors': ['SEC', 'Binance', 'Coinbase'],
        ...     'key_actions': ['filed lawsuit', 'regulatory enforcement']
        ... }
        >>> fp2 = {
        ...     'nucleus_entity': 'SEC',
        ...     'narrative_focus': 'regulatory enforcement',
        ...     'top_actors': ['SEC', 'Binance', 'Kraken'],
        ...     'key_actions': ['filed lawsuit', 'compliance review']
        ... }
        >>> calculate_fingerprint_similarity(fp1, fp2)
        0.85  # High similarity: matching focus (0.5) + matching nucleus (0.3) + actor overlap (0.05)
    """
    # Extract components from fingerprints
    nucleus1 = fingerprint1.get('nucleus_entity', '')
    nucleus2 = fingerprint2.get('nucleus_entity', '')

    focus1 = fingerprint1.get('narrative_focus', '')
    focus2 = fingerprint2.get('narrative_focus', '')

    actors1 = set(fingerprint1.get('top_actors', []))
    actors2 = set(fingerprint2.get('top_actors', []))

    actions1 = set(fingerprint1.get('key_actions', []))
    actions2 = set(fingerprint2.get('key_actions', []))

    # HARD GATE: Require either focus match or entity match to proceed
    # This prevents unrelated stories from merging
    has_focus_match = focus1 and focus2 and focus1.lower() == focus2.lower()
    has_entity_match = nucleus1 and nucleus2 and nucleus1.lower() == nucleus2.lower()

    if not (has_focus_match or has_entity_match):
        logger.debug(
            f"Hard gate: Blocking similarity - no focus or entity match. "
            f"Focus: '{focus1}' vs '{focus2}', Entity: '{nucleus1}' vs '{nucleus2}'"
        )
        return 0.0

    # Calculate focus match score using token-based similarity (primary signal)
    focus_match_score = _compute_focus_similarity(focus1, focus2)

    # Calculate nucleus match score (binary: 1.0 or 0.0)
    nucleus_match_score = 1.0 if has_entity_match else 0.0

    # Calculate actor overlap score (Jaccard similarity)
    actor_overlap_score = 0.0
    if actors1 and actors2:
        actor_overlap = len(actors1 & actors2)
        actor_union = len(actors1 | actors2)
        actor_overlap_score = actor_overlap / actor_union if actor_union > 0 else 0.0

    # Calculate action overlap score (Jaccard similarity)
    action_overlap_score = 0.0
    if actions1 and actions2:
        action_overlap = len(actions1 & actions2)
        action_union = len(actions1 | actions2)
        action_overlap_score = action_overlap / action_union if action_union > 0 else 0.0

    # Weighted sum of components (weights sum to 1.0)
    # Focus is now the primary signal with 0.5 weight
    similarity = (
        focus_match_score * 0.5 +
        nucleus_match_score * 0.3 +
        actor_overlap_score * 0.1 +
        action_overlap_score * 0.1
    )

    logger.debug(
        f"Fingerprint similarity: {similarity:.3f} "
        f"(focus={focus_match_score:.1f}*0.5={focus_match_score*0.5:.3f}, "
        f"nucleus={nucleus_match_score:.1f}*0.3={nucleus_match_score*0.3:.3f}, "
        f"actors={actor_overlap_score:.3f}*0.1={actor_overlap_score*0.1:.3f}, "
        f"actions={action_overlap_score:.3f}*0.1={action_overlap_score*0.1:.3f})"
    )

    return similarity


def clean_json_response(response: str) -> str:
    """
    Clean JSON response from LLM to handle control characters and newlines.
    
    Claude often includes newlines and control characters in JSON string values,
    which breaks json.loads(). This function:
    1. Strips markdown code blocks
    2. Extracts JSON object from text (handles "Here is..." prefixes)
    3. Replaces control characters (newlines, carriage returns, tabs) with spaces
    4. Normalizes multiple spaces to single space
    
    Args:
        response: Raw LLM response string
    
    Returns:
        Cleaned JSON string ready for parsing
    """
    # Strip markdown code blocks
    response_clean = response.strip()
    if response_clean.startswith("```json"):
        response_clean = response_clean[7:]
    if response_clean.startswith("```"):
        response_clean = response_clean[3:]
    if response_clean.endswith("```"):
        response_clean = response_clean[:-3]
    response_clean = response_clean.strip()
    
    # Extract JSON object if there's text before it
    # Look for the first { and last } to extract just the JSON
    first_brace = response_clean.find('{')
    last_brace = response_clean.rfind('}')
    
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        response_clean = response_clean[first_brace:last_brace + 1]
    
    # Replace control characters with spaces
    # This handles newlines (\n), carriage returns (\r), and tabs (\t)
    response_clean = response_clean.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    
    # Normalize multiple spaces to single space
    response_clean = re.sub(r'\s+', ' ', response_clean)
    
    return response_clean

# Predefined theme categories for crypto news
THEME_CATEGORIES = [
    "regulatory",           # SEC actions, legal frameworks, compliance
    "defi_adoption",        # DeFi protocols, TVL changes, yield farming
    "institutional_investment",  # Corporate adoption, ETFs, institutional flows
    "payments",             # Payment rails, merchant adoption, remittances
    "layer2_scaling",       # L2 solutions, rollups, scaling tech
    "security",             # Hacks, exploits, security audits
    "infrastructure",       # Node operators, validators, network upgrades
    "nft_gaming",           # NFTs, gaming, metaverse
    "stablecoin",           # Stablecoin regulation, depegs, adoption
    "market_analysis",      # Price action, trading volumes, market sentiment
    "technology",           # Protocol upgrades, new tech, research
    "partnerships",         # Collaborations, integrations, ecosystem growth
]


async def extract_themes_from_article(
    article_id: str,
    title: str,
    summary: str
) -> List[str]:
    """
    Extract thematic categories from an article using Claude Sonnet.
    
    Args:
        article_id: Article ID for logging
        title: Article title
        summary: Article summary/description
    
    Returns:
        List of theme strings (e.g., ["regulatory", "institutional_investment"])
    """
    if not title and not summary:
        logger.warning(f"Article {article_id} has no title or summary for theme extraction")
        return []
    
    # Build prompt for Claude
    prompt = f"""Analyze this crypto news article and identify the primary themes.

Article Title: {title}
Article Summary: {summary[:500]}

Available themes:
{', '.join(THEME_CATEGORIES)}

Return ONLY a JSON array of 1-3 most relevant themes from the list above.
Example: ["regulatory", "institutional_investment"]

JSON array:"""
    
    try:
        # Call Claude
        llm_client = get_llm_provider()
        response = llm_client._get_completion(prompt)
        
        if not response:
            logger.warning(f"Empty response from LLM for article {article_id}")
            return []
        
        # Parse JSON response with cleaning
        response_clean = clean_json_response(response)
        
        try:
            themes = json.loads(response_clean)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON for article {article_id}: {e}. Response: {response_clean[:200]}")
            return []
        
        # Validate themes are in our predefined list
        valid_themes = [t for t in themes if t in THEME_CATEGORIES]
        
        if not valid_themes:
            logger.warning(f"No valid themes extracted for article {article_id}. Response: {themes}")
            return []
        
        logger.debug(f"Extracted themes for article {article_id}: {valid_themes}")
        return valid_themes
    
    except Exception as e:
        logger.exception(f"Error extracting themes for article {article_id}: {e}")
        return []


async def backfill_themes_for_recent_articles(hours: int = 48, limit: int = 100) -> int:
    """
    Backfill themes for recent articles that don't have them yet.
    
    Args:
        hours: Look back this many hours for articles
        limit: Maximum number of articles to process
    
    Returns:
        Number of articles updated with themes
    """
    db = await mongo_manager.get_async_database()
    articles_collection = db.articles
    
    from datetime import timedelta
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    
    # Find recent articles without themes
    cursor = articles_collection.find({
        "published_at": {"$gte": cutoff_time},
        "$or": [
            {"themes": {"$exists": False}},
            {"themes": {"$size": 0}}
        ]
    }).limit(limit)
    
    updated_count = 0
    
    async for article in cursor:
        article_id = str(article.get("_id"))
        title = article.get("title", "")
        summary = article.get("description", "") or article.get("text", "") or article.get("content", "")
        
        # Extract themes
        themes = await extract_themes_from_article(article_id, title, summary)
        
        if themes:
            # Update article with themes
            await articles_collection.update_one(
                {"_id": article["_id"]},
                {"$set": {"themes": themes, "themes_extracted_at": datetime.now(timezone.utc)}}
            )
            updated_count += 1
            logger.info(f"Updated article {article_id} with themes: {themes}")
    
    logger.info(f"Backfilled themes for {updated_count} articles")
    return updated_count


async def get_articles_by_theme(
    theme: str,
    hours: int = 48,
    min_articles: int = 2
) -> Optional[List[Dict[str, Any]]]:
    """
    Get articles that share a specific theme within a time window.
    
    Args:
        theme: Theme to filter by
        hours: Look back this many hours
        min_articles: Minimum number of articles required to return results
    
    Returns:
        List of article documents or None if below threshold
    """
    db = await mongo_manager.get_async_database()
    articles_collection = db.articles
    
    from datetime import timedelta
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    
    # Find articles with this theme (high-signal only)
    # Include articles with no tier yet (unclassified) for backward compatibility
    cursor = articles_collection.find({
        "themes": theme,
        "published_at": {"$gte": cutoff_time},
        "$or": [
            {"relevance_tier": {"$lte": MAX_RELEVANCE_TIER}},
            {"relevance_tier": {"$exists": False}},
            {"relevance_tier": None},
        ]
    }).sort("published_at", -1)
    
    articles = []
    async for article in cursor:
        articles.append(article)
    
    if len(articles) < min_articles:
        return None
    
    return articles


def _build_degraded_narrative(
    article_id: str,
    title: str,
    summary: str,
    content_hash: str,
    reason: str = ""
) -> Dict[str, Any]:
    """
    Build a minimal degraded narrative result when LLM output fails validation.

    This keeps the pipeline moving without additional LLM calls.
    Degraded narratives can be identified by status="degraded" and
    optionally backfilled later with a prompt/schema fix.

    Args:
        article_id: Article ID for logging
        title: Article title (used as fallback nucleus entity)
        summary: Article summary
        content_hash: Content hash for caching
        reason: Why the result is degraded

    Returns:
        Dict with minimal narrative structure
    """
    # Extract a simple nucleus entity from the title
    # Use the first capitalized multi-word phrase or first 3 words
    fallback_nucleus = title.split(":")[0].strip()[:50] if title else "Unknown"

    logger.info(
        f"Building degraded narrative for article {article_id[:8]}... "
        f"(reason: {reason})"
    )

    return {
        "actors": [fallback_nucleus],
        "actor_salience": {fallback_nucleus: 3},
        "nucleus_entity": fallback_nucleus,
        "narrative_focus": "unclassified",
        "actions": [],
        "tensions": [],
        "implications": "",
        "narrative_summary": summary[:200] if summary else title,
        "narrative_hash": content_hash,
        "status": "degraded",
        "degraded_reason": reason,
    }


async def discover_narrative_from_article(
    article: Dict,
    max_retries: int = 2  # Reduced: only retries transient errors (429, 529, timeout), not validation failures
) -> Optional[Dict[str, Any]]:
    """
    Extract narrative elements from article with caching.

    Uses content hash to skip re-processing unchanged articles.
    Validation failures return degraded fallback (no retry - validation failures are deterministic).
    Transient errors (429, 529) are retried with backoff.

    Args:
        article: Article document dict with _id, title, description/text/content
        max_retries: Maximum number of retry attempts for transient errors only (not validation failures)

    Returns:
        Dict with narrative elements including actor_salience and nucleus_entity,
        or degraded stub with status="degraded" if validation fails,
        or None if extraction fails
    """
    article_id = str(article.get('_id', 'unknown'))
    
    # Generate content hash for caching
    title = article.get('title', '')
    summary = article.get('description', '') or article.get('text', '') or article.get('content', '')
    content_for_hash = f"{title}:{summary}"
    content_hash = hashlib.sha1(content_for_hash.encode()).hexdigest()
    
    # Check if we already have current narrative data
    existing_hash = article.get('narrative_hash')
    existing_summary = article.get('narrative_summary')
    existing_actors = article.get('actors')
    
    # Skip if hash matches and we have valid data
    if (existing_hash == content_hash and 
        existing_summary and 
        existing_actors):
        logger.debug(
            f"✓ Skipping article {article_id[:8]}... - "
            f"narrative data already current (hash: {content_hash[:8]}...)"
        )
        return None  # Signal that no update needed
    
    if existing_hash and existing_hash != content_hash:
        logger.info(
            f"♻️  Article {article_id[:8]}... content changed - "
            f"re-extracting narrative (old hash: {existing_hash[:8]}, new: {content_hash[:8]})"
        )
    else:
        logger.info(f"🔄 Processing article {article_id[:8]}... (hash: {content_hash[:8]}...)")
    
    if not title and not summary:
        logger.warning(f"Article {article_id} has no title or summary for narrative discovery")
        return None

    # Per-article LLM call cap (belt-and-suspenders on zero-retry validation fix)
    llm_calls_made = 0
    MAX_LLM_CALLS_PER_ARTICLE = 2

    # Retry loop (only for transient errors, not validation failures)
    for attempt in range(max_retries):
        # Build prompt for Claude with salience scoring
        prompt = f"""You are a narrative analyst studying emerging patterns in crypto news.

Given the following article, describe:

1. The main *actors* (people, organizations, protocols, assets, regulators)
   - For each actor, assign a salience score from 1-5:
     * 5 = central protagonist of the story (the article is ABOUT this entity)
     * 4 = key participant (actively involved in the main events)
     * 3 = secondary participant (mentioned with some relevance)
     * 2 = supporting context (provides background but not central)
     * 1 = passing mention (could remove without changing story)
   
   **IMPORTANT**: Only include actors with salience >= 2 in your final list.
   Background mentions (salience 1) should be excluded.

2. **Nucleus entity** (required): The ONE entity this article is primarily about.
   This is the anchor of the story - if you had to summarize in one word, which entity?

3. **Narrative focus** (required): A 2-5 word phrase describing WHAT IS HAPPENING.
   This captures the core development/claim of the story, NOT the entity itself.
   Examples: "price surge", "regulatory enforcement", "protocol upgrade", "governance dispute",
   "ETF approval", "hack investigation", "partnership announcement", "market manipulation probe"

   The focus should be:
   - Verb-driven (captures action/development)
   - Specific enough to distinguish parallel stories about the same entity
   - General enough to merge related articles
   - NOT just the entity name or topic label (avoid "Dogecoin news" or "Bitcoin update")

5. The main *actions or events* (what happened)

6. The *forces or tensions* at play (e.g., regulation vs innovation, centralization vs decentralization)

7. The *implications* or *stakes* (why it matters)

Then summarize in 2-3 sentences what broader narrative this article contributes to.

**CRITICAL - ANTI-HALLUCINATION RULES:**
1. ONLY extract information explicitly stated in the article
2. Do NOT add titles or roles from your training knowledge
3. Do NOT assume someone is CEO, Chairman, etc. - people change positions
4. If the article says "CZ" without a title, just use "CZ" - don't add "Binance CEO"
5. Focus on WHAT happened, not assumptions about who holds what position

**ENTITY NORMALIZATION GUIDELINES:**

1. **Normalize entity names to canonical forms:**
   - "U.S. Securities and Exchange Commission" → "SEC"
   - "Securities and Exchange Commission" → "SEC"
   - "US SEC" → "SEC"
   - "Ethereum Foundation" → "Ethereum"
   - "Ethereum network" → "Ethereum"
   - "Tether Holdings Limited" → "Tether"
   - "Tether USDT" → "Tether"
   - "Bitcoin Core developers" → "Bitcoin"
   - "Bitcoin network" → "Bitcoin"
   - "Binance.US" → "Binance" (unless US distinction is critical to the story)
   - "Binance exchange" → "Binance"
   - Always use the shortest, most recognizable form
   - Use common abbreviations (SEC, ETF, DeFi) not full names
   - For cryptocurrencies, use the name not ticker (Bitcoin not BTC, Ethereum not ETH)
   - For people: use their name only, NOT their title (e.g., "CZ" not "Binance CEO CZ")

2. **Nucleus entity selection rules:**
   - If multiple entities have salience 5, choose the one most directly responsible for the main action
   - Prefer specific entities over generic categories ("Binance" not "crypto exchanges")
   - Prefer actors over objects in regulatory stories ("SEC" not "lawsuit" or "regulation")
   - Prefer companies/organizations over people ("Coinbase" not "Brian Armstrong" unless person is the focus)
   - The nucleus should be the grammatical subject of the article's main action

3. **Salience scoring consistency:**
   - Reserve salience 5 for 1-2 entities maximum (the true protagonists)
   - Use salience 4 for 2-4 key participants
   - Use salience 3 for 3-6 secondary participants
   - Avoid giving everything high salience - be selective
   - Background mentions like "Bitcoin" or "crypto market" in passing should be excluded (salience 1)

Article Title: {title}
Article Summary: {summary[:500]}

**CRITICAL**: Respond with ONLY valid JSON. Do not include any explanatory text, markdown formatting, or commentary. Start your response with {{ and end with }}.

Required JSON format:
{{
  "actors": ["list of actors with salience >= 2"],
  "actor_salience": {{
    "EntityName": 4,
    "AnotherEntity": 3
  }},
  "nucleus_entity": "PrimaryEntityName",
  "narrative_focus": "2-5 word phrase describing what is happening",
  "actions": ["list of key events"],
  "tensions": ["list of forces or tensions"],
  "implications": "why this matters",
  "narrative_summary": "2-3 sentence description"
}}

Example for "SEC sues Binance for regulatory violations":
{{
  "actors": ["SEC", "Binance", "Coinbase"],
  "actor_salience": {{
    "SEC": 5,
    "Binance": 4,
    "Coinbase": 2
  }},
  "nucleus_entity": "SEC",
  "narrative_focus": "regulatory enforcement action",
  "actions": ["SEC filed lawsuit against Binance"],
  "tensions": ["Regulation vs Innovation", "Compliance vs Growth"],
  "implications": "Signals escalation in regulatory enforcement",
  "narrative_summary": "Regulators are intensifying enforcement against major exchanges as the SEC targets Binance for alleged securities violations, with implications for the broader industry."
}}

Example for "Dogecoin surges 40% as retail traders pile in":
{{
  "actors": ["Dogecoin", "retail traders"],
  "actor_salience": {{
    "Dogecoin": 5,
    "retail traders": 3
  }},
  "nucleus_entity": "Dogecoin",
  "narrative_focus": "price surge momentum",
  "actions": ["Dogecoin price increased 40%", "retail traders increased positions"],
  "tensions": ["Speculation vs Fundamentals", "Retail vs Institutional"],
  "implications": "Renewed meme coin interest signals risk appetite returning",
  "narrative_summary": "Dogecoin is experiencing a significant price surge driven by retail trader enthusiasm, marking a potential return of speculative momentum in the meme coin sector."
}}

Your JSON response:"""
        
        try:
            # Per-article LLM call cap
            if llm_calls_made >= MAX_LLM_CALLS_PER_ARTICLE:
                logger.warning(
                    f"Per-article LLM call cap ({MAX_LLM_CALLS_PER_ARTICLE}) reached "
                    f"for article {article_id[:8]}... Returning degraded result."
                )
                return _build_degraded_narrative(
                    article_id, title, summary, content_hash,
                    reason=f"per-article call cap ({MAX_LLM_CALLS_PER_ARTICLE})"
                )

            llm_calls_made += 1

            # Call LLM
            llm_client = get_llm_provider()
            response = llm_client._get_completion(prompt)
            
            if not response:
                logger.warning(f"Empty response from LLM for article {article_id}")
                return None
            
            # Parse JSON response with cleaning
            response_clean = clean_json_response(response)
            
            # Parse JSON response
            try:
                narrative_data = json.loads(response_clean)
                
                # VALIDATE JSON structure before returning
                is_valid, error = validate_narrative_json(narrative_data)

                if is_valid:
                    logger.debug(f"✓ Validation passed for article {article_id}")

                    # Validate that extracted nucleus_entity actually appears in article text
                    # This prevents LLM hallucinations (e.g., "Netflix" → "Coinbase" errors)
                    nucleus_entity = narrative_data.get('nucleus_entity', '')
                    if not validate_entity_in_text(
                        nucleus_entity=nucleus_entity,
                        article_title=title,
                        article_text=summary
                    ):
                        logger.warning(
                            f"✗ Entity validation failed for article {article_id}: "
                            f"'{nucleus_entity}' not found in text (hallucination detected). "
                            f"Returning degraded result (no retry)."
                        )
                        # FAIL CHEAP: Return degraded result instead of retrying
                        return _build_degraded_narrative(
                            article_id, title, summary, content_hash,
                            reason=f"hallucinated nucleus_entity: {nucleus_entity}"
                        )

                    # Add content hash to narrative data for caching
                    narrative_data['narrative_hash'] = content_hash

                    return narrative_data
                else:
                    logger.warning(
                        f"✗ Validation failed for article {article_id}: {error}. "
                        f"Returning degraded result (no retry)."
                    )
                    # FAIL CHEAP: Return degraded fallback instead of retrying
                    # Validation failures are deterministic - retrying won't help
                    return _build_degraded_narrative(
                        article_id, title, summary, content_hash,
                        reason=f"validation: {error}"
                    )
            
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse error for article {article_id} (attempt {attempt + 1}/{max_retries}): {e}")
                logger.debug(f"Raw response length: {len(response)} chars")
                logger.debug(f"Cleaned response preview: {response_clean[:200]}")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                else:
                    return None
        
        except Exception as e:
            error_str = str(e).lower()
            error_type = type(e).__name__
            
            # Handle rate limit errors (429 Too Many Requests)
            if '429' in str(e) or 'rate_limit' in error_str or 'rate limit' in error_str:
                wait_time = (2 ** attempt) * 5  # Exponential backoff: 5s, 10s, 20s
                logger.warning(
                    f"⚠️  Rate limited for article {article_id[:8]}... "
                    f"Waiting {wait_time}s before retry {attempt + 1}/{max_retries}"
                )
                await asyncio.sleep(wait_time)
                
                if attempt < max_retries - 1:
                    continue
                else:
                    logger.error(f"❌ Max retries exhausted due to rate limiting for article {article_id[:8]}...")
                    return None
            
            # Handle API overload errors (529 Overloaded)
            elif '529' in str(e) or 'overloaded' in error_str:
                wait_time = 10 * (attempt + 1)  # Linear backoff: 10s, 20s, 30s
                logger.warning(
                    f"⚠️  API overloaded for article {article_id[:8]}... "
                    f"Waiting {wait_time}s before retry {attempt + 1}/{max_retries}"
                )
                await asyncio.sleep(wait_time)
                
                if attempt < max_retries - 1:
                    continue
                else:
                    logger.error(f"❌ Max retries exhausted due to API overload for article {article_id[:8]}...")
                    return None
            
            # Handle other unexpected errors (don't retry)
            else:
                logger.error(
                    f"❌ Unexpected error for article {article_id[:8]}...: "
                    f"{error_type}: {e}"
                )
                logger.debug(f"Full error: {str(e)}")
                return None
    
    return None


async def generate_narrative_from_theme(
    theme: str,
    articles: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Generate a narrative summary for a theme-based article cluster.
    
    Args:
        theme: The theme connecting these articles
        articles: List of article documents
    
    Returns:
        Dict with narrative data or None if generation fails
    """
    if not articles:
        return None
    
    # Collect article titles and summaries
    article_snippets = []
    for article in articles[:5]:  # Use up to 5 articles for context
        title = article.get("title", "")
        summary = article.get("description", "") or article.get("text", "")[:200]
        article_snippets.append(f"- {title}: {summary}")
    
    snippets_text = "\n".join(article_snippets)
    
    # Build prompt for Claude
    prompt = f"""Analyze these crypto news articles that share the theme "{theme}":

{snippets_text}

Generate a narrative summary:
1. Create a concise title (max 60 characters) that captures the main story
2. Write a 2-3 sentence summary of what's happening in this narrative

Return valid JSON with no newlines in string values: {{"title": "...", "summary": "..."}}"""
    
    try:
        # Call Claude
        llm_client = get_llm_provider()
        response = llm_client._get_completion(prompt)
        
        if not response:
            logger.warning(f"Empty response from LLM for theme {theme}")
            return None
        
        # Parse JSON response with cleaning
        response_clean = clean_json_response(response)
        
        try:
            narrative_data = json.loads(response_clean)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON for theme {theme}: {e}. Using fallback. Response: {response_clean[:200]}")
            # Fallback
            return {
                "title": f"{theme.replace('_', ' ').title()} Narrative",
                "summary": f"Multiple articles discussing {theme.replace('_', ' ')} in the crypto space."
            }
        
        return {
            "title": narrative_data.get("title", f"{theme.replace('_', ' ').title()} Narrative"),
            "summary": narrative_data.get("summary", "")
        }
    
    except Exception as e:
        logger.exception(f"Error generating narrative for theme {theme}: {e}")
        return None


async def cluster_by_narrative_salience(
    articles: List[Dict],
    min_cluster_size: int = 3
) -> List[List[Dict]]:
    """
    Cluster articles by nucleus entity and weighted actor/tension overlap.
    
    Clustering logic uses weighted link strength:
    - Same nucleus entity: +1.0 (strongest signal)
    - 2+ shared high-salience actors (≥4): +0.7
    - 1 shared high-salience actor: +0.4
    - 1+ shared tensions: +0.3
    
    Articles cluster together if link_strength >= 0.8
    
    Args:
        articles: List of article dicts with actors, actor_salience, nucleus_entity, tensions
        min_cluster_size: Minimum articles required to form a cluster
    
    Returns:
        List of article clusters (each cluster is a list of articles)
    """
    clusters = []
    
    logger.info(f"Starting clustering for {len(articles)} articles")
    
    for idx, article in enumerate(articles, 1):
        nucleus = article.get('nucleus_entity')
        actors = article.get('actors') or []
        actor_salience = article.get('actor_salience') or {}
        tensions = article.get('tensions') or []
        article_title = article.get('title', 'Unknown')[:50]
        
        # Skip articles with missing critical data
        if not nucleus or not actors:
            logger.warning(f"Skipping article {idx} - missing nucleus or actors")
            continue
        
        # Get high-salience actors only (salience >= 4.5)
        # These are the key players, not background mentions
        core_actors = [a for a in actors if actor_salience.get(a, 0) >= 4.5]
        
        logger.info(f"Article {idx}/{len(articles)}: {article_title}")
        logger.info(f"  Nucleus: {nucleus}, Core actors: {core_actors}")
        logger.info(f"  All actors: {actors}, Tensions: {tensions}")
        
        # Try to match with existing cluster
        matched = False
        best_cluster = None
        best_strength = 0.0
        
        for cluster in clusters:
            # Get cluster properties from first article (representative)
            cluster_nucleus = cluster[0].get('nucleus_entity')
            
            # Aggregate cluster properties
            cluster_actors = set()
            cluster_core_actors = set()
            cluster_tensions = set()
            
            for cluster_article in cluster:
                cluster_actors.update(cluster_article.get('actors') or [])
                cluster_tensions.update(cluster_article.get('tensions') or [])
                c_salience = cluster_article.get('actor_salience') or {}
                c_actors = cluster_article.get('actors') or []
                cluster_core_actors.update(
                    a for a in c_actors
                    if c_salience.get(a, 0) >= 4.5
                )
            
            # Calculate weighted link strength
            link_strength = 0.0
            
            # Strongest signal: Same nucleus entity
            # e.g., Both articles are fundamentally about "SEC"
            if nucleus and nucleus == cluster_nucleus:
                link_strength += 1.0
            
            # Medium signal: High-salience actors overlap
            # e.g., Both feature "Binance" and "Coinbase" as key players
            shared_core = len(set(core_actors) & cluster_core_actors)
            if shared_core >= 2:
                link_strength += 0.7
            elif shared_core >= 1:
                link_strength += 0.4
            
            # Weaker signal: Shared tensions/themes
            # e.g., Both involve "Regulation vs Innovation"
            shared_tensions = len(set(tensions) & cluster_tensions)
            if shared_tensions >= 1:
                link_strength += 0.3
            
            # Track best matching cluster
            if link_strength > best_strength:
                best_strength = link_strength
                best_cluster = cluster
        
        # Cluster if link strength is strong enough (threshold: 0.8)
        logger.info(f"  Best cluster match: strength={best_strength:.2f}, threshold=0.8")
        
        if best_strength >= 0.8 and best_cluster is not None:
            best_cluster.append(article)
            matched = True
            logger.info(f"  ✓ Matched to existing cluster (now {len(best_cluster)} articles)")
        
        # Create new cluster if no good match
        if not matched:
            clusters.append([article])
            logger.info(f"  ✗ Created new cluster (total clusters: {len(clusters)})")
    
    # Filter out small clusters (below minimum size)
    substantial_clusters = [c for c in clusters if len(c) >= min_cluster_size]
    
    logger.info(f"Clustering complete: {len(clusters)} total clusters, {len(substantial_clusters)} substantial (>={min_cluster_size} articles)")
    for idx, cluster in enumerate(substantial_clusters, 1):
        cluster_nucleus = cluster[0].get('nucleus_entity', 'Unknown')
        logger.info(f"  Cluster {idx}: {len(cluster)} articles, nucleus={cluster_nucleus}")
    
    return substantial_clusters


async def backfill_narratives_for_recent_articles(hours: int = 48, limit: int = 100) -> int:
    """
    Backfill narrative data for recent articles that don't have them yet.
    
    Uses discover_narrative_from_article to extract actors, tensions, and narrative elements.
    
    Args:
        hours: Look back this many hours for articles
        limit: Maximum number of articles to process
    
    Returns:
        Number of articles updated with narrative data
    """
    db = await mongo_manager.get_async_database()
    articles_collection = db.articles
    
    from datetime import timedelta
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    
    # Find articles needing narrative extraction (high-signal only)
    # Only process if:
    # 1. Missing narrative_summary, OR
    # 2. Missing narrative_hash (old format), OR
    # 3. Missing actors or nucleus_entity (incomplete data)
    # AND: relevance_tier is high/medium or not yet classified
    cursor = articles_collection.find({
        "published_at": {"$gte": cutoff_time},
        # Relevance filter: skip tier 3 (low signal) articles
        "$and": [
            {
                "$or": [
                    {"relevance_tier": {"$lte": MAX_RELEVANCE_TIER}},
                    {"relevance_tier": {"$exists": False}},
                    {"relevance_tier": None},
                ]
            },
            {
                "$or": [
                    {"narrative_summary": {"$exists": False}},
                    {"narrative_summary": None},
                    {"actors": {"$exists": False}},
                    {"actors": None},
                    {"nucleus_entity": {"$exists": False}},
                    {"nucleus_entity": None},
                    {"narrative_hash": {"$exists": False}},  # Missing hash = needs processing
                ]
            }
        ]
    }).limit(limit)

    updated_count = 0
    degraded_count = 0
    failed_count = 0
    results = []

    async for article in cursor:
        article_id = str(article.get("_id"))

        # Extract narrative elements (now with caching)
        narrative_data = await discover_narrative_from_article(article)

        if narrative_data:
            results.append(narrative_data)

            # Track degraded status
            if narrative_data.get("status") == "degraded":
                degraded_count += 1
                logger.debug(
                    f"Degraded narrative for article {article_id[:8]}... "
                    f"(reason: {narrative_data.get('degraded_reason', 'unknown')})"
                )

            # Update article with narrative data (including hash)
            await articles_collection.update_one(
                {"_id": article["_id"]},
                {"$set": {
                    "actors": narrative_data.get("actors", []),
                    "actor_salience": narrative_data.get("actor_salience", {}),
                    "nucleus_entity": narrative_data.get("nucleus_entity", ""),
                    "narrative_focus": narrative_data.get("narrative_focus", ""),
                    "actions": narrative_data.get("actions", []),
                    "tensions": narrative_data.get("tensions", []),
                    "implications": narrative_data.get("implications", ""),
                    "narrative_summary": narrative_data.get("narrative_summary", ""),
                    "narrative_hash": narrative_data.get("narrative_hash", ""),
                    "narrative_extracted_at": datetime.now(timezone.utc),
                    "status": narrative_data.get("status"),  # "degraded" or implicit success
                    "degraded_reason": narrative_data.get("degraded_reason")  # Reason if degraded
                }}
            )
            updated_count += 1
            logger.info(f"Updated article {article_id} with narrative data")
        else:
            failed_count += 1

    # Log degraded rate for this batch
    total = len(results)
    succeeded = sum(1 for r in results if r and r.get("status") != "degraded")
    degraded = sum(1 for r in results if r and r.get("status") == "degraded")

    if total > 0:
        degraded_pct = (degraded / total) * 100
        logger.info(
            f"Narrative backfill complete: {total} articles, "
            f"{succeeded} succeeded, {degraded} degraded ({degraded_pct:.0f}%), "
            f"{failed_count} failed"
        )
    else:
        logger.info(f"Narrative backfill complete: no articles processed")

    return updated_count


async def generate_narrative_from_cluster(cluster: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Generate a narrative summary for a cluster of articles.
    
    Aggregates actors, tensions, and article IDs from the cluster and generates
    a cohesive narrative title and summary.
    
    Args:
        cluster: List of article documents with narrative data
    
    Returns:
        Dict with narrative data (title, summary, actors, article_ids, etc.) or None if generation fails
    """
    if not cluster:
        return None
    
    logger.info(f"Generating narrative for cluster of {len(cluster)} articles")

    # Aggregate data from cluster
    all_actors = []
    all_tensions = []
    article_ids = []
    nucleus_entities = []
    narrative_focuses = []

    for article in cluster:
        all_actors.extend(article.get("actors", []))
        all_tensions.extend(article.get("tensions", []))
        article_ids.append(str(article.get("_id")))
        nucleus = article.get("nucleus_entity")
        if nucleus:
            nucleus_entities.append(nucleus)
        focus = article.get("narrative_focus")
        if focus:
            narrative_focuses.append(focus.lower().strip())

    # Get unique actors and tensions
    unique_actors = list(set(all_actors))
    unique_tensions = list(set(all_tensions))

    # Determine primary nucleus entity (most common)
    nucleus_counts = Counter(nucleus_entities)
    primary_nucleus = nucleus_counts.most_common(1)[0][0] if nucleus_counts else ""

    # Determine primary narrative focus (most common)
    focus_counts = Counter(narrative_focuses)
    primary_focus = focus_counts.most_common(1)[0][0] if focus_counts else ""

    logger.info(f"  Primary nucleus: {primary_nucleus}")
    logger.info(f"  Primary focus: {primary_focus}")
    logger.info(f"  Unique actors ({len(unique_actors)}): {unique_actors[:10]}")
    logger.info(f"  Unique tensions ({len(unique_tensions)}): {unique_tensions[:5]}")
    
    # Extract entity relationships (co-occurrence in same articles)
    entity_links = defaultdict(int)
    for article in cluster:
        actors = article.get("actors", [])
        if len(actors) >= 2:
            for a, b in combinations(actors, 2):
                pair = tuple(sorted([a, b]))
                entity_links[pair] += 1
    
    # Store top 5 relationships by co-occurrence count
    top_relationships = sorted(
        entity_links.items(),
        key=lambda x: x[1],
        reverse=True
    )[:5]
    
    entity_relationships = [
        {"a": pair[0], "b": pair[1], "weight": count}
        for pair, count in top_relationships
    ]
    
    logger.info(f"  Entity relationships ({len(entity_relationships)}): {entity_relationships}")
    
    # Collect article snippets for context
    article_snippets = []
    for article in cluster[:5]:  # Use up to 5 articles for context
        title = article.get("title", "")
        summary = article.get("narrative_summary", "") or article.get("description", "")[:200]
        article_snippets.append(f"- {title}: {summary}")
    
    snippets_text = "\n".join(article_snippets)
    
    # Build prompt for narrative generation
    prompt = f"""Analyze these related crypto news articles and generate a narrative summary.

ARTICLES:
{snippets_text}

Common actors: {', '.join(unique_actors[:10])}
Primary focus: {primary_nucleus}

CRITICAL RULES:
1. ONLY use information explicitly stated in the articles above
2. Do NOT add titles, roles, or facts from your training knowledge
3. Do NOT assume current roles/titles - people change positions (e.g., someone may have resigned)
4. If articles don't specify a person's title, don't add one
5. Focus on WHAT happened, not who holds what position

Generate:
1. A concise title (max 60 characters) capturing the main story
2. A 2-3 sentence summary of what's happening based ONLY on the article content

Return valid JSON with no newlines in string values: {{"title": "...", "summary": "..."}}"""
    
    try:
        # Call LLM
        llm_client = get_llm_provider()
        response = llm_client._get_completion(prompt)
        
        if not response:
            logger.warning(f"Empty response from LLM for cluster with {len(cluster)} articles")
            return None
        
        # Parse JSON response with cleaning
        response_clean = clean_json_response(response)
        
        try:
            narrative_content = json.loads(response_clean)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON for cluster: {e}. Using fallback. Response: {response_clean[:200]}")
            # Fallback
            narrative_content = {
                "title": f"{primary_nucleus} Narrative" if primary_nucleus else "Emerging Narrative",
                "summary": f"Multiple articles discussing {primary_nucleus or 'related topics'} in the crypto space."
            }
        
        # Build full narrative data
        narrative_data = {
            "title": narrative_content.get("title", "Emerging Narrative"),
            "summary": narrative_content.get("summary", ""),
            "actors": unique_actors[:20],  # Limit to top 20 actors
            "tensions": unique_tensions[:10],  # Limit to top 10 tensions
            "nucleus_entity": primary_nucleus,
            "narrative_focus": primary_focus,
            "article_ids": article_ids,
            "article_count": len(cluster),
            "entity_relationships": entity_relationships
        }
        
        # Polish the summary for better tone and consistency
        if narrative_data and narrative_data.get('summary'):
            polish_prompt = f"""Rewrite this narrative summary in 1-2 punchy sentences suitable for a crypto intelligence dashboard.

Original: {narrative_data['summary']}

Requirements:
- No phrases like "These articles highlight" or "The articles show"
- Active voice, strong verbs
- Focus on the key insight or development
- 1-2 sentences maximum
- Professional, neutral tone
- CRITICAL: Do NOT add any titles, roles, or facts not in the original
- Do NOT call anyone CEO, Chairman, etc. unless the original says so

Respond with ONLY the rewritten summary, no other text."""

            try:
                polished = llm_client._get_completion(polish_prompt)
                # Clean response
                polished = polished.strip().strip('"').strip("'")
                if polished and len(polished) > 10:
                    narrative_data['summary'] = polished
                    logger.debug(f"✓ Summary polished: {polished[:50]}...")
            except Exception as e:
                logger.warning(f"Summary polish failed, using original: {e}")
                # Keep original summary
        
        logger.info(f"  Generated narrative: '{narrative_data['title']}'")
        return narrative_data
    
    except Exception as e:
        logger.exception(f"Error generating narrative for cluster: {e}")
        return None


async def merge_shallow_narratives(narratives: List[Dict]) -> List[Dict]:
    """
    Merge single-article narratives into nearest semantic cluster.
    
    Heuristic: If narrative has only 1 article, few unique actors, or a 
    ubiquitous nucleus (Bitcoin/Ethereum), try to merge it into the most
    similar substantial narrative.
    
    Args:
        narratives: List of narrative dicts with article_ids, actors, nucleus_entity
        
    Returns:
        Merged list of narratives with shallow ones absorbed into substantial ones
    """
    # Define ubiquitous entities that shouldn't be standalone narratives
    UBIQUITOUS_ENTITIES = {'Bitcoin', 'Ethereum', 'crypto', 'blockchain', 'cryptocurrency'}
    
    logger.info(f"Starting shallow narrative merging for {len(narratives)} narratives")
    
    substantial_narratives = []
    shallow_narratives = []
    
    # Separate substantial from shallow narratives
    for narrative in narratives:
        article_count = len(narrative.get('article_ids', []))
        unique_actors = len(set(narrative.get('actors', [])))
        nucleus = narrative.get('nucleus_entity', '')
        title = narrative.get('title', 'Unknown')[:50]
        
        # Criteria for shallow narrative:
        # - Only 1 article AND few unique actors (< 3)
        # - OR nucleus is ubiquitous entity (Bitcoin/Ethereum as standalone)
        is_shallow = (
            (article_count == 1 and unique_actors < 3) or
            (nucleus in UBIQUITOUS_ENTITIES and article_count < 3)
        )
        
        if is_shallow:
            shallow_narratives.append(narrative)
            logger.info(f"Shallow: '{title}' (articles={article_count}, actors={unique_actors}, nucleus={nucleus})")
        else:
            substantial_narratives.append(narrative)
            logger.info(f"Substantial: '{title}' (articles={article_count}, actors={unique_actors}, nucleus={nucleus})")
    
    # Try to merge each shallow narrative into a substantial one
    logger.info(f"Attempting to merge {len(shallow_narratives)} shallow narratives into {len(substantial_narratives)} substantial ones")
    
    merged_count = 0
    standalone_count = 0
    
    for shallow in shallow_narratives:
        best_match = None
        best_score = 0.5  # Minimum similarity threshold to merge
        
        shallow_title = shallow.get('title', 'Unknown')[:40]
        shallow_entities = set(shallow.get('actors', []))
        
        logger.info(f"Merging shallow narrative: '{shallow_title}'")
        logger.info(f"  Actors: {list(shallow_entities)}")
        
        for substantial in substantial_narratives:
            substantial_entities = set(substantial.get('actors', []))
            
            if not shallow_entities or not substantial_entities:
                continue
            
            # Calculate Jaccard similarity (overlap / union)
            overlap = len(shallow_entities & substantial_entities)
            union = len(shallow_entities | substantial_entities)
            similarity = overlap / union if union > 0 else 0
            
            # Track best match
            if similarity > best_score:
                best_score = similarity
                best_match = substantial
        
        logger.info(f"  Best match: similarity={best_score:.2f}, threshold=0.5")
        
        # Merge into best match if found
        if best_match:
            match_title = best_match.get('title', 'Unknown')[:40]
            # Extend article list
            best_match['article_ids'] = list(set(
                best_match.get('article_ids', []) + shallow.get('article_ids', [])
            ))
            # Merge actors (unique)
            best_match['actors'] = list(set(
                best_match.get('actors', []) + shallow.get('actors', [])
            ))
            merged_count += 1
            logger.info(f"  ✓ Merged into '{match_title}'")
        else:
            # No good match - keep as standalone
            substantial_narratives.append(shallow)
            standalone_count += 1
            logger.info(f"  ✗ Kept as standalone (no good match)")
    
    logger.info(f"Merge complete: {merged_count} merged, {standalone_count} kept standalone, {len(substantial_narratives)} total narratives")
    
    return substantial_narratives
