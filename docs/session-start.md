# Sprint 12 — Backdrop Stability & Production-Grade Monitoring

**Status:** Not Started
**Started:**
**Target:** Open-ended (until stable)

---

## Sprint Goal

_Get Backdrop continuously operational and affordable, then integrate NVIDIA NeMo Agent Toolkit for production-grade observability and optimization._

---

## Sprint Order

| # | Ticket | Title | Status | Est |
|---|--------|-------|--------|-----|
| | | **--- PHASE 1: Triage & Stabilize ---** | | |
| 1 | TASK-024 | LLM Spend Audit | 🔲 COMPLETE | 2 hr |
| 2 | TASK-025 | Implement Cost Controls | 🔲 OPEN | 3 hr |
| 3 | TASK-026 | Fix Active LLM Failures (BUG-052) | 🔲 OPEN | 3 hr |
| 4 | TASK-027 | Health Check & Site Status | 🔲 OPEN | 2 hr |
| 5 | TASK-028 | Burn-in Validation (72hr) | 🔲 OPEN | 1 hr |
| | | **--- PHASE 2: NeMo Agent Toolkit ---** | | |
| 6 | TASK-029 | NeMo Research & Integration Plan | 🔲 OPEN | 2 hr |
| 7 | FEATURE-051 | NeMo Setup & Workflow Instrumentation | 🔲 OPEN | 4 hr |
| 8 | FEATURE-052 | Eval Framework & Baselines | 🔲 OPEN | 3 hr |
| 9 | FEATURE-053 | Optimization & Cost Dashboards | 🔲 OPEN | 4 hr |

---

## Success Criteria

### Phase 1: Stable & Affordable
- [ ] Root cause of LLM spend identified and documented in `_generated/evidence/13-llm-spend-audit.md`
- [ ] Per-system cost controls in place (daily limits, circuit breakers)
- [ ] All three LLM systems operational (briefing generation, entity extraction, sentiment analysis)
- [ ] No silent failures — all LLM errors logged with context
- [ ] `/health` endpoint live, frontend status indicator working
- [ ] System runs 72 hours without intervention
- [ ] Daily LLM spend under $X (define after audit)

### Phase 2: Production-Grade Monitoring
- [ ] NeMo Agent Toolkit integrated and capturing telemetry
- [ ] OpenTelemetry tracing on all three LLM workflows
- [ ] Eval baselines established (briefing quality, entity accuracy, sentiment accuracy)
- [ ] Hyperparameter optimization run (model selection, temperature, max_tokens)
- [ ] Cost dashboard live via telemetry
- [ ] Cost reduced vs. Phase 1 baseline with quality scores maintained

---

## Key Decisions

_Decisions made during the sprint that affect scope, priority, or approach._

---

## Discovered Work

- **TASK-030: Rename GitHub Repo & Update Public-Facing Metadata** — 15 min, manual (GitHub UI). Pre-sprint housekeeping before TASK-024. Repo name still shows legacy name; employers hitting GitHub links from resume/LinkedIn see the wrong project name. Full README rewrite deferred to Sprint 13 backlog.

---

## Completed

_Move tickets here as they finish._

---

## Next Sprint: RSS Feed Pivot (AI Content)

**Note:** Sprint 13 will overhaul RSS feeds and content sourcing — replacing crypto sources with AI-related articles and information. The core ingestion/processing pipeline stays, but feed list, relevance classifiers, entity models, and briefing prompts all change. This is a major change requiring an ADR before implementation. No action needed this sprint beyond this note.

**Backlog for Sprint 13:**
- Full README rewrite (pairs with RSS pivot — README should reflect what the app actually does post-pivot)