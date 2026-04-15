---
id: BUG-082
type: bug
status: backlog
priority: low
severity: low
created: 2026-04-15
updated: 2026-04-15
---

# Narrative summary pipeline passes implausible financial figures without warning

## Problem
The narrative summary generation pipeline in `optimized_anthropic.py` can produce summaries containing implausible financial figures (e.g., "$204.7B in liquidations in 24 hours") without any validation or logging. By the time the briefing agent sees this data, the bad figure is treated as source-of-truth and passes all guardrails.

BUG-081 adds a briefing-level critique check as the primary defense. This ticket adds defense-in-depth: a warning log at the narrative summary layer and a prompt instruction to verify figure consistency across source articles.

## Expected Behavior
- The summary prompt should instruct the LLM to verify that financial figures are consistent across source articles and flag discrepancies.
- After generating a summary, the pipeline should log a warning if any single-event dollar figure exceeds a plausibility threshold ($50B), creating visibility for investigation.

## Actual Behavior
`generate_narrative_summary()` accepts whatever the LLM returns and caches it without any figure validation. The summary prompt does not instruct the LLM to cross-check figures across articles.

## Steps to Reproduce
1. Ingest articles where one source misreports "$204.7M" as "$204.7B" (or the LLM misreads the unit)
2. Observe that `generate_narrative_summary()` produces a summary with "$204.7B"
3. No warning is logged; the figure is cached and fed downstream

## Environment
- Environment: production
- User impact: low (defense-in-depth; BUG-081 is the primary catch)

---

## Resolution

**Status:** Open

### Root Cause
No validation layer exists between LLM output and the narrative summary cache. The summary prompt does not instruct the LLM to verify figures against source articles.

### Changes Made

**File: `crypto_news_aggregator/llm/optimized_anthropic.py`**

**Change 1 — Add `import re` to imports (after line 10)**

Find:
```python
import json
import logging
from typing import List, Dict, Any, Optional
```

Replace with:
```python
import json
import logging
import re
from typing import List, Dict, Any, Optional
```

**Change 2 — Add figure verification instruction to `_build_summary_prompt()` (rule 4)**

Find:
```python
        return f"""Synthesize these related crypto news articles into a cohesive narrative summary.

{articles_text}

Write a 2-3 sentence summary that:
1. Identifies the main story/theme
2. Explains why it matters
3. Notes any conflicting perspectives

Be concise and informative."""
```

Replace with:
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

**Change 3 — Add post-generation figure plausibility warning in `generate_narrative_summary()` (after `summary = api_response["content"].strip()`, before caching)**

Find:
```python
        summary = api_response["content"].strip()
        result = {"summary": summary}

        # Cache the result
        if use_cache:
            await self.cache.set(prompt, self.SONNET_MODEL, result)

        return summary
```

Replace with:
```python
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
            await self.cache.set(prompt, self.SONNET_MODEL, result)

        return summary
```

### Testing
1. Unit test: call `generate_narrative_summary()` with mock articles that would produce a summary containing "$204.7B in liquidations." Verify a WARNING log is emitted containing "SUSPICIOUS FIGURE" and "$50B single-event threshold."
2. Unit test: call with articles producing a summary containing "$2.5B" (below threshold). Verify no warning is logged.
3. Unit test: verify the regex handles formats like "$204.7B", "$204.7 billion", "$1.2T", "$1.2 trillion."
4. Run existing narrative generation tests to confirm no regressions.

### Files Changed
- `crypto_news_aggregator/llm/optimized_anthropic.py`