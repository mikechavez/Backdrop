---
sprint_number: 11
project: Backdrop (Context Owl)
status: in-progress
created: 2026-02-25
---

# Sprint 11 — 48-Hour Launch: Substack + Interactive Site + Distribution

**Status:** In Progress
**Previous Sprint:** ✅ Sprint 10 Complete (ADR-012 Signals Recovery + Deployment)
**Duration:** 2026-02-25 to 2026-02-27
**Deadline:** Hard launch window — content is time-sensitive
**Launch:** 9:00 AM EST, target date TBD within window

---

## Completed (Pre-Sprint)

- ✅ BUG-029 — Anthropic API credits exhausted (fixed)
- ✅ TASK-013 — Production URLs (no longer relevant, Railway deployment handled in Sprint 10)
- ✅ ADR-012 — Signals Recovery complete, deployed to Railway 2026-02-25

---

## Sprint Order

### Phase 1: Pre-Launch

| # | Ticket | Title | Status | Est |
|---|--------|-------|--------|-----|
| ~~1~~ | ~~FEATURE-045~~ | ~~Add Share Mechanics to Interactive Site~~ | CANCELED | — |
| 1 | FEATURE-046 | Email Capture page w/ Substack Embed | ✅ DONE | 1 hr |
| 2 | TASK-017 | Substack Profile Setup | ✅ DONE | 1–2 hrs |
| 3 | TASK-014 | Pre-launch Security Hardening | OPEN | 1 hr |
| 4 | TASK-003 | Deploy Interactive Site to backdropxyz.vercel.app | ✅ DONE | 30 min–1 hr |
| 4.5 | TASK-018 | Add Story Page Integration (Navigation & Links) | ✅ DONE (committed, ready to deploy) | 30 min |
| 5 | TASK-002 | Mobile/Desktop QA (on live site) | OPEN | 1 hr |
| 6 | TASK-004 | Create OG Image / Social Card | OPEN | 1 hr |
| 7 | TASK-005 | Final Polish Substack Draft | OPEN | 1–2 hrs |
| 8 | TASK-006 | Adapt Article for LinkedIn | OPEN | 1 hr |
| 9 | TASK-007 | Adapt Article for X | OPEN | 1 hr |
| 10 | TASK-008 | Write All Launch Distribution Copy | OPEN | 1–2 hrs |

### Phase 2: Launch

| # | Ticket | Title | Status | Est |
|---|--------|-------|--------|-----|
| 11 | TASK-009 | Warm-Up Phase (T-36 to T-24) | OPEN | 1 hr (spread) |
| 12 | TASK-001 | Wire Substack URLs + Redeploy (launch morning) | OPEN | 30 min |
| 13 | TASK-010 | Launch Day Execution (9am EST publish → distribute) | OPEN | Ongoing 48 hrs |

---

## Background / Ongoing

- **ADR-012 Post-Deployment Monitoring** — runs throughout sprint
  - [ ] Cache hit rates for entity articles
  - [ ] Response latency (signals page, trending, entity articles)
  - [ ] Parameter clamp frequency
  - [ ] Log duplication incidents
  - [ ] Close ADR-012 epic once metrics confirmed stable

- **Deferred verification:** Substack subscribe flow end-to-end test (got error during TASK-017, needs incognito retest)

---

## Key Decisions

- **TASK-001 moved to launch morning** — requires published Substack URL. Publish → grab URL → wire into interactive site → redeploy → blast distribution.
- **FEATURE-046** — ✅ Done. Substack iframe embed with styled fallback button. Dark theme rendering to be verified post-deploy.
- **TASK-017** — ✅ Done. Full editorial branding applied. See details below.
- **TASK-004** — OG image draft already exists (`v2-og-1200x630.png`) from TASK-017 visual work. May only need refinement.
- **TASK-003 before TASK-002** — deploy first, then QA on live site.
- **TASK-018** — ✅ Complete & Committed. Files synced, built, and committed to repo. Story→app: amber back-nav, inline links, pre-footer CTA. App→story: amber nav pill "✦ See It Break" + StoryBanner on Briefing page with "I had code. I didn't have a system." copy + "The fastest way to master agentic AI is to learn exactly where it breaks. This is that lesson." subtext. Substack URL fixed: earlysignalx.substack.com. **Pending:** Deploy via `vercel --prod`.

### Substack Identity (from TASK-017)
- **Publication name:** Early Signal
- **Handle:** @earlysignalx (earlysignalx.substack.com)
- **Tagline:** On AI, systems, markets, and the signals that matter.
- **Embed URL:** https://earlysignalx.substack.com/embed
- **Visual direction:** Editorial/intelligence brief — deep charcoal, Instrument Serif, muted amber accent, signal dot motif
- **Categories:** Technology (primary), Business/Finance (secondary)
- **AI training:** Not blocked (wants discoverability)
- **All assets uploaded:** logo, cover, email banner, profile banner
- **Website editor:** accent color C4A060, serif titles, center crop

---

## Parallel Work Strategy

**Claude Code** handles TASK-014 → TASK-003 → TASK-002 (dev work)
- **Next Claude Code action:** Deploy TASK-018 via `vercel --prod` from context-owl-ui directory. Then proceed to TASK-002 QA.

**Claude Web / separate sessions** handle in parallel:
- TASK-004: OG image (draft exists, needs refinement)
- TASK-005 → TASK-008: All content polish, adaptation, and launch copy

All Phase 1 work converges → Phase 2 launch.

---

## Success Metrics

### Minimum Success
- [ ] Interactive page deployed and functional
- [x] Substack published with polished profile
- [ ] Main tweet + thread posted
- [ ] OG cards rendering correctly

### Full Success
- [ ] All of the above, plus:
- [ ] LinkedIn native article published
- [ ] X article or thread published
- [ ] Reddit + HN submitted
- [ ] Email capture working on interactive site

### Stretch Success
- [ ] 48-hour sustain phase executed
- [ ] Meaningful engagement metrics (shares, subscribers)

---

## Backlog (Not in Sprint)

These items remain available for future sprints:

- **TASK-011:** Audit allowDiskUse across non-signals code
- **TASK-012:** MongoDB index optimization
- **FEATURE-040:** Complete system documentation
- **FEATURE-041b:** Contradiction resolution
- **FEATURE-042:** Archive navigation

---

## Notes

- This sprint has a hard deadline — no deferring tickets
- The interactive site is the viral hook — lead with it, not the Substack link
- LinkedIn and X get native content, not just links to Substack
- Mike is publishing for the first time on Substack, LinkedIn articles, and possibly X articles
- Sprint 10 archived to `/docs/sprints/sprint-010-ui-polish-stability.md`
- Railway deployment successful on 2026-02-25
- TASK-017 visual branding went through two iterations: v1 (neon/wave) scrapped after feedback, v2 (editorial) adopted