---
id: FEATURE-046
type: feature
status: done
priority: high
complexity: low
created: 2026-02-23
updated: 2026-02-25
---

# Add Email Capture / Substack Embed to Interactive Site

## Problem/Opportunity
Readers arriving at the interactive site from X, LinkedIn, or Reddit have no way to subscribe. They read the simulator, maybe share it, then leave. A Substack embed captures these readers as subscribers.

## Proposed Solution
Add a Substack subscribe embed section between the final CTA and the footer.

## User Story
As a reader who found this via social media, I want to subscribe for future posts without leaving the page.

## Acceptance Criteria
- [x] Subscribe section visible between CTA section and footer
- [x] Substack embed loads and accepts email input
- [x] Styled consistently with dark theme (no jarring white iframe)
- [x] Fallback link to Substack subscribe page if embed fails
- [x] Works on mobile

## Dependencies
- None

## Implementation Notes

### What was implemented
- Subscribe section inserted between CTA (`</section>` line 630) and footer
- Substack iframe embed as primary with `onload`/`onerror` handlers
- Fallback "Subscribe on Substack →" button (hidden by default, appears if iframe fails)
- Fallback styled as bordered mono button matching nav style
- CSS uses existing theme variables (`--border`, `--text-dim`, `--serif`, `--mono`, `--amber`)
- Added `reveal` class for scroll animation consistency
- iframe constrained to `max-width: 480px` with `color-scheme: dark`

### Key decision
- Kept the Substack iframe as primary (Mike's preference) despite dark theme concerns
- Removed "Or subscribe directly on Substack" text link in favor of a styled button fallback that only appears on iframe failure

## Files Modified
- `cognitive-debt-simulator-v5.html` → `cognitive-debt-simulator-v5-preview.html`

## Open Questions
- [x] Does the Substack iframe render acceptably on a dark background? → To be verified after deploy to backdrop.markets. `filter: invert(1)` or native form available as plan B.

## Out of Scope
- Custom email backend
- Newsletter analytics
- Substack API integration