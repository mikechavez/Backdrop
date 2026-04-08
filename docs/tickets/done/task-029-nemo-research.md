---
ticket_id: TASK-029
title: NeMo Research & Integration Plan
priority: medium
severity: low
status: OPEN
date_created: 2026-03-31
branch:
effort_estimate: 2 hr
---

# TASK-029: NeMo Research & Integration Plan

## Problem Statement

NVIDIA NeMo Agent Toolkit offers production-grade observability, eval frameworks, and hyperparameter optimization that would replace the ad-hoc cost controls from Phase 1 with a proper system. Before integrating, we need to understand how NeMo maps to Backdrop's architecture and which features to adopt first.

---

## Task

### 1. Compatibility Assessment
- Review NeMo Agent Toolkit documentation and requirements
- Assess compatibility with Backdrop's stack: FastAPI, Celery workers, httpx-based Anthropic calls, MongoDB, Redis
- Identify any framework adapters needed (NeMo supports LangChain, Google ADK, CrewAI, custom — Backdrop is custom)
- Flag any Python version, dependency, or infrastructure conflicts

### 2. Architecture Mapping
- Map Backdrop's three LLM systems to NeMo's agent/workflow model:
  - Briefing generation (multi-step: article selection → prompt assembly → LLM call → quality check → save)
  - Entity extraction (single-step per article: content → LLM call → parse entities)
  - Sentiment analysis (single-step per article: content → LLM call → parse sentiment)
- Define how each maps to NeMo's YAML configuration (agents, tools, workflows)
- Identify what NeMo calls "tools" in Backdrop's context (Anthropic API, MongoDB reads/writes, Redis cache)

### 3. Feature Prioritization
Recommend adoption order based on value and effort:
- **Telemetry/Observability** (OpenTelemetry tracing, token usage, cost tracking)
- **Eval framework** (dataset-based evaluation, scoring, baseline reports)
- **Hyperparameter optimizer** (model selection, temperature, max_tokens tuning)
- **Caching/acceleration** (intelligent request routing, result caching)

### 4. Integration Plan Document
Write integration plan to `docs/_generated/system/80-nemo-integration-plan.md`:
- **Compatibility findings** (go/no-go with any required workarounds)
- **Architecture mapping** (how Backdrop systems map to NeMo concepts)
- **Adoption phases** (which features first, what order, estimated effort per feature)
- **Risk assessment** (what could go wrong, rollback strategy)

---

## Verification

- [ ] Compatibility confirmed or blockers identified with workarounds
- [ ] All three LLM systems mapped to NeMo's model
- [ ] Integration plan written to `docs/_generated/system/80-nemo-integration-plan.md`

---

## Acceptance Criteria

- [ ] Compatibility assessment complete (go/no-go)
- [ ] Architecture mapping covers all three LLM systems
- [ ] Feature adoption order recommended with rationale
- [ ] Integration plan document written and actionable
- [ ] Risk assessment includes rollback strategy

---

## Impact

Defines the roadmap for FEATURE-051, FEATURE-052, and FEATURE-053. If compatibility issues are found, this is where we catch them before investing implementation time.

---

## Related Tickets

- TASK-028: Burn-in Validation (must pass before starting this)
- FEATURE-051: NeMo Setup & Workflow Instrumentation (depends on this plan)
- FEATURE-052: Eval Framework & Baselines (depends on this plan)
- FEATURE-053: Optimization & Cost Dashboards (depends on this plan)