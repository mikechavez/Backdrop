# TASK-045: Remove Verbose Narrative Logging

**Status:** ✅ COMPLETE (with critical bug fix)  
**Priority:** HIGH (unblocks TASK-046)  
**Commits:** dde11bf (verbose logging), 869baa8 (critical velocity bug fix)  
**Branches:** fix/task-045-remove-verbose-narrative-logging, fix/narrative-clustering-merge-log  
**Time:** 5 minutes + 2 minutes for bug fix = 7 minutes total

---

## Problem

Narrative clustering debug logs hitting Railway's 500 logs/sec limit, dropping messages that mask briefing failures.

Each narrative merge generates 20+ debug log lines. With 19 narratives being merged, that's 380+ lines per cycle—exceeding the rate limit.

---

## Solution

Remove all `[VELOCITY DEBUG]` and `[MERGE NARRATIVE DEBUG]` blocks from `narrative_service.py`. Replace with single-line summaries.

---

## File Changes

### File: `src/crypto_news_aggregator/services/narrative_service.py`

#### Change 1: `calculate_recent_velocity()` function (lines 90-116)

**Find this block:**
```python
    # Debug logging
    logger.info(f"[VELOCITY DEBUG] ========== VELOCITY CALCULATION START ==========")
    logger.info(f"[VELOCITY DEBUG] Total articles: {len(article_dates)}")
    logger.info(f"[VELOCITY DEBUG] Current time (now): {now} (UTC)")
    logger.info(f"[VELOCITY DEBUG] Cutoff date ({lookback_days} days ago): {cutoff_date} (UTC)")
    logger.info(f"[VELOCITY DEBUG] Time delta calculation: ({now} - {cutoff_date}).total_seconds() / 86400")
    logger.info(f"[VELOCITY DEBUG] Time delta result: {(now - cutoff_date).total_seconds() / 86400:.2f} days")
    logger.info(f"[VELOCITY DEBUG] Time delta in seconds: {(now - cutoff_date).total_seconds():.0f} seconds")
    
    # Log all article dates for debugging
    if article_dates:
        logger.info(f"[VELOCITY DEBUG] All article dates (sorted):")
        for i, date in enumerate(sorted(article_dates, reverse=True)):
            in_window = "✓ IN WINDOW" if date >= cutoff_date else "✗ EXCLUDED"
            logger.info(f"[VELOCITY DEBUG]   [{i+1}] {date} {in_window}")
    
    logger.info(f"[VELOCITY DEBUG] Articles within window: {len(recent_articles)}")
    if recent_articles:
        oldest = min(recent_articles)
        newest = max(recent_articles)
        logger.info(f"[VELOCITY DEBUG] Oldest article in window: {oldest}")
        logger.info(f"[VELOCITY DEBUG] Newest article in window: {newest}")
        logger.info(f"[VELOCITY DEBUG] Article span: {(newest - oldest).total_seconds() / 86400:.2f} days")
    
    logger.info(f"[VELOCITY DEBUG] Final calculation: {len(recent_articles)} articles / {lookback_days} days")
    logger.info(f"[VELOCITY DEBUG] Result: {len(recent_articles) / lookback_days:.2f} articles/day")
    logger.info(f"[VELOCITY DEBUG] ========== VELOCITY CALCULATION END ==========")
```

**Replace with:**
```python
    # Single-line velocity summary (replaced 26+ debug lines)
    velocity = len(recent_articles) / lookback_days if recent_articles else 0.0
    logger.info(f"Narrative velocity: {velocity:.2f} articles/day ({len(article_dates)} total, {len(recent_articles)} in {lookback_days}-day window)")
```

---

#### Change 2: Merge upsert debug logging (lines 1069-1085) 

**CRITICAL BUG FIX:** The original Change 2 replacement code had an undefined variable bug. The `articles_by_id` variable doesn't exist in that code path, causing a crash during narrative clustering.

**Find this block:**
```python
                    logger.info(f"[MERGE NARRATIVE DEBUG] ========== MERGE UPSERT START ==========")
                    logger.info(f"[MERGE NARRATIVE DEBUG] Theme: {theme}")
                    logger.info(f"[MERGE NARRATIVE DEBUG] Title: {title}")
                    logger.info(f"[MERGE NARRATIVE DEBUG] Combined article IDs: {combined_article_ids}")
                    logger.info(f"[MERGE NARRATIVE DEBUG] Article dates collected: {len(article_dates)}")
                    if article_dates:
                        logger.info(f"[MERGE NARRATIVE DEBUG] Article dates (sorted):")
                        for i, date in enumerate(sorted(article_dates)):
                            logger.info(f"[MERGE NARRATIVE DEBUG]   [{i+1}] {date}")
                        logger.info(f"[MERGE NARRATIVE DEBUG] Earliest article: {min(article_dates)}")
                        logger.info(f"[MERGE NARRATIVE DEBUG] Latest article: {max(article_dates)}")
                    logger.info(f"[MERGE NARRATIVE DEBUG] Existing narrative first_seen: {matching_narrative.get('first_seen')}")
                    logger.info(f"[MERGE NARRATIVE DEBUG] Calculated first_seen (from existing or now): {first_seen}")
                    logger.info(f"[MERGE NARRATIVE DEBUG] Calculated last_updated (now): {last_updated}")
                    logger.info(f"[MERGE NARRATIVE DEBUG] Is first_seen > last_updated? {first_seen > last_updated}")
                    logger.info(f"[MERGE NARRATIVE DEBUG] Timestamp sources: first_seen from existing narrative, last_updated from now()")
                    logger.info(f"[MERGE NARRATIVE DEBUG] ========== MERGE UPSERT END ==========")
```

**Replace with:**
```python
                    logger.info(f"Merged {len(combined_article_ids)} articles into narrative '{title}'")
```

**Why:** Removed the undefined `articles_by_id` variable reference that was causing crashes during narrative clustering merge operations.

---

## Verification

After making changes, verify no `[VELOCITY DEBUG]` or `[MERGE NARRATIVE DEBUG]` strings remain:

```bash
grep -n "VELOCITY DEBUG\|MERGE NARRATIVE DEBUG" src/crypto_news_aggregator/services/narrative_service.py
```

**Expected output:** Empty (no matches)

---

## Deployment

```bash
git add src/crypto_news_aggregator/services/narrative_service.py
git commit -m "fix(narrative): Reduce verbose logging to avoid Railway rate limits (TASK-045)"
git push origin main
```

Wait for Railway deployment (~2 minutes).

---

## Success Criteria

✅ No `[VELOCITY DEBUG]` or `[MERGE NARRATIVE DEBUG]` in code  
✅ Railway logs no longer show rate limit warnings  
✅ Narrative processing still completes successfully  
✅ Single-line summaries appear in logs for each narrative merge