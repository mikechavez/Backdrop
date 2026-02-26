---
ticket_id: TASK-017
title: Substack Profile Setup
priority: HIGH
severity: MEDIUM
status: DONE
date_created: 2026-02-25
date_completed: 2026-02-25
branch: N/A (manual)
effort_estimate: 1-2 hours
---

# TASK-017: Substack Profile Setup

## Problem Statement

Substack profile is currently under the default handle `mikechavez2` with no branding. Before launch, the profile needs a name, banner image, and polished identity so that incoming traffic from X/LinkedIn/Reddit/HN lands on something that looks intentional and credible.

---

## Task

1. ✅ **Name the Substack** — "Early Signal"
2. ✅ **Change handle** — `@earlysignalx` (earlysignal was taken)
3. ✅ **Banner image** — editorial/intelligence brief aesthetic, uploaded to profile
4. ✅ **Profile description** — tagline, introduction, and about page written
5. ✅ **Review settings** — all settings configured

---

## Decisions Made

### Publication Identity
- **Name:** Early Signal
- **Handle:** @earlysignalx
- **URL:** earlysignalx.substack.com
- **Tagline:** On AI, systems, markets, and the signals that matter.

### Copy — Final Versions

**Publication short description (tagline):**
> On AI, systems, markets, and the signals that matter.

**Introduction (2-3 sentence field):**
> Early Signal is where I write about building at the frontier: AI systems in production, markets, and the mental models behind both. I'm Mike Chavez, a product manager and builder. I write from inside the space, not the sidelines.

**About page:**
> Early Signal
> On AI, systems, markets, and the signals that matter.
>
> I'm Mike Chavez, a product manager, builder, and the person behind Backdrop, a crypto narrative intelligence platform that processes hundreds of news articles daily to detect market narratives in real time.
>
> I try to show up early to things. This is where I write about what I find.

### Naming Process
- Explored multiple directions: niche publication brand vs. personal platform
- Key filters: timeless, signals frontier positioning, topic-agnostic, recruiter-friendly
- Finalists: Uncharted, Forward Deployed, Early Signal, The Vanguard, Off Consensus, Already There, At the Frontier
- Selected "Early Signal" — aligns with Backdrop (signal extraction), scales beyond AI, not trend-locked
- Original tagline "the discipline of understanding" replaced with "the signals that matter" (less vague, ties to publication name)

### Visual Branding (v2 — Editorial Direction)
- **v1 rejected** — neon waves/grid/dots aesthetic was too "AI dashboard SaaS," not editorial
- **v2 adopted** — editorial/intelligence brief direction based on external feedback
- **Design system:** Deep charcoal background, Instrument Serif for name, GeistMono for labels, muted amber accent, single signal dot motif
- **No waves, no glow, no gradients** — typography is the brand
- **Assets created:**
  - `v2-logo-512.png` / `v2-logo-256.png` — typographic wordmark with amber dot
  - `v2-logo-mark-512.png` — minimal dot mark for small contexts
  - `v2-banner-1200x400.png` — "AI · Systems · Markets" (selected)
  - `v2-banner-alt-1200x400.png` — "Clarity Before Consensus" (alternate, not used)
  - `v2-cover-800.png` — welcome page cover
  - `v2-email-banner-1100x220.png` — newsletter email header
  - `v2-og-1200x630.png` — OG image draft (head start for TASK-004)

### Settings Configured
- ✅ Publication logo → uploaded
- ✅ Cover/welcome page photo → uploaded
- ✅ Email banner → uploaded
- ✅ Profile banner → uploaded (Settings → Edit Profile → Theme)
- ✅ Accent color → `C4A060` (muted amber, replaced default orange)
- ✅ Post titles → Serif
- ✅ Thumbnails → Center (replaced Smart crop)
- ✅ Categories → Technology (primary), Business/Finance (secondary)
- ✅ Subscribe prompts → ON
- ✅ Show approximate subscriber count → OFF
- ✅ Allow listing on Substack.com → ON
- ✅ Block AI training → OFF (left discoverable — content is about AI)

---

## Remaining Work

- [ ] **Subscribe flow end-to-end test** — deferred. Got "Something went wrong" error, likely due to testing while logged in. Needs incognito test with different email.

---

## Verification

- [x] Publication has a named identity (not default)
- [x] Handle updated from `mikechavez2`
- [x] Banner image uploaded and displaying correctly
- [x] Profile description written with real name included
- [ ] Subscribe flow tested end-to-end (deferred)

---

## Acceptance Criteria

- [x] Handle is memorable and discoverable
- [x] Substack profile looks polished and intentional to a first-time visitor
- [x] Visual branding is consistent with editorial/intelligence brief aesthetic
- [x] Real name is visible somewhere in the profile

---

## Impact

First impressions for every reader who clicks through from social distribution. A default-looking profile undermines the credibility of the content.

---

## Related Tickets

- TASK-005: Final Polish Substack Draft
- FEATURE-046: Email Capture / Substack Embed
- TASK-001: Replace Placeholder URLs + Add OG/Twitter Meta
- TASK-004: Create OG Image / Social Card (OG draft already created as part of this ticket)

---

## Notes

- Handle `@earlysignal` was taken; `@earlysignalx` chosen as alternative (x adds frontier/edge feel)
- FEATURE-046 embed URL confirmed: `https://earlysignalx.substack.com/embed`
- v1 assets (neon wave aesthetic) scrapped after external feedback — "competent but interchangeable"
- v2 assets (editorial/intelligence brief) adopted — matches writing tone and anti-hype positioning
- OG image draft (`v2-og-1200x630.png`) created as byproduct — gives TASK-004 a head start
- All default Substack boilerplate on about page has been replaced with custom copy