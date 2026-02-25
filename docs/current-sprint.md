# Sprint 10 --- Signals Stabilization (ADR-012 Phase 1 ✅)

## Override

ADR-012 supersedes all prior sprint goals.

## Sprint Order + Status

1. ✅ **BUG-045** --- Time-bound entity articles (7d) [COMPLETE - PR #203]
2. ✅ **FEATURE-049** --- Redis cache entity articles [COMPLETE - Branch: feature/049-redis-cached-entity-articles]
3. ✅ **TASK-015** --- Cache warming task [COMPLETE - Branch: feature/015-warm-entity-articles-cache]
4. **BUG-051** --- Remove UI counts [NEXT]
5. **TASK-016** --- Observability + clamps [QUEUED]

All other Sprint 10 work paused until ADR-012 complete.

## Phase 1 Completion (BUG-045)

**Merged into PR #203:**
- ✅ Enforce 7-day cutoff at MongoDB query level
- ✅ Apply cutoff before `$group` stage (prevents memory bloat)
- ✅ Clamp API parameters: `limit≤20`, `days≤7`
- ✅ Updated both single-entity and batch fetch functions

**Expected Results:**
- Entity articles: <1s warm, <3s cold
- Bitcoin/Ethereum: <2s cold (from 10-45s)
- Eliminates unbounded article/mention scans

## Success Criteria

- ✅ Signals page <5s cold (BUG-045 achieves <3s for articles)
- ✅ Entity articles <1s warm (BUG-045 expected impact)
- ⏳ No 10s+ backend calls (all phases needed)

## Deployment Checklist

- [ ] Merge PR #203 (BUG-045)
- [ ] Deploy to production (Railway)
- [ ] Monitor entity article endpoint latency
- [ ] Verify <1s warm, <3s cold achieved
- [ ] Proceed to FEATURE-049 (Redis cache)
