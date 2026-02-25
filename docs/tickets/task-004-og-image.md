---
id: TASK-004
type: task
status: backlog
priority: high
created: 2026-02-23
updated: 2026-02-23
---

# Create OG Image / Social Card

## Objective
Create a 1200×630px image used as the social preview card for both the interactive site and the Substack article. This is what people see when the link is shared on X, LinkedIn, Slack, iMessage, etc.

## Context
Without an OG image, shared links display as plain text with no visual preview. A compelling OG image dramatically increases click-through rate from social feeds.

## Tool Routing
- Tool: Claude Web (design discussion + generation)
- Model: N/A

## Requirements
- Dimensions: 1200×630px
- Dark background matching site (#09090b or close)
- Headline: "AI Lets You Build Faster Than You Can Understand"
- One metric callout: choose from:
  - "6 months · 3 critical failures · 1 production system"
  - "89.1% accuracy · $10/mo · 1,500+ articles/day"
- Author attribution: "Mike Chavez"
- Label: "Interactive Case Study" or "A 6-Month Case Study"
- Aesthetic: Minimal, editorial, dark — NOT a tech-bro YouTube thumbnail
- Must be legible at small sizes (Twitter card is ~500px wide)

## Execution Steps
1. Design in Claude Web or generate with image tool
2. Export as PNG or JPG (keep under 1MB)
3. Host somewhere publicly accessible (Vercel static, imgur, or Substack media)
4. Update TASK-001 meta tags with final hosted URL

## Acceptance Criteria
- [ ] Image is 1200×630px
- [ ] Readable at Twitter card preview size
- [ ] Hosted at public URL
- [ ] URL added to og:image and twitter:image meta tags

## Dependencies
- None (can do anytime)

## Out of Scope
- Animated preview
- Multiple image variants per platform
