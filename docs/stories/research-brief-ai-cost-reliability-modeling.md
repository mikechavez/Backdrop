# RESEARCH BRIEF: AI Cost, Reliability, and Model Optimization in Backdrop

## EXECUTIVE SUMMARY

Four distinct candidate stories emerge from repository evidence:

1. **COST-01: Making AI Pipeline Economically Viable (Tier 1 Cost Optimization)**
   - **Story hypothesis:** Initial pipeline enriched all articles (tier 1-3) with LLM calls, causing ~$1.80/day spend. Tier 1 filtering reduced to ~$0.36-0.45/day.
   - **Interview value:** HIGH — Product judgment, prioritization, cost-driven design change
   - **Evidence:** TASK-060 (tier classification), TASK-063 (model swap), commit 76f912c
   - **Timeline:** ~2026-04-09 to 2026-04-10 (rapid implementation)

2. **COST-02: Retry Storm and Budget Exhaustion Prevention**
   - **Story hypothesis:** After pipeline restart, backlog triggered 400+ wasted LLM calls from retry loops on deterministic validation failures, exhausting $10-15 monthly budget in 2 hours.
   - **Interview value:** VERY HIGH — Operational crisis, root cause analysis, systematic fix
   - **Evidence:** BUG-057 (retry storm), BUG-056 (spend cap enforcement), commit 20e5e28
   - **Timeline:** 2026-04-02 to 2026-04-03 (incident + fix)

3. **COST-03: Cost Observability and Guardrails**
   - **Story hypothesis:** System had cost tracking but no enforcement gate. Implemented two-tier spend limits ($0.25 soft, $0.33 hard) + backlog throttle to prevent budget blowouts.
   - **Interview value:** HIGH — Responsible AI, observability, operational safety
   - **Evidence:** TASK-024 (audit), TASK-025 (cost controls), BUG-056 (spend cap)
   - **Timeline:** 2026-03-31 to 2026-04-01 (audit + implementation)

4. **COST-04: Model Routing and Tier Classification**
   - **Story hypothesis:** Implemented observable model routing (MD5 bucketing) + tiered operation classification (Tier 1-3) to enable A/B testing cheaper models (Flash, DeepSeek) while maintaining quality gates.
   - **Interview value:** MEDIUM-HIGH — Model selection, quality/cost tradeoff, technical architecture
   - **Evidence:** Sprint 016 (model tiering, observable routing), TASK-076 (routing strategy)
   - **Timeline:** 2026-04-27 to 2026-05-03 (Sprint 016 deliverables)

---

## EVIDENCE MATRIX

| Story ID | Claim | Evidence Type | Source Path / Commit | Confidence | Needs Confirmation |
|---|---|---|---|---|---|
| COST-01a | Initial pipeline enriched all articles (tier 1-3) | Strong inference | `docs/tickets/done/task-060-tier-1-enrichment-filter.md` line 17-25 | HIGH | How was this discovered? Who noticed tier 2 articles had no value? |
| COST-01b | ~$1.80/day spend before filter | Direct evidence | TASK-060 problem statement line 18 | HIGH | Is $1.80/day actual observed cost or calculated estimate? |
| COST-01c | ~$0.36-0.45/day after filter (98% reduction candidate) | Direct evidence | TASK-060 line 27, "Cost impact: $0.36-0.45/day" | MEDIUM | Post-deployment verification of actual reduction? |
| COST-01d | Tier 1 filtering applied via rss_fetcher.py logic | Direct evidence | TASK-060 implementation spec (lines 104-120) | HIGH | When deployed to production? Any rollback? |
| COST-01e | Model swap: Sonnet → Haiku primary | Direct evidence | TASK-063 implementation (lines 42-46) | HIGH | Quality regression testing on briefings? |
| COST-02a | Retry storm occurred post-pipeline-restart | Direct evidence | BUG-057 problem statement, Sentry errors 2026-04-02 | HIGH | Exact trigger: restart on 2026-04-02, backlog size? |
| COST-02b | 400+ wasted API calls from retries | Strong inference | BUG-057 scenario: 100 articles × 4 retries = 400 calls | MEDIUM | Actual Sentry trace count? |
| COST-02c | Validation failures were deterministic (not transient) | Direct evidence | BUG-057 root cause analysis | HIGH | Confirmed via actual LLM outputs? |
| COST-02d | Fixed by: 1) zero-retry on validation, 2) degraded fallback | Direct evidence | Commit 20e5e28, `_build_degraded_narrative()` | HIGH | When deployed? Did pipeline resume successfully after? |
| COST-02e | Cost reduction: 4 retries → 1-2 calls per article | Direct evidence | BUG-057 commit message | HIGH | Post-fix cost per article? |
| COST-03a | Cost tracking implemented but no enforcement gate | Direct evidence | TASK-024 problem statement, BUG-056 line 34-39 | HIGH | How was this gap discovered? Timeline? |
| COST-03b | Two-tier spend limits: $0.25 soft, $0.33 hard | Direct evidence | BUG-056 config.py changes (lines 85-87) | HIGH | Why these specific numbers? Rationale? |
| COST-03c | Backlog throttle: max 5 articles per cycle | Direct evidence | BUG-056 implementation (line 90) | HIGH | Tuned via simulation or trial-and-error? |
| COST-03d | Backfill retry storm burned $10-15 in 2 hours | Direct evidence | BUG-056 problem statement line 20-22 | MEDIUM | Exact Anthropic billing receipt? Or inferred from call counts? |
| COST-04a | Model routing observable (MD5 bucketing) | Direct evidence | Sprint 016 notes, TASK-076 implementation | HIGH | Determinism verified? Same routing_key → same variant? |
| COST-04b | Classified all 14 operations into Tier 1-3 | Direct evidence | Sprint 016, TASK-079 (operation-tiers.md) | HIGH | Tier 1 = high volume + deterministic + low failure cost? |
| COST-04c | Tier 1 Flash evals on 3 operations | Direct evidence | Sprint 016, FEATURE-053 (Tier 1 Flash Evaluations) | HIGH | Quality regression threshold >5% = halt? |
| COST-04d | Rejected Flash models based on quality (not cost alone) | Direct evidence | Sprint 016 MSD-001/002/003 decision records | HIGH | Any pressure to adopt Flash despite regression? How was it decided? |

---

## TIMELINE

### Phase 0: Initial Architecture (Pre-2026-04)
- **State:** All articles (tier 1-3) enriched with LLM calls (entity extraction, sentiment, themes, narratives)
- **Cost baseline:** ~$1.80/day (~$54/month), exceeding acceptable budget
- **Observability:** Cost tracking via `cost_tracker.py` but no enforcement gate

### Phase 1: Crisis Detection & Audit (2026-03-31 to 2026-04-01)
- **2026-03-31:** TASK-024 (LLM Spend Audit) triggered
  - Mapped 16 LLM call sites, identified 3 systems
  - Found System 3 (enrichment) 100% untracked (~4,320 calls/day)
  - Estimated monthly cost: $300-500 with 70-80% invisible
- **2026-04-01:** TASK-025 (Cost Controls) implemented in 4 stages
  - Stage 1: Rate limiting per system
  - Stage 2: Circuit breaker for failure recovery
  - Stage 3: Spend logging aggregation
  - Stage 4: End-to-end testing (42 tests, all passing)

### Phase 2: Spend Gate & Throttle (2026-04-02 to 2026-04-03)
- **2026-04-02:** BUG-056 triggered (spend cap enforcement)
  - **Initial event:** Pipeline restarted with backlog of unenriched articles
  - **Result:** Burned $10-15 credits in ~2 hours (entire monthly budget)
  - **Root cause:** No budget gate; backlog concentration
- **2026-04-02 20:29-21:00:** Sentry alerts
  - "Credit balance too low"
  - "Circuit breaker OPEN for theme_extraction/sentiment_analysis"
- **2026-04-02 evening:** BUG-056 implementation begins
  - Config: `LLM_DAILY_SOFT_LIMIT=$0.25`, `LLM_DAILY_HARD_LIMIT=$0.33`
  - Backlog throttle: `ENRICHMENT_MAX_ARTICLES_PER_CYCLE=5`
  - Budget cache with 30s TTL (no per-call DB reads)
  - Commit: 9d63412 (code), e4d16b3 (tests, 32/33 passing)

### Phase 3: Cost-Driven Design Optimization (2026-04-09 to 2026-04-10)
- **2026-04-09:** TASK-060 (Tier 1 Only Enrichment Filter)
  - Findings: 56% of articles are tier 2-3 (low signal), 218 tier 2 have no narrative despite enrichment
  - Decision: Skip LLM enrichment for tier 2-3, keep rule-based classification (free)
  - Implementation: Modify `rss_fetcher.py` enrichment loop
  - **Expected cost reduction:** $1.80/day → $0.36-0.45/day (80% reduction)
  - Commit: 76f912c
- **2026-04-10:** TASK-063 (Model Swap: Sonnet → Haiku)
  - Briefing generation switched from Sonnet ($5/$15 per 1M tokens) to Haiku ($1/$5)
  - **Expected cost per briefing:** $0.05 → $0.005 (90% reduction)
  - NameError fix: `DEFAULT_MODEL` → `BRIEFING_PRIMARY_MODEL`
  - Effort: 15 minutes, Commit in `cost-optimization/tier-1-only` branch

### Phase 4: Retry Storm Crisis (2026-04-02 to 2026-04-03) — CONCURRENT with Phase 2
- **2026-04-02:** Post-restart backlog encountered
- **Issue:** `discover_narrative_from_article()` retried validation failures up to 4 times
  - Validation failures are deterministic (bad JSON, hallucinated entities)
  - Retrying same prompt = same failure, wasted API calls
  - 100 articles × 4 retries = 400 wasted calls
- **Root cause:** No distinction between transient (429, 529) and deterministic failures
- **2026-04-03:** BUG-057 implemented (Commit 20e5e28)
  - Zero-retry on validation failures (return degraded fallback instead)
  - New `_build_degraded_narrative()` function (status="degraded")
  - Per-article LLM call cap: 2 max (1 primary + 1 transient retry)
  - Tier 2/3 auto-fixes: nucleus salience auto-fix, empty actors backfill
  - Degraded rate tracking: "X articles, Y succeeded, Z degraded (%%)"
  - Downstream degraded filtering in `detect_narratives()`
  - **Impact:** 4 retries → 1-2 calls per article (80% reduction)
  - Tests: 12 comprehensive tests added, all passing

### Phase 5: Model Routing & Observable Tiering (2026-04-27 to 2026-05-03) — Sprint 016
- **Sprint 016 deliverables:**
  - BUG-090: Eliminated silent model override, introduced `RoutingStrategy` class
  - TASK-076: Deterministic A/B bucketing via MD5 hash
  - TASK-077: GeminiProvider stub (factory pattern)
  - TASK-078: Model Selection Rubric (5-axis decision framework)
  - TASK-079: Classify all 14 operations into Tiers 1-3
  - FEATURE-053: Tier 1 Flash Evaluations (3 operations: entity_extraction, sentiment_analysis, theme_extraction)
  - All 14 operations now routed via `_OPERATION_ROUTING` dict with explicit primary + variant
  - **Quality regression threshold:** >5% = halt eval (all 3 Tier 1 ops flagged >5%)

### Phase 6: Determinism & Validation (2026-05-10) — Sprint 019
- **Sprint 019 outcomes:**
  - BUG-099: Prevent invalid briefings publishing (4 pre-deploy invalid, 0 post-deploy)
  - FEATURE-060: Trusted summary eligibility filter (fresh_start_cutoff)
  - FEATURE-061: Display mode API fields (summary vs article_cluster)
  - FEATURE-062: Deterministic article-cluster fallback (no LLM)
  - BUG-100: Ground briefing refinement with source context
  - TASK-096: Post-deploy verification (BUG-099 containment verified)
  - TASK-097: MongoDB query skill (reduces verification friction)

---

## STORY DOSSIER: COST-01 (Making AI Pipeline Economically Viable)

### Candidate Title
"Reducing LLM costs by 80%: Tiered classification and model selection"

### One-Sentence Summary
Reduced enrichment pipeline cost from ~$1.80/day to ~$0.36-0.45/day by applying tier-based classification (enrichment only for high-signal tier 1 articles) and switching briefing generation from Sonnet to Haiku.

### Situation (Initial State)
- **Pipeline architecture:** All articles (1,385 daily ingestion) enriched with LLM calls regardless of signal value
- **Enrichment scope:** Entity extraction, sentiment analysis, theme extraction, narrative discovery (3-5 LLM calls per article)
- **Cost:** ~$1.80/day (~$54/month), exceeding target of $0.50/day
- **Quality gap:** 56% of articles are tier 2-3 (low signal), but still fully enriched
  - 218 tier 2 articles had no narrative despite enrichment (direct waste evidence)
  - 298 tier 2 articles are text stubs (<200 combined chars, low information density)
  - Tier 2 avg to tier 1 ratio is only 17-22% (low signal-to-article ratio)

### Trigger / Detection
- TASK-024 (LLM Spend Audit) revealed 16 call sites across 3 systems
- System 3 (enrichment: sentiment, theme, relevance) was 100% untracked (~4,320 calls/day)
- Estimated spend: $300-500/month with 70-80% invisible to monitoring
- **Product realization:** Optimizing call volume is more tractable than negotiating lower per-token costs

### Root Cause
Two distinct causes:
1. **No tier-based filtering:** All articles enriched equally, regardless of signal value
2. **Expensive primary model:** Briefing generation used Sonnet ($5/$15 per 1M tokens) when Haiku suffices

### Options Considered
**Option A: Reduce article ingestion volume**
- Skip certain news sources
- Increase minimum article quality threshold
- *Rejected:* Information loss; missed stories

**Option B: Reduce LLM operations per article (selective enrichment)**
- Skip entity extraction for low-confidence articles
- Skip narrative discovery for tier 2-3 articles
- Keep rule-based tier classification (free)
- *Selected:* TASK-060 implementation

**Option C: Use cheaper models for tier 2-3 enrichment**
- Keep full enrichment but use Flash for non-critical tiers
- *Not yet explored* (Sprint 016 Flash evals deferred)

**Option D: Batch processing to reduce per-article overhead**
- Combine multiple articles into single LLM calls
- *Partially implemented:* TASK-025 added batch enrichment

**Option E: Caching and deduplication**
- Cache entity extraction results for duplicate articles
- *Implemented:* Content hash + caching in narrative extraction

### Decision Made
**Implement Tier 1 Only enrichment filter + model swap:**
1. Enrichment skips tier 2-3 articles entirely (only rule-based classification)
2. Briefing generation swaps from Sonnet → Haiku (10x cheaper)

**Rationale:**
- High confidence: Tier classification is deterministic (rules-based)
- Low risk: Tier 2-3 articles already have low signal value
- Quick win: Both changes simple to implement (15-45 min each)
- Cost reduction: 80% for enrichment, 90% for briefings

### Implementation Changes

**TASK-060: Tier 1 Enrichment Filter**
- **File modified:** `src/crypto_news_aggregator/background/rss_fetcher.py` (lines 620-750)
- **Logic change:** Add conditional after tier classification
  ```python
  if relevance_tier != 1:
      # Minimal update: tier assignment only, skip enrichment
      await collection.update_one({
          "$set": {
              "relevance_tier": relevance_tier,
              "relevance_reason": relevance_reason,
              "updated_at": datetime.now(),
          }
      })
      continue  # Skip all LLM enrichment for tier 2-3
  # Full enrichment below (only for tier 1)
  ```
- **Commit:** 76f912c
- **Status:** Ready for merge (effort: ~15 min actual)

**TASK-063: Model Swap Sonnet → Haiku**
- **File modified:** `src/crypto_news_aggregator/services/briefing_agent.py` (lines 53-54)
- **Logic change:**
  ```python
  BRIEFING_PRIMARY_MODEL = "claude-haiku-4-5-20251001"  # Swap primary
  BRIEFING_FALLBACK_MODEL = "claude-sonnet-4-5-20250929"  # Keep fallback
  ```
- **Bug fix:** Line 921, change `DEFAULT_MODEL` → `BRIEFING_PRIMARY_MODEL` (NameError)
- **Status:** Complete (effort: 15 minutes)
- **Testing:** Manual smoke test via `/admin/trigger-briefing?is_smoke=true`

### Before/After Behavior

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| **Enrichment cost/day** | ~$1.80 | ~$0.36-0.45 | -80% |
| **LLM calls/day** | ~600 (all articles) | ~120-150 (tier 1 only) | -75-80% |
| **Articles enriched** | 1,385 (100%) | ~350-410 (25-30%, tier 1 only) | -70-75% |
| **Briefing cost** | ~$0.05/briefing | ~$0.005/briefing | -90% |
| **Primary briefing model** | Sonnet | Haiku | 10x cheaper |
| **Tier 2-3 visibility** | Full enrichment | Rule-based tier only | Degraded but acceptable |

### Quality Impact

**Positive:**
- Haiku tested for briefing generation; simpler prompts likely fine
- Rule-based tier classification accurate (no LLM regression risk)

**Negative (Tolerated):**
- Tier 2-3 articles lose enrichment (no entity extraction, sentiment, themes)
- Tier 2-3 articles invisible to narrative detection
- **Mitigation:** Tier 2 articles can still appear in signals/trends via entity mentions if they mention high-value entities

**Verification needed:**
- Did Haiku produce lower-quality briefings? Any user complaints?
- Did tier 2-3 articles create blind spots? Missed stories?

### Reliability Impact
- **Positive:** Reduced API calls → lower failure rate, fewer retry storms
- **Negative:** None observed
- **Verification:** Monitor Sentry error rates pre/post deployment

### Latency Impact
- **Positive:** Fewer enrichment cycles → faster article ingestion
- **Negative:** None
- **Verification:** Article processing time pre/post deployment

### Cost Impact
- **Direct savings:** -80% enrichment, -90% briefing = -$1.50-1.70/day = -$45-50/month
- **Baseline target:** $0.50/day (~$15/month) for entire system
- **Post-optimization:** On track to meet target

### Tests or Verification
- **Unit tests:** None required (logic change is simple conditional)
- **Integration tests:** TASK-060 can add tests for tier filtering
- **Manual smoke test:** 
  - Trigger enrichment batch via Celery
  - Verify tier 2-3 articles skip enrichment
  - Check logs for "enrichment skipped" messages
- **Post-deployment verification:**
  - Query `articles` collection: tier 2-3 should have no `sentiment`, `themes`, `entities`
  - Query `llm_traces` for date range: call count drops to ~120-150/day
  - Monitor Sentry: no regressions in briefing generation

### Tradeoffs
1. **Tier 2-3 enrichment loss:** Acceptable — tier classification captures tier 2 articles for signals, just not deeply analyzed
2. **Haiku quality risk:** Mitigated by keeping Sonnet as fallback; brief testing can validate
3. **Missing narratives:** Tier 2-3 articles won't participate in narrative clustering; acceptable given low signal value

### Known Limitations
1. **Tier classification rules may evolve:** If classification accuracy degrades, optimization becomes less effective
2. **No per-operation selective enrichment yet:** Eventually might want to keep entity extraction but skip narrative discovery for tier 2
3. **Backlog behavior:** When ingestion spikes, queue fills with tier 2-3 articles; throttle (from BUG-056) prevents runaway spend but doesn't prioritize tier 1

### Evidence Sources
- `docs/tickets/done/task-060-tier-1-enrichment-filter.md` (problem statement, data on tier 2 waste)
- `docs/tickets/done/task-063-switch-model-for-briefing-generation.md` (model swap details)
- Commit 76f912c (TASK-060 implementation)
- Commit in `cost-optimization/tier-1-only` branch (TASK-063)

### Facts to Confirm from Memory
1. Was $1.80/day actual observed cost or calculated estimate? What's the exact baseline?
2. When did TASK-060 and TASK-063 deploy to production?
3. Post-deployment, what was the actual cost reduction observed?
4. Did Haiku briefings meet quality standards, or did fallback to Sonnet occur?
5. Were there user-facing regressions or blind spots from tier 2-3 article loss?
6. How was tier 2 article classification validated? Ground truth?
7. Why Tier 1 filtering before exploring cheaper models for tier 2-3?

---

## STORY DOSSIER: COST-02 (Retry Storm and Budget Exhaustion)

### Candidate Title
"When retrying deterministic failures costs more than the initial mistake: The retry storm crisis"

### One-Sentence Summary
A backlog of unenriched articles triggered a retry storm (400+ wasted LLM calls from retrying deterministic validation failures), exhausting the monthly API budget ($10-15) in 2 hours; fixed by recognizing validation failures as deterministic and returning degraded fallbacks instead of retrying.

### Situation (Initial State)
- **Post-BUG-055 restart:** RSS pipeline re-enabled after credit limit exhaustion
- **Backlog state:** 100+ articles awaiting narrative element extraction (`discover_narrative_from_article()`)
- **Retry architecture:** 4 retry attempts on any validation failure
  - Logic: "If LLM output fails validation, retry with stricter prompt"
  - Assumption: Validation failures are transient (rate limits, API overload)
- **No budget gate:** System spending freely; cost tracking was observability-only (TASK-024 audit)

### Trigger / Detection
- **2026-04-02 20:29-21:00 UTC:** Sentry alerts fire
  - "Your credit balance is too low to access the Anthropic API"
  - "Circuit breaker OPEN for 'theme_extraction' after 4 consecutive failures"
  - "Circuit breaker OPEN for 'sentiment_analysis' after 4 consecutive failures"
  - 15+ duplicate alerts within 30 minutes
- **Impact:** All LLM features offline; pipeline stalled
- **Cost damage:** Entire monthly budget ($10-15) burned in ~2 hours

### Root Cause

**Why validation failures occurred:**
- `discover_narrative_from_article()` called LLM to extract narrative elements (nucleus_entity, actors, tensions, implications)
- LLM output sometimes invalid: JSON parse error, hallucinated entities (not in article text), missing required fields
- For example:
  - Article: "Bitcoin hits $80K"
  - LLM: `nucleus_entity="crypto industry"` (not in text) → validation fails
  - Retry with same article/prompt → LLM again: `nucleus_entity="crypto world"` (still not in text) → fails again

**Why retry strategy failed:**
- **Misconception:** Validation failures treated as transient (like rate limits)
- **Reality:** Validation failures are **deterministic for a given input**
  - Same article + same prompt → structurally similar but invalid output every time
  - Retrying doesn't fix hallucination or bad JSON structure
- **Retry cost:** 4 attempts × $0.10/call (Haiku) = $0.40 per article
- **Scale:** 100+ articles in backlog × 4 retries = 400+ wasted calls = $40+ in minutes

**Why it cascaded:**
- Circuit breaker (from TASK-025) recorded each failed retry attempt
- After 4 failures in quick succession → circuit breaker OPEN
- OPEN state blocks ALL LLM calls for that system (theme_extraction, sentiment_analysis)
- Backlog can't progress, cost spirals from retries

**Why no budget gate prevented it:**
- Cost tracking existed (TASK-025 implemented) but was observability-only
- No code checked `CostTracker.get_daily_cost()` before making LLM calls
- All three LLM call paths (`_get_completion()`, `extract_entities_batch()`, `enrich_articles_batch()`) fired without budget check
- Result: Uncontrolled spend until Anthropic denied access

### Options Considered

**Option A: Increase Retry Count**
- Retry 8 times instead of 4; hope for random LLM variance
- *Rejected:* Doesn't fix deterministic failures; burns more credits

**Option B: Change Retry Prompt**
- Add more examples, stricter instructions, different prompt phrasing
- *Rejected:* Prompt changes are slow; doesn't help backlog in crisis

**Option C: Catch Validation Failures as Deterministic**
- Recognize when validation fails: hallucinated entity, bad JSON, missing field
- Return degraded fallback (minimal usable narrative stub) instead of retry
- Only retry on true transient errors (429, 529, timeout)
- *Selected:* BUG-057 implementation
- *Parallel:* BUG-056 (implement budget gate to prevent future crisis)

**Option D: Disable Retry Loop Entirely**
- No retries at all; accept lower quality
- *Rejected:* Loses real retryable errors (rate limits)

### Decision Made
**Implement multi-layered fix:**

1. **Zero-retry on validation failures** (BUG-057)
   - Distinguish between transient errors (429, 529, timeout) and deterministic failures (bad JSON, hallucination)
   - Validation failures → return degraded fallback immediately (no retry)
   - Transient errors → retry up to 2 times with backoff

2. **Degraded fallback design** (BUG-057)
   - Instead of `None` (lost data), return minimal valid narrative with `status="degraded"`
   - Example: `{"nucleus_entity": title.split(":")[0], "actors": [...], "status": "degraded", "degraded_reason": "hallucinated entity"}`
   - Downstream systems filter out `status="degraded"` to avoid polluting briefings
   - Keeps pipeline moving, preserves data for manual review

3. **Per-article LLM call cap** (BUG-057)
   - Belt-and-suspenders: max 2 calls per article (1 primary + 1 transient retry)
   - Even if validation retry logic slipped through, cap enforces limit

4. **Tier 2/3 auto-fixes** (BUG-057)
   - Recognize recoverable validation failures:
     - **Tier 2:** Missing nucleus_entity in actor_salience → auto-fix with default score (5)
     - **Tier 3:** Empty actors list → auto-fix by backfilling from nucleus_entity
   - Reduces degraded rate without LLM calls

5. **Spend gate to prevent future crisis** (BUG-056)
   - Concurrent fix (same incident window)
   - Budget check before every LLM call
   - Two-tier limits: $0.25 soft (degrade non-critical), $0.33 hard (halt all)
   - Details in COST-03 dossier

### Implementation Changes

**BUG-057: Retry Storm Prevention**

**Commit:** 20e5e28 (feat: narrative-retry)
**Tests:** Commit 54631ac (test: 12 comprehensive tests, all passing)

**File modified:** `src/crypto_news_aggregator/services/narrative_themes.py`

**Change 1: Validation auto-fixes (Tier 2-3)**
- Line 92-103: Auto-fix empty actors by backfilling from nucleus_entity
- Line 139-147: Auto-fix missing nucleus salience with default 5
- Result: Fewer rejections, more pass-through on first try

**Change 2: New degraded fallback function**
- New `_build_degraded_narrative()` (lines 609-655)
- Returns: `{"nucleus_entity": fallback, "actors": [...], "status": "degraded", "degraded_reason": reason}`
- Enables pipeline continuity without losing data

**Change 3: Zero-retry on validation failures**
- Line 881-918: Replace retry-on-validation logic with immediate degraded fallback
- Validation failure now returns `_build_degraded_narrative()` immediately (no retry)
- Entity hallucination detected → degraded, no retry
- Reduced `max_retries` from 4 to 2 (transient errors only)

**Change 4: Per-article LLM call cap**
- Line 849-861: Add `llm_calls_made` counter
- Cap at `MAX_LLM_CALLS_PER_ARTICLE = 2`
- If cap exceeded → degraded fallback

**Change 5: Degraded rate tracking**
- Line 1263-1278: Count degraded narratives per backfill batch
- Log: "X articles, Y succeeded, Z degraded (%%)"
- Metric to monitor: If degraded% > 25%, prompt needs audit

**Change 6: Downstream degraded filtering**
- File `src/crypto_news_aggregator/services/narrative_service.py`
- Modified `detect_narratives()` to exclude `status="degraded"` narratives from clustering
- Prevents degraded stubs from polluting briefing inputs

### Before/After Behavior

| Behavior | Before | After | Change |
|----------|--------|-------|--------|
| **Validation failure handling** | Retry 4 times | Return degraded, no retry | Deterministic failure recognition |
| **Per-article LLM calls** | Unbounded (up to 4+) | Max 2 | Cost capped per article |
| **Wasted calls on backlog** | 100 articles × 4 retries = 400+ | 100 articles × 1-2 calls = 100-200 | 50-75% reduction |
| **Article cost** | ~$0.40 (4 calls) | ~$0.05-0.10 (1-2 calls) | 75-80% reduction |
| **Pipeline behavior** | Stalls on circuit breaker trip | Continues via degraded fallback | Resilience improved |
| **Data loss on failure** | Yes (returns None) | No (degraded stub preserved) | Observability improved |

### Quality Impact

**Positive:**
- Degraded rate tracking provides insight into failure patterns
- Downstream filtering prevents polluted narrative inputs
- Pipeline continues operating (doesn't stall)

**Negative (Tolerated):**
- Degraded narratives have synthetic nucleus_entity (from article title)
- Degraded narratives excluded from briefing synthesis
- ~5-10% of articles may become degraded on first run

**Verification needed:**
- Post-fix degradation rate? Expected <10% with auto-fixes
- Did downstream filtering prevent quality issues?
- Pipeline resume: how long to clear backlog after fix?

### Reliability Impact
- **Positive:** No more retry storm cascades; circuit breaker trips are graceful
- **Positive:** Reduced retry-induced load on Anthropic API (fewer repeated failures)
- **Negative:** None significant

### Latency Impact
- **Positive:** No retry delays; immediate degraded fallback
- **Negative:** None

### Cost Impact
- **Direct savings:** Eliminates 400+ wasted retry calls per crisis = ~$40-50 per incident
- **Per-article savings:** $0.40 → $0.05-0.10 (75-80% reduction)
- **Backlog clearance:** 200-article backlog now costs $10-20 instead of $80+

### Tests or Verification

**Unit tests (12 added, all passing):**
1. `test_build_degraded_narrative_basic` - Verify structure, status="degraded"
2. `test_validation_failure_returns_degraded_not_retried` - Single LLM call on validation failure
3. `test_entity_hallucination_no_retry` - Hallucination detected, degraded, no retry
4. `test_llm_call_cap_enforced` - Cap limits to 2 calls per article
5. `test_tier2_auto_fix_nucleus_salience` - Nucleus salience auto-fixed to 5
6. `test_tier3_auto_fix_empty_actors` - Empty actors backfilled from nucleus
7. `test_backfill_tracks_degraded_count` - Degraded rate logging
8. `test_detect_narratives_filters_degraded` - Downstream filtering works
9. `test_transient_retry_still_works` - Rate limits still retried
10-12. Additional edge cases and integration tests

**Integration tests:**
- Mock `_get_completion()` to return invalid JSON
- Call `discover_narrative_from_article()`
- Assert: called exactly ONCE (no retries), returns `status="degraded"`
- Verify MongoDB stores degraded narrative with reason

**Post-deployment verification:**
- Trigger narrative enrichment on small batch (5 articles)
- Check logs for "Building degraded narrative" messages
- Query MongoDB: verify `status` field present, degraded count visible
- Monitor Sentry: no more "Max retries exhausted" errors
- Check `llm_traces`: call count ~1-2 per article (not 4+)

### Tradeoffs
1. **Degraded narratives lose semantic accuracy:** Fallback nucleus_entity is heuristic (title.split(":")[0]). Acceptable because: downstream filters them out anyway, and they're only for lost data recovery.
2. **Reduced retry chances:** ~1-5% of LLM outputs might succeed on retry. Acceptable because: most validation failures indicate genuine prompt/model issues, not transient errors.
3. **Maintenance burden on downstream:** Every consumer of narratives must respect `status` field. Low risk at current team size; documented in BUG-057 ticket.

### Known Limitations
1. **No learning loop from degraded rates:** Failures are logged but not systematically analyzed to improve prompts. Future work: prompt audit ticket.
2. **Tier auto-fixes may mask real issues:** If nucleus_entity consistently missing from actor_salience, that's a prompt problem, not an edge case. Monitor degraded% > 25% as signal.
3. **Backlog recovery is slow:** Per-article cost reduction helps, but backlog still takes hours to clear at throttled rates. Future: prioritization or more aggressive throttle tuning.

### Evidence Sources
- `docs/tickets/done/bug-057-narrative-retry-storm.md` (full problem statement, root cause analysis, fix design)
- Commit 20e5e28 (`src/crypto_news_aggregator/services/narrative_themes.py` changes)
- Commit 54631ac (test suite: `tests/services/test_narrative_themes.py`, 12 tests)
- Sentry alerts 2026-04-02 20:29-21:00 (referenced in BUG-056 and BUG-057)

### Facts to Confirm from Memory
1. Exact timeline: When was pipeline restarted on 2026-04-02? What was backlog size?
2. Anthropic billing: $10-15 figure based on actual invoice or calculated from call counts?
3. Retry behavior: Did users or monitoring surface the retry storm, or discovered during debugging?
4. Fix deployment: When was BUG-057 deployed to production? How long for backlog to clear?
5. Quality regression: Did degraded narratives cause visible issues? Manual review burden?
6. Post-fix cost per article: Actual observed after fix deployed?
7. Circuit breaker behavior: Did it actually prevent further damage, or was budget gate (BUG-056) the main win?

---

## STORY DOSSIER: COST-03 (Cost Observability and Guardrails)

### Candidate Title
"Building a budget firewall: Cost observability to enforcement gates"

### One-Sentence Summary
Implemented cost tracking but lacked enforcement, resulting in uncontrolled spend; added two-tier spend limits ($0.25 soft, $0.33 hard), backlog throttle (5 articles/cycle), and budget cache with 30s TTL to prevent future budget blowouts.

### Situation (Initial State)
- **Cost tracking:** TASK-025 implemented cost tracking (logs every LLM call to MongoDB with usage + cost)
- **Cost visibility:** Daily cost aggregation queries working
- **Cost enforcement:** NONE — no code checked budget before making API calls
- **Result:** Spend was transparent (observability) but uncontrolled (no gate)
- **Incident:** BUG-054/055 restart burned $10-15 in 2 hours (TASK-024 audit + TASK-025 controls only added visibility, not enforcement)

### Trigger / Detection
- **2026-03-31:** TASK-024 (LLM Spend Audit) discovered:
  - 16 LLM call sites across 3 systems
  - System 3 (enrichment) 100% untracked
  - Estimated spend: $300-500/month, 70-80% invisible
- **2026-04-02:** BUG-054 restart triggered incident:
  - Backlog of unenriched articles
  - Unthrottled enrichment pipeline
  - Retry storms (BUG-057 concurrent)
  - Result: Entire monthly budget burned in 2 hours
  - Anthropic API denied access: "Credit balance too low"

### Root Cause
Two compounding gaps:
1. **No enforcement:** Cost tracking was observability-only. `CostTracker.get_daily_cost()` existed but was never queried before LLM calls.
2. **No throughput control:** Backlog of unenriched articles flooded enrichment pipeline on restart, concentrating an entire day's budget into minutes.

**Why cost tracking alone wasn't enough:**
- TASK-024 audit correctly identified spend is high
- TASK-025 added cost tracking code (write to DB, aggregation queries)
- But zero places in code checked: "Is daily cost > limit? If so, block this LLM call."
- All three LLM call paths (`_get_completion`, `extract_entities_batch`, `enrich_articles_batch`, `_call_llm`) fired without budget check

**Why backlog amplified crisis:**
- Without throughput control, restart processed 100+ articles simultaneously
- Each article: 3-5 LLM calls (entity, sentiment, themes, narrative, relevance)
- Plus retries: 4 attempts per validation failure (BUG-057)
- Result: 1,000+ API calls in first 15 minutes (after restart)
- Cost: ~$10-15, i.e., entire monthly budget

### Options Considered

**Option A: Just monitor cost in dashboards**
- Show daily spend on admin dashboard; manually halt pipeline if high
- *Rejected:* Manual intervention too slow; crisis already happened before noticing

**Option B: Per-system daily call limits**
- Each system (entity extraction, theme, sentiment) gets daily call budget
- When limit hit, system stops making calls
- *Partially selected:* Implemented as TASK-025 (rate limiting, circuit breaker)
- **Gap:** Doesn't address total spend across all systems hitting daily budget ceiling

**Option C: Two-tier budget enforcement**
- Soft limit ($0.25): Non-critical operations degrade
- Hard limit ($0.33): All operations halt
- *Selected:* BUG-056 implementation
- **Advantage:** Graceful degradation, maintains critical operations (briefing, entity extraction) while blocking non-critical (theme, sentiment)

**Option D: Backlog throttle**
- Cap articles per enrichment cycle to spread cost across day
- *Selected:* BUG-056 implementation, `ENRICHMENT_MAX_ARTICLES_PER_CYCLE=5`
- **Advantage:** Prevents budget concentration; even if no gate, damage is limited

**Option E: Batch all enrichment calls**
- Process articles in single LLM call instead of per-article
- *Partially explored:* TASK-025 added batch methods, but throttle (Option D) still needed

### Decision Made
**Implement two-tier spend limits + backlog throttle:**

1. **Soft limit ($0.25/day):**
   - Non-critical operations blocked (theme extraction, sentiment analysis, narrative enrichment)
   - Critical operations allowed (briefing generation, entity extraction)
   - Graceful degradation: pipeline continues, lower quality

2. **Hard limit ($0.33/day):**
   - ALL operations blocked
   - Emergency stop; credits preserved

3. **Backlog throttle:**
   - Cap articles per enrichment cycle to 5
   - At 10-min cycle intervals: 5 × 6 cycles/hr = 30 articles/hr = 720 articles/day
   - Spread across full day instead of concentrated in first minutes
   - Backlog of 200 articles clears in ~7 hours, not 20 minutes

4. **Budget cache with 30s TTL:**
   - All LLM call sites read from in-memory cache (fast, no DB overhead)
   - Cache refreshed every 30s from DB (debounced, not per-call)
   - Async code paths refresh cache before LLM calls
   - Sync code paths read cached value (zero overhead)
   - **Design:** Avoids sync/async bridge problem; acceptable overshoot window (30s of calls past limit = cents, not dollars)

### Implementation Changes

**BUG-056: LLM Spend Cap Enforcement**

**Commits:** 9d63412 (code), e4d16b3 (tests, 32/33 passing)

**Files modified:**

1. **`src/crypto_news_aggregator/core/config.py`**
   - Add 3 settings:
     ```python
     LLM_DAILY_SOFT_LIMIT: float = 0.25  # Degrade non-critical
     LLM_DAILY_HARD_LIMIT: float = 0.33  # Halt all
     ENRICHMENT_MAX_ARTICLES_PER_CYCLE: int = 5  # Throttle
     ```

2. **`src/crypto_news_aggregator/services/cost_tracker.py`**
   - Module-level `_budget_cache` dict (status, daily_cost, last_checked, TTL)
   - `refresh_budget_cache()` — async, updates cache from DB
   - `is_critical_operation()` — classify operation (briefing + entity = critical)
   - `check_llm_budget(operation)` — sync gate, reads cache, returns (allowed, reason)
   - `refresh_budget_if_stale()` — async helper, no-op if cache fresh

3. **`src/crypto_news_aggregator/llm/anthropic.py`**
   - Add budget check + cache refresh to all LLM methods:
     - `_get_completion()` (sync, reads cache)
     - `_get_completion_with_usage()` (sync, reads cache)
     - `extract_entities_batch()` (sync, reads cache)
     - `enrich_articles_batch()` (async, refreshes cache + reads)
     - `score_relevance_tracked()` (async, refreshes + reads)
     - `analyze_sentiment_tracked()` (async, refreshes + reads)
     - `extract_themes_tracked()` (async, refreshes + reads)
   - Add throttle to `enrich_articles_batch()`: cap at `ENRICHMENT_MAX_ARTICLES_PER_CYCLE`

4. **`src/crypto_news_aggregator/services/briefing_agent.py`**
   - Add budget check to `_call_llm()` before model loop

### Before/After Behavior

| Behavior | Before | After | Change |
|----------|--------|-------|--------|
| **Budget check before LLM call** | None | Yes (reads cache) | Enforcement enabled |
| **Cost observability** | Yes (logs, DB) | Yes (logs, DB, cache) | Enhanced |
| **Spend limit enforcement** | None | Two-tier ($0.25 soft, $0.33 hard) | Gate implemented |
| **Soft limit behavior** | N/A | Critical ops allowed, non-critical blocked | Graceful degradation |
| **Hard limit behavior** | N/A | All ops blocked | Emergency stop |
| **Backlog throttle** | None (unbounded) | 5 articles/cycle | Spread across day |
| **Budget check performance** | N/A | Cache reads (~1 microsecond) | No DB overhead |
| **Cache refresh pattern** | N/A | Async code refreshes if stale (30s TTL) | Debounced DB reads |
| **API call on budget hit** | Proceeds to spend more | Raises LLMError for critical, returns empty for non-critical | Circuit breaker prevents overspend |

### Quality Impact
- **Positive:** Soft limit allows briefings and entities (critical) to continue
- **Negative:** Theme, sentiment, narrative extraction (non-critical) paused when soft limit hit
- **Verification needed:** How long do users tolerate degraded mode?

### Reliability Impact
- **Positive:** Prevents complete budget exhaustion; circuit breaker protects from cascades
- **Positive:** Graceful degradation (some features continue) better than complete halt
- **Negative:** None significant

### Latency Impact
- **Positive:** Cache reads faster than DB queries (~1 microsecond vs ~10ms)
- **Negative:** None

### Cost Impact
- **Direct savings:** Prevents uncontrolled spend, e.g., $10-15 incident now stopped at $0.33/day limit
- **Incident prevention:** Backlog throttle spreads cost; worst-case 1-day limit vs. 2-hour exhaustion
- **Example:** 200-article backlog now max cost $0.33/day × 7 days = $2.31, not $40+ in one burst

### Tests or Verification

**Unit tests (33 added, 32 passing, 1 skipped):**
- TestBudgetCacheState: Cache initialization, TTL (2 tests)
- TestCriticalOperationClassification: Briefing/entity critical, theme/sentiment non-critical (6 tests)
- TestCheckLLMBudget: Hard/soft limits, stale cache, fail-open (7 tests)
- TestRefreshBudgetCache: State transitions, DB error handling (5 tests)
- TestRefreshBudgetIfStale: Cache freshness, refresh timing (2 tests)
- TestBacklogThrottle: ENRICHMENT_MAX_ARTICLES_PER_CYCLE enforcement (2 tests)
- TestCostCalculation: Haiku/Sonnet/Opus pricing, rounding (4 tests)
- TestBudgetGateIntegration: End-to-end soft/hard limits (2 tests)
- TestBudgetLimitConstants: Verify $0.25/$0.33 limits (3 tests)

**Integration tests:**
- Insert cost records, call `refresh_budget_cache()`, verify state
- Call `check_llm_budget()` with costs at soft, hard, above hard
- Call `_get_completion()`, verify LLMError on hard limit
- Call `enrich_articles_batch()` with 50 articles, cap=5, verify 5 processed
- Verify critical ops proceed at soft limit, non-critical blocked

**Deployment verification (production):**
- Set env: `LLM_DAILY_SOFT_LIMIT=0.25`, `LLM_DAILY_HARD_LIMIT=0.33`, `ENRICHMENT_MAX_ARTICLES_PER_CYCLE=5`
- Add $5 credits
- Trigger `/admin/trigger-fetch` (manual fetch)
- Monitor `db.api_costs` → spend stays within limits
- Check logs for "throttle" messages and "spend limit" warnings
- Verify no unhandled exceptions (spend limits are graceful)

### Tradeoffs
1. **Budget check is per-process, not shared:** Multiple workers could overshoot. Acceptable at single-worker scale; future: Redis atomic counter.
2. **30s TTL cache means overshoot window:** Up to 30s of LLM calls after true daily cost crosses threshold. Worst-case: ~$0.02 overshoot (acceptable).
3. **Operation classification is stringly typed:** Typo in operation name silently misclassifies as non-critical (low risk, solo developer).
4. **Soft/hard limits are configurable but not dynamic:** Changes require env var + redeploy. Low friction for testing.
5. **Throttle is FIFO, not priority-ordered:** Articles processed in insertion order, not by relevance. Low priority improvement.

### Known Limitations
1. **Budget check is not atomic across multiple processes:** Cache is per-process. If system scales to multiple workers, migrate to shared Redis counter.
2. **No intra-cycle rate limiting:** Backlog throttle caps per-cycle but not calls-per-second within cycle. If throughput increases, might want token-bucket limiter.
3. **No cost prediction/forecasting:** System reacts to spend but doesn't predict if current day will exceed limit. Future: extrapolate spend based on time-of-day trend.
4. **Backlog recovery is slow:** Even with throttle, 200-article backlog takes ~7 hours to clear at 5 articles/10min. Acceptable for monthly budgets, might frustrate daily operations.

### Evidence Sources
- `docs/tickets/done/task-024-llm-spend-audit.md` (audit findings, discovered gap)
- `docs/tickets/done/task-025-cost-controls.md` (rate limiting, circuit breaker, cost tracking implementation)
- `docs/tickets/done/bug-056-llm-spend-cap-enforcement.md` (spend gate + throttle design, cost calculations)
- Commit 9d63412 (config + cost_tracker + anthropic + briefing_agent changes)
- Commit e4d16b3 (test suite, 32/33 tests passing)
- Sentry alerts 2026-04-02 20:29-21:00 (incident trigger)

### Facts to Confirm from Memory
1. Soft/hard limit values ($0.25/$0.33): How were these numbers chosen? Calculation? Negotiation?
2. Throttle value (5 articles/cycle): Was this tuned via simulation or trial-and-error? Any issues in production?
3. Soft limit classification: Why is entity extraction critical but theme/sentiment non-critical? User impact difference?
4. Budget cache TTL (30s): Why 30s specifically? Tested with different values?
5. Deployment outcome: Post-deploy, how often did soft/hard limits trigger? Any false positives?
6. User communication: Were users told about soft limit degradation (theme/sentiment paused)?
7. Incident response: Once this deployed, did similar budget crises occur?

---

## STORY DOSSIER: COST-04 (Model Routing and Tier Classification)

### [ABBREVIATED — See Evidence Matrix for full details]

### Candidate Title
"Making model decisions observable and testable: Tiered operations and Flash evaluations"

### One-Sentence Summary
Implemented observable model routing (deterministic MD5 bucketing), classified all 14 LLM operations into tiers (Tier 1-3 based on volume/failure cost/quality requirements), and evaluated Flash models on Tier 1 operations with quality regression thresholds (>5% = halt adoption).

### Key Evidence Points
- **Sprint 016 deliverables:**
  - BUG-090: Eliminated silent model override → explicit `RoutingStrategy` class
  - TASK-076: MD5 deterministic bucketing for A/B testing
  - TASK-077: GeminiProvider stubbed (factory pattern)
  - TASK-078: Model Selection Rubric (5-axis decision framework)
  - TASK-079: All 14 operations classified into Tiers 1-3
  - FEATURE-053: Tier 1 Flash evals (entity_extraction, sentiment_analysis, theme_extraction)
  - **Results:** All 3 Tier 1 ops flagged >5% quality regression; decisions: STAY Haiku for entity & theme, CONDITIONAL Flash for sentiment

- **Quality regression threshold:** >5% = halt adoption (all 3 ops exceeded this)
- **MSD decision records:** 3 decisions written (MSD-001, MSD-002, MSD-003) with evidence
- **Timeline:** 2026-04-27 to 2026-05-03 (Sprint 016)

### Facts to Confirm from Memory
1. Flash eval results: Why did all 3 ops show >5% regression? Was this expected?
2. Model selection outcome: Did anyone push to adopt Flash despite regression? How was decision reached?
3. GeminiProvider stub: Was real Gemini implementation ever attempted?
4. Routing determinism: Were A/B experiments run to verify MD5 bucketing? Any issues?
5. Tier classification: How much time did TASK-079 take? Was it consensus-driven?
6. Tier 1 definition: Exactly "high volume + deterministic + low failure cost"? Any debate?

---

## CODE AND ARCHITECTURE FINDINGS

### Theme: Deterministic vs. Transient Failures

**Core insight across stories:**
The pipeline struggled to distinguish between:
- **Transient errors:** Rate limits (429), overload (529), timeouts → retryable with backoff
- **Deterministic failures:** Validation errors, hallucinations, JSON parse failures → not retryable; need fallback

**Examples in codebase:**
- **BUG-057:** Retried validation failures 4 times (mistake)
- **BUG-042:** React Query refetch on window focus always (retry without checking cache)
- **BUG-056:** Budget gate: soft/hard limits reflect "fail toward caution" on deterministic degradation

**Pattern:** System treats all failures as transient; smarter systems classify failures and respond differently.

### Theme: Cache and Cost Tradeoffs

**Insights:**
- **Budget cache (BUG-056):** 30s TTL means ~$0.02 overshoot but eliminates DB overhead per LLM call
- **Narrative cache (TASK-075):** One-pass processing makes exact-match caching useless (structural constraint)
- **Feedback loop:** Better models + lower costs → more articles enriched → higher total spend (complexity!)

### Theme: Observability Enables Optimization

**Timeline:**
1. No observability → blind optimization (guess and test)
2. Cost tracking (TASK-024) → visible spend, optimization opportunities clear
3. Cost enforcement (BUG-056) → prevents blowouts
4. Model routing observability (Sprint 016) → data-driven model selection

**Key insight:** Observability came before enforcement; enforcement required a crisis trigger.

### Theme: Graceful Degradation Over Failure

**Patterns:**
- **BUG-057:** Degraded narrative stub instead of None
- **BUG-056:** Soft limit allows critical ops, blocks non-critical
- **FEATURE-061/062:** Article cluster fallback for untrusted summaries
- **TASK-025:** Circuit breaker 3-state machine (CLOSED → OPEN → HALF_OPEN)

**Insight:** System is designed to continue under stress, not halt.

---

## INTERVIEW THEMES MAPPED TO STORIES

| Theme | Story ID | Connection |
|-------|----------|-----------|
| **Product judgment** | COST-01, COST-02, COST-03 | Tier 1 filtering decision, retry storm decision, soft/hard limit design |
| **Prioritization** | COST-01, COST-04 | Tier 1 enrichment before Flash testing, Tier 1 ops evaluated first |
| **Cost optimization** | COST-01, COST-03, COST-04 | Model swap, spend gate, cheaper model testing |
| **AI quality** | COST-01, COST-04 | Haiku briefing quality concern, Flash regression thresholds |
| **Reliability** | COST-02, COST-03 | Retry storm, graceful degradation, circuit breaker |
| **Failure and learning** | COST-02, COST-03 | Incident response (retry storm + spend exhaustion), root cause analysis |
| **Responsible AI** | COST-03, COST-04 | Budget guardrails, quality thresholds, explicit model decisions |
| **Observability** | COST-03, COST-04 | Cost tracking + enforcement, model routing visibility |
| **Saying no** | COST-04 | Rejected Flash models based on regression threshold |
| **Technical-to-business translation** | COST-01 | Tier filtering impacts user-facing narrative visibility; tradeoff articulation |
| **Operating under ambiguity** | COST-02 | No prior retry-storm data; how to decide what's deterministic vs. transient? |

---

## QUESTIONS FOR YOU

### COST-01: Making AI Pipeline Economically Viable

1. **Discovery:** How did you discover that tier 2 articles were being enriched but had low value? Was it a deliberate analysis or noticed during cost audit?
2. **Baseline data:** Is $1.80/day actual measured cost or a back-of-napkin estimate? Do you have the pre-optimization daily_cost graph?
3. **Post-deployment:** After TASK-060 and TASK-063 deployed, what was the actual observed cost reduction? Did it match the $0.36-0.45 target?
4. **Haiku briefing quality:** Any user complaints or quality regressions after switching to Haiku? Did fallback to Sonnet ever occur?
5. **Tier 2-3 blindspot:** After tier 2-3 articles lost enrichment, were there any missed stories or patterns that should have been detected?
6. **Decision timing:** Why optimize enrichment (TASK-060) before testing cheaper models on tier 2-3 (Flash testing)?

### COST-02: Retry Storm and Budget Exhaustion

1. **Timeline:** Exact date/time of restart on 2026-04-02? What was backlog size (100+ articles estimate accurate)?
2. **Detection:** How did you discover the retry storm? Sentry alerts? Cost spike? Manual investigation?
3. **Retry pattern:** Did logs show actual proof of 4 retries per article, or inferred from failure types?
4. **Deployment of fix:** When was BUG-057 deployed to production? How long did backlog take to clear?
5. **Degraded rate:** Post-fix, what % of articles became degraded? Did downstream filtering prevent quality issues?
6. **Circuit breaker vs. budget gate:** Which fixed the crisis first — circuit breaker (TASK-025) or budget gate (BUG-056)? Or both needed?
7. **Cost retrospective:** Actual Anthropic invoice showing $10-15 burn? Or calculated from LLM call counts?

### COST-03: Cost Observability and Guardrails

1. **Gap recognition:** When did you realize cost tracking (observability) wasn't enough without enforcement? During TASK-024 or after BUG-055 incident?
2. **Soft/hard limits:** How were the specific values ($0.25 soft, $0.33 hard) chosen? Formula? Negotiation? Tuning?
3. **Operation classification:** Why is entity extraction critical but theme/sentiment non-critical? Was there user impact analysis or internal judgment?
4. **Cache TTL:** Why 30 seconds specifically? Was this tuned? Any production issues with 30s overshoot window?
5. **Backlog throttle:** Was 5 articles/cycle derived mathematically or trial-and-error? Did you test different values?
6. **Post-deployment:** How often did soft/hard limits trigger in production after deployment? False positives? User complaints about degraded mode?
7. **Communication:** Did users know about soft limit (non-critical ops paused)? Or silent graceful degradation?

### COST-04: Model Routing and Tier Classification

1. **Flash eval results:** All 3 Tier 1 ops showed >5% quality regression. Was this expected? Surprising? Did anyone push to adopt despite regression?
2. **Tier definitions:** Exactly "high volume + deterministic + low failure cost"? Any disagreements or iterations on definitions?
3. **Operation classification:** How much time for TASK-079? Was it solo judgment or team consensus?
4. **GeminiProvider:** Was real Gemini implementation attempted? Why stubbed instead?
5. **MD5 routing determinism:** How was MD5 bucketing verified? Any A/B experiment issues or concerns?
6. **Decision records:** MSD-001/002/003 written for future reference? Are they still accurate?
7. **Future model testing:** After Flash was rejected, was there plan for tier 2 evals? Different models tested?

### Cross-Story Questions

1. **Overall cost target:** Was $0.50/day target explicit from the start, or emerged during work?
2. **Cost vs. quality tension:** Were there moments where you wanted to use cheaper models but held back for quality? How did you decide?
3. **Incident response:** After BUG-056 crisis, did team change incident response procedures? Monitoring improvements?
4. **Responsible AI perspective:** How do you think about model selection — quality-first, cost-first, or balanced?
5. **Learnings:** Biggest surprise from this work? What would you do differently?

---

## DO NOT DO YET

- [ ] Write STAR answers
- [ ] Add persuasive framing ("This work demonstrates strong leadership in...")
- [ ] Merge stories or assume they're connected (they're separate incidents)
- [ ] Fill gaps with plausible assumptions (e.g., "likely the throttle was tuned via...")
- [ ] Treat code commits as proof of personal ownership (code changes ≠ decision maker)
- [ ] Modify repository files
- [ ] Write interview scripts yet
- [ ] Assume metrics without asking (e.g., "$0.45/day" is a stated estimate, not verified)
