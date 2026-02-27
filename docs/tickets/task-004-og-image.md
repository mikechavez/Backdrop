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
-   **Status**: ✅ COMPLETE - All assets deployed to production

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

## Completed Steps (2026-02-26)

1. ✅ Updated story.html meta tags with final launch copy
2. ✅ Added favicon `gt-logo.png` to all pages (index.html + story.html)
3. ✅ Built and deployed to Vercel production
4. ✅ Verified Facebook rendering (working)
5. ✅ X validator confirms meta tags correctly deployed (awaiting cache refresh)
6. ✅ Capitalized "Agentic AI" in Briefing page case study section

------------------------------------------------------------------------

## Acceptance Criteria

-   [x] Image is 1200×630px
-   [x] Readable at Twitter card preview size
-   [x] Hosted at public URL (Vercel static)
-   [x] URL added to og:image and twitter:image meta tags
-   [x] Title & description updated to final launch copy
-   [x] Favicon updated to gt-logo.png (all pages)
-   [x] Verified rendering on X and Facebook (X cache pending refresh)

------------------------------------------------------------------------

## Out of Scope

-   Animated preview
-   Multiple image variants per platform
-   Text overlay on image
