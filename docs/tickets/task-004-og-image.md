---
created: 2026-02-23
id: TASK-004
priority: high
status: in-progress
type: task
updated: 2026-02-26
---

# Create OG Image / Social Card

## Objective

Create a 1200×630px image used as the social preview card for both the
interactive site and the Substack article. This is what people see when
the link is shared on X, LinkedIn, Slack, iMessage, etc.

## Context

Without an OG image, shared links display as plain text with no visual
preview. A compelling OG image dramatically increases click-through rate
from social feeds.

## Tool Routing

-   Tool: Claude Web (design discussion) + Google Imagen (generation) +
    Claude Code (wiring)
-   **Status**: Image selected (2026-02-26), meta copy updated, favicon
    addition pending wiring

------------------------------------------------------------------------

## Final Launch Copy (Locked)

**Title (matches webpage hero):** AI lets you build faster than you can
understand.

**Description:** It feels like progress. Until it isn't. Explore the
hidden costs of building with AI and what it takes to succeed in the
agent era.

------------------------------------------------------------------------

## Image Selected

**File:** `og-image-1200x630.jpg` (1200×630px, 194KB JPEG) - Resized
from original 1424×752 Imagen output - Centered crop preserves figure
and chasm composition

**Concept:** "The Gap" --- a lone figure at the edge of a massive dark
chasm with amber light rising from the depths.

**Inspiration:** Kazimir Malevich's Suprematist work. Dark, atmospheric,
amber palette matches Early Signal brand identity.

------------------------------------------------------------------------

## Remaining Steps (Claude Code)

1.  Update story.html meta tags with final launch copy.
2.  Add favicon `gt-logo.png` to `context-owl-ui/public/` Add to
    `<head>`: `<link rel="icon" type="image/png" href="/gt-logo.png">`
3.  Build and deploy:
    `cd context-owl-ui && npm run build && vercel --prod`
4.  Verify rendering on X and Facebook.

------------------------------------------------------------------------

## Acceptance Criteria

-   [x] Image is 1200×630px
-   [x] Readable at Twitter card preview size
-   [ ] Hosted at public URL (Vercel static)
-   [ ] URL added to og:image and twitter:image meta tags
-   [ ] Title & description updated to final launch copy
-   [ ] Favicon updated to gt-logo.png
-   [ ] Verified rendering on X and Facebook

------------------------------------------------------------------------

## Out of Scope

-   Animated preview
-   Multiple image variants per platform
-   Text overlay on image
