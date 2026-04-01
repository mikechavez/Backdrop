---
id: TASK-001
type: task
status: backlog
priority: high
created: 2026-02-23
updated: 2026-02-23
---

# Replace Placeholder URLs + Add OG/Twitter Meta Tags

## Objective
Replace all `YOUR_SUBSTACK_URL_HERE` placeholders in the interactive site with the actual Substack URL. Add OpenGraph and Twitter Card meta tags so shared links render rich previews on social platforms.

## Context
The interactive Cognitive Debt Simulator has 6 hardcoded placeholder URLs and no social sharing meta tags. Without these, shared links will display as plain text with no preview card — dramatically reducing click-through rates.

## Tool Routing
- Tool: Claude Code
- Model: Sonnet

## Execution Steps

### 1. Replace placeholder URLs (6 locations)
Find and replace all `YOUR_SUBSTACK_URL_HERE`:
- Line 382: nav CTA button
- Line 483: velocity-comprehension gap link
- Line 540: AI agent failure link
- Line 586: context engineering link
- Line 611: LLM cost routing link
- Line 629: final CTA link

**Temporary value:** `https://mikechavez.substack.com/p/PLACEHOLDER`
**Note:** After Substack is published, do a final find-and-replace with the real URL.

### 2. Add meta tags after line 9 (after existing og:description)
```html
<meta property="og:image" content="OG_IMAGE_URL_HERE">
<meta property="og:type" content="website">
<meta property="og:url" content="PRODUCTION_SITE_URL_HERE">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Cognitive Debt Simulator">
<meta name="twitter:description" content="Most AI-built apps collapse. This interactive case study shows you exactly why — and how to avoid it.">
<meta name="twitter:image" content="OG_IMAGE_URL_HERE">
```

## Files Involved
- MODIFY: `cognitive-debt-simulator-v5.html`

## Acceptance Criteria
- [ ] All 6 `YOUR_SUBSTACK_URL_HERE` instances replaced
- [ ] OG image meta tag present (placeholder URL ok for now)
- [ ] Twitter card meta tags present
- [ ] Page loads correctly after changes
- [ ] No other broken links

## Dependencies
- None (can start immediately)

## Out of Scope
- Creating the OG image (TASK-004)
- Share buttons (FEATURE-045)
- Email capture (FEATURE-046)
- Final URL replacement (happens after Substack publish)
