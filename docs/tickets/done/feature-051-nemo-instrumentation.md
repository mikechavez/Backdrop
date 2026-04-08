---
id: FEATURE-051
type: feature
status: backlog
priority: medium
complexity: high
created: 2026-03-31
updated: 2026-03-31
---

# FEATURE-051: NeMo Setup & Workflow Instrumentation

## Problem/Opportunity

Phase 1 cost controls are functional but ad-hoc. NeMo Agent Toolkit provides production-grade telemetry with OpenTelemetry tracing, token usage tracking, and execution path visibility across all LLM workflows. This replaces hand-rolled logging with a proper observability layer and demonstrates real production quality control to prospective employers.

## Proposed Solution

Install NeMo Agent Toolkit, configure YAML workflow definitions for Backdrop's three LLM systems, and add OpenTelemetry tracing to all LLM call paths. Export telemetry to a compatible backend (Phoenix, Langfuse, or similar).

## User Story

As a developer/operator, I want full execution visibility into every LLM workflow so that I can debug failures, track costs, and optimize performance from a single dashboard.

## Acceptance Criteria

- [ ] NeMo Agent Toolkit installed and initialized
- [ ] YAML workflow configs defined for briefing generation, entity extraction, and sentiment analysis
- [ ] OpenTelemetry tracing captures every LLM call with: model, tokens in/out, latency, success/failure
- [ ] Telemetry exported to at least one backend (Phoenix, Langfuse, or OTel-compatible)
- [ ] Existing Phase 1 cost controls and error handling remain functional (no regressions)
- [ ] All new code has tests confirming telemetry is captured and exported

## Dependencies

- TASK-029: NeMo Research & Integration Plan (defines architecture mapping and YAML structure)
- TASK-028: Burn-in Validation (Phase 1 must be stable before layering NeMo)

## Open Questions

- [ ] Which telemetry backend is best suited? (TASK-029 will research)
- [ ] Does NeMo's tracing conflict with existing httpx-based API calls? (TASK-029 will assess)
- [ ] Can NeMo coexist with the existing `OptimizedAnthropicLLM` client or does it need to wrap/replace it?

## Implementation Notes
<!-- Fill in during development -->

## Completion Summary
<!-- Fill in after completion -->
- Actual complexity:
- Key decisions made:
- Deviations from plan: