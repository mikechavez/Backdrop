---
id: BUG-083
type: bug
status: backlog
priority: critical
severity: critical
created: 2026-04-15
updated: 2026-04-15
---

# Market event detector creates phantom narratives from unrelated articles, fabricating financial figures

## Problem
The `MarketEventDetector` is the root cause of fabricated financial figures in briefings. It matched 23 unrelated articles (prediction markets, Bitcoin price commentary, Polygon staking, Ether.fi validators, Virginia legislation, etc.) under a fictional "Major Market Liquidation Event - $5.0B Cascade" narrative. No liquidation event occurred. The $5.0B figure was fabricated by summing dollar amounts from unrelated article contexts. This phantom narrative was force-boosted to the top of both the evening (April 14) and morning (April 15) briefings. The previous evening briefing cited $204.7B from the same mechanism.

## Expected Behavior
The market event detector should only create narratives when a real market event is occurring, using articles that actually describe that event, with financial figures drawn from relevant context.

## Actual Behavior
Six compounding failures:

1. **OR keyword matching:** `$text.$search` with space-separated words uses MongoDB OR semantics. Searching for `"liquidation liquidations liquidated cascade cascading margin call forced liquidation flash crash market crash sell-off massive liquidations capitulation"` matches any article containing ANY of these words. The Virginia article about *protecting* crypto from forced liquidation matched. The ARIA flash crash article matched. Bitcoin "crash" recovery articles matched.

2. **No relevance validation:** Any article containing any keyword counts toward the detection threshold. No check that the article is actually about a liquidation event.

3. **Volume extraction sums all dollar amounts:** The regex `r"\$(\d+(?:\.?\d+)?)\s*[mb]"` extracts dollar amounts from ALL matched articles regardless of context. The $3B from Ether.fi's validator commitment, the $1T from prediction market projections, Bitcoin price figures — all summed into "liquidation volume."

4. **Low thresholds:** `LIQUIDATION_ARTICLE_THRESHOLD = 4` is trivially met when OR-matching 12+ keyword variants across a 24-hour window of crypto news. `MULTI_ENTITY_THRESHOLD = 3` is trivially met because every crypto article mentions multiple entities.

5. **Missing narrative metadata:** `create_or_update_market_event_narrative()` creates narratives without `nucleus_entity`, `narrative_focus`, `actors`, or `fingerprint` fields. These narratives can never be deduplicated, merged, or validated by the normal clustering pipeline.

6. **Force-boosted ranking:** The narrative is created with `lifecycle_state="hot"`, `recency_score=1.0`, and then `boost_market_event_in_briefing()` adds another `1.0` to `_fresh_recency`. This guarantees the phantom narrative ranks #1 in every briefing cycle until its articles age out.

The result: the LLM receives 23 unrelated articles under a narrative titled "Major Market Liquidation Event - $5.0B Cascade" and is told to synthesize them. It invents a coherent liquidation story, fabricating details to explain why these articles are related. The briefing's hallucination guardrails (BUG-081) cannot catch this because the fabrication is in the source data, not the briefing generation.

## Steps to Reproduce
1. Wait for any 24-hour window where 4+ crypto articles contain any of: "crash", "liquidation", "sell-off", "capitulation", "cascade"
2. Observe that `detect_market_events()` creates a phantom narrative
3. Observe that the narrative summary contains a fabricated dollar figure
4. Observe that the next briefing leads with this fabricated event

## Environment
- Environment: production
- User impact: critical — every briefing since this narrative was created leads with fabricated financial data

---

## Resolution

**Status:** Open

### Root Cause
See "Actual Behavior" above. The market event detector's keyword matching, volume extraction, threshold logic, and narrative creation are all fundamentally broken. A proper rebuild is out of scope for this ticket — see follow-up TASK-072.

### Changes Made

#### Part 1 — Disable the market event detector

**File: `crypto_news_aggregator/services/market_event_detector.py`**

Find:
```python
    async def detect_market_events(self) -> List[Dict[str, Any]]:
        """
        Detect market shock events from recent articles.

        Returns:
            List of detected market events with details
        """
        db = await mongo_manager.get_async_database()
        articles_collection = db.articles
        now = datetime.now(timezone.utc)

        detected_events = []
```

Replace with:
```python
    async def detect_market_events(self) -> List[Dict[str, Any]]:
        """
        Detect market shock events from recent articles.

        Returns:
            List of detected market events with details

        NOTE: DISABLED (BUG-083). The detection logic has six compounding
        failures — OR keyword matching, no relevance validation, blind volume
        extraction, low thresholds, missing narrative metadata, and force-boosted
        ranking — that cause phantom narratives with fabricated financial figures
        to lead every briefing. Disabled until a proper rebuild (TASK-072).
        """
        logger.info("Market event detector disabled (BUG-083). Returning empty list.")
        return []

        # --- DISABLED CODE BELOW (BUG-083) ---
        db = await mongo_manager.get_async_database()
        articles_collection = db.articles
        now = datetime.now(timezone.utc)

        detected_events = []
```

#### Part 2 — Clean up existing phantom narratives

Run once in production MongoDB after deploying Part 1:

```javascript
// Mark all market_shock narratives as dormant so they stop appearing in briefings
db.narratives.updateMany(
  { theme: { $regex: /^market_shock_/ } },
  {
    $set: {
      lifecycle_state: "dormant",
      dormant_since: new Date(),
      last_updated: new Date(),
      _disabled_by: "BUG-083"
    }
  }
)

// Verify — should return 0 active market_shock narratives
db.narratives.countDocuments({
  theme: { $regex: /^market_shock_/ },
  lifecycle_state: { $nin: ["dormant", "merged"] }
})
```

### Testing
1. Deploy the code change.
2. Run the cleanup query and verify the count returns 0.
3. Trigger a test briefing (`force=True`). Verify the narrative does not mention any liquidation cascade or market shock event. Verify the briefing only discusses narratives from the normal clustering pipeline.
4. Monitor the next organic briefing cycle (evening April 15). Confirm no phantom narratives appear.

### Files Changed
- `crypto_news_aggregator/services/market_event_detector.py`

### Follow-up
TASK-072 (not yet written): Rebuild market event detector with proper phrase matching, relevance validation, contextual volume extraction, higher thresholds, complete narrative metadata, and integration with the existing clustering/dedup pipeline. Design question to resolve: whether market event detection should remain a separate system or be folded into the normal clustering pipeline.