---
id: FEATURE-052
type: feature
status: backlog
priority: medium
complexity: medium
created: 2026-03-31
updated: 2026-03-31
---

# FEATURE-052: Eval Framework & Baselines

## Problem/Opportunity

There's no systematic way to measure whether Backdrop's LLM outputs are good. Briefing quality, entity extraction accuracy, and sentiment accuracy are assessed by vibes, not data. NeMo's eval framework provides built-in dataset-based evaluation, scoring, and reporting — establishing baselines that let us measure the impact of any optimization.

## Proposed Solution

Define eval datasets for each LLM system, run NeMo eval commands to establish baseline scores, and create a repeatable eval pipeline that can be run before and after changes.

## User Story

As a developer, I want baseline quality scores for every LLM system so that I can make optimization decisions (cheaper models, lower temperatures) with confidence that quality is maintained.

## Acceptance Criteria

- [ ] Eval datasets defined for each system:
  - Briefing generation: sample inputs with human-judged quality scores
  - Entity extraction: sample articles with known-correct entity lists
  - Sentiment analysis: sample articles with known-correct sentiment scores
- [ ] NeMo eval pipeline runs end-to-end for all three systems
- [ ] Baseline scores generated and stored
- [ ] Eval results documented in `docs/_generated/evidence/15-eval-baselines.md`
- [ ] Pipeline is repeatable (can re-run after changes to measure impact)

## Dependencies

- FEATURE-051: NeMo Setup & Workflow Instrumentation (NeMo must be installed and configured)
- TASK-029: NeMo Research & Integration Plan (defines eval approach)

## Open Questions

- [ ] How many eval samples are needed per system for meaningful baselines?
- [ ] What scoring metrics are appropriate for briefing quality? (factual accuracy, coherence, completeness?)
- [ ] Can we use existing production data to seed eval datasets or do we need to hand-curate?

## Implementation Notes
<!-- Fill in during development -->

## Completion Summary
<!-- Fill in after completion -->
- Actual complexity:
- Key decisions made:
- Deviations from plan: