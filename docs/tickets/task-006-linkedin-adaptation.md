---
id: TASK-006
type: task
status: backlog
priority: medium
created: 2026-02-23
updated: 2026-02-23
---

# Adapt Article for LinkedIn (Native Article)

## Objective
Create a LinkedIn-native version of the Substack article. Not a copy-paste — a rewrite optimized for LinkedIn's professional audience and algorithmic preferences.

## Context
LinkedIn heavily penalizes external links and rewards native content. A LinkedIn Article (published via LinkedIn's built-in editor) gets significantly more distribution than a post with a Substack link. Mike's audience on LinkedIn skews toward PMs, engineers, and tech leaders — the framing should match.

## Tool Routing
- Tool: Claude Web
- Model: N/A

## Execution Steps

### 1. Reframe for LinkedIn audience
- Less crypto-specific, more "building production software with AI"
- Emphasize PM/leadership lessons: managing AI tools, cost governance, quality control
- Position Mike as an experienced builder, not a crypto trader
- Professional but not corporate — keep the personality

### 2. Structural changes
- Shorter than Substack version (aim for 1,200–1,500 words vs ~4,000+)
- Front-load the credentials leak story (it's universally compelling)
- Cut or compress the crypto-specific sections
- Expand the "cognitive debt" concept (resonates with any technical leader)
- Add a "What I'd tell my PM self" framing

### 3. LinkedIn-specific formatting
- Short paragraphs (2–3 sentences max — LinkedIn renders poorly with long blocks)
- Use line breaks aggressively
- No markdown headers — LinkedIn doesn't render them in Articles the same way
- Bold key phrases sparingly

### 4. CTA optimization
- Link to interactive site (not Substack)
- "Try the simulator" is more engaging than "read my article"
- Invite comments: "What's your experience building with AI agents?"

## Files Involved
- Input: `Full_Draft_-_revised-3.md`
- Output: New file — `linkedin-article.md`

## Acceptance Criteria
- [ ] Standalone article that makes sense without reading the Substack
- [ ] 1,200–1,500 words
- [ ] Professional tone, not corporate
- [ ] Interactive site linked
- [ ] No crypto jargon that would lose a general tech audience
- [ ] Reads well on LinkedIn's Article renderer

## Dependencies
- TASK-005 (Substack draft finalized first)

## Out of Scope
- LinkedIn post (short-form) — that's in TASK-008
- LinkedIn profile optimization
- LinkedIn ads
