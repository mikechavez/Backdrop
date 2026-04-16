---
id: BUG-084
type: bug
status: backlog
priority: critical
severity: critical
created: 2026-04-15
updated: 2026-04-15
---

# Narrative summary generator fabricates events not present in source articles

## Problem
`generate_narrative_summary()` in `optimized_anthropic.py` produces summaries describing events that do not exist in any source article. The prompt instructs the LLM to "synthesize" a "cohesive" narrative, which incentivizes fabrication when articles share an entity but not a story. Only 300 characters of article text are provided, giving the LLM insufficient grounding context. Additionally, the function uses Sonnet instead of Haiku, contradicting the project-wide model standardization.

## Expected Behavior
Narrative summaries should describe only events, facts, and claims explicitly present in the source articles. Three Kraken IPO articles should produce a summary about Kraken's IPO filing.

## Actual Behavior
Three Kraken IPO articles ("Kraken Co-CEO Arjun Sethi Confirms Confidential IPO Filing at Semafor World Economy Summit", "Kraken Confirms Confidential IPO Filing as Deutsche Börse Takes $200M Stake", "Kraken boss signals IPO still in play despite reports of pause") produced a narrative titled "Kraken Faces Extortion Over Stolen Internal Data" describing a criminal extortion group breaching Kraken's internal systems, stealing support videos, compromising ~2,000 customer accounts, and Kraken refusing to negotiate. The entire extortion story was fabricated. This narrative then fed into the evening briefing, which reported the fabricated breach as fact.

## Steps to Reproduce
1. Query the narrative: `db.narratives.findOne({ title: /Kraken.*Extortion/ })`
2. Retrieve its `article_ids` and check the source articles
3. All three source articles are about Kraken's IPO filing — zero mention of extortion, breaches, or stolen data
4. The narrative summary, actors ("criminal extortion group", "extortionists", "attackers"), and title are entirely fabricated

## Environment
- Environment: production
- Browser/Client: N/A (backend pipeline)
- User impact: high — fabricated narratives feed directly into user-facing briefings

## Screenshots/Logs
Narrative ObjectId: `68f102d6f791cb6cf711833c`
Source article ObjectIds: `69dea2e61b80de5043c19775`, `69df1202b8ea0f0ffa9dfeb5`, `69dea94c2adcac6279c197a4`

---

## Resolution

**Status:** Open
**Fixed:**
**Branch:**
**Commit:**

### Root Cause
Three compounding issues in `generate_narrative_summary()` and `_build_summary_prompt()`:

1. **Prompt encourages fabrication.** "Synthesize these related crypto news articles into a cohesive narrative summary" tells the LLM to find coherence even when articles share only an entity, not a story. The model invents events to create coherence.
2. **Insufficient grounding context.** Article text is truncated to 300 characters, providing only a title and roughly one sentence. With "Kraken" + "confidential" + "filing" and minimal context, the model has room to hallucinate a security breach narrative.
3. **Wrong model.** The function uses `self.SONNET_MODEL` (claude-sonnet-4-5-20250929) instead of Haiku, contradicting the project-wide standardization to Haiku and increasing cost unnecessarily.

### Changes Made
Three changes to `optimized_anthropic.py`:

**Change 1 — Increase article text from 300 to 800 characters in `_build_summary_prompt()`:**

Find:
```python
f"Article {i+1}:\nTitle: {article['title']}\nSummary: {article.get('text', '')[:300]}"
```

Replace:
```python
f"Article {i+1}:\nTitle: {article['title']}\nText: {article.get('text', '')[:800]}"
```

**Change 2 — Replace prompt instructions in `_build_summary_prompt()`:**

Find:
```python
        return f"""Synthesize these related crypto news articles into a cohesive narrative summary.

{articles_text}

Write a 2-3 sentence summary that:
1. Identifies the main story/theme
2. Explains why it matters
3. Notes any conflicting perspectives
4. Verifies financial figures are consistent across articles — if sources disagree on a number, note the discrepancy rather than picking one

Be concise and informative."""
```

Replace:
```python
        return f"""Summarize these related crypto news articles.

{articles_text}

Write a 2-3 sentence summary that:
1. Identifies the main story or theme based ONLY on events explicitly described in the articles above
2. Explains why it matters
3. Notes any conflicting perspectives
4. Verifies financial figures are consistent across articles — if sources disagree on a number, note the discrepancy rather than picking one

CRITICAL: Your summary must describe only events, facts, and claims that are explicitly stated in the provided articles. Do not infer, speculate, or add events not present in the source text. If the articles describe an IPO filing, summarize the IPO filing — do not introduce security breaches, hacks, lawsuits, or other events unless they are explicitly described in the articles.

Be concise and informative."""
```

**Change 3 — Switch from Sonnet to Haiku in `generate_narrative_summary()`:**

Find:
```python
cached_response = await self.cache.get(prompt, self.SONNET_MODEL)
```

Replace:
```python
cached_response = await self.cache.get(prompt, self.HAIKU_MODEL)
```

Find:
```python
        api_response = self._make_api_call(
            prompt=prompt,
            model=self.SONNET_MODEL,
            max_tokens=500,
            temperature=0.7,
            operation="narrative_summary"
        )
```

Replace:
```python
        api_response = self._make_api_call(
            prompt=prompt,
            model=self.HAIKU_MODEL,
            max_tokens=500,
            temperature=0.5,
            operation="narrative_summary"
        )
```

**Post-deploy cleanup — mark the existing Kraken narrative dormant:**
```js
db.narratives.updateOne(
  { _id: ObjectId("68f102d6f791cb6cf711833c") },
  { $set: { lifecycle_state: "dormant", dormant_since: new Date(), _disabled_by: "BUG-084" } }
)
```

### Testing
1. Deploy changes and mark existing Kraken narrative dormant
2. Wait for next narrative clustering cycle to regenerate Kraken narrative from the three IPO articles
3. Verify the new narrative summary describes the IPO filing, not an extortion event
4. Verify logs show Haiku model for `narrative_summary` operations
5. Force a briefing and confirm no fabricated events appear

### Files Changed
- `optimized_anthropic.py` — `_build_summary_prompt()`, `generate_narrative_summary()`

### Notes
- Token cost increase from 300 to 800 chars is modest: ~50 extra input tokens per article x 10 articles = ~500 additional input tokens per summary call
- Temperature reduced from 0.7 to 0.5 to limit creative drift under the tighter grounding constraints
- Monitor Haiku's instruction-following on the grounding constraints after deploy — Haiku is more prone to instruction-following gaps than Sonnet
- Follow-up TASK-073: post-generation validation that checks whether key claims in the summary (breach, hack, lawsuit, extortion) have lexical support in the source article text