# Decision 001 — BugOps v1 Scope

**Status:** Accepted
**Date:** 2026-05-08

## Decision

Sprint 018 will build the thinnest end-to-end BugOps signal path while preserving seams for future signal sources.

BugOps v1 is a deterministic runtime reliability harness. It is not an autonomous bug fixer. LLM synthesis, Q&A, ticket drafting, and remediation are deferred.

## Consequences

- First live signal source is `llm_traces` cost-runaway detection.
- Railway logs are inspected in a spike but not fully ingested.
- Alert-to-case behavior is exact `dedupe_key` passthrough, not a correlation engine.
- Slack is outbound webhook only.
- Case lifecycle is manual-only.
- Multi-source case correlation begins after at least two real signal sources exist.

## Rationale

This reduces scope while preventing `llm_traces` assumptions from hard-coding the BugOps architecture. It also avoids speculative correlation logic before real multi-source event overlap exists.
