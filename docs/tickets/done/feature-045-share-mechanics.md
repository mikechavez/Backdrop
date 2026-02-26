---
id: FEATURE-045
type: feature
status: canceled
priority: high
complexity: medium
created: 2026-02-23
updated: 2026-02-25
---

# Add Share Mechanics to Interactive Site

## Status Update (2026-02-25)
❌ **CANCELED** — Share mechanic competes with Substack CTA at the highest-engagement moment. Most scores deliver critical feedback, limiting share motivation. Viral loop not worth the conversion tradeoff.

## Problem/Opportunity
Readers who complete the routing mini-game have no way to share their score. This is the highest-engagement moment — they just got a personalized result. A share button here turns readers into distributors. Without it, the viral loop is broken.

## Proposed Solution
Two buttons that appear after the routing mini-game score is revealed:
1. "Share your score on 𝕏" — opens Twitter intent with pre-filled tweet
2. "Copy tweet" — copies tweet text to clipboard with toast confirmation

## User Story
As a reader who just completed the routing game, I want to share my score on X so that my followers see the simulator and try it themselves.

## Acceptance Criteria
- [ ] Share on X button appears only after checking routing answers
- [ ] Tweet opens with pre-filled text including score and site URL
- [ ] Copy button copies tweet text to clipboard
- [ ] Toast notification confirms copy (use existing `showToast()` function)
- [ ] Buttons styled consistently with existing site aesthetic (mono font, amber accent)
- [ ] Buttons hidden until score is revealed
- [ ] Works on mobile (touch targets adequate)

## Dependencies
- TASK-001 (URLs in place so the share text includes the right link)

## Implementation Notes

### Button insertion point
After the `routeScore` element display (around line 1091 in `checkRouting()` function).

### Share function
```javascript
function shareScore() {
  const score = document.getElementById('routeScore').querySelector('strong').textContent;
  const text = `I scored ${score} on the Cognitive Debt Simulator 🧠\n\nAI lets you build faster than you can understand. This interactive shows exactly how.\n\nTry it: PRODUCTION_URL`;
  window.open(`https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}`, '_blank');
}
```

### Copy function
```javascript
function copyScore() {
  const score = document.getElementById('routeScore').querySelector('strong').textContent;
  const text = `I scored ${score} on the Cognitive Debt Simulator.\n\nMost AI-built apps collapse — this shows exactly why.\n\nPRODUCTION_URL`;
  navigator.clipboard.writeText(text);
  showToast('Copied to clipboard!', true);
}
```

### Styling
Match `.nb` button pattern: `var(--mono)` font, `.55rem`, `.1em` letter-spacing, uppercase, `var(--amber)` border/color on primary, `var(--border)` on secondary.

## Files to Modify
- `cognitive-debt-simulator-v5.html` (HTML + JS + CSS)

## Open Questions
- [ ] Should we add a share button elsewhere (hero, CTA section) or just at the game?

## Out of Scope
- LinkedIn share button
- General social sharing toolbar
- Analytics on share clicks