---
id: FEATURE-046
type: feature
status: backlog
priority: high
complexity: low
created: 2026-02-23
updated: 2026-02-23
---

# Add Email Capture / Substack Embed to Interactive Site

## Problem/Opportunity
Readers arriving at the interactive site from X, LinkedIn, or Reddit have no way to subscribe. They read the simulator, maybe share it, then leave. A Substack embed captures these readers as subscribers.

## Proposed Solution
Add a Substack subscribe embed section between the final CTA and the footer.

## User Story
As a reader who found this via social media, I want to subscribe for future posts without leaving the page.

## Acceptance Criteria
- [ ] Subscribe section visible between CTA section and footer
- [ ] Substack embed loads and accepts email input
- [ ] Styled consistently with dark theme (no jarring white iframe)
- [ ] Fallback link to Substack subscribe page if embed fails
- [ ] Works on mobile

## Dependencies
- None

## Implementation Notes

### Insertion point
Between `</section>` (line 630) and `<!-- FOOTER -->` (line 632)

### Primary: Substack iframe
```html
<section class="subscribe-section">
  <div class="container">
    <p class="label">Stay informed</p>
    <h3 class="subscribe-heading">Get the next build log</h3>
    <p class="subscribe-sub">Lessons from building production AI systems. No hype — just what actually works.</p>
    <iframe src="https://mikechavez.substack.com/embed" width="100%" height="150" style="border:none; background:transparent;" frameborder="0" scrolling="no"></iframe>
  </div>
</section>
```

### Fallback: Simple link
```html
<a href="https://mikechavez.substack.com/subscribe" class="nb cta-nav" target="_blank">Subscribe on Substack →</a>
```

### CSS
```css
.subscribe-section { padding: 4rem 2rem; text-align: center; border-top: 1px solid var(--border); }
.subscribe-heading { font-family: var(--serif); font-weight: 300; font-size: 1.4rem; margin: 0.75rem 0; }
.subscribe-sub { color: var(--text-dim); font-size: 0.9rem; max-width: 440px; margin: 0 auto 1.5rem; }
```

## Files to Modify
- `cognitive-debt-simulator-v5.html`

## Open Questions
- [ ] Does the Substack iframe render acceptably on a dark background? May need CSS override.

## Out of Scope
- Custom email backend
- Newsletter analytics
- Substack API integration
