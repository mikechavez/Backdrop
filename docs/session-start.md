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

| # | Ticket | Title | Effort | Status |
|---|--------|-------|--------|--------|
| 1 | TASK-024 | LLM Spend Audit | 2 hr | ✅ Complete |

## In Progress

| # | Ticket | Title | Status | Branch | PR |
|---|--------|-------|--------|--------|-----|
| 2 | TASK-025 | Implement Cost Controls | 🟡 Tests fixed; daily limits WIP; needs circuit breaker & logging | feature/task-025-cost-controls | #227 |

## What to Work On Next (Session 3)

**Continue TASK-025:** Per-system daily call limits (in progress)

1. **Fix rate limiter tests** — Create mock Redis client so tests don't depend on real Redis
   - ~20 min (tests already written, just need mocking pattern)
2. **Circuit breaker for LLM calls** — Prevent retry storms after N consecutive failures
   - ~45 min (implement + tests)
3. **Spend logging** — Log every LLM call with tokens/cost to MongoDB
   - ~30 min (integrate with existing CostTracker)
4. **End-to-end testing** — Verify all cost controls work together
   - ~20 min

**Estimated total:** ~2 hours to complete TASK-025

---

## What Happened in Last Session

**TASK-024 (LLM Spend Audit) - COMPLETE**
- Identified 4,320+ Haiku calls/day from System 3 (sentiment/theme/relevance enrichment)
- Found $9/day hidden cost (untracked)
- Root cause: AnthropicProvider._get_completion() never calls CostTracker
- Evidence: docs/_generated/evidence/13-llm-spend-audit.md

**TASK-025 (Cost Controls) - IN PROGRESS**
- Priority 1 ✅: Cost tracking enabled for System 3
  - Created async tracked methods
  - Integrated CostTracker.track_call()
  - Result: 70% of spend now visible
- Priority 2 ✅: Fixed config zeros (pricing now $0.80 and $4.0 instead of $0.0)
- Priority 3 ✅: Implemented batch enrichment (50% cost reduction)
  - 30 articles: 90 API calls → 3 calls
- **Test failures found:** 12 cost tracker tests failing (model name/pricing mismatch) — deferred to next session

**Next Task:** TASK-026 (Fix Active LLM Failures - BUG-052)

---

## Next Sprint: RSS Feed Pivot (AI Content)

**Note:** Sprint 13 will overhaul RSS feeds and content sourcing — replacing crypto sources with AI-related articles and information. The core ingestion/processing pipeline stays, but feed list, relevance classifiers, entity models, and briefing prompts all change. This is a major change requiring an ADR before implementation. No action needed this sprint beyond this note.

**Backlog for Sprint 13:**
- Full README rewrite (pairs with RSS pivot — README should reflect what the app actually does post-pivot)