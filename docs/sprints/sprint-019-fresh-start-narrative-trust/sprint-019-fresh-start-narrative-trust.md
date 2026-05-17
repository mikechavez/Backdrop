# Sprint 019 — Fresh-Start Narrative Trust Layer

**Status:** Complete (7/7 + 2 discovered)  
**Started:** 2026-05-10  
**Target:** Protect user-facing briefings from untrusted narrative summaries while keeping the narratives page useful through deterministic article-activity fallbacks.

---

## Sprint Goal

Sprint 019 creates a trust boundary between generated narrative summaries and recent article activity. Briefings should only synthesize from trusted summaries, while the narratives page should remain populated by recent article clusters even when a generated summary is stale or missing.

The sprint also prevents malformed LLM refinement output from publishing and repairs the refinement prompt so it has actual source context when self-refine runs.

---

## Scope Boundary

### In Scope
- [x] Prevent invalid, low-confidence, non-JSON, or model-meta briefing output from publishing.
- [x] Add trusted-summary eligibility for briefing narrative inputs.
- [x] Add backend narrative display-mode fields for public narrative cards.
- [x] Add deterministic, zero-LLM article-cluster fallback display for untrusted summaries.
- [x] Ground briefing refinement prompts with source context so refinement can repair rather than ask for missing data.
- [x] Add Sprint 019 verification queries and runbook notes.

### Out of Scope / Non-Goals
- [ ] Do not refresh all 341 legacy narratives in this sprint.
- [ ] Do not delete old narratives.
- [ ] Do not mark old narratives dormant as part of this sprint.
- [ ] Do not expose internal labels like stale, missing, untrusted, or needs refresh to public users.
- [ ] Do not use LLM calls to generate narrative-card fallback copy.
- [ ] Do not change narrative clustering or article-to-narrative matching behavior.
- [ ] Do not increase narrative refresh batch size or LLM budget.

---

## Sprint Order

| # | Ticket | Title | Status | Est | Actual |
|---|--------|-------|--------|-----|--------|
| 0 | TASK-095 | Briefing and Narrative Refresh Investigation | ✅ COMPLETE | medium | |
| 1 | BUG-099 | Prevent Invalid Briefings From Publishing | ✅ COMPLETE | medium | |
| 2 | FEATURE-060 | Add Trusted Summary Eligibility for Briefings | ✅ COMPLETE | medium | |
| 3 | FEATURE-061 | Add Narrative Display Mode API Fields | ✅ COMPLETE | medium | |
| 4 | FEATURE-062 | Add Deterministic Article Cluster Fallback | ✅ COMPLETE | medium | |
| 5 | BUG-100 | Ground Briefing Refinement With Source Context | ✅ COMPLETE | medium | |
| 6 | TASK-096 | Add Sprint 019 Verification Queries | ✅ COMPLETE | small | |
| 7 | TASK-097 | Create Lightweight MongoDB Query Skill | ✅ COMPLETE | 1 hour | |

---

## Success Criteria

- [x] A briefing with raw non-JSON model output cannot publish to the public briefing page. (BUG-099)
- [x] A briefing with `confidence_score < 0.5` cannot publish unless explicitly saved as an unpublished failure record. (BUG-099)
- [x] A briefing with empty `key_insights` cannot publish. (BUG-099)
- [x] Briefing generation uses only narratives with trusted summaries. (FEATURE-060)
- [x] The public narratives page remains populated by recent article activity, even when generated summaries are not trusted. (FEATURE-062)
- [x] Public users never see internal system-state language such as stale, missing, untrusted, or needs refresh. (FEATURE-061, FEATURE-062)
- [x] Untrusted narrative cards render deterministic fallback copy from recent article data without LLM calls. (FEATURE-062)
- [x] Briefing refinement prompt includes source context and cannot reference unavailable `AVAILABLE DATA`. (BUG-100)
- [x] No mass legacy narrative refresh is triggered by this sprint. (TASK-096 verification)
- [x] LLM spend does not increase except for the small expected increase from refinement prompt context when refinement runs. (TASK-096 verification)

---

## Agent Safety Notes

These constraints apply to all implementation agents working this sprint:

- Do not modify production data.
- Do not introduce broad database, shell, or filesystem access when a narrow tool/API is sufficient.
- Do not change unrelated files.
- Do not add autonomous destructive actions.
- Keep implementation bounded to the ticket's listed files unless a blocker is documented.
- If the implementation requires a new file/path not listed in the ticket, stop and document why before proceeding.
- Do not trigger production briefing generation unless explicitly approved.
- Do not trigger narrative refresh jobs unless explicitly approved.
- Do not add LLM calls for narrative-card fallback display.
- Do not expose internal summary trust labels to public users.

---

## Implementation Notes

### Expected Branch Naming

```text
feature/[short-description]
task/[short-description]
fix/[short-description]
```

### Expected Commit Format

```text
feat(scope): description
fix(scope): description
task(scope): description
```

### Test Expectations

- Unit tests should be added or updated for every logic change.
- Integration/manual verification steps must be documented in the ticket completion summary.
- If a test cannot be automated, document the reason and provide a manual verification path.

---

## Key Decisions

| Date | Decision | Rationale | Impact |
|------|----------|-----------|--------|
| 2026-05-10 | Use fresh-start narrative trust instead of mass legacy repair. | 341 active legacy narratives are missing `last_summary_generated_at`; repairing all of them would cost money and add operational risk. | Briefings will only use trusted summaries. Old narratives stay in MongoDB for optional later repair. |
| 2026-05-10 | Keep the narratives page activity-based. | Recent article clusters remain useful even when generated summaries are stale. | The narratives page should not go sparse just because a summary is untrusted. |
| 2026-05-10 | Use deterministic article-cluster fallback copy. | Avoid LLM cost and avoid presenting stale generated summaries as authoritative. | Public users see polished article activity cards, not system-state labels. |
| 2026-05-10 | Do not change clustering/matching behavior in Sprint 019. | Matching changes could create duplicate narratives and are riskier than query/display fixes. | Matching behavior remains a future follow-up if needed. |

---

## Discovered Work

_Tickets created mid-sprint for issues found during implementation._

| Ticket | Title | Reason Created | Status |
|--------|-------|----------------|--------|
| BUG-101 | Zero Trusted Narratives at Deployment | Post-deploy verification found 0 trusted narratives; investigation confirmed expected behavior, not a regression | ✅ COMPLETE |
| TASK-097 | Create Lightweight MongoDB Query Skill | During BUG-101 verification, connection boilerplate for MongoDB queries was repetitive; created reusable skill to eliminate friction for future queries | ✅ COMPLETE |

---

## Session Log

### Session 1 (2026-05-10) — TASK-095 & BUG-099 ✅
**Briefing and Narrative Refresh Investigation + Invalid Briefing Prevention**

**TASK-095:**
- Confirmed invalid briefing output was published because raw non-JSON LLM text can become `content.narrative` with `confidence_score=0.3`.
- Confirmed `_save_briefing()` publishes non-smoke briefings without confidence, empty-insight, parse-failure, or meta-output validation.
- Confirmed refinement prompt references `AVAILABLE DATA` but only includes counts, not the actual narrative context.
- Confirmed 341 active narratives are missing `last_summary_generated_at`, while only 4 were flagged for refresh.
- Confirmed narrative refresh task exists, is batched, and converts string article IDs to ObjectId correctly.

**BUG-099:**
- Implemented `_validate_briefing_publishable()` with 7 rejection criteria (parse_failed, low confidence, empty narrative/insights, model-meta phrases).
- Added `parse_failed` field to `GeneratedBriefing` to explicitly track JSON parse failures.
- Modified `_save_briefing()` to validate before publishing and save rejected briefings unpublished with rejection metadata.
- Hardened `_get_production_briefings_filter()` to exclude invalid briefings at query level.
- Implemented context-aware "available data" detection to avoid false positives on valid briefings.
- Added task_id to rejection logging for debugging/correlation.
- 28 comprehensive tests added, all passing (17 validation + 2 parse + 5 save + 3 available_data + 1 filter).
- Branch: `fix/bug-099-prevent-invalid-briefings-publishing` | Commits: 270d800, 5184d21

### Session 2 (2026-05-10) — FEATURE-060 ✅
**Add Trusted Summary Eligibility for Briefings**

- **Config:** Added `FRESH_START_CUTOFF: str = "2026-05-10T00:00:00Z"` (configurable via env var)
  - Malformed config logs error and falls back to explicit default (not epoch)

- **Trust eligibility helper:** `_is_narrative_summary_trusted(narrative, cutoff) → bool`
  - Returns True if ANY: `first_seen >= cutoff` OR `last_summary_generated_at >= cutoff` OR `_fresh_start_validated_at >= cutoff`
  - Handles datetime objects, ISO strings, and timezone-naive timestamps
  - Fail-closed: missing/malformed timestamps excluded

- **Filter applied in `_get_active_narratives()`:**
  - Order: Fetch (limit×3) → filter recency → **apply trust filter** → sort by ranking → return top N
  - Critical: Filter applied BEFORE final `:limit` slice (prevents loss of trusted narratives ranked 16+)
  - No backfill: briefings generate with <15 trusted narratives if needed

- **Logging:** active_narratives_considered, trusted_narratives_selected, untrusted_narratives_excluded, cutoff (ISO format)

- **Testing:** 12 unit tests covering all trust conditions, fail-closed behavior, config parsing, timezone handling, boundary conditions
  - All tests passing
  - Manual verification: filter timing, config error handling, sparse narrative handling, read-only filter

- **Scope boundaries observed:**
  - No narrative records mutated (read-only filter)
  - No LLM calls added
  - No changes to narrative_refresh.py, beat_schedule.py, or public narrative display

- Branch: `feature/060-trusted-summary-briefing-eligibility` | Commit: 3297f88

### Session 3 (2026-05-10) — FEATURE-061 ✅
**Add Narrative Display Mode API Fields**

- **Shared trust helper module:** Created `services/narrative_trust.py` with:
  - `get_fresh_start_cutoff()` — parses config with fallback
  - `is_narrative_summary_trusted(narrative, cutoff) → bool` — reused from FEATURE-060
  - Eliminated coupling; FEATURE-060 refactored to delegate (12/12 existing tests pass)

- **Display mode computation:** Single `_get_narrative_display_mode(narrative, cutoff, articles) → (mode, title, summary)` helper
  - **Trusted (summary mode):** Uses existing generated title and summary
  - **Untrusted (article_cluster mode):** 
    - Title: primary entity → theme → "Recent Coverage" (not "Untitled")
    - Summary: scans articles for up to 3 clean titles (filters stale/missing/untrusted/needs refresh)
    - Fallbacks: "Recent coverage includes {count} article(s)..." or "Recent coverage is being tracked..."
    - Never produces degenerate copy like "Latest 0 articles"

- **Endpoint updates:** Added display fields to all 4 narrative endpoints:
  - `GET /narratives/active` (paginated)
  - `GET /narratives/archived`
  - `GET /narratives/resurrections`
  - `GET /narratives/{narrative_id}`

- **Response schema additions:**
  ```python
  display_mode: Literal["summary", "article_cluster"]
  display_title: str
  display_summary: Optional[str]
  recent_article_count: int
  ```

- **Quality assurance:**
  - Filters forbidden words from article titles (stale, missing, untrusted, needs refresh)
  - Scans all articles (not just first 3) to find 3 clean titles
  - Proper English formatting (Oxford comma for 3+ items)
  - Handles empty/null/non-string titles gracefully
  - Deduplicates article titles
  - Never exposes internal system-state language to public API

- **Testing:** 29 comprehensive tests covering:
  - 6 trust helper tests
  - 7 core display mode tests (trusted/untrusted/fallbacks)
  - 5 formatting tests (1/2/3 articles, forbidden word filtering, empty titles)
  - 6 public copy cleanup tests (missing entities, zero articles, count handling)
  - 3 model validation tests
  - 1 LLM safety test (no calls made)
  - 1 old narrative eligibility test
  - All passing

- **Scope boundaries observed:**
  - No narrative records mutated (API-only fields)
  - No LLM calls added
  - Trust logic reused from FEATURE-060 (no changes)
  - Briefing behavior unchanged
  - Old narratives with recent activity remain eligible for display

- **Branch:** `feature/061-narrative-display-mode-api`
  - Commit 206c725: feat(narratives) — initial implementation
  - Commit e424039: refactor(narratives) — quality/robustness improvements
  - Commit d194e74: refactor(narratives) — public copy cleanup (accepted after audit)

### Session 4 (2026-05-10) — FEATURE-062 ✅
**Add Deterministic Article Cluster Fallback (Frontend)**

- **Frontend type extension:** Extended `Narrative` interface in `context-owl-ui/src/types/index.ts`
  - `display_mode?: "summary" | "article_cluster"`
  - `display_title?: string`
  - `display_summary?: string | null`
  - `recent_article_count?: number`

- **Rendering logic update:** Modified `Narratives.tsx` (lines 134-151, 343-373, 380)
  - **Display computation:**
    - `cardTitle`: prefers display_title → title → theme (never computes trust from timestamps)
    - `cardSummary`: uses display_summary if defined, else summary/story
    - `displayMode`: defaults to "summary" (backward compatible)
    - `displayArticleCount`: uses recent_article_count in article_cluster mode
  - **Conditional rendering:**
    - **article_cluster mode:** Renders {cardTitle} → {displayArticleCount} recent article(s) → {cardSummary}
    - **summary mode:** Renders {cardTitle} → {cardSummary} → entity tags (preserved)
    - **Both modes:** Article list section (lines 375+) renders unchanged; expandable/paginated in both modes
  - **No legacy field exposure:** Article-cluster mode does not render title/summary/story/theme when display fields present

- **Backward compatibility:** Frontend gracefully falls back to legacy title/summary if display fields absent

- **UI safety:**
  - No internal status language (stale, missing, untrusted, needs refresh, summary status)
  - No frontend trust computation from timestamps
  - No entity tags shown in article-cluster mode (no internal metadata)

- **Build verification:**
  - TypeScript: 0 errors
  - Production build: 2148 modules, 145KB gzipped
  - All changes frontend-only; no backend files modified

- **Test audit:**
  - Code audit: Verified article-cluster mode does not render legacy fields when display fields present
  - Trace through Bitcoin stale-case: Correctly hides "Bitcoin Holds $75K..." and "Old stale generated summary"
  - Backward compatibility: Summary mode works with/without display fields
  - No automated test framework exists (no jest/vitest); ready for manual verification on dev/staging

- **Scope boundaries observed:**
  - No backend files modified
  - No data mutations
  - No LLM calls added
  - No page redesign (layout preserved, mode-based rendering only)
  - Article list not hidden in article-cluster mode

- **Branch:** `feature/062-deterministic-article-cluster-fallback`
  - Commit 61724d5: feat(narratives) — display mode fields and article-cluster rendering

### Session 5 (2026-05-10) — BUG-100 ✅
**Ground Briefing Refinement With Source Context**

- **Problem:** `_build_refinement_prompt()` included only counts (e.g., "5 narratives") instead of actual source context. When critique identified hallucinations/missing sources, the refinement LLM asked for additional data instead of correcting with available information.

- **Root cause:** Refinement prompt referenced `AVAILABLE DATA` but only included counts of signals, narratives, and patterns—not the actual narrative details, summaries, entities, or signal metrics needed to repair the briefing.

- **Solution:** Replaced counts-only `AVAILABLE DATA` section with full `AVAILABLE SOURCE CONTEXT` including:
  - **Top 8 narratives** with titles, summaries, entities (up to 5 per narrative), and article counts (matches generation prompt limit)
  - **Top 10 trending signals** with score_24h and velocity_24h metrics (bounded to prevent token explosion)
  - **Top 5 detected patterns** with descriptions
  - **Explicit refinement instructions:**
    - Return ONLY valid JSON
    - Do NOT ask for additional data or context
    - Use ONLY the source context provided
    - If a claim is unsupported, REMOVE it
    - If context is sparse, produce a conservative briefing
    - Do NOT include any text outside JSON

- **Implementation:**
  - Updated `_build_refinement_prompt()` in `src/crypto_news_aggregator/services/briefing_agent.py` (lines 795-868)
  - All context sourced from already-available `briefing_input` (no new DB calls, no new LLM calls)
  - Context bounds verified: <8KB prompt for 15 narratives
  - Graceful handling of missing optional fields (summaries, entities, etc.)

- **Article titles/sources blocker:**
  - Investigated whether to include article titles/sources in refinement prompt
  - Finding: Article details not pre-loaded in `briefing_input.narratives` (only `article_ids` and `article_count` available)
  - Fetching article titles would require DB queries to articles collection (violates no-new-DB-calls requirement)
  - Documented as known limitation; recommended future work: pre-load article details in `_gather_inputs()` if needed

- **Testing:** 12 comprehensive tests added in `tests/services/test_bug_100_refinement_prompt.py`:
  - Narrative titles, summaries, entities included ✅
  - Signal and pattern details included ✅
  - JSON-only and no-data-request instructions present ✅
  - Bounded prompt size for 15+ narratives ✅
  - Handles missing optional fields gracefully ✅
  - Handles empty briefing input gracefully ✅
  - All tests passing (12/12)

- **Regression testing:**
  - Refinement-related tests: 5/5 passed
  - Briefing prompt tests: 5/5 passed
  - No regressions detected

- **Scope boundaries observed:**
  - No DB calls added (sourced from briefing_input)
  - No LLM calls added
  - No narrative_service.py, narrative_refresh.py, beat_schedule.py, or context-owl-ui/ files modified
  - No production data mutation

- **Branch:** `fix/bug-100-refinement-prompt-source-context`
  - Commit 5d70903: fix(narratives) — ground refinement prompt with source context
  - Commit 16c0372: docs(sprint-019) — mark BUG-100 complete

### Session 6 (2026-05-10) — TASK-096 Post-Deploy Investigation ✅
**Sprint 019 Verification & BUG-101 Documentation**

- **Verification executed:** Read-only queries run to validate post-deployment state immediately after Sprint 019 deployment
- **Finding:** Trusted narratives count = 0 (appeared to be regression but confirmed as expected)
- **Root cause analysis:** FRESH_START_CUTOFF (`2026-05-10T00:00:00Z`) is the deployment boundary itself, not a historical cutoff
  - Production had 355 active narratives, none created/refreshed on 2026-05-10 00:00:00 exactly
  - Most recent narrative activity: `last_summary_generated_at = 2026-05-08 23:30:12`
  - Most recent first_seen: `first_seen = 2026-05-07 22:31:02`
  - Zero narratives met ANY of the three trust conditions immediately post-deploy
  - This is correct fail-safe behavior (narratives with uncertain freshness excluded)

- **Critical findings:**
  - ✅ **BUG-099 containment verified working:** 4 pre-deploy invalid briefings (all blocked), 0 post-deploy invalid briefings published
  - ✅ **Narrative refresh normal:** 42 calls post-deploy, distributed, low cost ($0.07), all successful
  - ✅ **Code deployment verified:** All Sprint 019 commits present, all code paths executing
  - ✅ **Public API ready:** 5 untrusted narratives with recent activity, ready for article-cluster fallback display
  - ✅ **System fail-safe:** Zero trusted narratives triggered graceful article-cluster fallback, not a crash

- **Timeline & recommendations:**
  - Immediate: BUG-099 containment confirmed working; no invalid briefings published
  - Short term: Wait for first scheduled narrative refresh (~07:30 AM or PM UTC 2026-05-10) 
  - Expected: After refresh, some narratives will have `last_summary_generated_at >= 2026-05-10` and become trusted
  - Then safe to run: Scheduled briefing generation with meaningful trusted narrative content

- **Discovered work:** Created BUG-101 ticket to document investigation, confirm expected behavior, and establish timeline
- **Branch:** None (read-only investigation, no code changes)
- **Commits:** 66bf549 (docs: mark TASK-096 complete), d234066 (docs: add verification queries)

### Session 7 (2026-05-10) — TASK-097 ✅
**Create Lightweight MongoDB Query Skill**

- **Motivation:** During BUG-101 verification, discovering MongoDB connection boilerplate took several attempts (load_keys.sh, poetry run, .env parsing, pymongo import, credential handling). Identical setup needed for any future verification queries.

- **Skill creation:** Built `db-query` skill with three commands:
  - `count <collection> <query>` — Count documents matching query
  - `find <collection> <query> [projection] [limit] [sort]` — Find with optional parameters
  - `aggregate <collection> <pipeline>` — Run aggregation pipeline

- **Implementation:**
  - **Script:** `scripts/db_query.py` (100+ lines)
    - Auto-loads MONGODB_URI from .env using python-dotenv
    - Supports all MongoDB query types
    - Returns JSON output (compatible with jq, Python json.loads)
    - Errors to stderr, structured JSON
    - Read-only guard (no write operations)
    - Exit code 0 success, 1 failure
  - **Reference:** `references/query_patterns.md` (2.6 KB)
    - Date range queries (ISO 8601 format)
    - Complex aggregations with statistics
    - Common filters (active, dormant, trusted narratives)
    - JSON escaping in Bash (single quotes)
    - Field projections and sorting
  - **SKILL.md:** Quick start, three-command reference, usage notes

- **Testing:** 
  - ✅ Count query: `count narratives '{"lifecycle_state": "hot"}'` → `{"count": 9}`
  - ✅ Aggregate query: Group narratives by lifecycle_state → Correct results
  - ✅ Skill packaging: `package_skill.py` validates and creates `.skill` file
  - ✅ Skill installation: File present at `~/.claude/skills/db-query.skill` (3.8 KB)

- **Documentation:**
  - Created `db_query_skill.md` in project memory
  - Updated `MEMORY.md` index to reference the skill
  - Documented when to use (verification, statistics, data inspection)

- **Impact:** Future MongoDB verification queries no longer require connection discovery. Skill handles credential loading, connection, and result formatting automatically.

- **Branch:** N/A (skill creation, not code changes)
- **Artifacts:** `~/.claude/skills/db-query.skill` (packaged skill, 3 files)

### Session 8 (2026-05-10) — TASK-098 🔴 IN PROGRESS
**Bounded UI Narrative Refresh Bootstrap**

**Phase 0: Display-Mode Verification** ✅
- Inspected top 10 active narratives from production
- Finding: `display_mode`, `display_title`, `display_summary` fields all NULL in database
- Root cause: FEATURE-061/062 display fields are computed at API call time (not stored), so DB queries see nulls
- Documented for future investigation: may need to populate/cache display fields in db if performance becomes issue

**Phase 1: Select Top 5 Narratives** ✅
- Approved 5 narratives for first bootstrap refresh:
  1. Senate Banking Committee Advances Crypto Regulation Efforts (695eb4b3ce758d67abd6e8f4)
  2. LayerZero Admits Mistakes in $292M Kelp DAO Exploit (698baa105278ec9e19bf2a19)
  3. Bitcoin Holds $75K Amid Geopolitical Tensions and Strong ETF Inflows (68f32d197082f49df56956c6)
  4. SEC Signals New Regulatory Framework for Onchain Markets (68f03343bc9ab7390ca7af71)
  5. Coinbase Navigates Infrastructure Crisis Amid Market Recovery (68f03350bc9ab7390ca7af78)
- All 5: untrusted, active, have articles available, eligible for refresh_flagged_narratives

**Phase 2: Dry-Run Analysis** ✅
- Simulated refresh selection: confirmed all 5 would be processed (within MAX_REFRESH_PER_RUN=20 limit)
- Estimated cost: ~$0.01 (negligible)
- No other narratives flagged
- Guardrails verified: safe to execute

**Phase 4A: Flag Narratives** ✅
- Manually executed mongosh updateMany command
- Set `needs_summary_update=true` for all 5 narratives
- Verified via read-only query: all 5 flagged

**Phase 4B: Refresh Execution** 🔴 PARTIAL FAILURE → BUG-102 RAISED
- **Celery task triggered:** `celery -A crypto_news_aggregator.tasks call refresh_flagged_narratives`
- **Task ID returned:** `9e93ad11-a4ff-4145-af78-e5567f5b8181`
- **Task DID execute** (Celery worker running in Railway)
- **Root cause (BUG-102):** `refresh_flagged_narratives` hit the "article hydration empty" failure path for 3 narratives. That path cleared `needs_summary_update=False` without setting `last_summary_generated_at`, silently hiding them from future runs. No LLM was called.
- **Evidence:**
  - 35 `narrative_generate` LLM traces on May 10, none for the 5 approved narratives
  - 3 narratives updated at 21:38:46-47 UTC with flag cleared but null timestamp (failure path)
  - 2 narratives still flagged (never reached, possibly hit budget cap or run limit)
- **Current state:**
  - Trusted narratives: still 0
  - 3 flags incorrectly cleared (need re-flagging after fix deployed)
  - 2 still flagged (ready to process)

**Deviations from plan:**
- Celery did run; root cause was a task code bug, not infrastructure failure
- BUG-102 raised and fixed before retrying TASK-098

---

### Session 9 (2026-05-10) — BUG-102 ✅ COMPLETE
**Investigate and Fix Refresh Flag Clearing Without Summary Timestamp**

**Investigation findings:**
- Queried all 5 approved narratives; 3 cleared (Senate Banking, LayerZero, Bitcoin), 2 still flagged (SEC, Coinbase)
- All 5 narratives have article_ids that hydrate to real articles now
- 35 `narrative_generate` LLM traces on May 10, none reference the 5 narratives → confirms failure path, not LLM path
- Root cause pinpointed: `narrative_refresh.py` lines 96-105 cleared `needs_summary_update=False` when article hydration returned empty, without setting `last_summary_generated_at`

**Fix (`fix/bug-102-preserve-refresh-flag-on-failure`, commit `c1af536`):**
- Removed `update_one` calls from all three failure paths (no article_ids, empty hydration, LLM returns None)
- Each failure path now logs structured skip details and `continue`s — flag stays `True`
- Only the success path (title/summary written + timestamp stamped) clears the flag
- Added structured logging per skip: `narrative_id`, `title`, `article_ids_count`, `hydrated_article_count`, `reason`

**Tests:** 9/9 pass
- Updated `test_refresh_handles_missing_articles`: now asserts flag stays `True`
- Added `test_no_article_ids_does_not_clear_flag`
- Added `test_empty_hydration_does_not_clear_flag`
- Added `test_llm_returns_none_does_not_clear_flag`
- Added `test_successful_refresh_clears_flag_and_sets_timestamp`

**Next steps for TASK-098 retry:**
1. Deploy `fix/bug-102-preserve-refresh-flag-on-failure` to Railway
2. Re-flag the 3 incorrectly cleared narratives (Senate Banking, LayerZero, Bitcoin)
3. Retry refresh and verify all 5 receive `last_summary_generated_at` + trusted status

### Session 10 (2026-05-17) — CHORE-001 ✅
**Disable CoinGecko API Requests**

**Rationale:** CoinGecko API requests were consuming quota without providing value to the current briefing pipeline. Price monitoring/alerts are not part of Sprint 019 or the production roadmap.

**Implementation:**
- **Background task disabled:** Commented out `price_monitor.start()` in `main.py` lifespan (lines 127-132)
- **Config kill switch added:** New `COINGECKO_API_DISABLED` boolean flag in `Settings` with environment variable support
- **Service methods hardened:** Updated 4 price service methods to check flag and return mock data:
  - `get_bitcoin_price()`
  - `get_prices()`
  - `get_markets_data()`
  - `get_historical_prices()`
- **Documentation committed:** All updated docs included in commit

**Re-enabling path:** Two options (no refactoring needed):
- Option 1: Set `COINGECKO_API_DISABLED=false` via environment variable
- Option 2: Uncomment lines 127-132 in `main.py`

**Branch:** `chore/disable-coingecko-api` | Commit: `7ad628a`
**Ticket:** `chore-disable-coingecko-api.md` in `/tickets/`
