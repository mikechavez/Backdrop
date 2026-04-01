---
created: 2026-02-25
project: Backdrop (Context Owl)
sprint_number: 11
status: in-progress
---

# Sprint 11 --- 48-Hour Launch: Substack + Interactive Site + Distribution

**Status:** In Progress **Previous Sprint:** Sprint 10 Complete
**Duration:** 2026-02-25 to 2026-02-27

------------------------------------------------------------------------

## Sprint Order

  -------------------------------------------------------------------------
  #     Ticket             Title                Status             Est
  ----- ------------------ -------------------- ------------------ --------
  6     TASK-004           Create OG Image /    ✅ COMPLETE        1 hr
                           Social Card + Final
                           Meta Copy + Favicon

  7     TASK-005           Final Polish         ✅ COMPLETE        1.5 hr
                           Substack Draft

  8     TASK-019           Make Substack CTAs   ✅ COMPLETE        0.5 hr
                           More Visible

  9     TASK-020           LinkedIn             ✅ DRAFT COMPLETE  0.5 hr
                           Distribution Post    (needs publish)

  10    TASK-021           Instagram Story      🔲 OPEN            0.25 hr
                           (Friends/Family)

  11    TASK-022           Facebook             🔲 OPEN            0.25 hr
                           Distribution Post

  12    TASK-023           LinkedIn Video Post   ✅ LINKEDIN POSTED  2 hr
                           + X Distribution      (X draft ready)
                           (Three Walls)

  13    TASK-006/007       X / Reddit / HN      🔲 OPEN            TBD
                           Distribution

  14    FEATURE-050           Add Google Analytics  ✅ COMPLETE        0.5 hr
                           (GA4) to Backdrop

  15    BUG-052              All LLM Systems      🔲 OPEN            TBD
                           Non-Functional         (ticket created)
  -------------------------------------------------------------------------

------------------------------------------------------------------------

## Key Decisions

-   **TASK-004** --- ✅ COMPLETE (2026-02-26). Final launch copy locked
    and deployed. All assets live on https://backdropxyz.vercel.app.
    Facebook rendering verified. X preview awaiting cache refresh.

-   **TASK-005** --- ✅ COMPLETE (2026-02-26). Editorial pass
    complete (revised-4). Final Substack draft assembled with pull-quotes
    and image placements. Published to Substack. Vercel redeployed with
    live Substack URLs.

    **Post-publish completion (2026-02-26):**
    - [x] Published to Substack (live: https://open.substack.com/pub/earlysignalx/p/ai-lets-you-build-faster-than-you)
    - [x] Grabbed live Substack URL → replaced 5x YOUR_SUBSTACK_URL_HERE in story.html
    - [x] Redeployed story.html to Vercel
    - [ ] Distribution posts live (X, LinkedIn, Reddit, HN) — in progress

-   **TASK-019** --- ✅ COMPLETE (2026-02-26). Reader feedback: both
    interactive companion CTAs were invisible when skimming. Bolded and
    cleaned up copy for both top and bottom CTAs in Substack editor.

-   **TASK-020** --- ✅ DRAFT COMPLETE (2026-02-26). LinkedIn post
    drafted. Professional/authoritative tone. Leads with database
    credentials hook, introduces "cognitive debt" concept, includes
    concrete metrics. Final copy approved by Mike. Needs publishing +
    link in first comment.

    **Final post copy:**
    - Hook: database credentials to public GitHub repo
    - Concept: cognitive debt (vs technical debt)
    - Metrics: $100→$10 costs, 67%→90% accuracy
    - CTA: link in comments to Substack article
    - Hashtags: #AI #SoftwareEngineering #BuildInPublic #LLMs

-   **TASK-023** --- ✅ LINKEDIN POSTED (2026-02-28). New thought leadership
    content separate from Substack distribution. Video clip from Lenny's Podcast
    (Jeetu Patel, Cisco President) on three AI deployment constraints + Mike's
    fourth wall (workforce gap). Positions Mike as practical voice in the
    Shumer/Citrini AI doom conversation.

    **Pipeline:** yt-dlp download → CapCut (1.15x speed, 9:16 vertical) →
    Whisper base model (subtitle regen) → CapCut (burn-in captions, MP4 export)

    **LinkedIn performance insight:** No-link teaser posts (2,700 impressions)
    outperform link posts (326) by 8x. Video post follows this pattern.

    **X/Twitter adaptation:** Draft ready, pending final hook refinement and publish.
    Targeting broader AI/tech builder audience beyond crypto. Riding viral
    Shumer (85M views) / Citrini (22M views) AI doom conversation wave.

-   **FEATURE-050** --- ✅ COMPLETE (2026-03-02). Add Google Analytics (GA4) to both
    the React SPA and static Vercel site (story.html). Implemented GA4 hook with
    React Router integration, proper TypeScript types, and graceful fallback when
    env var missing. Measurement ID: G-BLF9ZG7TBV. Frontend builds clean.

-   **BUG-052** --- 🔲 OPEN (2026-03-11). All LLM-dependent systems non-functional:
    briefing generation, entity extraction, sentiment analysis. Previous credits issue
    (resolved 2026-02-27) is ruled out. Ticket created with layered investigation guide
    covering API key validation, model deprecation checks, client code paths, and
    infrastructure. Assigned to Claude Code for investigation and fix.
    **Ticket:** `bug-052-llm-systems-down.md`

------------------------------------------------------------------------

## Remaining Work (prioritized)

**✅ BRIEFING GENERATION RESTORED:** Credits added to Anthropic account on 2026-02-27.
- BUG-050: Endpoint error handling improved to surface API errors clearly
- Briefing generation tested & working: evening briefing successfully generated
- BUG-051: Auto-detect briefing type based on time of day (in progress)

1. **BUG-052** — 🚨 All LLM systems down — investigate and fix (ticket created, assigned to Claude Code)
2. **FEATURE-050** — ✅ Add Google Analytics (GA4) to React SPA + story.html (code complete, pending Vercel deploy)
3. **BUG-051** — Auto-detect briefing type based on time of day (code ready, testing)
3. **TASK-020** — Publish LinkedIn post + link in first comment
4. **TASK-023** — Post X/Twitter adaptation of Three Walls video post
5. **TASK-021** — Draft + post Instagram story (friends/family support)
6. **TASK-022** — Draft + post Facebook distribution post
7. **TASK-006/007** — X / Reddit / HN distribution posts (Substack article)

------------------------------------------------------------------------

## Success Metrics

### Minimum Success

-   [x] Interactive page deployed and functional
-   [x] OG cards rendering correctly (Facebook verified, X awaiting cache refresh)
-   [x] Favicon rendering correctly in browser tab
-   [x] Article editorial pass complete
-   [x] Interactive companion linked from article (top + bottom)
-   [x] Pull-quotes and images placed in final Substack draft
-   [x] Article published on Substack
-   [x] story.html placeholders replaced with live URL (5 locations)
-   [x] Redeployed story.html to Vercel
-   [x] Substack CTAs made more visible (TASK-019)
-   [x] LinkedIn post drafted (TASK-020)
-   [ ] LinkedIn post published
-   [x] LinkedIn video post published (TASK-023 — Three Walls / workforce gap)
-   [ ] X post published (TASK-023 — Three Walls adaptation)
-   [ ] Instagram story posted (TASK-021)
-   [ ] Facebook post published (TASK-022)
-   [ ] X / Reddit / HN distribution posts live (TASK-006/007)
-   [x] Google Analytics live on React SPA + story.html (FEATURE-050 code complete)