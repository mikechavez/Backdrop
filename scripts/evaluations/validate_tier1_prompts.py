#!/usr/bin/env python3
"""
TASK-081 Spot-Check Validation: Tier 1 Prompts
Validates updated entity extraction, sentiment analysis, and theme extraction prompts
against 5 sample articles per operation.
"""

import json
import sys
from datetime import datetime
from typing import Any
from bson import ObjectId
from anthropic import Anthropic

# Article IDs from TASK-081
ARTICLE_IDS = {
    "entity_extraction": [
        "69e124b4cd3cb7bb0f1de49a",
        "69e10224b05c1d4ddc1de4c7",
        "69de1566972adb5ad8c76cb6",
        "69dfb314a634582621effb78",
        "69deb85f2adcac6279c197b5",
    ],
    "sentiment_analysis": [
        "69e124b4cd3cb7bb0f1de49a",  # neutral
        "69e10224b05c1d4ddc1de4c7",  # negative
        "69e0c3100a57f1a2701de53e",  # negative
        "69e124b5cd3cb7bb0f1de49b",  # positive
        "69de613a972adb5ad8c76df6",  # positive
    ],
    "theme_extraction": [
        "69e124b4cd3cb7bb0f1de49a",
        "69e10224b05c1d4ddc1de4c7",
        "69e0c3100a57f1a2701de53e",
        "69e124b5cd3cb7bb0f1de49b",
        "69de613a972adb5ad8c76df6",
    ],
}

EXPECTED_SENTIMENT_LABELS = {
    "69e124b4cd3cb7bb0f1de49a": "neutral",
    "69e10224b05c1d4ddc1de4c7": "negative",
    "69e0c3100a57f1a2701de53e": "negative",
    "69e124b5cd3cb7bb0f1de49b": "positive",
    "69de613a972adb5ad8c76df6": "positive",
}

SENTIMENT_RANGES = {
    "bullish": (0.3, 1.0),
    "bearish": (-1.0, -0.3),
    "neutral": (-0.3, 0.3),
}


def fetch_articles(db, article_ids: list[str]) -> dict[str, Any]:
    """Fetch articles from MongoDB by IDs."""
    articles = {}
    for article_id in article_ids:
        try:
            article = db["articles"].find_one({"_id": ObjectId(article_id)})
            if article:
                articles[article_id] = article
            else:
                print(f"[WARN] Article {article_id} not found in database")
        except Exception as e:
            print(f"[ERROR] Error fetching article {article_id}: {e}")
    return articles


def build_entity_extraction_prompt(title: str, text: str) -> str:
    """Build the updated entity extraction prompt."""
    return f"""Extract cryptocurrency-related entities relevant to the article's primary narrative.

Title: {title}
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


def build_sentiment_analysis_prompt(text: str) -> str:
    """Build the updated sentiment analysis prompt."""
    return f"""Analyze the sentiment of this crypto text. Return ONLY a single number from -1.0 (very bearish) to 1.0 (very bullish). Do not include any explanation or additional text. Just the number.

Sentiment Scale:
- Bullish (0.3 to 1.0): Article emphasizes gains, positive developments, bullish signals, or constructive news
- Bearish (-1.0 to -0.3): Article emphasizes losses, negative events, regulatory concerns, or destructive developments
- Neutral (-0.3 to 0.3): Factual reporting without strong directional bias. Includes crime/legal/regulatory articles where the event is negative but the framing is factual (e.g., "CFTC filed lawsuit" without inflammatory language or speculation)

EXAMPLE:
Text: "Jean-Didier Berger said at Paris Blockchain Week that France is preparing new steps to protect crypto holders as wrench attacks and kidnappings keep mounting."

WRONG (misclassified as negative): -0.4
CORRECT (neutral): -0.1
   (Reports negative event [kidnappings] factually without inflammatory language or speculation. Focus is on preparedness/protection, not loss/harm.)

Return ONLY the number, no explanation:

{text}"""


def build_theme_extraction_prompt(combined_texts: str) -> str:
    """Build the updated theme extraction prompt."""
    return f"""Extract the key conceptual themes from the following texts. Respond with ONLY a comma-separated list of themes (e.g., 'regulatory pressure, market volatility, institutional adoption'). Do not include any preamble.

Themes should be:
- Conceptual (not entity names): "regulation" not "SEC", "market volatility" not "Bitcoin"
- Exclude proper nouns: No company names, person names, coin names, or protocol names
- Focus on narrative concepts: regulatory, technical, market, adoption, security, legal, etc.

EXAMPLE:
Text: "Goldman Sachs filed for a Bitcoin Premium Income ETF..."

WRONG (includes entity names): Bitcoin, ETF, Goldman Sachs, Institutional Adoption, Covered Call Strategy
CORRECT (conceptual only): ETF, Institutional Adoption
   (Exclude: Bitcoin [cryptocurrency], Goldman Sachs [company], Covered Call Strategy [implementation detail]. Keep: conceptual themes.)

Return ONLY the comma-separated list, no explanation:

Texts:
{combined_texts}"""


def run_validation(db, client: Anthropic):
    """Run spot-check validation on all three operations."""
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "model": "claude-haiku-4-5-20251001",
        "operations": {
            "entity_extraction": {"status": "pending", "results": []},
            "sentiment_analysis": {"status": "pending", "results": []},
            "theme_extraction": {"status": "pending", "results": []},
        },
    }

    # ============================================================================
    # 1. ENTITY EXTRACTION
    # ============================================================================
    print("\n[ENTITY EXTRACTION VALIDATION]")
    print("=" * 80)
    articles = fetch_articles(db, ARTICLE_IDS["entity_extraction"])
    for article_id in ARTICLE_IDS["entity_extraction"]:
        if article_id not in articles:
            continue

        article = articles[article_id]
        title = article.get("title", "[No title]")
        text = article.get("content", "")[:2000]  # Truncate for API

        print(f"\n[Article {article_id}]")
        print(f"   Title: {title[:60]}...")

        try:
            prompt = build_entity_extraction_prompt(title, text)
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = message.content[0].text
            try:
                entities_obj = json.loads(response_text)
                entities = entities_obj.get("entities", [])
                entity_count = len(entities)
                entity_names = [e.get("name") for e in entities]

                print(f"   [OK] Extracted {entity_count} entities: {', '.join(entity_names)}")

                results["operations"]["entity_extraction"]["results"].append(
                    {
                        "article_id": article_id,
                        "title": title,
                        "entity_count": entity_count,
                        "entities": entity_names,
                        "raw_response": response_text,
                    }
                )
            except json.JSONDecodeError:
                print(f"   [WARN] Could not parse JSON response")
                results["operations"]["entity_extraction"]["results"].append(
                    {"article_id": article_id, "error": "JSON parse failed", "raw": response_text}
                )

        except Exception as e:
            print(f"   [ERROR] API Error: {e}")
            results["operations"]["entity_extraction"]["results"].append(
                {"article_id": article_id, "error": str(e)}
            )

    results["operations"]["entity_extraction"]["status"] = "completed"

    # ============================================================================
    # 2. SENTIMENT ANALYSIS
    # ============================================================================
    print("\n\n[SENTIMENT ANALYSIS VALIDATION]")
    print("=" * 80)
    articles = fetch_articles(db, ARTICLE_IDS["sentiment_analysis"])
    for article_id in ARTICLE_IDS["sentiment_analysis"]:
        if article_id not in articles:
            continue

        article = articles[article_id]
        title = article.get("title", "[No title]")
        text = article.get("content", "")[:1500]
        expected_label = EXPECTED_SENTIMENT_LABELS.get(article_id, "unknown")

        print(f"\n[Article {article_id} (expected: {expected_label})]")
        print(f"   Title: {title[:60]}...")

        try:
            prompt = build_sentiment_analysis_prompt(text)
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = message.content[0].text.strip()
            try:
                sentiment_score = float(response_text)
                # Classify into range
                if SENTIMENT_RANGES["bullish"][0] <= sentiment_score <= SENTIMENT_RANGES["bullish"][1]:
                    classified = "bullish"
                elif SENTIMENT_RANGES["bearish"][0] <= sentiment_score <= SENTIMENT_RANGES["bearish"][1]:
                    classified = "bearish"
                else:
                    classified = "neutral"

                match = "[OK]" if classified == expected_label else "[WARN]"
                print(f"   {match} Score: {sentiment_score:.2f} (classified: {classified})")

                results["operations"]["sentiment_analysis"]["results"].append(
                    {
                        "article_id": article_id,
                        "title": title,
                        "expected": expected_label,
                        "score": sentiment_score,
                        "classified_as": classified,
                        "match": classified == expected_label,
                    }
                )
            except ValueError:
                print(f"   [WARN] Could not parse sentiment score: '{response_text}'")
                results["operations"]["sentiment_analysis"]["results"].append(
                    {
                        "article_id": article_id,
                        "error": "Float parse failed",
                        "raw": response_text,
                    }
                )

        except Exception as e:
            print(f"   [ERROR] API Error: {e}")
            results["operations"]["sentiment_analysis"]["results"].append(
                {"article_id": article_id, "error": str(e)}
            )

    results["operations"]["sentiment_analysis"]["status"] = "completed"

    # ============================================================================
    # 3. THEME EXTRACTION
    # ============================================================================
    print("\n\n[THEME EXTRACTION VALIDATION]")
    print("=" * 80)
    articles = fetch_articles(db, ARTICLE_IDS["theme_extraction"])
    for article_id in ARTICLE_IDS["theme_extraction"]:
        if article_id not in articles:
            continue

        article = articles[article_id]
        title = article.get("title", "[No title]")
        text = article.get("content", "")[:1500]

        print(f"\n[Article {article_id}]")
        print(f"   Title: {title[:60]}...")

        try:
            prompt = build_theme_extraction_prompt(text)
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = message.content[0].text.strip()
            themes = [t.strip() for t in response_text.split(",")]

            print(f"   [OK] Extracted {len(themes)} themes: {', '.join(themes)}")

            results["operations"]["theme_extraction"]["results"].append(
                {
                    "article_id": article_id,
                    "title": title,
                    "theme_count": len(themes),
                    "themes": themes,
                }
            )

        except Exception as e:
            print(f"   [ERROR] API Error: {e}")
            results["operations"]["theme_extraction"]["results"].append(
                {"article_id": article_id, "error": str(e)}
            )

    results["operations"]["theme_extraction"]["status"] = "completed"

    return results


def write_results_markdown(results: dict) -> str:
    """Write results to markdown file for analysis."""
    md = "# TASK-081 Tier 1 Prompt Validation Results\n\n"
    md += f"**Timestamp:** {results['timestamp']}\n"
    md += f"**Model:** {results['model']}\n\n"

    # Entity Extraction Section
    md += "## 1. Entity Extraction\n\n"
    md += "**Objective:** Verify outputs are focused on primary entities, not all mentions.\n\n"
    entity_results = results["operations"]["entity_extraction"]["results"]
    for i, result in enumerate(entity_results, 1):
        if "error" in result:
            md += f"### Article {i}: [ERROR]\n"
            md += f"- **ID:** {result['article_id']}\n"
            md += f"- **Error:** {result['error']}\n\n"
        else:
            md += f"### Article {i}\n"
            md += f"- **ID:** {result['article_id']}\n"
            md += f"- **Title:** {result['title']}\n"
            md += f"- **Entity Count:** {result['entity_count']}\n"
            md += f"- **Entities:** {', '.join(result['entities']) if result['entities'] else '(none)'}\n"
            md += f"- **Validation:** Check that entity count is reasonable (typically 3-7 primary entities, not 10+)\n\n"

    # Sentiment Analysis Section
    md += "\n## 2. Sentiment Analysis\n\n"
    md += "**Objective:** Verify neutral articles score in -0.3 to 0.3 range (not extreme).\n\n"
    sentiment_results = results["operations"]["sentiment_analysis"]["results"]
    sentiment_accuracy = sum(1 for r in sentiment_results if r.get("match")) / len(
        sentiment_results
    )
    md += f"**Accuracy:** {sentiment_accuracy * 100:.0f}% ({sum(1 for r in sentiment_results if r.get('match'))}/{len(sentiment_results)})\n\n"

    for i, result in enumerate(sentiment_results, 1):
        if "error" in result:
            md += f"### Article {i}: [ERROR]\n"
            md += f"- **ID:** {result['article_id']}\n"
            md += f"- **Error:** {result['error']}\n\n"
        else:
            status = "[OK]" if result["match"] else "[WARN]"
            md += f"### Article {i}: {status}\n"
            md += f"- **ID:** {result['article_id']}\n"
            md += f"- **Title:** {result['title']}\n"
            md += f"- **Expected:** {result['expected']}\n"
            md += f"- **Score:** {result['score']:.2f}\n"
            md += f"- **Classified As:** {result['classified_as']}\n"
            if result["expected"] == "neutral":
                in_range = -0.3 <= result["score"] <= 0.3
                range_status = "[OK]" if in_range else "[WARN]"
                md += f"- **Neutral Range (-0.3 to 0.3):** {range_status}\n\n"
            else:
                md += "\n"

    # Theme Extraction Section
    md += "\n## 3. Theme Extraction\n\n"
    md += "**Objective:** Verify outputs contain conceptual themes, not entity/coin names.\n\n"
    theme_results = results["operations"]["theme_extraction"]["results"]
    for i, result in enumerate(theme_results, 1):
        if "error" in result:
            md += f"### Article {i}: [ERROR]\n"
            md += f"- **ID:** {result['article_id']}\n"
            md += f"- **Error:** {result['error']}\n\n"
        else:
            md += f"### Article {i}\n"
            md += f"- **ID:** {result['article_id']}\n"
            md += f"- **Title:** {result['title']}\n"
            md += f"- **Theme Count:** {result['theme_count']}\n"
            md += f"- **Themes:** {', '.join(result['themes']) if result['themes'] else '(none)'}\n"
            md += f"- **Validation:** Check for coin names (Bitcoin, Ethereum) or company names (Goldman Sachs, SEC) — should be conceptual only\n\n"

    # Summary Section
    md += "\n## Validation Summary\n\n"
    md += "### Manual Checks Required\n\n"
    md += "**Entity Extraction:**\n"
    md += "- [ ] Do entity counts feel right (not too many)?\n"
    md += "- [ ] Are extracted entities central to the story (not infrastructure/background)?\n\n"
    md += "**Sentiment Analysis:**\n"
    md += f"- [ ] Neutral articles are scoring in -0.3 to 0.3 range (current accuracy: {sentiment_accuracy*100:.0f}%)\n"
    md += "- [ ] Positive/Negative articles still scoring correctly (no regressions)\n\n"
    md += "**Theme Extraction:**\n"
    md += "- [ ] Are themes conceptual (e.g., 'regulation', 'adoption', 'market volatility')?\n"
    md += "- [ ] No coin names (Bitcoin, Ethereum) in theme lists?\n"
    md += "- [ ] No company names (Goldman Sachs, SEC) in theme lists?\n\n"

    return md


def main():
    """Main entry point."""
    # User must pass MongoDB client and database
    # Usage: validate_tier1_prompts.py <db_instance>

    # For now, provide example usage
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║          TASK-081 Tier 1 Prompt Validation                                ║
║          Entity Extraction | Sentiment Analysis | Theme Extraction        ║
╚════════════════════════════════════════════════════════════════════════════╝

Usage:
------
from pymongo import MongoClient
from anthropic import Anthropic
from validate_tier1_prompts import run_validation, write_results_markdown

# Connect to your database
client = MongoClient("mongodb://localhost:27017")
db = client["your_database_name"]

# Connect to Anthropic API (uses ANTHROPIC_API_KEY env var)
anthropic = Anthropic()

# Run validation
results = run_validation(db, anthropic)

# Write results to markdown
markdown = write_results_markdown(results)
with open("task-081-validation-results.md", "w") as f:
    f.write(markdown)

print("✅ Validation complete. Results written to task-081-validation-results.md")
""")


if __name__ == "__main__":
    main()