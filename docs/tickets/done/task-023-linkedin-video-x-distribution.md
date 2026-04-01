---
ticket_id: TASK-023
title: LinkedIn Video Post + X Distribution (Three Walls / Jeetu Patel)
priority: HIGH
severity: N/A
status: IN PROGRESS
date_created: 2026-02-28
branch: N/A
effort_estimate: 2 hr
---

# TASK-023: LinkedIn Video Post + X Distribution (Three Walls / Jeetu Patel)

## Problem Statement

Need to create and distribute original thought leadership content beyond the Substack article. Leveraging a clip from Lenny's Podcast (Jeetu Patel, Cisco President) discussing three constraints on AI deployment, with Mike adding a fourth constraint (workforce gap) to position as a practical voice in the AI transition conversation.

---

## Task

### LinkedIn Video Post
1. ✅ Extract video clip from Lenny's Podcast (YouTube timestamp 16:00-17:25)
2. ✅ Speed up clip to 1.15x in CapCut
3. ✅ Regenerate Whisper subtitles for sped-up clip (`--model base --word_timestamps True --max_words_per_line 6`)
4. ✅ Burn in captions and export as MP4 from CapCut
5. ✅ Write LinkedIn post copy — "Three Walls" framing + Mike's fourth wall (workforce gap)
6. ✅ Publish LinkedIn post with video (9:16 vertical format)

### X/Twitter Distribution
7. ✅ Adapt copy for X audience — shorter, punchier, contrarian angle
8. 🔲 Finalize X post copy (draft ready, refining hook)
9. 🔲 Post video + copy to X

---

## Verification

- [x] Video clip plays correctly with burned-in subtitles
- [x] LinkedIn post published with video
- [ ] X post published with video
- [ ] Monitor engagement metrics (impressions, comments, profile visits)

---

## Acceptance Criteria

- [x] LinkedIn post live with video clip and written copy
- [ ] X post live with adapted copy and video clip
- [ ] Both posts position Mike as practical/experienced voice on AI deployment constraints

---

## Impact

Thought leadership content that rides the viral Shumer/Citrini AI doom conversation while positioning Mike in a third lane: not doom, not dismissal, but practical constraints + workforce readiness. Implicit CTA for consulting/advisory work.

---

## Key Artifacts

- **Video clip (MP4):** `/Users/mc/Documents/content-clips/final-cut.mp4`
- **SRT captions:** `/Users/mc/Documents/content-clips/finalcut.srt`
- **Whisper venv:** `~/whisper-env`
- **Source:** Lenny's Podcast w/ Jeetu Patel (Cisco President)

### LinkedIn Post (Published)
Everyone's talking about what AI can do.

Nobody's talking about what challenges companies face in the great AI transition.

Jeetu Patel (Cisco's President) laid out three constraints that every employee and every company needs to overcome to win:

1. We're running out of power, compute, and bandwidth
2. People don't trust these systems yet
3. We've nearly exhausted public human-generated training data

I'd add a fourth: the workforce gap.

Every company, everywhere, needs to retrain their people to work alongside these systems. The tech is moving faster than the talent.

That's the wall nobody's building a plan for yet.

### X Post (Draft — Refining)
Everyone's debating whether AI will take your job. Almost nobody's asking what's stopping companies from deploying it. Cisco's President breaks down 3 constraints. I'd add a 4th: the workforce gap. Models get better every week. Who's training the people using them?

---

## LinkedIn Performance Context (from this session)

- Teaser post (no link): 2,700 impressions — best performer
- Article post (native LinkedIn article): 404 impressions
- Link post (Substack URL): 326 impressions
- Takeaway: No outbound links + failure-led hooks + on-platform content wins

---

## Related Tickets

- TASK-020: LinkedIn Distribution Post (Substack article — separate content)
- TASK-006/007: X / Reddit / HN Distribution