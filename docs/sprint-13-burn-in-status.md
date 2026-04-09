# Sprint 13 Burn-in Status

**Task:** TASK-041 — Attribution Burn-in (48hr) + Findings Doc

## Burn-in Period

**Start Time:** 2026-04-08 20:00 UTC (when deployed to Railway)
**End Time:** 2026-04-10 20:00 UTC (48 hours later)
**Status:** 🔄 IN PROGRESS

## Pre-Burn-in Verification

- ✅ All Sprint 13 code merged to main
- ✅ Deployed to Railway
- ✅ $6 Anthropic credits added
- ✅ llm_traces collection ready (0 records, awaiting first pipeline run)
- ✅ briefing_drafts collection ready
- ✅ api_costs collection ready

## What's Being Measured

1. **Cost by operation**: Which operation costs the most?
   - `briefing_generate`, `briefing_critique`, `briefing_refine`
   - `entity_extraction`, `narrative_extraction`, `narrative_summary`, etc.
   - `health_check` (should be near-zero)

2. **Cost by model**: Are we mostly using Sonnet or Haiku?
   - `claude-sonnet-4-5-20250929`
   - `claude-haiku-4-5-20251001`

3. **Refine loop behavior**: How many iterations per briefing?
   - 0 iterations (no refine)
   - 1 iteration (needed refinement)
   - 2 iterations (max, needs further work)

4. **Error rate**: Any operations failing?
   - Per-operation error counts and rates

5. **Daily spend**: Are we meeting the $0.33/day target?
   - Total spend over 48 hours
   - Daily average (divide by 2)

## Analysis Plan

After 48 hours:
1. Run `poetry run python scripts/analyze_burn_in.py`
2. Review cost breakdown
3. Write `docs/sprint-13-burn-in-findings.md` with:
   - Cost by operation (table)
   - Cost by model (table)
   - Refine loop statistics
   - Error rates
   - **Decision section**: What should Sprint 14 optimize?

## Expected Findings

Based on code review, hypotheses are:
- `briefing_refine` is likely the top cost driver (Sonnet reprocessing)
- Refine loop should iterate 0-2 times per briefing
- Health check should be negligible (<0.1% of cost)
- Daily spend should be $0.60-1.50 (on high-volume days)

**Data will confirm or refute these guesses.**

## Next Steps

1. Let system run for 48 hours with no intervention
2. Monitor Sentry for errors (should see none)
3. Check UptimeRobot health endpoint (should be "healthy" or "degraded")
4. After 48hr: Run analysis script, write findings, make decision
5. Proceed to Sprint 14 with data-driven optimization

---

**Do not proceed to Sprint 14 until this analysis is complete.**
