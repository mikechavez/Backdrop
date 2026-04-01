---
id: TASK-008
type: task
status: backlog
priority: high
created: 2026-02-23
updated: 2026-02-23
---

# Write All Launch Distribution Copy

## Objective
Write every piece of launch copy needed for distribution across X, LinkedIn, Reddit, and Hacker News. All copy ready to paste on launch day.

## Context
Distribution is the make-or-break for this launch. The content is strong — what matters now is how it's packaged for each platform. Each platform has a different audience, tone, and algorithmic preference. Copy must be tailored, not cross-posted.

## Tool Routing
- Tool: Claude Web
- Model: N/A

## What to Write

### X/Twitter (7 pieces)
1. **Main tweet** — Links to interactive site (NOT Substack). Hook + "try it" CTA.
2. **Long thread** (5–7 tweets) — Story arc: failure → insight → system. Links to Substack.
3. **Quote-tweet draft #1** — First pull-quote (for T+1 hour self-QT)
4. **Quote-tweet draft #2** — Metric angle (for T+90 min self-QT)
5. **Quote-tweet draft #3** — "Cognitive debt" concept (for T+3 hours)
6. **5 standalone tweet variations** — Different hooks:
   - Technical angle (for dev Twitter)
   - Narrative/story angle (for general audience)
   - Hiring/PM angle (for recruiters/hiring managers)
   - Contrarian angle ("AI isn't replacing developers")
   - Data angle (specific metrics from the build)
7. **1 cryptic teaser tweet** — For T-36 warm-up (no links, just intrigue)

### LinkedIn (1 piece)
1. **LinkedIn post** — Short-form post (not the Article from TASK-006). Professional angle: "Here's what 6 months of AI-assisted development actually taught me." Links to interactive site.

### Reddit (3 pieces)
1. **r/ClaudeAI** — Focus on Claude Code workflow, what broke, what worked. Humble, detailed.
2. **r/ChatGPTPro or r/artificial** — Multi-model comparison angle, cognitive debt concept.
3. **r/SideProject** — Solo dev building a production app with AI. Journey angle.

### Hacker News (2 pieces)
1. **Title** — Understated, factual. HN penalizes clickbait. Example: "Six months building a production app with AI coding agents"
2. **First comment** — 2–3 paragraphs of context. What you built, what you learned, what's in the interactive companion.

## Angle Matrix
| Platform | Primary Hook | Tone | Links To |
|----------|-------------|------|----------|
| X (main tweet) | Interactive sim | Confident, direct | Interactive site |
| X (thread) | Story arc | Narrative | Substack |
| LinkedIn (post) | Professional lessons | Authoritative | Interactive site |
| Reddit | What broke | Humble, detailed | Both |
| HN | Case study framing | Understated | Substack |

## Acceptance Criteria
- [ ] All 15+ pieces of copy written
- [ ] Each platform's voice is distinct and native
- [ ] Interactive site link in main tweet (not Substack)
- [ ] Substack link in thread and HN
- [ ] No AI-slop phrasing anywhere
- [ ] All copy ready to paste with no editing needed
- [ ] Teaser tweet is intriguing without giving everything away

## Dependencies
- TASK-005 (final headline decided — copy references it)

## Out of Scope
- Scheduling tools setup
- DM templates for outreach (covered in TASK-009)
- Livestream script
